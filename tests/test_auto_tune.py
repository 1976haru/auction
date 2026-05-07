"""
tests/test_auto_tune.py
가중치 자동 튜닝: parameterization / quality / grid search / 활성화.
"""


def _seed():
    from scripts.generate_mock_data import generate
    from scripts.run_daily_pipeline import run_pipeline
    generate(count=30, seed=42, reset=True)
    run_pipeline(use_mock=True, count=30, top=5, reset=False,
                  query="시세차익 큰 물건 5개")


def test_score_item_accepts_weights_override():
    """_score_item 이 weights override 를 받으면 다르게 동작."""
    from agents.recommendation_agent import _score_item, WEIGHTS_DEFAULT
    item = {
        "id": 1, "_risk_level": "low",
        "min_bid_price": 50000, "bid_date": "2026-12-01",
        "is_watched": 0, "_price": {"appraisal_inflated": False},
    }
    profit_info = {"profit": 30000, "roi": 15.0, "market_price": 100000}
    conf = {"price_confidence": 0.9, "overall_confidence": 0.8}
    pref = {"regions": [], "item_types": [], "max_risk_level": "medium",
            "min_profit_man": 0, "min_roi": 0, "exclude_keywords": []}

    a = _score_item(item, profit_info, conf, pref)
    b = _score_item(item, profit_info, conf, pref,
                     weights={**WEIGHTS_DEFAULT, "profit_max": 100,
                              "profit_divisor": 1000})
    # b 의 profit_pts 가 더 커야 함
    assert b["score"] > a["score"]


def test_load_active_weights_returns_default_initially():
    from agents.recommendation_agent import _load_active_weights, WEIGHTS_DEFAULT
    w = _load_active_weights()
    for k in WEIGHTS_DEFAULT:
        assert k in w


def test_quality_score_rewards_monotonic():
    from agents.auto_tune_agent import quality_score
    monotonic_report = {
        "grades": {
            "A": {"count": 5, "win_rate": 100,
                   "actual_profit": {"mean": 100000}},
            "B": {"count": 10, "win_rate": 100,
                   "actual_profit": {"mean": 70000}},
            "X": {"count": 5, "win_rate": 0,
                   "actual_profit": {"mean": -10000}},
        },
    }
    monotonic_ord = {
        "monotonic_decreasing": True,
        "grade_means": {"A": 100000, "B": 70000, "X": -10000},
    }
    not_mono_ord = {
        "monotonic_decreasing": False,
        "grade_means": {"A": 70000, "B": 100000, "X": -10000},
    }
    q_mono = quality_score(monotonic_report, monotonic_ord)
    q_no = quality_score(monotonic_report, not_mono_ord)
    assert q_mono > q_no
    assert q_mono >= 100  # monotonic bonus


def test_grid_search_returns_sorted_results():
    from agents.auto_tune_agent import grid_search
    _seed()
    # 작은 그리드로 빠르게
    small = {
        "profit_max": [40, 45],
        "profit_divisor": [2000],
        "grade_a_cutoff": [70, 75],
    }
    results = grid_search(grid=small, max_combos=4)
    assert len(results) >= 1
    qualities = [r["quality"] for r in results]
    assert qualities == sorted(qualities, reverse=True)


def test_save_and_activate_weights():
    from agents.auto_tune_agent import (
        save_tuned_weights,
        list_tuned_weights,
        activate_weights,
        get_active_weights,
    )
    _seed()
    rid = save_tuned_weights({"profit_max": 50, "profit_divisor": 1500},
                              quality=42.0, notes="test", activate=True)
    rows = list_tuned_weights()
    assert any(r["id"] == rid for r in rows)
    active = next(r for r in rows if r["id"] == rid)
    assert active["is_active"] == 1
    # get_active_weights 가 적용된 가중치 반환
    aw = get_active_weights()
    assert aw["profit_max"] == 50
    assert aw["profit_divisor"] == 1500


def test_evaluate_all_items_with_weights():
    """weights 인자가 evaluate_all_items 에 전달되어 점수가 변함."""
    from agents.backtest_agent import evaluate_all_items
    from agents.recommendation_agent import WEIGHTS_DEFAULT
    _seed()
    base = evaluate_all_items()
    boosted = evaluate_all_items(weights={**WEIGHTS_DEFAULT,
                                              "profit_max": 100})
    assert len(base) == len(boosted)
    # 동일 item 의 score 가 다를 수 있음 (profit > 0 이면 boosted 가 큼)
    base_by_id = {e["item_id"]: e["score"] for e in base}
    for e in boosted:
        if e.get("profit_estimate", 0) > 0:
            assert e["score"] >= base_by_id[e["item_id"]]
