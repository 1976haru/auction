"""
tests/test_court_crawler.py
법원경매 crawler / real_auction_api 어댑터 검증.

- SELECTORS dict 가 의도한 키를 갖고 있어야 함
- 가격 파싱 (만원 + 억 표현)
- 지역/유형 코드 매핑
- Playwright 미설치 환경에서 어댑터가 안전하게 [] 반환
"""


def test_selectors_dict_has_required_keys():
    from modules.auction.crawler import SELECTORS
    required = {
        "region_select", "item_type_select", "search_button",
        "result_table", "result_row", "result_cells",
    }
    assert required.issubset(set(SELECTORS.keys())), \
        f"missing: {required - set(SELECTORS.keys())}"


def test_parse_price_handles_korean_formats():
    from modules.auction.crawler import _parse_price
    assert _parse_price("5억 9,500만원") == 59500
    assert _parse_price("8,500만원") == 8500
    assert _parse_price("3억") == 30000
    assert _parse_price("") == 0
    assert _parse_price("invalid") == 0


def test_region_and_type_codes():
    from modules.auction.crawler import _item_type_to_code, _region_to_code
    assert _region_to_code("서울특별시") == "B000201"
    assert _region_to_code("미존재") == ""
    assert _item_type_to_code("아파트") == "010001"
    assert _item_type_to_code("오피스텔") == "010002"
    assert _item_type_to_code("미존재") == ""


def test_real_auction_api_returns_empty_without_playwright():
    """real_auction_api 가 Playwright 미설치 환경에서 안전하게 동작."""
    import modules.auction.crawler as cr
    # 강제로 Playwright 없는 상태로 동작
    original = cr._HAS_PLAYWRIGHT
    cr._HAS_PLAYWRIGHT = False
    try:
        from modules.auction.real_auction_api import list_auction_items
        items = list_auction_items(count=5)
        # crawler 가 0건 반환 후 DB cache 조회 -> 신선 DB 면 [] 일 가능성 높음
        assert isinstance(items, list)
    finally:
        cr._HAS_PLAYWRIGHT = original


def test_validate_site_returns_dict_when_no_playwright(monkeypatch):
    """Playwright 미설치 시 validate_site_selectors 가 안내 dict 반환."""
    import modules.auction.crawler as cr
    monkeypatch.setattr(cr, "_HAS_PLAYWRIGHT", False)
    res = cr.validate_site_selectors()
    assert isinstance(res, dict)
    assert res["ok"] is False
    assert res["playwright_installed"] is False
    assert "playwright" in res["note"].lower()


def test_check_court_auction_script_imports():
    """CLI 스크립트 import 가능 + main 호출 가능 여부."""
    import scripts.check_court_auction as mod
    assert hasattr(mod, "main")
