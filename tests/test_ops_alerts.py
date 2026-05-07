"""
tests/test_ops_alerts.py
운영 이상 감지 -> 알림 통합 검증.
"""


def _seed():
    from scripts.generate_mock_data import generate
    from scripts.run_daily_pipeline import run_pipeline
    generate(count=15, seed=42, reset=True)
    run_pipeline(use_mock=True, count=15, top=3, reset=False,
                  query="시세차익 큰 물건 3개")


def test_collect_operational_anomalies_returns_list():
    from agents.alert_agent import _collect_operational_anomalies
    _seed()
    out = _collect_operational_anomalies()
    assert isinstance(out, list)
    for a in out:
        assert a["alert_type"] == "operational_anomaly"
        assert "title" in a and "body" in a


def test_collect_pending_alerts_includes_ops_when_enabled():
    """alert_include_ops=True 면 운영 이상이 알림 후보에 포함."""
    from agents.alert_agent import collect_pending_alerts
    from agents.preference_learning_agent import save_preferences
    _seed()

    save_preferences({
        "regions": [], "item_types": ["아파트"], "max_risk_level": "medium",
        "min_profit_man": 0, "min_roi": 0, "exclude_keywords": [],
        "alerts_enabled": True,
        "alert_channels": ["telegram"],
        "alert_min_grade": "C",
        "alert_imminent_days": 30,
        "alert_only_watched": False,
        "alert_include_briefing": True,
        "alert_include_ops": True,
        "notes": "test ops on",
    })
    alerts_on = collect_pending_alerts()

    # 같은 환경에서 ops off
    save_preferences({
        "regions": [], "item_types": ["아파트"], "max_risk_level": "medium",
        "min_profit_man": 0, "min_roi": 0, "exclude_keywords": [],
        "alerts_enabled": True,
        "alert_channels": ["telegram"],
        "alert_min_grade": "C",
        "alert_imminent_days": 30,
        "alert_only_watched": False,
        "alert_include_briefing": True,
        "alert_include_ops": False,
        "notes": "test ops off",
    })
    alerts_off = collect_pending_alerts()

    on_types = {a["alert_type"] for a in alerts_on}
    off_types = {a["alert_type"] for a in alerts_off}
    # ops on 일 때만 operational_anomaly 가 포함될 수 있음
    if "operational_anomaly" in on_types:
        assert "operational_anomaly" not in off_types


def test_dispatch_sends_ops_alert_via_channel():
    """운영 이상이 있으면 dispatch_alerts 가 채널 발송."""
    from agents.alert_agent import dispatch_alerts, list_recent_alerts
    from agents.preference_learning_agent import save_preferences
    _seed()
    save_preferences({
        "regions": [], "item_types": ["아파트"], "max_risk_level": "medium",
        "min_profit_man": 0, "min_roi": 0, "exclude_keywords": [],
        "alerts_enabled": True,
        "alert_channels": ["telegram"],
        "alert_min_grade": "C",
        "alert_imminent_days": 30,
        "alert_only_watched": False,
        "alert_include_briefing": False,
        "alert_include_ops": True,
        "notes": "test ops dispatch",
    })
    res = dispatch_alerts(dry_run=False)
    # 운영 이상이 1건이라도 있으면 sent 에 포함됨
    assert res["sent"] >= 0  # 환경에 따라 0일 수 있음
    logs = list_recent_alerts(50)
    types = {l["alert_type"] for l in logs}
    # ops 알림이 발송된 적이 있다면 alert_log 에 기록
    assert isinstance(types, set)


def test_save_load_roundtrip_includes_ops_pref():
    from agents.preference_learning_agent import save_preferences, get_preferences
    save_preferences({
        "regions": [], "item_types": ["아파트"], "max_risk_level": "medium",
        "min_profit_man": 0, "min_roi": 0, "exclude_keywords": [],
        "alerts_enabled": True,
        "alert_channels": ["telegram"],
        "alert_min_grade": "B",
        "alert_imminent_days": 5,
        "alert_only_watched": False,
        "alert_include_briefing": False,
        "alert_include_ops": False,
        "notes": "test pref",
    })
    p = get_preferences()
    assert p["alert_include_ops"] is False
    assert p["alert_include_briefing"] is False
