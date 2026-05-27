"""
modules/finance/roe_calculator.py
자기자본수익률(ROE) + 연환산 + 레버리지 효과 + 회수기간.
금액 단위는 원(₩).
"""
from __future__ import annotations


def calc_roe(
    equity: int,
    total_return: int,
    holding_years: float,
    all_costs: int = 0,
    unleveraged_equity: int | None = None,
) -> dict:
    """ROE 계산.

    equity: 자기자본(원), total_return: 총수익(원, 비용 차감 전),
    all_costs: 추가 비용(원), holding_years: 보유연수
    unleveraged_equity: 대출 없이 전액 자기자본일 때의 자본(레버리지 효과 비교용)

    Returns: {net_return, roe, annualized_roe, leverage_effect, payback_years}
    """
    equity = max(1, equity)
    net_return = total_return - all_costs
    roe = net_return / equity * 100

    years = max(0.01, holding_years)
    base = 1 + roe / 100
    if base > 0:
        annualized = (base ** (1 / years) - 1) * 100
    else:
        annualized = -100.0  # 원금 전손 이하

    # 레버리지 효과: 동일 수익을 전액 자기자본으로 냈을 때 ROE 대비 차이(%p)
    leverage_effect = None
    if unleveraged_equity:
        unlev_roe = net_return / max(1, unleveraged_equity) * 100
        leverage_effect = round(roe - unlev_roe, 2)

    # 회수기간(연): 자기자본 / 연평균 순수익
    annual_profit = net_return / years
    payback_years = round(equity / annual_profit, 2) if annual_profit > 0 else None

    return {
        "net_return": int(net_return),
        "roe": round(roe, 2),
        "annualized_roe": round(annualized, 2),
        "leverage_effect": leverage_effect,
        "payback_years": payback_years,
    }
