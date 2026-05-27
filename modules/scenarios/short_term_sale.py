"""
modules/scenarios/short_term_sale.py
단타(낙찰 후 6개월 보유 후 매도) 시나리오.
"""
from __future__ import annotations

from modules.finance.roe_calculator import calc_roe
from modules.finance.tax_calculator import calc_acquisition_tax, calc_transfer_tax
from modules.scenarios import _common as C

HOLDING_MONTHS = 6


def simulate_short_sale(item_id: int, bid_price: int, user_profile: dict | None = None,
                        item: dict | None = None) -> dict:
    """bid_price: 원 단위 입찰가."""
    profile = C.load_profile(user_profile)
    item = item or C.get_item(item_id)

    market = C.market_price_won(item)
    loc = C.location_total(item_id)
    sale_price = int(market * (1 + C.market_premium(loc)))

    # 비용
    acq = calc_acquisition_tax(bid_price, item.get("item_type") or "주택")["tax"]
    eviction = C.eviction_cost_won(item_id, item)
    loan = C.get_loan(bid_price, profile)
    finance_cost = int(loan["monthly_payment"] * HOLDING_MONTHS * 0.6)  # 6개월 이자성 비용 근사
    repair = 3_000_000
    broker = int(sale_price * 0.005)

    gain = sale_price - bid_price
    transfer = calc_transfer_tax(gain, holding_years=HOLDING_MONTHS / 12,
                                 item_type=item.get("item_type") or "주택")
    total_costs = acq + eviction + finance_cost + repair + broker + transfer["tax"]
    net_return = gain - (acq + eviction + finance_cost + repair + broker + transfer["tax"])

    # 자기자본 = (낙찰가 - 대출) + 선취 현금비용
    equity = max(1, (bid_price - loan["max_loan"]) + acq + eviction + repair)
    affordable = equity <= profile["capital_max"]

    roe = calc_roe(equity, net_return, HOLDING_MONTHS / 12,
                   unleveraged_equity=bid_price)
    score = C.roe_to_score(roe["annualized_roe"], affordable)

    return {
        "scenario": "short_sale",
        "label": "단타 매도",
        "bid_price": bid_price,
        "holding_months": HOLDING_MONTHS,
        "sale_price": sale_price,
        "loan_amount": loan["max_loan"],
        "capital_needed": equity,
        "costs": {
            "acquisition_tax": acq, "eviction": eviction, "finance": finance_cost,
            "repair": repair, "broker": broker, "transfer_tax": transfer["tax"],
            "total": total_costs,
        },
        "net_return": net_return,
        "roe": roe["roe"],
        "annualized_roe": roe["annualized_roe"],
        "score": score,
        "affordable": affordable,
        "notes": [
            f"6개월 내 매도 시 양도세 {transfer['rate_type']}",
            "단기 유동성 높음, 절세 어려움",
        ],
    }
