"""
tests/test_location.py — 입지 분석 엔진 (블록 4)
"""
from core.database import upsert_item


def _make_item(address="서울특별시 마포구 망원동 1-1", gu="마포구"):
    return upsert_item({
        "source": "test", "case_no": f"2024타경{abs(hash(address)) % 9999}",
        "item_type": "빌라", "address_full": address, "address_gu": gu,
        "min_bid_price": 30000,
    })


def test_geocoder_deterministic_and_in_range():
    from modules.location.geocoder import geocode
    a = geocode("서울특별시 마포구 망원동 1-1")
    b = geocode("서울특별시 마포구 망원동 1-1")
    assert a == b  # 결정적
    lat, lng = a
    assert 33.0 <= lat <= 39.0 and 125.0 <= lng <= 130.0
    assert geocode("") is None


def test_each_scorer_within_max():
    from modules.location import (score_transit, score_school, score_amenity,
                                  score_development, score_environment)
    lat, lng = 37.55, 126.9
    assert 0 <= score_transit(lat, lng)["score"] <= 30
    assert 0 <= score_school(lat, lng, "서울 마포구")["score"] <= 25
    assert 0 <= score_amenity(lat, lng)["score"] <= 20
    assert 0 <= score_development("서울 마포구 망원동", "마포구")["score"] <= 15
    assert 0 <= score_environment(lat, lng)["score"] <= 10


def test_school_district_bonus():
    """강남구 주소는 학군 보너스 반영."""
    from modules.location.school_scorer import score_school
    gangnam = score_school(37.5, 127.05, "서울특별시 강남구 대치동")
    assert gangnam["school_district"] != "일반 학군"


def test_total_score_and_grade():
    from modules.location.total_scorer import calculate_location_score
    item_id = _make_item()
    r = calculate_location_score(item_id)
    assert r["total"] == (r["transit"] + r["school"] + r["amenity"]
                          + r["development"] + r["environment"])
    assert 0 <= r["total"] <= 100
    assert r["grade"] in ("우량 입지", "양호", "보통", "주의")


def test_persist_and_reload():
    from modules.location.total_scorer import calculate_location_score, get_location_score
    item_id = _make_item("경기도 성남시 분당구 정자동", "분당구")
    r = calculate_location_score(item_id)
    loaded = get_location_score(item_id)
    assert loaded is not None
    assert loaded["total"] == r["total"]
    assert "transit" in loaded["detail"]
