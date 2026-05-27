"""
modules/finance — 금융 시뮬레이터 (세금/대출/현금흐름/ROE)

순수 계산 모듈(USE_AI 무관). 금액 단위는 원(₩).
세율/공제 정보는 각 모듈 상단 상수로 정의(법 개정 시 수정 용이).
실제 세액은 개별 상황에 따라 달라지므로 추정치로 활용한다.
"""
from __future__ import annotations

from modules.finance.tax_calculator import (
    calc_acquisition_tax,
    calc_transfer_tax,
    calc_rental_income_tax,
    calc_property_holding_tax,
    progressive_income_tax,
)
from modules.finance.loan_simulator import (
    calc_max_loan,
    monthly_payment,
)
from modules.finance.cashflow_simulator import simulate_cashflow
from modules.finance.roe_calculator import calc_roe

__all__ = [
    "calc_acquisition_tax",
    "calc_transfer_tax",
    "calc_rental_income_tax",
    "calc_property_holding_tax",
    "progressive_income_tax",
    "calc_max_loan",
    "monthly_payment",
    "simulate_cashflow",
    "calc_roe",
]
