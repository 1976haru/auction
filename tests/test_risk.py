"""
tests/test_risk.py — 리스크 + 몬테카를로 (블록 8)
"""
from core.database import upsert_item


def _make_item():
    return upsert_item({
        "source": "test", "case_no": "2024타경8888", "item_type": "아파트",
        "address_full": "서울특별시 마포구 망원동", "address_si": "서울특별시",
        "address_gu": "마포구", "area_m2": 84.0,
        "min_bid_price": 28000, "appraisal_price": 40000, "fail_count": 1,
    })


def test_scenario_risk_cases_and_ordering():
    from modules.risk.scenario_risk import analyze_scenario_risk
    item_id = _make_item()
    r = analyze_scenario_risk(item_id, 300_000_000)
    assert set(r["cases"].keys()) == {"best", "base", "worst"}
    # 확률 합 = 1
    assert abs(sum(c["probability"] for c in r["cases"].values()) - 1.0) < 1e-9
    # best ROE >= base >= worst
    assert r["cases"]["best"]["roe"] >= r["cases"]["base"]["roe"] >= r["cases"]["worst"]["roe"]
    assert isinstance(r["mean_roe"], float)
    assert r["worst_case_loss"] >= 0


def test_monte_carlo_loss_probability_range():
    from modules.risk.monte_carlo import run_monte_carlo
    item_id = _make_item()
    r = run_monte_carlo(item_id, 300_000_000, n=2000)
    assert 0.0 <= r["loss_probability"] <= 1.0
    assert r["percentiles"]["p10"] <= r["percentiles"]["p50"] <= r["percentiles"]["p90"]
    assert len(r["histogram"]["counts"]) == 20
    assert sum(r["histogram"]["counts"]) == 2000


def test_monte_carlo_deterministic_seed():
    """동일 시드 -> 동일 결과."""
    from modules.risk.monte_carlo import run_monte_carlo
    item_id = _make_item()
    a = run_monte_carlo(item_id, 300_000_000, n=1000, seed=7)
    b = run_monte_carlo(item_id, 300_000_000, n=1000, seed=7)
    assert a["mean_roe"] == b["mean_roe"]
    assert a["percentiles"] == b["percentiles"]


def test_monte_carlo_persists_to_items():
    from modules.risk.monte_carlo import run_monte_carlo
    from core.database import get_connection
    item_id = _make_item()
    r = run_monte_carlo(item_id, 300_000_000, n=1000)
    conn = get_connection()
    row = conn.execute(
        "SELECT expected_roe, loss_probability, worst_case_loss FROM items WHERE id=?",
        (item_id,)
    ).fetchone()
    conn.close()
    assert row["expected_roe"] == r["mean_roe"]
    assert row["loss_probability"] == r["loss_probability"]
    assert row["worst_case_loss"] == r["worst_case_loss"]
