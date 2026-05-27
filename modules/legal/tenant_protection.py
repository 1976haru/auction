"""
modules/legal/tenant_protection.py
임차인 대항력 / 우선변제권 / 소액임차인 최우선변제 판정.

판정 결과는 추정치이며, 전입세대열람·확정일자·배당요구 여부 등 실제 서류 확인이 필요하다.
지역별 소액임차인 보증금 한도/최우선변제액은 주택임대차보호법 시행령 기준(개정 시 수정).
"""
from __future__ import annotations

from core.logger import log
from modules.legal.senior_right import get_senior_right, identify_senior_right

# 지역 구분 -> (소액임차인 보증금 한도(원), 최우선변제액(원))
SMALL_LEASE_LIMITS: dict[str, tuple[int, int]] = {
    "서울": (165_000_000, 55_000_000),
    "수도권과밀": (145_000_000, 48_000_000),
    "기타": (85_000_000, 28_000_000),
}

_SEOUL = ("서울",)
_OVERCONCENTRATED = ("과천", "성남", "하남", "고양", "수원", "안양", "부천", "광명", "인천", "의왕", "군포", "용인")


def _region_key(region: str | None) -> str:
    r = region or ""
    if any(k in r for k in _SEOUL):
        return "서울"
    if any(k in r for k in _OVERCONCENTRATED):
        return "수도권과밀"
    return "기타"


def analyze_tenant(item_id: int, tenant_info: dict) -> dict:
    """임차인 보호 판정.

    tenant_info 권장 키:
      move_in_date(전입신고일, YYYY-MM-DD), occupied(거주/인도 여부, bool),
      fixed_date(확정일자, YYYY-MM-DD), deposit(보증금, 원), region(주소/지역)

    Returns dict: has_priority, has_preferred_claim, is_small_lease,
                  estimated_inherit, reason, check_items
    """
    move_in = (tenant_info or {}).get("move_in_date")
    occupied = bool((tenant_info or {}).get("occupied", True))
    fixed_date = (tenant_info or {}).get("fixed_date")
    deposit = int((tenant_info or {}).get("deposit") or 0)
    region = (tenant_info or {}).get("region")

    check_items: list[str] = [
        "전입세대열람 내역 확인 필요",
        "확정일자 부여 여부 확인 필요",
        "배당요구 종기 내 배당요구 여부 확인 필요",
    ]

    senior = get_senior_right(item_id)
    if senior is None:
        senior = identify_senior_right(item_id)
    senior_date = senior.get("register_date") if senior else None

    # 대항력: 전입 + 인도 완료 + 말소기준권리보다 빠름
    has_priority = False
    if move_in and occupied and senior_date:
        has_priority = move_in < senior_date
    elif move_in and occupied and senior_date is None:
        # 말소기준권리가 없으면 대항력 인정 가능성
        has_priority = True

    # 우선변제권: 대항력 + 확정일자
    has_preferred_claim = bool(has_priority and fixed_date)

    # 소액임차인 최우선변제
    region_key = _region_key(region)
    limit, max_priority = SMALL_LEASE_LIMITS[region_key]
    is_small_lease = bool(deposit > 0 and deposit <= limit)
    small_lease_amount = min(deposit, max_priority) if is_small_lease else 0

    # 인수 예상액(추정): 대항력 있고 배당으로 회수 못하는 보증금이 인수 대상이 될 가능성
    if has_priority:
        # 보수적으로 보증금 전액을 인수 가능성으로 본다(배당 미확정 가정)
        estimated_inherit = deposit
    else:
        estimated_inherit = 0

    if has_priority:
        reason = (
            f"전입일({move_in})이 말소기준권리"
            f"({senior_date or '미상'})보다 빨라 대항력이 있는 것으로 보입니다. "
            f"보증금 {deposit:,}원이 인수될 가능성이 있습니다(배당 여부 확인 필요)."
        )
    elif senior_date and move_in and move_in >= senior_date:
        reason = (
            f"전입일({move_in})이 말소기준권리({senior_date})보다 늦어 "
            f"대항력이 없는 것으로 보입니다. 인수 부담은 낮을 가능성이 있습니다."
        )
    else:
        reason = "임차 정보가 부족하여 대항력 판단을 위해 추가 확인이 필요합니다."

    result = {
        "has_priority": has_priority,
        "has_preferred_claim": has_preferred_claim,
        "is_small_lease": is_small_lease,
        "small_lease_amount": small_lease_amount,
        "estimated_inherit": estimated_inherit,
        "region_key": region_key,
        "senior_date": senior_date,
        "reason": reason,
        "check_items": check_items,
    }
    log.info(
        f"[legal] item_id={item_id} 임차인 분석 -> "
        f"대항력={has_priority}, 인수예상={estimated_inherit:,}원"
    )
    return result
