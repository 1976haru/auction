"""
modules/finance/loan_simulator.py
대출 한도(LTV/DSR) + 원리금균등 상환액 계산.
금액 단위는 원(₩).
"""
from __future__ import annotations

DEFAULT_LTV = 0.70
DEFAULT_DSR = 0.40


def monthly_payment(principal: int, annual_rate: float, years: int) -> int:
    """원리금균등 월 상환액(원)."""
    if principal <= 0:
        return 0
    n = max(1, years * 12)
    r = annual_rate / 12
    if r == 0:
        return int(principal / n)
    factor = (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    return int(round(principal * factor))


def _loan_from_payment(monthly_budget: float, annual_rate: float, years: int) -> int:
    """월 상환 가능액 -> 최대 원금(역산)."""
    if monthly_budget <= 0:
        return 0
    n = max(1, years * 12)
    r = annual_rate / 12
    if r == 0:
        return int(monthly_budget * n)
    factor = (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    return int(monthly_budget / factor)


def calc_max_loan(
    price: int,
    annual_income: int = 0,
    existing_debt_monthly: int = 0,
    ltv: float = DEFAULT_LTV,
    dsr_limit: float = DEFAULT_DSR,
    annual_rate: float = 0.04,
    years: int = 30,
) -> dict:
    """LTV/DSR 기준 최대 대출 한도(원).

    Returns: {max_loan, ltv_cap, dsr_cap, monthly_payment, binding, equity_needed}
    """
    ltv_cap = int(price * ltv)

    # DSR: 연소득×한도 - 기존부채 연상환 = 신규 대출에 쓸 수 있는 연 상환여력
    annual_capacity = annual_income * dsr_limit - existing_debt_monthly * 12
    monthly_capacity = max(0, annual_capacity / 12)
    dsr_cap = _loan_from_payment(monthly_capacity, annual_rate, years) if annual_income else ltv_cap

    if annual_income:
        max_loan = min(ltv_cap, dsr_cap)
        binding = "LTV" if ltv_cap <= dsr_cap else "DSR"
    else:
        max_loan = ltv_cap
        binding = "LTV"

    max_loan = max(0, max_loan)
    pay = monthly_payment(max_loan, annual_rate, years)
    return {
        "max_loan": max_loan,
        "ltv_cap": ltv_cap,
        "dsr_cap": dsr_cap if annual_income else None,
        "monthly_payment": pay,
        "binding": binding,
        "equity_needed": max(0, price - max_loan),
        "ltv": ltv,
        "annual_rate": annual_rate,
        "years": years,
    }
