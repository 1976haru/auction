"""
modules/finance/cashflow_simulator.py
임대 보유 시 현금흐름 시뮬레이션. 금액 단위는 원(₩).
"""
from __future__ import annotations

from modules.finance.loan_simulator import monthly_payment
from modules.finance.tax_calculator import calc_rental_income_tax


def simulate_cashflow(
    loan_principal: int,
    annual_rate: float,
    years: int,
    monthly_rent: int = 0,
    monthly_cost: int = 0,
    vacancy_rate: float = 0.05,
    hold_years: int = 5,
) -> dict:
    """월/연/누적 현금흐름.

    Returns: {monthly_loan_payment, monthly_net, annual_net, cumulative_net,
              effective_monthly_rent, rental_income_tax}
    """
    loan_pay = monthly_payment(loan_principal, annual_rate, years)
    effective_rent = int(monthly_rent * (1 - vacancy_rate))

    monthly_net = effective_rent - loan_pay - monthly_cost
    annual_rent = effective_rent * 12
    tax = calc_rental_income_tax(annual_rent)["tax"]
    annual_net = monthly_net * 12 - tax
    cumulative_net = annual_net * hold_years

    return {
        "monthly_loan_payment": loan_pay,
        "effective_monthly_rent": effective_rent,
        "monthly_net": monthly_net,
        "annual_net": annual_net,
        "cumulative_net": cumulative_net,
        "rental_income_tax": tax,
        "vacancy_rate": vacancy_rate,
        "hold_years": hold_years,
    }
