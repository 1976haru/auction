"""
tests/test_observability.py — 관측성/메트릭 (블록 16)
"""


def test_record_and_get_metrics():
    from core.observability import record_metric, get_metrics
    record_metric("api_call_count", 1, {"api": "kakao"})
    record_metric("api_call_count", 1, {"api": "molit"})
    rows = get_metrics("api_call_count", hours=24)
    assert len(rows) == 2
    assert rows[0]["name"] == "api_call_count"
    assert isinstance(rows[0]["tags"], dict)


def test_get_summary_aggregates():
    from core.observability import record_metric, get_summary
    record_metric("items_processed_count", 100)
    record_metric("items_processed_count", 200)
    s = get_summary(hours=24)
    assert "items_processed_count" in s
    agg = s["items_processed_count"]
    assert agg["count"] == 2
    assert agg["sum"] == 300
    assert agg["max"] == 200
    assert agg["last"] in (100, 200)


def test_track_metric_decorator():
    from core.observability import track_metric, get_metrics

    @track_metric("test.duration")
    def slow():
        return 42

    assert slow() == 42
    rows = get_metrics("test.duration", hours=24)
    assert len(rows) == 1
    assert rows[0]["value"] >= 0


def test_track_metric_records_on_exception():
    from core.observability import track_metric, get_metrics
    import pytest

    @track_metric("test.fail")
    def boom():
        raise ValueError("x")

    with pytest.raises(ValueError):
        boom()
    rows = get_metrics("test.fail", hours=24)
    assert len(rows) == 1
    assert rows[0]["tags"]["ok"] is False


def test_check_thresholds_api_error_rate():
    """API 오류율이 임계값 초과하면 알림 생성."""
    from core.observability import record_metric, check_thresholds
    for _ in range(10):
        record_metric("api_call_count", 1)
    for _ in range(3):
        record_metric("api_error_count", 1)
    alerts = check_thresholds()
    names = {a["name"] for a in alerts}
    assert "api_error_rate" in names
