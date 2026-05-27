"""
tests/test_personalization.py — 개인 맞춤 추천 (블록 9)
"""
from core.database import upsert_item


def _make_item(gu="마포구", min_bid=28000, appraisal=40000, roe=15.0, loss=0.1, item_type="아파트"):
    iid = upsert_item({
        "source": "test", "case_no": f"2024타경{abs(hash((gu, min_bid, appraisal))) % 99999}",
        "item_type": item_type, "address_full": f"서울특별시 {gu} 망원동",
        "address_si": "서울특별시", "address_gu": gu, "area_m2": 84.0,
        "min_bid_price": min_bid, "appraisal_price": appraisal, "fail_count": 1,
    })
    from core.database import get_connection
    conn = get_connection()
    conn.execute("UPDATE items SET expected_roe=?, loss_probability=? WHERE id=?",
                 (roe, loss, iid))
    conn.commit()
    conn.close()
    return iid


def test_load_profile_defaults_and_env(monkeypatch):
    import importlib, core.user_profile as up
    importlib.reload(up)
    p = up.load_user_profile()
    assert p["capital_max"] == 200_000_000
    assert abs(sum(p["scenario_weights"].values()) - 1.0) < 1e-6

    monkeypatch.setenv("USER_CAPITAL_MAX", "150000000")
    monkeypatch.setenv("USER_INTEREST_REGIONS", "서울 마포구,서울 성동구")
    monkeypatch.setenv("USER_SCENARIO_WEIGHTS", "0.5,0.3,0.2")
    importlib.reload(up)
    p2 = up.load_user_profile()
    assert p2["capital_max"] == 150_000_000
    assert "서울 마포구" in p2["interest_regions"]
    assert p2["scenario_weights"]["short_sale"] == 0.5


def test_preference_score_matching():
    """관심지역+고ROE+저리스크 물건이 그렇지 않은 물건보다 높은 선호점수."""
    from core.user_profile import get_preference_score
    profile = {"interest_regions": ["마포구"], "min_roi": 0.08}
    good = {"address_full": "서울 마포구 망원동", "address_gu": "마포구",
            "expected_roe": 20.0, "loss_probability": 0.05}
    bad = {"address_full": "부산 해운대구", "address_gu": "해운대구",
           "expected_roe": 2.0, "loss_probability": 0.6}
    assert get_preference_score(good, profile) > get_preference_score(bad, profile)
    assert 0.0 <= get_preference_score(bad, profile) <= 1.0


def test_affordability_excludes_too_expensive():
    """자본 2억 한도로 매수 불가한 초고가 물건은 can_afford=False."""
    from core.user_profile import can_afford
    profile = {"capital_max": 200_000_000, "capital_min": 50_000_000,
               "annual_income": 60_000_000, "other_debt_monthly": 300_000,
               "loan_rate": 0.04, "ltv": 0.70, "dsr": 0.40, "loan_years": 30,
               "scenario_weights": {"short_sale": 0.3, "rental": 0.4, "residence": 0.3},
               "annual_appreciation": 0.03, "is_one_house": True, "min_roi": 0.08}
    cheap = _make_item(min_bid=20000, appraisal=28000)       # ~2억대
    expensive = _make_item(gu="강남구", min_bid=300000, appraisal=400000)  # 40억대
    assert can_afford(cheap, profile) is True
    assert can_afford(expensive, profile) is False


def test_recommend_order_consistent():
    from core.user_profile import recommend_for_user
    profile = {"capital_max": 200_000_000, "capital_min": 50_000_000,
               "annual_income": 60_000_000, "other_debt_monthly": 300_000,
               "loan_rate": 0.04, "ltv": 0.70, "dsr": 0.40, "loan_years": 30,
               "scenario_weights": {"short_sale": 0.3, "rental": 0.4, "residence": 0.3},
               "annual_appreciation": 0.03, "is_one_house": True, "min_roi": 0.08,
               "interest_regions": ["마포구"]}
    _make_item(gu="마포구", min_bid=25000, appraisal=35000, roe=18.0, loss=0.1)
    _make_item(gu="성동구", min_bid=22000, appraisal=30000, roe=8.0, loss=0.4)
    _make_item(gu="노원구", min_bid=20000, appraisal=28000, roe=12.0, loss=0.2)

    r1 = recommend_for_user(profile, limit=5)
    r2 = recommend_for_user(profile, limit=5)
    assert [x["item_id"] for x in r1] == [x["item_id"] for x in r2]  # 일관성
    assert len(r1) >= 1
    # 선호점수 내림차순
    prefs = [x["preference_score"] for x in r1]
    assert prefs == sorted(prefs, reverse=True)
