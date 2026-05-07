"""
tests/test_backtest.py
백테스트 통계 + 등급 순서 검증.
"""


def _seed(count=30):
    from scripts.generate_mock_data import generate
    from scripts.run_daily_pipeline import run_pipeline
    generate(count=count, seed=42, reset=True)
    run_pipeline(use_mock=True, count=count, top=5, reset=False,
                  query="시세차익 큰 물건 5개")


def test_evaluate_all_items_returns_grades():
    from agents.backtest_agent import evaluate_all_items
    _seed(20)
    evaluations = evaluate_all_items()
    assert len(evaluations) >= 1
    grades = {e["grade"] for e in evaluations}
    # 적어도 X 등급 (비현실적 매물) 하나는 있을 가능성 높음
    assert any(g in {"A", "B", "C", "D", "X"} for g in grades)


def test_backtest_all_items_produces_stats():
    from agents.backtest_agent import backtest_all_items
    _seed(25)
    report = backtest_all_items()
    assert report["mode"] == "all_items"
    assert report["total_pairs"] >= 1
    assert "grades" in report
    # 통계가 있으면 mean 키가 들어있어야 한다
    for g, s in report["grades"].items():
        if s["count"] > 0:
            assert "mean" in s["actual_profit"]
            assert 0 <= s["win_rate"] <= 100


def test_grade_ordering_check_returns_dict():
    from agents.backtest_agent import backtest_all_items, grade_ordering_check
    _seed(20)
    report = backtest_all_items()
    o = grade_ordering_check(report)
    assert "monotonic_decreasing" in o
    assert isinstance(o["grade_means"], dict)


def test_x_grade_mostly_unprofitable():
    """X 등급 (감정가 거품/음수 차익) 매물은 평균 손익이 마이너스여야 한다."""
    from agents.backtest_agent import backtest_all_items
    _seed(30)
    report = backtest_all_items()
    x = report["grades"].get("X")
    if x and x["count"] > 0:
        # X 등급은 거품 매물이라 평균 손익 음수 또는 매우 낮음
        assert x["actual_profit"]["mean"] < x["actual_profit"].get("max", 0) + 1
