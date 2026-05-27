"""
tests/test_alert_triggers.py — 알림 트리거 8종 (블록 14)
"""
from core.database import upsert_item, get_connection


def _seed_analyzed(n=15):
    from scripts.generate_mock_data import generate
    generate(count=n, seed=42, reset=True, analyze=True)


def test_all_8_triggers_registered():
    from agents.alert_agent import TRIGGERS
    expected = {"new_item_match", "price_drop", "deadline_approaching", "bid_result",
                "weekly_calendar", "monthly_report", "market_signal", "scenario_opportunity"}
    assert set(TRIGGERS.keys()) == expected


def test_check_triggers_fires_and_formats():
    _seed_analyzed()
    from agents.alert_agent import check_triggers
    alerts = check_triggers()
    assert len(alerts) >= 1
    for a in alerts:
        assert a["alert_type"] and a["title"] and "dedupe_key" in a
        assert isinstance(a["body"], str)
    types = {a["alert_type"] for a in alerts}
    # 분석 데이터가 있으면 신규추천/시나리오기회/월간/주간 중 일부는 발화
    assert types & {"new_item_match", "scenario_opportunity", "weekly_calendar", "monthly_report"}


def test_dedupe_prevents_resend():
    _seed_analyzed()
    from agents.alert_agent import run_triggers
    # 첫 발송(실발송 실패해도 alert_log 기록) -> 두번째는 skip 증가
    r1 = run_triggers(["weekly_calendar", "monthly_report"])
    r2 = run_triggers(["weekly_calendar", "monthly_report"])
    assert r2["skipped"] >= 1
    assert r2["sent"] == 0


def test_deadline_trigger_d3_watched():
    """관심 물건이 D-3이면 deadline_approaching 발화."""
    from datetime import date, timedelta
    from agents.alert_agent import check_triggers
    target = (date.today() + timedelta(days=3)).isoformat()
    iid = upsert_item({"source": "test", "case_no": "2024타경D3", "item_type": "아파트",
                       "address_full": "서울 마포구 망원동", "min_bid_price": 25000,
                       "bid_date": target})
    conn = get_connection()
    conn.execute("UPDATE items SET is_watched=1 WHERE id=?", (iid,))
    conn.commit()
    conn.close()
    alerts = check_triggers(["deadline_approaching"])
    assert any(a["item_id"] == iid and a["alert_type"] == "deadline_approaching"
               for a in alerts)


def test_send_trigger_backtest_report():
    from agents.alert_agent import send_trigger
    res = send_trigger("backtest_report",
                       {"accuracy": 0.82, "f1_score": 0.85, "avg_roe_recommended": 14.2},
                       dry_run=True)
    assert res["trigger"] == "backtest_report"
    assert res["failed"] == 0
