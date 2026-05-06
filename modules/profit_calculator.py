"""
modules/profit_calculator.py
수익 계산 모듈 — 예상 시세차익 / 수익률 / 입찰가 범위 계산
"""
from core.config import (
    ACQUISITION_TAX_RATE, DEFAULT_REPAIR_COST,
    DEFAULT_EVICTION_COST, FINANCE_RATE
)


def calc_acquisition_tax(price_man: int, item_type: str = "아파트") -> int:
    """취득세 계산 (만원)"""
    # 6억 이하 1주택 기준 간소화 (실제는 더 복잡)
    price_eok = price_man / 10000
    if item_type in ("아파트", "오피스텔"):
        if price_eok <= 6:
            rate = 0.01
        elif price_eok <= 9:
            rate = ACQUISITION_TAX_RATE
        else:
            rate = 0.03
    else:
        rate = ACQUISITION_TAX_RATE
    return int(price_man * rate)


def calc_total_cost(
    bid_price_man: int,
    item_type: str = "아파트",
    repair_cost: int = None,
    eviction_cost: int = None,
    finance_months: int = 6,
) -> dict:
    """
    총 비용 계산.
    반환: {acquisition_tax, repair, eviction, finance, total, items}
    """
    repair    = repair_cost    if repair_cost    is not None else DEFAULT_REPAIR_COST
    eviction  = eviction_cost  if eviction_cost  is not None else DEFAULT_EVICTION_COST
    acq_tax   = calc_acquisition_tax(bid_price_man, item_type)
    finance   = int(bid_price_man * FINANCE_RATE * (finance_months / 12))

    total = acq_tax + repair + eviction + finance
    return {
        "acquisition_tax": acq_tax,
        "repair":          repair,
        "eviction":        eviction,
        "finance":         finance,
        "total":           total,
        "items": {
            "취득세":   acq_tax,
            "수리비":   repair,
            "명도비":   eviction,
            "금융비용": finance,
        }
    }


def calc_profit(
    market_price_man: int,
    bid_price_man: int,
    item_type: str = "아파트",
    repair_cost: int = None,
    eviction_cost: int = None,
) -> dict:
    """
    예상 시세차익 및 수익률 계산.
    market_price_man: 시세 (만원)
    bid_price_man: 입찰가 (만원)
    """
    costs = calc_total_cost(bid_price_man, item_type, repair_cost, eviction_cost)
    invested = bid_price_man + costs["total"]
    profit   = market_price_man - invested
    roi      = (profit / invested * 100) if invested > 0 else 0

    return {
        "market_price":  market_price_man,
        "bid_price":     bid_price_man,
        "total_cost":    costs["total"],
        "invested":      invested,
        "profit":        profit,
        "roi":           round(roi, 2),
        "cost_breakdown": costs["items"],
        "is_profitable": profit > 0,
    }


def recommend_bid_prices(
    market_price_man: int,
    item_type: str = "아파트",
    target_roi: float = 10.0,
) -> dict:
    """
    보수적 / 기준 / 공격적 입찰가 3단계 추천.
    target_roi: 목표 수익률 (%)
    """
    # 각 시나리오별 비용 역산 (반복법 대신 근사값)
    def bid_for_roi(roi_target):
        # bid * (1 + cost_rate) = market * (1 - roi_target/100) 역산
        cost_rate = ACQUISITION_TAX_RATE + 0.02  # 취득세 + 기타 약 2%
        return int(market_price_man / (1 + cost_rate) * (1 - roi_target / 100))

    conservative = bid_for_roi(target_roi + 5)   # 높은 수익률 목표 → 낮은 가격
    standard     = bid_for_roi(target_roi)
    aggressive   = bid_for_roi(max(target_roi - 5, 2))

    return {
        "conservative": {"label": "보수적",  "price": conservative,
                         "desc": f"수익률 {target_roi+5:.0f}% 목표"},
        "standard":     {"label": "기준",    "price": standard,
                         "desc": f"수익률 {target_roi:.0f}% 목표"},
        "aggressive":   {"label": "공격적",  "price": aggressive,
                         "desc": f"수익률 {max(target_roi-5,2):.0f}% 목표"},
        "market_price": market_price_man,
        "note": "입찰가는 추정치입니다. 실제 비용·시세를 직접 확인하세요."
    }


def top_n_by_profit(items: list[dict], n: int = 5) -> list[dict]:
    """
    items 리스트에서 예상 시세차익 TOP N 반환.
    각 item에 market_price_man 키가 있어야 함.
    """
    results = []
    for item in items:
        market = item.get("market_price_man") or item.get("appraisal_price", 0)
        bid    = item.get("min_bid_price", 0)
        if not bid or not market:
            continue
        p = calc_profit(market, bid, item.get("item_type", "아파트"))
        results.append({**item, **p})

    results.sort(key=lambda x: x["profit"], reverse=True)
    return results[:n]
