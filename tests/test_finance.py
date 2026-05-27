"""
tests/test_finance.py — 금융 시뮬레이터 (블록 6)
"""
import pytest


def test_acquisition_tax_under_6eok():
    """주택 6억 이하 취득세 1%."""
    from modules.finance.tax_calculator import calc_acquisition_tax
    r = calc_acquisition_tax(500_000_000, "아파트")
    assert r["rate"] == 0.01
    assert r["tax"] == 5_000_000


def test_acquisition_tax_commercial_and_multi_house():
    from modules.finance.tax_calculator import calc_acquisition_tax
    assert calc_acquisition_tax(500_000_000, "상가")["rate"] == 0.04
    # 조정지역 3주택 중과 12%
    multi = calc_acquisition_tax(500_000_000, "아파트", house_count=3, is_adjusted_area=True)
    assert multi["rate"] == 0.12


def test_transfer_tax_short_term_70pct():
    """1년 미만 양도세 70%."""
    from modules.finance.tax_calculator import calc_transfer_tax
    r = calc_transfer_tax(gain=100_000_000, holding_years=0.5, item_type="아파트")
    assert r["tax"] == 70_000_000
    assert "70%" in r["rate_type"]


def test_one_house_exemption():
    """1세대1주택(보유2년+거주2년) 12억 이하 비과세."""
    from modules.finance.tax_calculator import calc_transfer_tax
    r = calc_transfer_tax(gain=200_000_000, holding_years=3, item_type="아파트",
                          is_one_house=True, sale_price=900_000_000, residence_years=2)
    assert r["tax"] == 0
    assert r["rate_type"] == "비과세"


def test_progressive_tax_bracket():
    """누진세율: 과표 1억 -> 35% 구간."""
    from modules.finance.tax_calculator import progressive_income_tax
    # 1억 * 0.35 - 1544만 = 1956만
    assert progressive_income_tax(100_000_000) == 19_560_000
    assert progressive_income_tax(0) == 0


def test_ltv_dsr_max_loan():
    """LTV/DSR 한도 계산. 저소득은 DSR이 바인딩."""
    from modules.finance.loan_simulator import calc_max_loan
    # 소득 충분 -> LTV 바인딩
    r1 = calc_max_loan(500_000_000, annual_income=100_000_000,
                       annual_rate=0.04, years=30)
    assert r1["ltv_cap"] == 350_000_000
    assert r1["max_loan"] <= r1["ltv_cap"]
    # 소득 매우 낮음 -> DSR 바인딩(LTV보다 작음)
    r2 = calc_max_loan(500_000_000, annual_income=20_000_000,
                       annual_rate=0.04, years=30)
    assert r2["binding"] == "DSR"
    assert r2["max_loan"] < r2["ltv_cap"]


def test_roe_leverage_effect():
    """레버리지 사용 시 ROE가 무레버리지보다 높다."""
    from modules.finance.roe_calculator import calc_roe
    # 자기자본 1.5억, 총수익 5천만, 5년, 무레버리지 자본 5억
    r = calc_roe(equity=150_000_000, total_return=50_000_000, holding_years=5,
                 unleveraged_equity=500_000_000)
    assert r["roe"] == pytest.approx(33.33, abs=0.1)
    assert r["annualized_roe"] > 0
    assert r["leverage_effect"] > 0   # 레버리지 효과 양(+)
    assert r["payback_years"] is not None


def test_cashflow_positive_and_negative():
    from modules.finance.cashflow_simulator import simulate_cashflow
    # 임대료 > 상환액 -> 양의 현금흐름
    pos = simulate_cashflow(loan_principal=200_000_000, annual_rate=0.04, years=30,
                            monthly_rent=1_500_000, monthly_cost=100_000)
    assert pos["monthly_loan_payment"] > 0
    assert pos["monthly_net"] == pos["effective_monthly_rent"] - pos["monthly_loan_payment"] - 100_000
    assert pos["cumulative_net"] == pos["annual_net"] * 5
