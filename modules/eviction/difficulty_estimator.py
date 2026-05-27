"""
modules/eviction/difficulty_estimator.py
점유자 유형 분류 + 명도 난이도(1~10) 평가.
"""
from __future__ import annotations

from core.database import get_connection
from core.logger import log

OCCUPANT_TYPES = (
    "vacant",                # 공실
    "owner",                 # 소유자 점유
    "tenant_no_priority",    # 임차인(대항력 없음)
    "tenant_with_priority",  # 임차인(대항력 있음 - 보증금 인수)
    "lien_holder",           # 유치권 주장자
    "hostile",               # 악성/점유자 미상
)

# 유형별 기본 난이도(1~10)
BASE_DIFFICULTY: dict[str, int] = {
    "vacant": 1,
    "owner": 3,
    "tenant_no_priority": 4,
    "tenant_with_priority": 7,
    "lien_holder": 9,
    "hostile": 8,
}

_LABELS_KO: dict[str, str] = {
    "vacant": "공실",
    "owner": "소유자 점유",
    "tenant_no_priority": "임차인(대항력 없음)",
    "tenant_with_priority": "임차인(대항력 있음)",
    "lien_holder": "유치권 주장",
    "hostile": "악성/점유자 미상",
}


def _risk_flag_types(item_id: int) -> set[str]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT flag_type, keyword FROM risk_flags WHERE item_id=?", (item_id,)
    ).fetchall()
    conn.close()
    out: set[str] = set()
    for r in rows:
        for v in (r["flag_type"], r["keyword"]):
            if v:
                out.add(str(v))
    return out


def classify_occupant(item_id: int, hint: dict | None = None) -> str:
    """점유자 유형 분류.

    hint 우선순위:
      - hint['occupant_type'] 직접 지정 시 그대로 사용
      - hint['tenant'] (analyze_tenant 결과 dict) 로 대항력 여부 판정
      - hint['vacant'] / hint['owner_occupied'] 불리언
    그 외에는 risk_flags 키워드로 추정한다.
    """
    hint = hint or {}

    explicit = hint.get("occupant_type")
    if explicit in OCCUPANT_TYPES:
        return explicit

    flags = _risk_flag_types(item_id)

    # 유치권 / 악성 우선
    if "유치권" in flags or hint.get("lien"):
        return "lien_holder"
    if "점유자 미상" in flags or hint.get("hostile"):
        return "hostile"

    # 명시적 공실/소유자
    if hint.get("vacant") or "공실 추정" in flags:
        return "vacant"
    if hint.get("owner_occupied") or "소유자 점유" in flags:
        return "owner"

    # 임차인 정보
    tenant = hint.get("tenant")
    if tenant:
        return "tenant_with_priority" if tenant.get("has_priority") else "tenant_no_priority"

    if "대항력" in flags or "선순위임차인" in flags:
        return "tenant_with_priority"
    if "임차인" in flags or "전입세대" in flags:
        return "tenant_no_priority"

    # 정보 부족 시 보수적으로 소유자 점유 가정(중간 난이도)
    return "owner"


def evaluate_difficulty(occupant_type: str, item_info: dict | None = None) -> dict:
    """유형 + 물건 특성으로 난이도(1~10) 보정.

    Returns: {occupant_type, label, difficulty, level, factors}
    """
    item_info = item_info or {}
    if occupant_type not in BASE_DIFFICULTY:
        occupant_type = "owner"

    difficulty = BASE_DIFFICULTY[occupant_type]
    factors: list[str] = [f"기본 유형: {_LABELS_KO[occupant_type]} ({difficulty})"]

    item_type = (item_info.get("item_type") or "")
    if any(t in item_type for t in ("상가", "토지", "공장", "사무실")):
        difficulty += 1
        factors.append("상가/토지/공장 등 특수물건 +1")

    min_bid = item_info.get("min_bid_price") or item_info.get("appraisal_price") or 0
    # min_bid 가 만원 단위(기존 스키마)일 수 있어 1억=10000(만원) 기준으로 판단
    if min_bid and min_bid >= 100_000:  # 10억(만원) 이상 고가
        difficulty += 1
        factors.append("고가 물건(협상 장기화 가능) +1")

    difficulty = max(1, min(10, difficulty))

    if difficulty <= 3:
        level = "easy"
    elif difficulty <= 5:
        level = "medium"
    elif difficulty <= 7:
        level = "hard"
    else:
        level = "severe"

    result = {
        "occupant_type": occupant_type,
        "label": _LABELS_KO[occupant_type],
        "difficulty": difficulty,
        "level": level,
        "factors": factors,
    }
    log.info(f"[eviction] 난이도 평가 -> {occupant_type}={difficulty}/10 ({level})")
    return result
