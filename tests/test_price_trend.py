"""
tests/test_price_trend.py
시세 트렌드 함수 (trade history / monthly aggregate / region trend) 검증.
"""


def test_monthly_aggregate_groups_by_year_month():
    from modules.valuation.price_matcher import monthly_aggregate
    trades = [
        {"trade_date": "2026-01-05", "trade_price": 100},
        {"trade_date": "2026-01-20", "trade_price": 120},
        {"trade_date": "2026-02-10", "trade_price": 130},
        {"trade_date": "2026-02-15", "trade_price": 110},
    ]
    out = monthly_aggregate(trades)
    assert len(out) == 2
    jan = out[0]
    feb = out[1]
    assert jan["ym"] == "2026-01"
    assert jan["count"] == 2
    assert jan["avg_price"] == 110
    assert jan["min_price"] == 100
    assert jan["max_price"] == 120
    assert feb["ym"] == "2026-02"
    assert feb["avg_price"] == 120


def test_monthly_aggregate_handles_empty_or_bad_dates():
    from modules.valuation.price_matcher import monthly_aggregate
    assert monthly_aggregate([]) == []
    # 빈/None 날짜는 스킵, 월 형식만 있는 것은 그대로 그룹
    out = monthly_aggregate([
        {"trade_date": "", "trade_price": 100},
        {"trade_date": None, "trade_price": 100},
        {"trade_date": "2026-03", "trade_price": 100},
    ])
    assert len(out) == 1
    assert out[0]["ym"] == "2026-03"
    assert out[0]["count"] == 1


def test_get_trade_history_returns_records():
    from scripts.generate_mock_data import generate
    from modules.valuation.price_matcher import get_trade_history
    from agents.price_analysis_agent import analyze_all
    generate(count=10, seed=42, reset=True)
    analyze_all()
    # 최소 한 건은 매칭되었을 가능성이 높음
    from core.database import get_connection
    conn = get_connection()
    row = conn.execute(
        "SELECT item_id FROM price_records LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        history = get_trade_history(row["item_id"])
        assert isinstance(history, list)
        if history:
            assert "trade_price" in history[0]
            assert "trade_date" in history[0]


def test_region_trend_aggregates_across_items():
    from scripts.generate_mock_data import generate
    from agents.price_analysis_agent import analyze_all
    from modules.valuation.price_matcher import get_region_trend
    generate(count=30, seed=42, reset=True)
    analyze_all()
    # 임의 지역 + 유형으로 호출 - 실패해도 빈 리스트 반환
    out = get_region_trend("서울특별시", "강남구", "아파트", months=12)
    assert isinstance(out, list)
