"""
tests/test_filters_inflation.py
감정가 거품 필터 / 사용자 선호 강제 / 등급 X 자동 부여 검증.
"""


def _seed_with_inflated_item(monkeypatch=None):
    """정상 매물 1건 + 감정가 거품 매물 1건을 직접 삽입.
    mock_molit 의 fetch_trades 를 결정론적으로 패치해서 시세 35,000만원 보장."""
    from core.database import upsert_item
    from agents.price_analysis_agent import analyze_item_price
    from agents.legal_risk_agent import analyze_item_risk
    from agents.confidence_agent import compute_confidence
    from modules.valuation import price_matcher

    def stub_fetch_trades(address, item_type, area_m2=0, seed=None):
        if "역삼" in (address or ""):
            base = 113000
        else:
            base = 35000
        return [{
            "complex_name": "test",
            "area_m2": area_m2 or 60.0,
            "trade_price": base + i * 100,
            "trade_date": "2026-04-01",
            "address_dong": "test",
            "source": "test_stub",
        } for i in range(8)]

    if monkeypatch is not None:
        monkeypatch.setattr(price_matcher, "fetch_trades", stub_fetch_trades)

    normal_id = upsert_item({
        "source": "auction", "case_no": "2025타경0001", "item_type": "아파트",
        "address_full": "서울특별시 강남구 역삼동 1", "address_si": "서울특별시",
        "address_gu": "강남구", "address_dong": "역삼동",
        "appraisal_price": 80000, "min_bid_price": 56000,
        "area_m2": 60.0, "bid_date": "2026-12-01",
    })

    inflated_id = upsert_item({
        "source": "public_sale", "mgmt_no": "PS-INFL-1", "item_type": "오피스텔",
        "address_full": "서울특별시 영등포구 여의도동 449",
        "address_si": "서울특별시", "address_gu": "영등포구", "address_dong": "여의도동",
        "appraisal_price": 150000, "min_bid_price": 138000,
        "area_m2": 60.0, "bid_date": "2026-12-01",
    })

    for iid in (normal_id, inflated_id):
        analyze_item_price(iid)
        analyze_item_risk(iid)
        compute_confidence(iid)
    return normal_id, inflated_id


def test_inflation_warning_set_on_overpriced_item(monkeypatch):
    from modules.valuation.price_matcher import get_price_analysis
    _, inflated_id = _seed_with_inflated_item(monkeypatch)
    pa = get_price_analysis(inflated_id)
    assert pa is not None
    assert pa["appraisal_to_market_ratio"] > 1.5
    assert pa["appraisal_inflated"] == 1


def test_recommendation_excludes_inflated_item(monkeypatch):
    """감정가 거품 매물은 후보에서 자동 제외되어야 한다."""
    from agents.recommendation_agent import recommend
    normal_id, inflated_id = _seed_with_inflated_item(monkeypatch)

    res = recommend("시세차익 큰 물건 5개")
    returned_ids = {r["item"]["id"] for r in res["results"]}
    assert inflated_id not in returned_ids, "거품 매물이 추천 후보에 포함됨"


def test_high_min_profit_pref_filters_results(monkeypatch):
    """선호의 min_profit_man 가 임계값을 넘는 매물만 후보로 남긴다."""
    from agents.preference_learning_agent import save_preferences
    from agents.recommendation_agent import recommend
    _seed_with_inflated_item(monkeypatch)

    save_preferences({
        "regions": [], "item_types": ["아파트", "오피스텔"],
        "max_risk_level": "medium",
        "min_profit_man": 10**9,
        "min_roi": 0,
        "exclude_keywords": [],
        "notes": "test - 임계값 매우 높음",
    })

    res = recommend("시세차익 큰 물건 5개")
    assert res["total_found"] == 0


def test_briefing_separates_grades():
    """브리핑 결과가 top_picks(A/B/C) + warning_picks(D/X) 로 분리되어야 한다."""
    from agents.daily_briefing_agent import generate_briefing
    from scripts.generate_mock_data import generate
    generate(count=30, seed=42, reset=True)
    b = generate_briefing()
    assert "top_picks" in b
    assert "warning_picks" in b
    for r in b["top_picks"]:
        assert r["grade"] in ("A", "B", "C")
    for r in b["warning_picks"]:
        assert r["grade"] in ("D", "X")
