"""
modules/scenarios/long_term_rental.py
임대(5년 보유, 임대수익 + 매도) 시나리오.
"""
from __future__ import annotations

from modules.finance.cashflow_simulator import simulate_cashflow
from modules.finance.roe_calculator import calc_roe
from modules.finance.tax_calculator import (calc_acquisition_tax, calc_transfer_tax,
                                            calc_property_holding_tax)
from modules.scenarios import _common as C

HOLD_YEARS = 5


def simulate_rental(item_id: int, bid_price: int, user_profile: dict | None = None,
                    rental_type: str = "monthly", item: dict | None = None) -> dict:
    profile = C.load_profile(user_profile)
    item = item or C.get_item(item_id)

    market = C.market_price_won(item)
    rate = C.cap_rate(item.get("item_type"), item.get("address_full"))
    annual_rent = int(market * rate)
    monthly_rent = annual_rent // 12

    acq = calc_acquisition_tax(bid_price, item.get("item_type") or "주택")["tax"]
    eviction = C.eviction_cost_won(item_id, item)
    loan = C.get_loan(bid_price, profile)

    cf = simulate_cashflow(
        loan_principal=loan["max_loan"], annual_rate=profile["loan_rate"],
        years=profile["loan_years"], monthly_rent=monthly_rent,
        monthly_cost=80_000, vacancy_rate=0.05, hold_years=HOLD_YEARS,
    )
    cumulative_rental = cf["cumulative_net"]

    # 5년 후 매도
    sale_price = int(market * (1 + profile["annual_appreciation"]) ** HOLD_YEARS)
    gain = sale_price - bid_price
    transfer = calc_transfer_tax(gain, holding_years=HOLD_YEARS,
                                 item_type=item.get("item_type") or "주택",
                                 is_one_house=profile.get("is_one_house", False),
                                 sale_price=sale_price)
    holding_tax = calc_property_holding_tax(sale_price,
                                            is_one_house=profile.get("is_one_house", False))["tax"]

    net_return = ((sale_price - bid_price) - transfer["tax"]
                  + cumulative_rental - acq - eviction - holding_tax)

    equity = max(1, (bid_price - loan["max_loan"]) + acq + eviction)
    affordable = equity <= profile["capital_max"]

    roe = calc_roe(equity, net_return, HOLD_YEARS, unleveraged_equity=bid_price)
    score = C.roe_to_score(roe["annualized_roe"], affordable)

    return {
        "scenario": "rental",
        "label": "임대 보유",
        "bid_price": bid_price,
        "holding_months": HOLD_YEARS * 12,
        "sale_price": sale_price,
        "loan_amount": loan["max_loan"],
        "capital_needed": equity,
        "rental_yield": round(rate, 4),
        "monthly_rent": monthly_rent,
        "monthly_cashflow": cf["monthly_net"],
        "cumulative_rental_net": cumulative_rental,
        "vacancy_assumed": cf["vacancy_rate"],
        "costs": {
            "acquisition_tax": acq, "eviction": eviction,
            "transfer_tax": transfer["tax"], "holding_tax": holding_tax,
            "rental_income_tax_annual": cf["rental_income_tax"],
        },
        "net_return": net_return,
        "roe": roe["roe"],
        "annualized_roe": roe["annualized_roe"],
        "score": score,
        "affordable": affordable,
        "notes": [
            f"임대수익률 {rate*100:.1f}% 가정, 공실 5%",
            f"5년 보유 {transfer['rate_type']}"
            + ("(장특공 적용)" if transfer.get("long_term_deduction_rate") else ""),
        ],
    }
