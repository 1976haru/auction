"""
tests/test_pricing_and_confidence.py
시세 매칭 + 수익 계산 + 신뢰도.
"""


def test_calc_profit_basic():
    from modules.profit_calculator import calc_profit
    r = calc_profit(80000, 60000, "아파트")
    assert r["market_price"] == 80000
    assert r["bid_price"] == 60000
    assert r["profit"] == r["market_price"] - r["invested"]


def test_recommend_bid_prices_ordering():
    from modules.profit_calculator import recommend_bid_prices
    bids = recommend_bid_prices(80000, "아파트", 10.0)
    assert bids["conservative"]["price"] < bids["aggressive"]["price"]


def test_price_matcher_returns_confidence():
    from core.database import upsert_item
    from modules.valuation.price_matcher import match_price, save_price_analysis, get_price_analysis
    iid = upsert_item({
        "source": "auction", "case_no": "2025타경5001",
        "item_type": "아파트", "address_full": "서울특별시 강남구 역삼동 1",
        "appraisal_price": 80000, "min_bid_price": 56000,
        "area_m2": 60.0, "bid_date": "2025-12-01",
    })
    item = {
        "id": iid,
        "address_full": "서울특별시 강남구 역삼동 1",
        "item_type": "아파트", "area_m2": 60.0,
        "appraisal_price": 80000, "min_bid_price": 56000,
    }
    res = match_price(item)
    assert "confidence" in res
    assert res["confidence"] in ("very_low", "low", "medium", "high")
    save_price_analysis(iid, res)
    pa = get_price_analysis(iid)
    assert pa is not None


def test_confidence_compute_full():
    from agents.confidence_agent import compute_confidence
    from core.database import upsert_item
    from modules.documents.mock_documents import generate_documents_for_item, save_documents
    from modules.risk.keyword_analyzer import analyze_keywords, save_risk_flags

    iid = upsert_item({
        "source": "auction", "case_no": "2025타경6001",
        "item_type": "아파트", "address_full": "서울특별시 마포구 망원동 1",
        "appraisal_price": 50000, "min_bid_price": 35000,
        "area_m2": 50.0, "bid_date": "2025-12-01",
    })
    docs = generate_documents_for_item(iid, {"address_full": "x", "appraisal_price": 1, "min_bid_price": 1}, seed=1)
    save_documents(iid, docs)
    save_risk_flags(iid, analyze_keywords("유치권 신고"))
    res = compute_confidence(iid)
    assert 0 <= res["overall_confidence"] <= 1.0
    for k in ("price_confidence", "legal_risk_confidence",
              "document_confidence", "address_match_confidence"):
        assert 0 <= res[k] <= 1.0
