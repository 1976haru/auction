"""
modules/backtest/accuracy_evaluator.py
추천 분류 정확도 평가 + backtest_results 저장.
"""
from __future__ import annotations

import json

from core.database import get_connection, init_db
from core.logger import log


def evaluate(predictions: list[bool], actuals: list[bool],
             roes: list[float] | None = None) -> dict:
    """추천(predictions) vs 실제 좋은 결과(actuals) 분류 평가.

    Returns: TP/FP/TN/FN + precision/recall/f1/accuracy + avg ROE.
    """
    if len(predictions) != len(actuals):
        raise ValueError("predictions/actuals 길이 불일치")

    tp = fp = tn = fn = 0
    rec_roes: list[float] = []
    exc_roes: list[float] = []
    for i, (pred, act) in enumerate(zip(predictions, actuals)):
        roe = roes[i] if roes and i < len(roes) else None
        if pred and act:
            tp += 1
        elif pred and not act:
            fp += 1
        elif not pred and not act:
            tn += 1
        else:
            fn += 1
        if roe is not None:
            (rec_roes if pred else exc_roes).append(roe)

    total = tp + fp + tn + fn or 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    accuracy = (tp + tn) / total

    def _avg(xs):
        return round(sum(xs) / len(xs), 2) if xs else 0.0

    return {
        "total": total,
        "true_positive": tp, "false_positive": fp,
        "true_negative": tn, "false_negative": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "accuracy": round(accuracy, 4),
        "avg_roe_recommended": _avg(rec_roes),
        "avg_roe_excluded": _avg(exc_roes),
    }


def save_backtest_result(metrics: dict, start_date: str, end_date: str,
                         report: dict | None = None) -> int:
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """INSERT INTO backtest_results
           (run_date, start_date, end_date, total_recommended,
            true_positive, false_positive, true_negative, false_negative,
            precision_score, recall_score, f1_score, accuracy,
            avg_roe_recommended, avg_roe_excluded, report_json)
           VALUES (datetime('now','localtime'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (start_date, end_date,
         metrics["true_positive"] + metrics["false_positive"],
         metrics["true_positive"], metrics["false_positive"],
         metrics["true_negative"], metrics["false_negative"],
         metrics["precision"], metrics["recall"], metrics["f1_score"],
         metrics["accuracy"], metrics["avg_roe_recommended"],
         metrics["avg_roe_excluded"],
         json.dumps(report or metrics, ensure_ascii=False)),
    )
    run_id = c.lastrowid
    conn.commit()
    conn.close()
    log.info(f"[backtest] 결과 저장 run #{run_id} "
             f"(정확도 {metrics['accuracy']*100:.1f}%, F1 {metrics['f1_score']*100:.1f}%)")
    return int(run_id)
