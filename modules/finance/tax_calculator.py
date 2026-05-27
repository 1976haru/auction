"""
modules/finance/tax_calculator.py
취득세 / 양도세 / 임대소득세 / 종합부동산세 계산.
세율/공제는 2024년 기준 상수(법 개정 시 본 파일만 수정).
금액 단위는 원(₩). 추정치이며 실제 세액은 개별 상황에 따라 다르다.
"""
from __future__ import annotations

# ── 취득세율 ──────────────────────────────────────────────
ACQ_RATE_NON_HOUSE = {
    "상가": 0.04, "사무실": 0.04, "오피스텔": 0.04,
    "토지": 0.04, "농지": 0.03, "공장": 0.04,
}
ACQ_RATE_MULTI_HOUSE = {2: 0.08, 3: 0.12}  # 조정대상지역 다주택 중과

# ── 양도소득세 기본세율(누진) : (과표 상한, 세율, 누진공제) ──
INCOME_TAX_BRACKETS = [
    (14_000_000, 0.06, 0),
    (50_000_000, 0.15, 1_260_000),
    (88_000_000, 0.24, 5_760_000),
    (150_000_000, 0.35, 15_440_000),
    (300_000_000, 0.38, 19_940_000),
    (500_000_000, 0.40, 25_940_000),
    (1_000_000_000, 0.42, 35_940_000),
    (float("inf"), 0.45, 65_940_000),
]

# ── 장기보유특별공제(1세대1주택, 보유연수→공제율) ──
LONG_TERM_DEDUCTION = {3: 0.24, 4: 0.32, 5: 0.40, 6: 0.40, 7: 0.40,
                       8: 0.40, 9: 0.40, 10: 0.80}

ONE_HOUSE_EXEMPT_LIMIT = 1_200_000_000   # 1세대1주택 비과세 양도가 한도(12억)


def progressive_income_tax(taxable: float) -> int:
    """누진세율(6~45%) 적용 세액(원)."""
    if taxable <= 0:
        return 0
    for limit, rate, deduction in INCOME_TAX_BRACKETS:
        if taxable <= limit:
            return int(max(0, taxable * rate - deduction))
    return 0


def calc_acquisition_tax(
    price: int,
    item_type: str = "주택",
    house_count: int = 1,
    is_adjusted_area: bool = False,
) -> dict:
    """취득세(원). 주택은 가액 구간/다주택 중과, 그 외는 유형별 정률."""
    item_type = item_type or "주택"

    # 비주택 정률
    for key, rate in ACQ_RATE_NON_HOUSE.items():
        if key in item_type:
            return {"rate": rate, "tax": int(price * rate), "basis": f"{key} {rate*100:.0f}%"}

    # 주택: 다주택 중과(조정지역)
    if is_adjusted_area and house_count >= 2:
        rate = ACQ_RATE_MULTI_HOUSE.get(min(house_count, 3), 0.12)
        return {"rate": rate, "tax": int(price * rate),
                "basis": f"{house_count}주택 중과 {rate*100:.0f}%"}

    # 주택 1주택 가액 구간
    if price <= 600_000_000:
        rate = 0.01
    elif price <= 900_000_000:
        # 6~9억 구간 선형: (가액×2/3억 - 3)%
        rate = (price / 100_000_000 * 2 / 3 - 3) / 100
        rate = max(0.01, min(0.03, rate))
    else:
        rate = 0.03
    return {"rate": round(rate, 4), "tax": int(price * rate),
            "basis": f"주택 1주택 {rate*100:.2f}%"}


