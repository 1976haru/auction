"""
agents/legal_risk_agent.py
권리위험 분석 에이전트.
1차: 키워드 분석 (modules.risk.keyword_analyzer)
2차: AI 분석 (mock 또는 실제)
"""
from __future__ import annotations

from typing import Any

from core.ai_client import analyze_risk
from core.config import USE_AI, USE_MOCK_APIS
from core.database import get_connection
from core.logger import log
from modules.documents.mock_documents import get_item_documents
from modules.risk.keyword_analyzer import (
    analyze_keywords,
    get_risk_flags,
    get_risk_level,
    get_risk_score,
    save_risk_flags,
)

FIELD_CHECK_TEMPLATE = [
    "점유자 현황 (거주 여부, 세입자 인원)",
    "건물 외관 하자 (균열, 누수, 도배·장판 상태)",
    "관리비 체납 여부 (관리사무소 확인)",
    "주차 환경 및 엘리베이터 상태",
    "주변 인프라 (학교, 마트, 교통)",
    "일조권·소음 환경",
    "등기부등본 최신본 확인 (현장 방문 직전)",
    "인근 경쟁 매물 시세 확인",
]


def _gather_text(item_id: int) -> str:
    docs = get_item_documents(item_id)
    return "\n".join(d.get("extracted_text") or "" for d in docs).strip()


def analyze_item_risk(item_id: int, document_text: str | None = None) -> dict:
    conn = get_connection()
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if not row:
        return {"error": f"item_id={item_id} 없음"}

    item = dict(row)
    if document_text is None:
        document_text = _gather_text(item_id)

    # 기존 키워드 플래그가 있으면 중복 저장 막기
    existing = get_risk_flags(item_id)
    if not existing:
        flags = analyze_keywords(document_text)
        save_risk_flags(item_id, flags)
    else:
        flags = existing

    # AI 보강 (USE_AI=true 일 때만; mock_mode면 mock_analyze_risk 사용)
    ai_result: dict | None = None
    if document_text and (USE_AI or USE_MOCK_APIS):
        try:
            ai_result = analyze_risk(document_text, item)
        except Exception as e:
            log.warning(f"[risk] AI 분석 실패: {e}")

    return {
        "item_id": item_id,
        "address": item.get("address_full", "미상"),
        "keyword_flags": flags,
        "risk_score": get_risk_score(item_id),
        "risk_level": get_risk_level(item_id),
        "ai_analysis": ai_result,
        "field_checklist": _field_checklist(item, flags),
        "disclaimer": "이 분석은 참고용이며 위험요소 체크리스트일 뿐 법률 판단이 아닙니다.",
    }


def _field_checklist(item: dict, flags: list[dict]) -> list[str]:
    base = list(FIELD_CHECK_TEMPLATE)
    types = {f.get("type") for f in flags}
    if "유치권" in types:
        base.insert(0, "[유치권 주의] 유치권 주장 내용 및 공사 관계 현장 확인")
    if "대항력" in types or "선순위임차인" in types:
        base.insert(0, "[임차인 주의] 전입세대열람 및 확정일자 확인")
    if "지분매각" in types:
        base.append("[지분] 다른 공유자와의 협의 가능성 확인")
    item_type = item.get("item_type", "")
    if item_type in ("빌라", "단독주택"):
        base.append("건물 신축연도/구조/불법증축 여부 확인")
    return base


def analyze_all() -> int:
    conn = get_connection()
    ids = [r["id"] for r in conn.execute("SELECT id FROM items").fetchall()]
    conn.close()
    n = 0
    for iid in ids:
        analyze_item_risk(iid)
        n += 1
    return n


def get_risk_summary(item_id: int) -> str:
    flags = get_risk_flags(item_id)
    if not flags:
        return "위험 키워드 미발견 (문서 분석 필요)"
    score = max(f["severity"] for f in flags)
    level = flags[0]["risk_level"]
    return f"위험도 {level} ({score}/10) - 주요: " + ", ".join(f["flag_type"] for f in flags[:3])
