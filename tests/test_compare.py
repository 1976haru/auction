"""
tests/test_compare.py
물건 비교: 데이터 수집 / best-worst 표시 / 요약.
"""


def _seed(count=20):
    from scripts.generate_mock_data import generate
    from scripts.run_daily_pipeline import run_pipeline
    generate(count=count, seed=42, reset=True)
    run_pipeline(use_mock=True, count=count, top=5, reset=False,
                  query="시세차익 큰 물건 5개")


def test_collect_compare_data_returns_per_item():
    from agents.compare_agent import collect_compare_data
    from core.database import get_connection
    _seed(15)
    conn = get_connection()
    ids = [r["id"] for r in conn.execute("SELECT id FROM items LIMIT 3").fetchall()]
    conn.close()
    data = collect_compare_data(ids)
    assert len(data) == 3
    for d in data:
        assert "address_full" in d
        assert "profit_estimate" in d
        assert "overall_conf_num" in d


def test_annotate_best_worst_marks_extremes():
    from agents.compare_agent import annotate_best_worst
    rows = [
        {"id": 1, "profit_estimate": 1000, "min_bid_price": 50000,
         "max_severity": 5, "transaction_count": 10},
        {"id": 2, "profit_estimate": 5000, "min_bid_price": 60000,
         "max_severity": 3, "transaction_count": 5},
        {"id": 3, "profit_estimate": 3000, "min_bid_price": 40000,
         "max_severity": 8, "transaction_count": 8},
    ]
    bw = annotate_best_worst(rows)
    # profit_estimate: higher better -> id=2 best, id=1 worst
    assert bw["profit_estimate"][2] == "best"
    assert bw["profit_estimate"][1] == "worst"
    # min_bid_price: lower better -> id=3 best, id=2 worst
    assert bw["min_bid_price"][3] == "best"
    assert bw["min_bid_price"][2] == "worst"
    # max_severity: lower better -> id=2 best, id=3 worst
    assert bw["max_severity"][2] == "best"
    assert bw["max_severity"][3] == "worst"


def test_annotate_best_worst_skips_when_all_equal():
    from agents.compare_agent import annotate_best_worst
    rows = [
        {"id": 1, "profit_estimate": 100},
        {"id": 2, "profit_estimate": 100},
    ]
    bw = annotate_best_worst(rows)
    assert "profit_estimate" not in bw  # 동일 값이면 표시 안 함


def test_summarize_returns_three_winners():
    from agents.compare_agent import summarize_compare
    rows = [
        {"id": 1, "address_full": "A", "score": 80, "grade": "A",
         "profit_estimate": 5000, "max_severity": 7},
        {"id": 2, "address_full": "B", "score": 60, "grade": "B",
         "profit_estimate": 8000, "max_severity": 3},
        {"id": 3, "address_full": "C", "score": 70, "grade": "B",
         "profit_estimate": 3000, "max_severity": 5},
    ]
    s = summarize_compare(rows)
    assert s["best_score"]["id"] == 1
    assert s["best_profit"]["id"] == 2
    assert s["lowest_risk"]["id"] == 2


def test_collect_compare_handles_missing_items():
    from agents.compare_agent import collect_compare_data
    _seed(5)
    data = collect_compare_data([99999, 88888])  # 존재 안 하는 id
    assert data == []
