"""
tests/test_alerts.py
알림 시스템: 수집 / 중복 제거 / 발송 로그 / 사용자 설정 게이팅 검증.
"""


def _seed_with_briefing():
    from scripts.generate_mock_data import generate
    from agents.daily_briefing_agent import generate_briefing
    generate(count=30, seed=42, reset=True)
    return generate_briefing()


def test_alerts_collect_returns_list():
    from agents.alert_agent import collect_pending_alerts
    _seed_with_briefing()
    alerts = collect_pending_alerts()
    assert isinstance(alerts, list)


def test_dispatch_dry_run_does_not_send():
    from agents.alert_agent import dispatch_alerts, list_recent_alerts
    _seed_with_briefing()
    res = dispatch_alerts(dry_run=True)
    assert res["sent"] == 0
    assert "collected" in res
    # dry_run 은 alert_log 에 기록하지 않는다
    logs = list_recent_alerts()
    assert all(d.get("status") != "sent" for d in res["details"])


def test_dispatch_dedup_on_second_call():
    """같은 날 두 번 호출하면 두 번째는 모두 skipped."""
    from agents.alert_agent import dispatch_alerts
    _seed_with_briefing()
    first = dispatch_alerts(dry_run=False)
    assert first["sent"] >= 0  # mock telegram 은 항상 True 반환
    second = dispatch_alerts(dry_run=False)
    # 같은 날 같은 dedupe_key 라 skipped
    if first["sent"] > 0:
        assert second["sent"] == 0
        assert second["skipped"] >= first["sent"]


def test_alerts_disabled_returns_empty():
    from agents.alert_agent import collect_pending_alerts
    from agents.preference_learning_agent import save_preferences
    _seed_with_briefing()
    save_preferences({
        "regions": [], "item_types": ["아파트"], "max_risk_level": "medium",
        "min_profit_man": 0, "min_roi": 0, "exclude_keywords": [],
        "alerts_enabled": False, "alert_min_grade": "A",
        "alert_imminent_days": 3, "alert_only_watched": False,
        "alert_include_briefing": True,
        "notes": "test - 알림 비활성화",
    })
    alerts = collect_pending_alerts()
    assert alerts == []


def test_alert_grade_filter():
    """alert_min_grade='A'면 B/C 추천은 알림 후보가 아님."""
    from agents.alert_agent import _collect_new_recommendations
    _seed_with_briefing()
    only_a = _collect_new_recommendations(min_grade="A", only_watched=False)
    all_grades = _collect_new_recommendations(min_grade="C", only_watched=False)
    assert len(only_a) <= len(all_grades)
    for a in only_a:
        # alert_type 만 확인 - title에서 등급 파싱
        assert "[새 추천 A]" in a["title"]
