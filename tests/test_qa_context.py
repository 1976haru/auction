"""
tests/test_qa_context.py
강화된 Q&A 컨텍스트 검증 - 트렌드/peer/입찰가/백테스트 통계 주입.
"""


def _seed():
    from scripts.generate_mock_data import generate
    from scripts.run_daily_pipeline import run_pipeline
    generate(count=20, seed=42, reset=True)
    run_pipeline(use_mock=True, count=20, top=5, reset=False,
                  query="시세차익 큰 물건 5개")


def test_qa_context_includes_new_keys():
    from agents.item_qa_agent import _build_context
    from core.database import get_connection
    _seed()
    conn = get_connection()
    iid = conn.execute("SELECT id FROM items LIMIT 1").fetchone()["id"]
    conn.close()
    ctx = _build_context(iid)
    for key in [
        "profit_estimate", "roi_estimate", "market_price", "bid_days_left",
        "trend", "peer_stats", "bid_recommendation", "recommendation",
        "backtest",
    ]:
        assert key in ctx, f"missing key {key}"


def test_peer_stats_returns_dict():
    from agents.item_qa_agent import _peer_stats
    from core.database import get_connection
    _seed()
    conn = get_connection()
    row = conn.execute("SELECT * FROM items LIMIT 1").fetchone()
    conn.close()
    item = dict(row)
    stats = _peer_stats(item)
    assert isinstance(stats, dict)
    assert "count" in stats


def test_trend_summary_handles_no_trades():
    from agents.item_qa_agent import _trend_summary
    # 가짜 id - trade 없을 가능성
    s = _trend_summary(99999)
    assert isinstance(s, dict)
    assert s.get("months") == 0


def test_ask_returns_context_summary_keys():
    from agents.item_qa_agent import ask
    from core.database import get_connection
    _seed()
    conn = get_connection()
    iid = conn.execute("SELECT id FROM items LIMIT 1").fetchone()["id"]
    conn.close()
    res = ask(iid, "이 물건 왜 추천됐어?")
    assert "answer" in res
    assert "context_summary" in res
    cs = res["context_summary"]
    for k in ("address", "grade", "score", "risk_score",
              "confidence", "trend_direction", "peer_count"):
        assert k in cs


def test_mock_qa_uses_enriched_context():
    """mock 응답에 트렌드/peer/입찰가 정보가 포함되어야."""
    from core.mock_api import mock_item_qa
    ctx = {
        "address_full": "서울특별시 강남구 역삼동 1",
        "risk_score": 5,
        "profit_estimate": 30000,
        "roi_estimate": 12.5,
        "trend": {"months": 6, "direction": "상승", "trend_pct": 5.3,
                   "first_avg": 100000, "last_avg": 105300, "trades": 8},
        "peer_stats": {"count": 5, "avg_appraisal": 80000,
                        "avg_min_bid": 56000, "avg_market": 85000,
                        "avg_fail_count": 1.0, "inflated_count": 0},
        "bid_recommendation": {
            "conservative": {"price": 60000, "profit": 25000, "roi": 30},
            "standard": {"price": 70000, "profit": 15000, "roi": 18},
            "aggressive": {"price": 75000, "profit": 8000, "roi": 9},
        },
        "recommendation": {"score": 80.0, "grade": "A"},
        "backtest": {"count": 8, "grade": "A", "mean_profit": 50000,
                      "win_rate": 100.0, "run_date": "2026-05-07"},
    }
    a1 = mock_item_qa("이 물건 왜 추천됐어?", ctx)
    assert "30,000" in a1 or "+30,000" in a1  # profit
    assert "상승" in a1  # trend
    assert "5건 평균" in a1  # peer

    a2 = mock_item_qa("얼마까지 써도 돼?", ctx)
    assert "60,000" in a2 and "70,000" in a2 and "75,000" in a2

    a3 = mock_item_qa("이 물건 위험해?", ctx)
    assert "severity 5" in a3
