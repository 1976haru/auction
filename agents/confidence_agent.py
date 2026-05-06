"""
agents/confidence_agent.py
시세/권리/문서/주소 신뢰도 종합 산정.
"""
from __future__ import annotations

from typing import Any

from core.database import get_connection, init_db
from core.logger import log
from core.utils import safe_json
from modules.documents.mock_documents import get_item_documents
from modules.valuation.price_matcher import get_price_analysis
from modules.risk.keyword_analyzer import get_risk_flags


CONF_LEVEL = {"very_low": 0.2, "low": 0.4, "medium": 0.7, "high": 0.95}


def compute_confidence(item_id: int) -> dict:
    init_db()
    conn = get_connection()
    item = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if not item:
        return {"error": f"item_id={item_id} 없음"}
    item = dict(item)

    reasons: list[str] = []

    # 가격 신뢰도
    pa = get_price_analysis(item_id) or {}
    price_conf = CONF_LEVEL.get(pa.get("confidence", "very_low"), 0.2)
    if pa.get("data_shortage"):
        reasons.append("실거래가 데이터 부족")
    if pa.get("transaction_count", 0) == 0:
        reasons.append("거래 0건 - 시세 추정 보조 사용")

    # 문서 신뢰도
    docs = get_item_documents(item_id)
    if not docs:
        document_conf = 0.2
        reasons.append("문서 없음")
    else:
        disclosed = [d for d in docs if d.get("is_disclosed")]
        if not disclosed:
            document_conf = 0.3
            reasons.append("문서 미공개")
        else:
            types = {d["doc_type"] for d in disclosed}
            score = 0.4
            if "매각물건명세서" in types:
                score += 0.25
            else:
                reasons.append("매각물건명세서 없음")
            if "감정평가서" in types:
                score += 0.2
            else:
                reasons.append("감정평가서 없음")
            if "현황조사서" in types:
                score += 0.15
            document_conf = min(score, 1.0)

    # 권리 위험 신뢰도
    flags = get_risk_flags(item_id)
    if flags:
        legal_conf = 0.85
        if not any(f.get("source_text") for f in flags):
            legal_conf = 0.55
            reasons.append("위험 키워드 원문 부족")
    else:
        legal_conf = 0.4
        reasons.append("위험 키워드 미발견 - 추가 분석 필요")

    # 주소 매칭 신뢰도
    addr = item.get("address_full") or ""
    if addr and addr.count(" ") >= 2:
        address_conf = 0.85
    elif addr:
        address_conf = 0.5
        reasons.append("주소 매칭 불확실")
    else:
        address_conf = 0.2
        reasons.append("주소 정보 없음")

    overall = round(
        (price_conf * 0.3 + legal_conf * 0.3 + document_conf * 0.25 + address_conf * 0.15), 3
    )

    result = {
        "item_id": item_id,
        "price_confidence": round(price_conf, 3),
        "legal_risk_confidence": round(legal_conf, 3),
        "document_confidence": round(document_conf, 3),
        "address_match_confidence": round(address_conf, 3),
        "overall_confidence": overall,
        "reasons": reasons,
    }

    conn = get_connection()
    conn.execute("""
        INSERT INTO confidence_scores
            (item_id, price_confidence, legal_risk_confidence,
             document_confidence, address_match_confidence,
             overall_confidence, reasons_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
            price_confidence=excluded.price_confidence,
            legal_risk_confidence=excluded.legal_risk_confidence,
            document_confidence=excluded.document_confidence,
            address_match_confidence=excluded.address_match_confidence,
            overall_confidence=excluded.overall_confidence,
            reasons_json=excluded.reasons_json,
            created_at=datetime('now','localtime')
    """, (
        item_id,
        result["price_confidence"], result["legal_risk_confidence"],
        result["document_confidence"], result["address_match_confidence"],
        result["overall_confidence"], safe_json(reasons),
    ))
    conn.commit()
    conn.close()
    return result


def compute_all() -> int:
    init_db()
    conn = get_connection()
    ids = [r["id"] for r in conn.execute("SELECT id FROM items").fetchall()]
    conn.close()
    n = 0
    for iid in ids:
        compute_confidence(iid)
        n += 1
    log.info(f"[confidence] {n}건 처리")
    return n


def get_confidence(item_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM confidence_scores WHERE item_id=?", (item_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None
