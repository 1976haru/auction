"""
tests/test_qa_cache.py
Q&A 캐싱: 저장/조회/TTL/무효화/통계.
"""
import time


def _seed():
    from scripts.generate_mock_data import generate
    from scripts.run_daily_pipeline import run_pipeline
    generate(count=15, seed=42, reset=True)
    run_pipeline(use_mock=True, count=15, top=3, reset=False,
                  query="시세차익 큰 물건 3개")


def test_normalize_question_unifies_punctuation():
    from agents.item_qa_agent import _normalize_question
    a = _normalize_question("이 물건 왜 추천?")
    b = _normalize_question("이 물건  왜  추천???")
    c = _normalize_question("이 물건 왜 추천!?")
    assert a == b == c


def test_context_signature_changes_when_grade_changes():
    from agents.item_qa_agent import _context_signature
    base = {"appraisal_price": 50000, "min_bid_price": 30000,
            "recommendation": {"grade": "A"}, "risk_score": 5,
            "confidence": {"overall_confidence": 0.8},
            "documents": [], "bid_date": "2026-12-01"}
    s_a = _context_signature(base)
    base2 = dict(base)
    base2["recommendation"] = {"grade": "B"}
    s_b = _context_signature(base2)
    assert s_a != s_b


def test_ask_first_call_not_cached_second_cached():
    from agents.item_qa_agent import ask
    from core.database import get_connection
    _seed()
    conn = get_connection()
    iid = conn.execute("SELECT id FROM items LIMIT 1").fetchone()["id"]
    conn.close()
    a1 = ask(iid, "이 물건 위험해?")
    assert a1["cached"] is False
    a2 = ask(iid, "이 물건 위험해?")
    assert a2["cached"] is True
    assert a2["answer"] == a1["answer"]


def test_ask_with_use_cache_false_bypasses():
    from agents.item_qa_agent import ask
    from core.database import get_connection
    _seed()
    conn = get_connection()
    iid = conn.execute("SELECT id FROM items LIMIT 1").fetchone()["id"]
    conn.close()
    ask(iid, "이 물건 위험해?")  # 캐시 적재
    a = ask(iid, "이 물건 위험해?", use_cache=False)
    assert a["cached"] is False  # 캐시 무시


def test_clear_cache_specific_item():
    from agents.item_qa_agent import ask, clear_cache, cache_stats
    from core.database import get_connection
    _seed()
    conn = get_connection()
    ids = [r["id"] for r in conn.execute("SELECT id FROM items LIMIT 3").fetchall()]
    conn.close()
    for iid in ids:
        ask(iid, "이 물건 위험해?")
    s_before = cache_stats()
    assert s_before["entries"] >= 3

    n = clear_cache(item_id=ids[0])
    assert n >= 1
    s_after = cache_stats()
    assert s_after["entries"] == s_before["entries"] - n


def test_clear_cache_full():
    from agents.item_qa_agent import ask, clear_cache, cache_stats
    from core.database import get_connection
    _seed()
    conn = get_connection()
    iid = conn.execute("SELECT id FROM items LIMIT 1").fetchone()["id"]
    conn.close()
    ask(iid, "왜 추천?")
    ask(iid, "위험?")
    assert cache_stats()["entries"] >= 2
    n = clear_cache()
    assert n >= 2
    assert cache_stats()["entries"] == 0


def test_ttl_expiration_returns_none():
    """TTL=0 시간이면 즉시 만료 처리."""
    from agents.item_qa_agent import ask
    from core.database import get_connection
    _seed()
    conn = get_connection()
    iid = conn.execute("SELECT id FROM items LIMIT 1").fetchone()["id"]
    conn.close()
    ask(iid, "왜 추천?")  # 적재
    a = ask(iid, "왜 추천?", ttl_hours=0)
    # TTL 0 이면 만료 -> 새로 호출 -> cached=False
    assert a["cached"] is False