def calc_transfer_tax(
    gain: int,
    holding_years: float,
    item_type: str = "주택",
    is_one_house: bool = False,
    sale_price: int = 0,
    residence_years: float = 0,
) -> dict:
    """양도소득세(원).

    - 1년 미만 70% / 1~2년 60% / 2년+ 누진(6~45%)
    - 1세대1주택(보유2년+거주2년) 양도가 12억 이하 비과세, 초과분만 과세
    - 2년+ 주택 1세대1주택은 장기보유특별공제 적용
    """
    item_type = item_type or "주택"
    is_house = "주택" in item_type or item_type in ("아파트", "빌라", "오피스텔", "단독")

    notes: list[str] = []

    # 1세대1주택 비과세 판정
    if is_house and is_one_house and holding_years >= 2 and residence_years >= 2:
        if sale_price and sale_price <= ONE_HOUSE_EXEMPT_LIMIT:
            return {"tax": 0, "rate_type": "비과세", "taxable_gain": 0,
                    "long_term_deduction_rate": 0,
                    "notes": ["1세대1주택 비과세(양도가 12억 이하)로 보입니다"]}
        if sale_price and sale_price > ONE_HOUSE_EXEMPT_LIMIT:
            # 12억 초과분 비율만 과세
            taxable_ratio = (sale_price - ONE_HOUSE_EXEMPT_LIMIT) / sale_price
            gain = int(gain * taxable_ratio)
            notes.append("12억 초과분만 과세")

    # 단기 양도 중과
    if holding_years < 1:
        rate = 0.70
        tax = int(max(0, gain) * rate)
        return {"tax": tax, "rate_type": "단기 1년 미만 70%",
                "taxable_gain": max(0, gain), "long_term_deduction_rate": 0,
                "notes": notes + ["1년 미만 보유 중과세율 70%"]}
    if holding_years < 2:
        rate = 0.60
        tax = int(max(0, gain) * rate)
        return {"tax": tax, "rate_type": "단기 1~2년 60%",
                "taxable_gain": max(0, gain), "long_term_deduction_rate": 0,
                "notes": notes + ["1~2년 보유 중과세율 60%"]}

    # 2년 이상: 장특공(1세대1주택만) → 누진세율
    ltd_rate = 0.0
    if is_house and is_one_house:
        yrs = int(holding_years)
        ltd_rate = LONG_TERM_DEDUCTION.get(min(yrs, 10), 0.24 if yrs >= 3 else 0.0)
    taxable = max(0, gain) * (1 - ltd_rate)
    tax = progressive_income_tax(taxable)
    return {
        "tax": tax,
        "rate_type": "2년 이상 누진(6~45%)",
        "taxable_gain": int(taxable),
        "long_term_deduction_rate": ltd_rate,
        "notes": notes + ([f"장기보유특별공제 {ltd_rate*100:.0f}%"] if ltd_rate else []),
    }


def calc_rental_income_tax(annual_rent: int, separate: bool = True,
                           expense_rate: float = 0.5) -> dict:
    """임대소득세(원). 분리과세(2천만 이하) 14% 가정, 필요경비율 적용."""
    if separate and annual_rent <= 20_000_000:
        taxable = max(0, annual_rent * (1 - expense_rate) - 2_000_000)
        tax = int(taxable * 0.14)
        return {"tax": tax, "type": "분리과세 14%", "taxable": int(taxable)}
    # 종합과세(누진)
    taxable = max(0, annual_rent * (1 - expense_rate))
    return {"tax": progressive_income_tax(taxable), "type": "종합과세 누진",
            "taxable": int(taxable)}


def calc_property_holding_tax(value: int, is_one_house: bool = True) -> dict:
    """종합부동산세(원). 1세대1주택 12억 초과분 과세(간이)."""
    threshold = 1_200_000_000 if is_one_house else 900_000_000
    if value <= threshold:
        return {"tax": 0, "excess": 0, "rate": 0.0}
    excess = value - threshold
    if value <= 2_500_000_000:
        rate = 0.005
    elif value <= 5_000_000_000:
        rate = 0.007
    elif value <= 9_400_000_000:
        rate = 0.010
    else:
        rate = 0.020
    return {"tax": int(excess * rate), "excess": excess, "rate": rate}
