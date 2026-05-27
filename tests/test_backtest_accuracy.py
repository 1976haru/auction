"""
tests/test_backtest_accuracy.py — 정확도 백테스트 (블록 13)
"""


def test_evaluate_metrics_known_input():
    from modules.backtest.accuracy_evaluator import evaluate
    # 추천 5건 중 4건 좋음(TP4,FP1), 비추천 5건 중 1건 좋았음(FN1, TN4)
    preds = [True, True, True, True, True, False, False, False, False, False]
    acts = [True, True, True, True, False, True, False, False, False, False]
    roes = [20, 18, 15, 12, -5, 11, 2, 1, 3, 0]
    m = evaluate(preds, acts, roes)
    assert m["true_positive"] == 4
    assert m["false_positive"] == 1
    assert m["false_negative"] == 1
    assert m["true_negative"] == 4
    assert m["precision"] == round(4 / 5, 4)
    assert m["recall"] == round(4 / 5, 4)
    assert m["accuracy"] == round(8 / 10, 4)
    assert m["avg_roe_recommended"] > m["avg_roe_excluded"]


def test_run_backtest_saves_and_deterministic():
    from scripts.generate_mock_data import generate
    from modules.backtest.historical_runner import run_backtest
    from core.database import get_connection
    generate(count=20, seed=42, reset=True, analyze=True)

    a = run_backtest("2024-01-01", "2024-07-01")
    b = run_backtest("2024-01-01", "2024-07-01", save=False)
    # 결정적
    assert a["accuracy"] == b["accuracy"]
    assert a["sample"] > 0
    assert 0.0 <= a["precision"] <= 1.0 and 0.0 <= a["recall"] <= 1.0

    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) FROM backtest_results").fetchone()[0]
    conn.close()
    assert row >= 1


def test_auto_adjust_weights_direction():
    from modules.backtest.historical_runner import auto_adjust_weights
    fp_heavy = auto_adjust_weights({"false_positive": 10, "false_negative": 2})
    fn_heavy = auto_adjust_weights({"false_positive": 2, "false_negative": 10})
    assert fp_heavy["direction"] == "conservative"
    assert fn_heavy["direction"] == "aggressive"
    # 가중치 합 ≈ 1
    assert abs(sum(fp_heavy["weights"].values()) - 1.0) < 1e-6
    # 보수적이면 단타 비중↓, 공격적이면 단타 비중↑
    assert fp_heavy["weights"]["short_sale"] < fn_heavy["weights"]["short_sale"]
