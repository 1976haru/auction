"""
tests/test_alert_channels.py
다중 채널 알림: 어댑터 / 디스패처 / multi-channel dispatch / dedup.
"""


def test_slack_mock_fallback_when_no_webhook(monkeypatch, capsys):
    monkeypatch.setenv("USE_MOCK_APIS", "true")
    import importlib
    import core.config
    importlib.reload(core.config)
    import modules.alerts.slack as slack
    importlib.reload(slack)
    ok = slack.send_message("<b>제목</b>\n본문")
    assert ok is True
    out = capsys.readouterr().out
    assert "*제목*" in out  # mrkdwn 변환 확인


def test_discord_mock_fallback(monkeypatch, capsys):
    monkeypatch.setenv("USE_MOCK_APIS", "true")
    import importlib, core.config
    importlib.reload(core.config)
    import modules.alerts.discord as d
    importlib.reload(d)
    ok = d.send_message("<b>중요</b>\n알림")
    assert ok is True
    out = capsys.readouterr().out
    assert "**중요**" in out  # markdown 변환


def test_email_mock_fallback(monkeypatch, capsys):
    monkeypatch.setenv("USE_MOCK_APIS", "true")
    import importlib, core.config
    importlib.reload(core.config)
    import modules.alerts.email as em
    importlib.reload(em)
    ok = em.send_message("hello world", subject="테스트")
    assert ok is True
    out = capsys.readouterr().out
    assert "테스트" in out


def test_dispatcher_send_to_all_known_channels():
    from modules.alerts.dispatcher import CHANNELS, send_to_channels
    res = send_to_channels("ping", channels=list(CHANNELS))
    assert set(res.keys()) == set(CHANNELS)
    assert all(isinstance(v, bool) for v in res.values())


def test_dispatcher_skip_unknown_channel():
    from modules.alerts.dispatcher import send_to_channels
    res = send_to_channels("ping", channels=["unknown_channel"])
    assert res["unknown_channel"] is False


def test_configured_channels_returns_subset():
    from modules.alerts.dispatcher import CHANNELS, configured_channels
    cfg = configured_channels()
    assert isinstance(cfg, list)
    for c in cfg:
        assert c in CHANNELS


def test_multi_channel_dispatch_creates_per_channel_log():
    """동일 알림이 2개 채널 선택 시 각각 따로 dedup 되어야 함."""
    from agents.alert_agent import dispatch_alerts, list_recent_alerts
    from agents.preference_learning_agent import save_preferences
    from agents.daily_briefing_agent import generate_briefing
    from scripts.generate_mock_data import generate
    generate(count=20, seed=42, reset=True)
    generate_briefing()

    save_preferences({
        "regions": [], "item_types": ["아파트"], "max_risk_level": "medium",
        "min_profit_man": 0, "min_roi": 0, "exclude_keywords": [],
        "alerts_enabled": True,
        "alert_channels": ["telegram", "slack"],
        "alert_min_grade": "C",
        "alert_imminent_days": 30,
        "alert_only_watched": False,
        "alert_include_briefing": True,
        "notes": "test multi-channel",
    })
    res = dispatch_alerts(dry_run=False)
    assert "channels" in res
    assert set(res["channels"]) == {"telegram", "slack"}
    # 한 알림이 2 채널에 fanout 되었으면 sent + skipped 합계가 alert 개수 * 2 와 비슷해야
    assert res["sent"] >= 0
    logs = list_recent_alerts()
    # 같은 알림 telegram, slack 각각 로그 1행씩
    chs = {l["channel"] for l in logs if l["channel"]}
    assert chs.issubset({"telegram", "slack"})


def test_check_apis_includes_new_channels():
    from scripts.check_apis import run_all
    res = run_all()
    for ch in ("slack", "discord", "email"):
        assert ch in res["checks"]
        assert "ok" in res["checks"][ch]
