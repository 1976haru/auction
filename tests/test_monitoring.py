"""
tests/test_monitoring.py
운영 모니터링 에이전트 + 차트 헬퍼.
"""


def _seed():
    from scripts.generate_mock_data import generate
    from scripts.run_daily_pipeline import run_pipeline
    generate(count=20, seed=42, reset=True)
    run_pipeline(use_mock=True, count=20, top=3, reset=False,
                  query="시세차익 큰 물건 3개")


def test_db_health_returns_table_counts():
    from agents.monitoring_agent import db_health
    _seed()
    h = db_health()
    assert "tables" in h
    assert h["tables"].get("items", 0) >= 1
    assert h["table_count"] > 0
    assert h["db_size_bytes"] >= 0


def test_pipeline_history_after_run():
    from agents.monitoring_agent import get_pipeline_history
    _seed()
    runs = get_pipeline_history(10)
    assert len(runs) >= 1
    assert "elapsed_sec" in runs[0]


def test_alert_summary_returns_breakdowns():
    from agents.alert_agent import dispatch_alerts
    from agents.monitoring_agent import alert_summary
    _seed()
    dispatch_alerts(dry_run=False)
    s = alert_summary()
    assert "by_channel" in s
    assert "by_status" in s
    assert "by_type" in s
    assert s["total"] >= 0


def test_detect_anomalies_returns_list():
    from agents.monitoring_agent import detect_anomalies
    _seed()
    issues = detect_anomalies()
    assert isinstance(issues, list)
    for it in issues:
        assert "severity" in it
        assert "message" in it


def test_pipeline_timeline_series_oldest_first():
    from agents.monitoring_agent import pipeline_timeline_series
    _seed()
    series = pipeline_timeline_series(10)
    assert isinstance(series, list)
    if len(series) >= 2:
        a, b = series[0]["created_at"], series[-1]["created_at"]
        assert a <= b


def test_alert_timeline_series_groups_by_day():
    from agents.alert_agent import dispatch_alerts
    from agents.monitoring_agent import alert_timeline_series
    _seed()
    dispatch_alerts(dry_run=False)
    series = alert_timeline_series(50)
    assert isinstance(series, list)
    for s in series:
        assert "day" in s
        assert "sent" in s
        assert "failed" in s


def test_charts_return_figure_objects():
    from dashboard.charts import (
        alert_timeline_chart,
        channel_distribution_pie,
        pipeline_timeline_chart,
    )
    import plotly.graph_objects as go

    f1 = pipeline_timeline_chart([
        {"created_at": "2026-05-07 10:00:00", "elapsed_sec": 5.0,
         "total_items": 100, "status": "ok"},
        {"created_at": "2026-05-07 11:00:00", "elapsed_sec": 6.0,
         "total_items": 100, "status": "ok"},
    ])
    f2 = alert_timeline_chart([
        {"day": "2026-05-06", "sent": 5, "failed": 0},
        {"day": "2026-05-07", "sent": 8, "failed": 1},
    ])
    f3 = channel_distribution_pie({"telegram": 10, "slack": 5})
    assert isinstance(f1, go.Figure)
    assert isinstance(f2, go.Figure)
    assert isinstance(f3, go.Figure)
