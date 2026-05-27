"""
tests/test_legal.py — 권리분석 엔진 (블록 2)
"""
from core.database import upsert_item


def _make_item() -> int:
    return upsert_item({
        "source": "test",
        "case_no": "2024타경1234",
        "item_type": "빌라",
        "address_full": "서울특별시 마포구 망원동 1-1",
        "address_si": "서울특별시",
        "address_gu": "마포구",
        "min_bid_price": 30000,
    })


def _save_custom_timeline(item_id, rights):
    from modules.legal.rights_parser import save_rights_timeline, _finalize
    save_rights_timeline(item_id, _finalize(rights))


def test_parse_rights_mock_generates_timeline():
    """텍스트 없으면 mock 시계열 3~7건 생성 + seq 오름차순."""
    from modules.legal.rights_parser import parse_rights
    item_id = _make_item()
    rights = parse_rights("", item_id)
    assert 3 <= len(rights) <= 7
    seqs = [r["seq"] for r in rights]
    assert seqs == sorted(seqs)
    dates = [r["register_date"] for r in rights if r["register_date"]]
    assert dates == sorted(dates)


def test_parse_korean_amount():
    from modules.legal.rights_parser import parse_korean_amount
    assert parse_korean_amount("채권최고액 금240,000,000원") == 240_000_000
    assert parse_korean_amount("금 1억5천만원") == 150_000_000
    assert parse_korean_amount("보증금 3억원") == 300_000_000
    assert parse_korean_amount("특이사항 없음") is None


def test_save_and_get_roundtrip():
    from modules.legal.rights_parser import parse_rights, save_rights_timeline, get_rights_timeline
    item_id = _make_item()
    rights = parse_rights("", item_id)
    n = save_rights_timeline(item_id, rights)
    loaded = get_rights_timeline(item_id)
    assert n == len(loaded) == len(rights)
    assert loaded[0]["seq"] == 1


def test_earliest_mortgage_is_senior():
    """가장 빠른 근저당권이 말소기준권리."""
    from modules.legal.senior_right import identify_senior_right, get_senior_right
    item_id = _make_item()
    _save_custom_timeline(item_id, [
        {"section": "갑구", "register_date": "2010-01-01", "right_type": "소유권이전", "amount": None},
        {"section": "을구", "register_date": "2015-06-01", "right_type": "근저당권", "amount": 200_000_000},
        {"section": "갑구", "register_date": "2018-03-01", "right_type": "가압류", "amount": 50_000_000},
        {"section": "갑구", "register_date": "2023-09-01", "right_type": "경매개시결정", "amount": None},
    ])
    senior = identify_senior_right(item_id)
    assert senior is not None
    assert senior["right_type"] == "근저당권"
    assert senior["register_date"] == "2015-06-01"
    # 소유권이전(2010)은 말소기준 후보 아님 -> 인수(말소 안됨)
    assert get_senior_right(item_id)["register_date"] == "2015-06-01"


def test_tenant_with_priority_before_senior():
    """말소기준권리보다 빠른 전입 임차인 -> 대항력 있음."""
    from modules.legal.senior_right import identify_senior_right
    from modules.legal.tenant_protection import analyze_tenant
    item_id = _make_item()
    _save_custom_timeline(item_id, [
        {"section": "갑구", "register_date": "2010-01-01", "right_type": "소유권이전", "amount": None},
        {"section": "을구", "register_date": "2018-06-01", "right_type": "근저당권", "amount": 200_000_000},
    ])
    identify_senior_right(item_id)
    result = analyze_tenant(item_id, {
        "move_in_date": "2016-02-01", "occupied": True,
        "fixed_date": "2016-02-01", "deposit": 100_000_000, "region": "서울 마포구",
    })
    assert result["has_priority"] is True
    assert result["has_preferred_claim"] is True
    assert result["estimated_inherit"] == 100_000_000


def test_tenant_after_senior_no_priority():
    """말소기준 이후 전입 -> 대항력 없음, 인수 0."""
    from modules.legal.senior_right import identify_senior_right
    from modules.legal.tenant_protection import analyze_tenant
    item_id = _make_item()
    _save_custom_timeline(item_id, [
        {"section": "을구", "register_date": "2015-01-01", "right_type": "근저당권", "amount": 200_000_000},
    ])
    identify_senior_right(item_id)
    result = analyze_tenant(item_id, {
        "move_in_date": "2020-02-01", "occupied": True, "deposit": 80_000_000,
        "region": "서울",
    })
    assert result["has_priority"] is False
    assert result["estimated_inherit"] == 0


def test_small_lease_preferred_claim():
    """소액임차인 최우선변제: 서울 보증금 5천만 -> 최우선변제 한도 내."""
    from modules.legal.tenant_protection import analyze_tenant
    item_id = _make_item()
    result = analyze_tenant(item_id, {
        "move_in_date": "2022-01-01", "occupied": True,
        "deposit": 50_000_000, "region": "서울",
    })
    assert result["is_small_lease"] is True
    # 서울 최우선변제 한도 5500만, 보증금 5000만 -> 5000만 전액 최우선변제 대상
    assert result["small_lease_amount"] == 50_000_000


def test_inheritance_cost_sum():
    """인수금액 합산: 대항력 보증금 + 당해세 + 관리비."""
    from modules.legal.senior_right import identify_senior_right
    from modules.legal.inheritance_cost import calculate_inheritance
    item_id = _make_item()
    _save_custom_timeline(item_id, [
        {"section": "을구", "register_date": "2018-06-01", "right_type": "근저당권", "amount": 200_000_000},
    ])
    identify_senior_right(item_id)
    result = calculate_inheritance(
        item_id,
        tenant_info={"move_in_date": "2016-01-01", "occupied": True,
                     "deposit": 100_000_000, "region": "서울"},
        tax_arrears=3_000_000,
        management_fee=2_000_000,
    )
    assert result["breakdown"]["tenant_deposit"] == 100_000_000
    assert result["total_inherited"] == 105_000_000
    assert 0.0 < result["confidence"] <= 0.95
    assert len(result["must_check_items"]) >= 1
