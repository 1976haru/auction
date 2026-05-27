"""
modules/scenarios/owner_residence.py
실거주(3년 거주 후 매도) 시나리오. 1세대1주택 비과세 효과 반영.
"""
from __future__ import annotations

from modules.finance.roe_calculator import calc_roe
from modules.finance.tax_calculator import calc_acquisition_tax, calc_transfer_tax
from modules.scenarios import _common as C

HOLD_YEARS = 3


def simulate_residence(item_id: int, bid_price: int, user_profile: dict | None = None,
                       item: dict | None = None) -> dict:
    profile = C.load_profile(user_profile)
    item = item or C.get_item(item_id)

    market = C.market_price_won(item)
    loc = C.location_total(item_id)

    # 3년간 월세 절감(거주가치) = 시세 × 0.3%/월 × 36
    monthly_saving = int(market * 0.003)
    living_value = monthly_saving * (HOLD_YEARS * 12)

    acq = calc_acquisition_tax(bid_price, item.get("item_type") or "주택")["tax"]
    eviction = C.eviction_cost_won(item_id, item)

    sale_price = int(market * (1 + profile["annual_appreciation"]) ** HOLD_YEARS)
    gain = sale_price - bid_price
    # 1세대1주택 비과세(보유3년+거주3년 가정), 12억 이하
    transfer = calc_transfer_tax(gain, holding_years=HOLD_YEARS,
                                 item_type=item.get("item_type") or "주택",
                                 is_one_house=True, sale_price=sale_price,
                                 residence_years=HOLD_YEARS)
    tax_savings = 0
    if transfer["rate_type"] == "비과세":
        # 비과세가 아니었다면 냈을 세금(대략) 추정
        ref = calc_transfer_tax(gain, holding_years=HOLD_YEARS,
                                item_type=item.get("item_type") or "주택")
        tax_savings = ref["tax"]

    loan = C.get_loan(bid_price, profile)
    net_return = ((sale_price - bid_price) - transfer["tax"] + living_value - acq - eviction)

    equity = max(1, (bid_price - loan["max_loan"]) + acq + eviction)
    affordable = equity <= profile["capital_max"]

    roe = calc_roe(equity, net_return, HOLD_YEARS, unleveraged_equity=bid_price)
    score = C.roe_to_score(roe["annualized_roe"], affordable)

    return {
        "scenario": "residence",
        "label": "실거주",
        "bid_price": bid_price,
        "holding_months": HOLD_YEARS * 12,
        "sale_price": sale_price,
        "loan_amount": loan["max_loan"],
        "capital_needed": equity,
        "living_value": living_value,
        "comfort_score": loc,
        "tax_savings": tax_savings,
        "costs": {
            "acquisition_tax": acq, "eviction": eviction,
            "transfer_tax": transfer["tax"],
        },
        "net_return": net_return,
        "roe": roe["roe"],
        "annualized_roe": roe["annualized_roe"],
        "score": score,
        "affordable": affordable,
        "notes": [
            transfer["rate_type"] + (" (양도세 절감)" if tax_savings else ""),
            f"거주가치(월세 절감) {living_value:,}원, 입지 {loc}/100",
        ],
    }
