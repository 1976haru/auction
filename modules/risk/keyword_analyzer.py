"""
modules/risk/keyword_analyzer.py
위험 키워드 사전 + 텍스트 분석.
risk_level: high / medium / low
"""
from __future__ import annotations

from typing import Iterable

from core.database import get_connection, init_db
from core.logger import log

RISK_KEYWORDS: dict[str, dict] = {
    # high
    "유치권":           {"keywords": ["유치권", "유치권 신고", "유치권자"], "level": "high", "severity": 9,
                          "description": "유치권 신고 가능성 - 권리 성립 여부 확인 필요"},
    "법정지상권":       {"keywords": ["법정지상권", "지상권"], "level": "high", "severity": 8,
                          "description": "법정지상권 성립 가능성 - 토지/건물 소유관계 확인 필요"},
    "선순위임차인":     {"keywords": ["선순위임차인", "최우선변제"], "level": "high", "severity": 8,
                          "description": "선순위 임차인 존재 시 보증금 인수 가능성"},
    "대항력":           {"keywords": ["대항력", "대항력있는", "대항력 있는"], "level": "high", "severity": 8,
                          "description": "대항력 있는 임차인 가능성 - 보증금 인수 검토 필요"},
    "인수되는 권리":    {"keywords": ["인수되는 권리", "인수권리"], "level": "high", "severity": 8,
                          "description": "낙찰자가 인수해야 할 권리 가능성"},
    "지분매각":         {"keywords": ["지분매각", "공유지분", "지분경매", "공유"], "level": "high", "severity": 7,
                          "description": "지분 매각 - 단독 처분 제약 가능성"},
    "농지취득자격증명": {"keywords": ["농지취득자격증명", "농취증"], "level": "high", "severity": 7,
                          "description": "농지취득자격증명 필요 - 자격 충족 여부 확인 필요"},
    "분묘기지권":       {"keywords": ["분묘기지권", "분묘"], "level": "high", "severity": 7,
                          "description": "분묘기지권 가능성 - 처분/이용 제약 가능성"},
    # medium
    "임차인":           {"keywords": ["임차인", "세입자"], "level": "medium", "severity": 5,
                          "description": "임차인 존재 - 전입/확정/배당요구 확인 필요"},
    "점유자 미상":      {"keywords": ["점유자 미상", "점유자미상"], "level": "medium", "severity": 5,
                          "description": "점유자 미상 - 명도 협의 어려울 수 있음"},
    "전입세대":         {"keywords": ["전입세대"], "level": "medium", "severity": 5,
                          "description": "전입세대 존재 - 임차 관계 확인 필요"},
    "관리비 체납":      {"keywords": ["관리비 체납", "관리비체납"], "level": "medium", "severity": 4,
                          "description": "관리비 체납 - 인수 부담 발생 가능"},
    "위반건축물":       {"keywords": ["위반건축물"], "level": "medium", "severity": 5,
                          "description": "위반건축물 등재 - 시정명령 이행 여부 확인 필요"},
    "대금미납 재매각":  {"keywords": ["대금미납", "재매각"], "level": "medium", "severity": 5,
                          "description": "대금미납 재매각 케이스 - 사유 확인 필요"},
    "명도":             {"keywords": ["명도"], "level": "medium", "severity": 4,
                          "description": "명도 필요 가능성 - 명도 비용/시간 발생 가능"},
    # low
    "소유자 점유":      {"keywords": ["소유자 점유", "소유자가 점유", "본인 점유"], "level": "low", "severity": 2,
                          "description": "소유자 점유 - 명도 부담 상대적으로 낮음"},
    "공실 추정":        {"keywords": ["공실"], "level": "low", "severity": 2,
                          "description": "공실 추정 - 현장 확인 필요"},
    "특이사항 없음":    {"keywords": ["특이사항 없음"], "level": "low", "severity": 1,
                          "description": "특이사항 미발견 - 일반적 진행"},
}


def _match(text_norm: str, kws: Iterable[str]) -> str | None:
    for kw in kws:
        if kw.replace(" ", "") in text_norm:
            return kw
    return None


def analyze_keywords(text: str) -> list[dict]:
    if not text:
        return []
    norm = text.replace(" ", "")
    found: list[dict] = []
    for risk_type, info in RISK_KEYWORDS.items():
        kw = _match(norm, info["keywords"])
        if kw:
            idx = text.find(kw) if kw in text else -1
            snippet = text[max(0, idx - 30): idx + 60] if idx >= 0 else text[:80]
            found.append({
                "type": risk_type,
                "keyword": kw,
                "risk_level": info["level"],
                "severity": info["severity"],
                "description": info["description"],
                "source_text": snippet.strip(),
                "source": "keyword",
            })
    found.sort(key=lambda x: x["severity"], reverse=True)
    return found


def save_risk_flags(item_id: int, flags: list[dict]) -> None:
    if not flags:
        return
    init_db()
    conn = get_connection()
    c = conn.cursor()
    for f in flags:
        c.execute("""
            INSERT INTO risk_flags
                (item_id, flag_type, keyword, risk_level, description, severity, source_text, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            item_id, f.get("type"), f.get("keyword"),
            f.get("risk_level"), f.get("description"),
            f.get("severity", 5), f.get("source_text"), f.get("source", "keyword"),
        ))
    conn.commit()
    conn.close()
    log.info(f"[risk] item_id={item_id} -> {len(flags)}개 플래그 저장")


def get_risk_score(item_id: int) -> int:
    conn = get_connection()
    row = conn.execute(
        "SELECT MAX(severity) FROM risk_flags WHERE item_id=?", (item_id,)
    ).fetchone()
    conn.close()
    return int(row[0] or 0)


def get_risk_level(item_id: int) -> str:
    conn = get_connection()
    row = conn.execute(
        "SELECT risk_level FROM risk_flags WHERE item_id=? "
        "ORDER BY severity DESC LIMIT 1", (item_id,)
    ).fetchone()
    conn.close()
    if not row:
        return "unknown"
    return row[0] or "unknown"


def get_risk_flags(item_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM risk_flags WHERE item_id=? ORDER BY severity DESC", (item_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
