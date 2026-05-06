"""
tests/test_smoke.py
핵심 모듈 기본 연기 테스트 — 임포트가 깨지지 않고 기본 동작이 성립하는지.
"""


def test_db_init_creates_tables():
    from core.database import get_connection, init_db
    init_db()
    conn = get_connection()
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()
    for t in [
        "items", "documents", "price_records", "price_analyses",
        "risk_flags", "risk_checklists", "agent_tasks",
        "recommendation_results", "user_preferences", "user_feedback",
        "daily_briefings", "action_items", "change_events",
        "confidence_scores", "outcome_simulations",
        "pipeline_runs", "stress_test_results", "item_snapshots",
    ]:
        assert t in tables, f"missing table {t}"


def test_unique_key_upsert_dedupes():
    from core.database import get_connection, upsert_item
    data = {
        "source": "auction", "case_no": "2025타경0001",
        "item_type": "아파트", "address_full": "서울특별시 강남구 역삼동 1",
        "appraisal_price": 50000, "min_bid_price": 35000, "fail_count": 1,
        "bid_date": "2025-12-01",
    }
    iid1 = upsert_item(data)
    data["min_bid_price"] = 30000
    iid2 = upsert_item(data)
    assert iid1 == iid2
    conn = get_connection()
    row = conn.execute("SELECT min_bid_price FROM items WHERE id=?", (iid1,)).fetchone()
    conn.close()
    assert row["min_bid_price"] == 30000


def test_alerts_fallback_to_mock(capsys):
    from modules.alerts.telegram import send_message
    ok = send_message("테스트 메시지")
    out = capsys.readouterr().out
    assert ok is True
    assert "테스트 메시지" in out
