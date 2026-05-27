"""
tests/test_scenarios.py — 시나리오 시뮬레이터 (블록 7, 핵심)
"""
from core.database import upsert_item


def _make_item(item_type="아파트", min_bid=28000, appraisal=40000, area=84.0, gu="마포구"):
    return upsert_item({
        "source": "test", "case_no": f"2024타경{abs(hash((item_type, min_bid))) % 99999}",
        "item_type": item_type, "address_full": f"서울특별시 {gu} 망원동",
        "address_si": "서울특별시", "address_gu": gu, "area_m2": area,
        "min_bid_price": min_bid, "appraisal_price": appraisal, "fail_count": 1,
    })


def test_each_scenario_required_keys_and_ranges():
    from modules.scenarios import simulate_short_sale, simulate_rental, simulate_residence
    item_id = _make_item()
    bid = 300_000_000  # 3억원
    for fn in (simulate_short_sale, simulate_rental, simulate_residence):
        r = fn(item_id, bid)
        for k in ("scenario", "net_return", "roe", "annualized_roe", "score",
                  "capital_needed", "affordable"):
            assert k in r, (fn.__name__, k)
        assert 0 <= r["score"] <= 100
        assert -100 <= r["annualized_roe"] <= 1000


def test_short_sale_short_term_tax():
    """단타는 6개월 보유 -> 단기 양도세(70%) 적용."""
    from modules.scenarios import simulate_short_sale
    item_id = _make_item()
    r = simulate_short_sale(item_id, 300_000_000)
    assert r["holding_months"] == 6
    assert any("70%" in n or "단기" in n for n in r["notes"])


def test_residence_tax_exemption():
    """실거주 3년 + 12억 이하 -> 비과세, 양도세 0."""
    from modules.scenarios import simulate_residence
    item_id = _make_item(min_bid=28000, appraisal=40000)  # 4억대
    r = simulate_residence(item_id, 300_000_000)
    assert r["costs"]["transfer_tax"] == 0
    assert r["holding_months"] == 36
    assert r["living_value"] > 0


def test_rental_has_yield_and_long_term():
    from modules.scenarios import simulate_rental
    item_id = _make_item()
    r = simulate_rental(item_id, 300_000_000)
    assert r["holding_months"] == 60
    assert r["rental_yield"] > 0
    assert "monthly_rent" in r


def test_compare_scenarios_persists_and_picks_best():
    from modules.scenarios import compare_scenarios
    from core.database import get_connection
    item_id = _make_item()
    result = compare_scenarios(item_id)
    assert set(result["scenarios"].keys()) == {"short_sale", "rental", "residence"}
    assert result["best_scenario"] in result["scenarios"]
    # best는 (자본가능 풀 내) 최고 점수
    best_score = result["scenarios"][result["best_scenario"]]["score"]
    assert best_score == max(v["score"] for v in result["scenarios"].values()
                             if v["affordable"]) or all(
        not v["affordable"] for v in result["scenarios"].values())

    conn = get_connection()
    rows = conn.execute("SELECT scenario, is_recommended FROM scenario_results WHERE item_id=?",
                        (item_id,)).fetchall()
    conn.close()
    assert len(rows) == 3
    assert sum(r["is_recommended"] for r in rows) == 1


def test_weights_affect_weighted_score():
    """가중치에 따라 weighted_score가 달라진다."""
    from modules.scenarios import compare_scenarios
    item_id = _make_item()
    r_short = compare_scenarios(item_id, {"scenario_weights":
                                          {"short_sale": 1.0, "rental": 0.0, "residence": 0.0}})
    r_rental = compare_scenarios(item_id, {"scenario_weights":
                                           {"short_sale": 0.0, "rental": 1.0, "residence": 0.0}})
    assert r_short["weighted_score"] == r_short["scenarios"]["short_sale"]["score"]
    assert r_rental["weighted_score"] == r_rental["scenarios"]["rental"]["score"]
    assert "bid_range" in r_short["recommendation"]
