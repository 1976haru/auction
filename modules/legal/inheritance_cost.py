"""
modules/legal/inheritance_cost.py
인수금액 자동 합산(추정).

인수 가능성이 있는 항목:
  - 말소기준권리 이전의 가처분/가등기/지상권/전세권 등 (인수 가능성)
  - 대항력 있는 임차인 보증금 (tenant_info 제공 시)
  - 당해세/체납 관리비/유치권(성립 시) 등 (호출 측에서 값 전달)

모든 값은 원 단위 추정치이며 실제 인수 여부는 사안별 확인이 필요하다.
"""
from __future__ import annotations

from core.logger import log
from modules.legal.rights_parser import get_rights_timeline
from modules.legal.senior_right import get_senior_right, identify_senior_right
from modules.legal.tenant_protection import analyze_tenant

# 말소기준 이전이면 인수 가능성이 있는 권리 유형
NON_EXTINGUISHING_TYPES = ("가처분", "가등기", "지상권", "전세권", "임차권", "주택임차권")


def calculate_inheritance(
    item_id: int,
    tenant_info: dict | None = None,
    tax_arrears: int = 0,
    management_fee: int = 0,
    lien_estimated: int = 0,
    others: int = 0,
) -> dict:
    """인수금액 합산(추정).

    Returns dict:
      total_inherited, breakdown{tenant_deposit, tax_arrears, management_fee,
      lien_estimated, senior_rights, others}, confidence(0~1), must_check_items
    """
    timeline = get_rights_timeline(item_id)
    senior = get_senior_right(item_id)
    if senior is None and timeline:
        senior = identify_senior_right(item_id)
    senior_date = senior.get("register_date") if senior else None

    must_check_items: list[str] = []

    # 1) 말소기준 이전의 비말소성 권리 금액 추정
    senior_rights_amount = 0
    for r in timeline:
        rt = r.get("right_type") or ""
        rdate = r.get("register_date")
        if not any(t in rt for t in NON_EXTINGUISHING_TYPES):
            continue
        # 말소기준보다 빠른 경우만 인수 검토
        if senior_date and rdate and rdate >= senior_date:
            continue
        amt = r.get("amount") or 0
        senior_rights_amount += amt
        must_check_items.append(
            f"{r.get('register_date') or '일자미상'} {rt}: 인수 가능성 확인 필요"
        )

    # 2) 대항력 있는 임차인 보증금
    tenant_deposit = 0
    if tenant_info:
        ta = analyze_tenant(item_id, tenant_info)
        tenant_deposit = ta.get("estimated_inherit", 0)
        if tenant_deposit > 0:
            must_check_items.append("대항력 임차인 보증금 배당/인수 여부 확인 필요")

    # 3) 호출 측 제공 항목
    if tax_arrears:
        must_check_items.append("당해세 체납액 확인 필요")
    if management_fee:
        must_check_items.append("체납 관리비(공용부분) 인수 범위 확인 필요")
    if lien_estimated:
        must_check_items.append("유치권 성립 여부 및 피담보채권액 확인 필요")

    breakdown = {
        "tenant_deposit": tenant_deposit,
        "tax_arrears": tax_arrears,
        "management_fee": management_fee,
        "lien_estimated": lien_estimated,
        "senior_rights": senior_rights_amount,
        "others": others,
    }
    total_inherited = sum(breakdown.values())

    # 신뢰도: 등기 시계열/말소기준 존재 여부, 임차정보 유무로 가감
    confidence = 0.5
    if senior:
        confidence += 0.2
    if timeline:
        confidence += 0.1
    if tenant_info:
        confidence += 0.1
    if lien_estimated:  # 유치권은 불확실성 큼
        confidence -= 0.2
    confidence = round(max(0.1, min(0.95, confidence)), 2)

    result = {
        "total_inherited": total_inherited,
        "breakdown": breakdown,
        "confidence": confidence,
        "must_check_items": must_check_items or ["특이 인수항목 미발견 - 현장/서류 확인 권장"],
    }
    log.info(
        f"[legal] item_id={item_id} 인수금액 추정 -> "
        f"{total_inherited:,}원 (신뢰도 {confidence})"
    )
    return result
