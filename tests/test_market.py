"""
tests/test_market.py — 시장 분석 엔진 (블록 5)
"""
from core.database import upsert_item


def _make_item(gu="마포구", item_type="아파트", area=84.0, min_bid=30000, appraisal=40000, fail=0):
    return upsert_item({
        "source": "test", "case_no": f"2024타경{abs(hash((gu, area, min_bid))) % 99999}",
        "item_type": item_type, "address_full": f"서울특별시 {gu} 망원동",
        "address_si": "서울특별시", "address_gu": gu, "area_m2": area,
        "min_bid_price": min_bid, "appraisal_price": appraisal, "fail_count": fail,
    })


def test_competition_base_by_fail_count():
    from modules.market.competition_predictor import predict_competition
    assert predict_competition({"fail_count": 0, "min_bid_price": 30000})["estimated_bidders"] == 5
    assert predict_competition({"fail_count": 1, "min_bid_price": 30000})["estimated_bidders"] == 4
    assert predict_competition({"fail_count": 3, "min_bid_price": 30000})["estimated_bidders"] == 2


def test_competition_adjustments_and_winning_price():
    from modules.market.competition_predictor import predict_competition
    hot = predict_competition({
        "fail_count": 0, "min_bid_price": 30000, "market_price": 50000,
        "location_total": 85, "near_station": True, "is_new": True,
    })
    cold = predict_competition({
        "fail_count": 0, "min_bid_price": 30000,
        "has_lien": True, "is_share": True, "eviction_difficulty": 8,
    })
    assert hot["estimated_bidders"] > cold["estimated_bidders"]
    assert hot["expected_winning_price"] >= 30000  # 낙찰배수 >=1
    assert hot["competition_level"] in ("high", "fierce")
    assert cold["estimated_bidders"] >= 1  # 음수 방지


def test_winning_rate_ranges():
    from modules.market.winning_rate_stats import get_winning_rate
    gangnam = get_winning_rate("서울특별시", "강남구", "아파트")
    villa = get_winning_rate("경기도", "성남시", "빌라")
    assert 0.5 <= gangnam["expected_rate"] <= 1.0
    assert gangnam["expected_rate"] > villa["expected_rate"]
    # 유찰 많을수록 낙찰가율 하락
    f0 = get_winning_rate("서울특별시", "강남구", "아파트", 0)["expected_rate"]
    f3 = get_winning_rate("서울특별시", "강남구", "아파트", 3)["expected_rate"]
    assert f3 < f0


def test_find_similar_cases():
    from modules.market.historical_cases import find_similar_cases
    # 동일 구/유형 후보 여러 건 생성
    base_id = _make_item(gu="마포구", area=84.0)
    for a in (80.0, 85.0, 60.0):
        _make_item(gu="마포구", area=a)
    _make_item(gu="강남구", area=84.0)  # 다른 구

    from core.database import get_connection
    conn = get_connection()
    base = dict(conn.execute("SELECT * FROM items WHERE id=?", (base_id,)).fetchone())
    conn.close()

    cases = find_similar_cases(base, limit=5)
    assert len(cases) >= 1
    assert all(0 < c["similarity_score"] <= 1.0 for c in cases)
    # 정렬: 유사도 내림차순
    sims = [c["similarity_score"] for c in cases]
    assert sims == sorted(sims, reverse=True)


def test_market_signal_deterministic():
    from modules.market.market_signal import detect_signals
    a = detect_signals("서울특별시", "강남구")
    b = detect_signals("서울특별시", "강남구")
    assert a["overall_signal"] == b["overall_signal"]
    assert a["overall_signal"] in ("bullish", "bearish", "neutral")
    assert isinstance(a["key_signals"], list)
