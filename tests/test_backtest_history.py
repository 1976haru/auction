"""
tests/test_backtest_history.py
백테스트 시계열 추적: save_backtest_run / list_backtest_runs / history_chart_series.
"""


def _seed():
    from scripts.generate_mock_data import generate
    from scripts.run_daily_pipeline import run_pipeline
    generate(count=20, seed=42, reset=True)
    run_pipeline(use_mock=True, count=20, top=5, reset=False,
                  query="시세차익 큰 물건 5개")


def test_save_backtest_run_persists_row():
    from agents.backtest_agent import (
        backtest_all_items,
        grade_ordering_check,
        list_backtest_runs,
        save_backtest_run,
    )
    _seed()
    report = backtest_all_items()
    ordering = grade_ordering_check(report)
    rid = save_backtest_run(report, ordering)
    assert rid > 0
    runs = list_backtest_runs(limit=5)
    assert len(runs) >= 1
    latest = runs[0]
    assert latest["scenario"] == "standard"
    assert latest["mode"] == "all_items"
    assert latest["total_pairs"] >= 0
    assert latest["report_json"]


def test_list_backtest_runs_filters_by_scenario():
    from agents.backtest_agent import (
        backtest_all_items, save_backtest_run,
        list_backtest_runs, grade_ordering_check,
    )
    _seed()
    for sc in ["standard", "aggressive"]:
        r = backtest_all_items(scenario=sc)
        save_backtest_run(r, grade_ordering_check(r))
    only_std = list_backtest_runs(scenario="standard")
    only_agg = list_backtest_runs(scenario="aggressive")
    assert all(r["scenario"] == "standard" for r in only_std)
    assert all(r["scenario"] == "aggressive" for r in only_agg)


def test_history_chart_series_returns_oldest_first():
    from agents.backtest_agent import (
        backtest_all_items, save_backtest_run,
        history_chart_series, grade_ordering_check,
    )
    _seed()
    for _ in range(3):
        r = backtest_all_items()
        save_backtest_run(r, grade_ordering_check(r))
    history = history_chart_series(limit=10)
    assert len(history) >= 3
    # 시간순 (오래된 순)
    dates = [h["run_date"] for h in history]
    assert dates == sorted(dates)
    for h in history:
        assert "overall_mean_profit" in h
        assert "monotonic" in h


def test_backtest_timeline_chart_returns_figure():
    from dashboard.charts import backtest_timeline, backtest_winrate_timeline
    import plotly.graph_objects as go
    history = [
        {"run_date": "2026-05-01 10:00:00", "total_pairs": 50,
         "overall_win_rate": 70, "overall_mean_profit": 30000,
         "a_mean": 80000, "b_mean": 60000, "c_mean": 30000,
         "d_mean": 5000, "x_mean": -10000, "monotonic": True},
        {"run_date": "2026-05-02 10:00:00", "total_pairs": 60,
         "overall_win_rate": 75, "overall_mean_profit": 35000,
         "a_mean": 85000, "b_mean": 65000, "c_mean": 35000,
         "d_mean": 7000, "x_mean": -8000, "monotonic": True},
    ]
    f1 = backtest_timeline(history)
    f2 = backtest_winrate_timeline(history)
    assert isinstance(f1, go.Figure)
    assert isinstance(f2, go.Figure)
    # backtest_timeline: A B C D X 평균 (5) + 전체 평균 (1) + monotonic OK 마커 (1) = 7
    assert len(f1.data) >= 6


def test_history_chart_empty_returns_placeholder():
    from dashboard.charts import backtest_timeline
    import plotly.graph_objects as go
    fig = backtest_timeline([])
    assert isinstance(fig, go.Figure)
