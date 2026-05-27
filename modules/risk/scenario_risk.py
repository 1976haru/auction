"""
modules/risk/scenario_risk.py
Best / Base / Worst 3케이스 리스크 시나리오(확률 가중).
재매각 모델(낙찰→명도→매도) 기준 ROE 추정. 금액 단위는 원(₩).
"""
from __future__ import annotations

from core.logger import log
from modules.finance.roe_calculator import calc_roe
from modules.finance.tax_calculator import calc_acquisition_tax, calc_transfer_tax
from modules.scenarios import _common as C

# (라벨, 확률, 낙찰가배수, 매도가배수, 명도배수, 보유연수)
CASES = {
    "best": {"prob": 0.25, "bid_mult": 1.00, "sale_mult": 1.05, "evict_mult": 0.5, "years": 0.5},
    "base": {"prob": 0.50, "bid_mult": 1.00, "sale_mult": 1.00, "evict_mult": 1.0, "years": 0.5},
    "worst": {"prob": 0.25, "bid_mult": 1.05, "sale_mult": 0.95, "evict_mult": 2.0, "years": 1.0},
}


def _roe_for_case(bid: int, sale: int, evict: int, years: float,
                  equity: int, loan_monthly: int, item_type: str) -> dict:
    acq = calc_acquisition_tax(bid, item_type)["tax"]
    finance_cost = int(loan_monthly * (years * 12) * 0.6)
    gain = sale - bid
    transfer = calc_transfer_tax(gain, holding_years=years, item_type=item_type)["tax"]
    net = gain - acq - evict - finance_cost - transfer
    roe = calc_roe(max(1, equity), net, years)
    return {"net_return": net, "roe": roe["roe"], "annualized_roe": roe["annualized_roe"]}


def analyze_scenario_risk(item_id: int, bid_price: int,
                          user_profile: dict | None = None,
                          item: dict | None = None) -> dict:
    profile = C.load_profile(user_profile)
    item = item or C.get_item(item_id)
    item_type = item.get("item_type") or "주택"

    market = C.market_price_won(item)
    base_evict = C.eviction_cost_won(item_id, item)
    loan = C.get_loan(bid_price, profile)
    loan_monthly = loan["monthly_payment"]

    results: dict[str, dict] = {}
    for name, p in CASES.items():
        bid = int(bid_price * p["bid_mult"])
        sale = int(market * p["sale_mult"])
        evict = int(base_evict * p["evict_mult"])
        acq = calc_acquisition_tax(bid, item_type)["tax"]
        equity = max(1, (bid - loan["max_loan"]) + acq + evict)
        case = _roe_for_case(bid, sale, evict, p["years"], equity, loan_monthly, item_type)
        case["probability"] = p["prob"]
        results[name] = case

    mean_roe = sum(results[n]["roe"] * CASES[n]["prob"] for n in results)
    worst_loss = min(0, results["worst"]["net_return"])

    out = {
        "item_id": item_id,
        "bid_price": bid_price,
        "cases": results,
        "mean_roe": round(mean_roe, 2),
        "worst_case_loss": int(abs(worst_loss)),
    }
    log.info(f"[risk] item_id={item_id} 시나리오 리스크 기댓값 ROE {out['mean_roe']}%")
    return out
