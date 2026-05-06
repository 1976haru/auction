"""
tests/test_mock_data.py
mock 데이터 생성 + mock API 응답 검증.
"""


def test_generate_mock_data_creates_items():
    from scripts.generate_mock_data import generate
    res = generate(count=20, seed=42, reset=True)
    assert res["items"] == 20
    assert res["documents"] >= 1


def test_mock_auction_api_listing_is_deterministic():
    from modules.auction.mock_auction_api import list_auction_items
    a = list_auction_items(count=10, seed=7)
    b = list_auction_items(count=10, seed=7)
    assert a == b
    assert all("source" in i and i["source"] == "auction" for i in a)


def test_mock_onbid_api_listing():
    from modules.public_sale.mock_onbid_api import list_public_sale_items
    items = list_public_sale_items(count=5, seed=1)
    assert len(items) == 5
    assert all(i["source"] == "public_sale" for i in items)


def test_mock_molit_api_summary():
    from modules.valuation.mock_molit_api import fetch_trades, summarize_trades
    trades = fetch_trades("서울특별시 강남구 역삼동 1", "아파트", 60.0, seed=11)
    summary = summarize_trades(trades)
    assert "transaction_count" in summary
    assert summary["transaction_count"] == len(trades)
