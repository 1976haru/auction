"""
tests/test_watchlist.py
워치리스트 토글 / 일괄 처리 / 요약 통계.
"""


def _seed():
    from scripts.generate_mock_data import generate
    from scripts.run_daily_pipeline import run_pipeline
    generate(count=15, seed=42, reset=True)
    run_pipeline(use_mock=True, count=15, top=3, reset=False,
                  query="시세차익 큰 물건 3개")


def test_toggle_watch_persists():
    from agents.watchlist_agent import toggle_watch, list_watched_items
    from core.database import get_connection
    _seed()
    conn = get_connection()
    iid = conn.execute("SELECT id FROM items LIMIT 1").fetchone()["id"]
    conn.close()
    toggle_watch(iid, True)
    watched = list_watched_items()
    assert any(it["id"] == iid for it in watched)
    toggle_watch(iid, False)
    watched_after = list_watched_items()
    assert all(it["id"] != iid for it in watched_after)


def test_bulk_set_watch_affects_multiple():
    from agents.watchlist_agent import bulk_set_watch, list_watched_items
    from core.database import get_connection
    _seed()
    conn = get_connection()
    ids = [r["id"] for r in conn.execute("SELECT id FROM items LIMIT 5").fetchall()]
    conn.close()
    n = bulk_set_watch(ids, watched=True)
    assert n == 5
    watched = list_watched_items()
    watched_ids = {it["id"] for it in watched}
    assert set(ids).issubset(watched_ids)
    # 일괄 해제
    n2 = bulk_set_watch(ids, watched=False)
    assert n2 == 5
    watched_after = list_watched_items()
    after_ids = {it["id"] for it in watched_after}
    assert set(ids).isdisjoint(after_ids)


def test_watch_summary_counts():
    from agents.watchlist_agent import bulk_set_watch, watch_summary
    from core.database import get_connection
    _seed()
    conn = get_connection()
    ids = [r["id"] for r in conn.execute("SELECT id FROM items LIMIT 4").fetchall()]
    conn.close()
    bulk_set_watch(ids, watched=True)
    s = watch_summary()
    assert s["count"] == 4
    assert "by_grade" in s
    assert isinstance(s["total_profit_estimate"], (int, float))


def test_list_watched_items_includes_context():
    from agents.watchlist_agent import bulk_set_watch, list_watched_items
    from core.database import get_connection
    _seed()
    conn = get_connection()
    iid = conn.execute("SELECT id FROM items LIMIT 1").fetchone()["id"]
    conn.close()
    bulk_set_watch([iid], watched=True)
    watched = list_watched_items()
    assert len(watched) >= 1
    it = next(x for x in watched if x["id"] == iid)
    for key in ["score", "grade", "profit_estimate", "roi_estimate",
                "risk_level", "open_actions", "recent_changes_7d", "bid_days_left"]:
        assert key in it


def test_empty_watchlist_returns_zero_summary():
    from agents.watchlist_agent import watch_summary, list_watched_items
    _seed()
    # 시드 후 아무것도 관심 등록 안 함
    s = watch_summary()
    assert s["count"] == 0
    assert s["total_profit_estimate"] == 0
    assert list_watched_items() == []
