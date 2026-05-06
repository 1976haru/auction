"""
tests/test_recommendation.py
추천 에이전트 + 사용자 선호 학습 + 입찰가 시뮬레이션.
"""


def _seed(count=20):
    from scripts.generate_mock_data import generate
    generate(count=count, seed=42, reset=True)


def test_recommend_returns_results():
    _seed(30)
    from agents.recommendation_agent import recommend
    res = recommend("시세차익 큰 물건 5개", n=5)
    assert "results" in res
    assert isinstance(res["results"], list)
    assert res["total_found"] >= 0
    if res["results"]:
        r = res["results"][0]
        assert "grade" in r and r["grade"] in ("A", "B", "C", "D", "X")
        assert "score" in r
        assert "score_breakdown" in r


def test_preference_learning_default():
    from agents.preference_learning_agent import (
        get_preferences, learn_preferences, save_preferences,
    )
    save_preferences({
        "regions": [], "item_types": ["아파트"], "max_risk_level": "medium",
        "min_profit_man": 3000, "min_roi": 0.05, "exclude_keywords": [],
        "notes": "test",
    })
    pref = get_preferences()
    assert pref["item_types"] == ["아파트"]
    learn_preferences()  # 데이터 없으면 default 저장
    pref2 = get_preferences()
    assert "item_types" in pref2


def test_bidding_agent_returns_three_levels():
    _seed(10)
    from agents.bidding_agent import get_bid_recommendation
    from agents.price_analysis_agent import analyze_item_price
    from core.database import get_connection
    conn = get_connection()
    iid = conn.execute("SELECT id FROM items LIMIT 1").fetchone()["id"]
    conn.close()
    analyze_item_price(iid)
    rec = get_bid_recommendation(iid)
    assert "bids" in rec
    for k in ("conservative", "standard", "aggressive"):
        assert k in rec["bids"]
        assert "profit" in rec["bids"][k]
