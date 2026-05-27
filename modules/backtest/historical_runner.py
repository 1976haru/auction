"""
modules/backtest/historical_runner.py
과거 시점 추천을 재현하고 실제 결과와 비교한다.

mock 데이터 모드: scenario_results의 추천 ROE를 기준으로 추천 여부를 정하고,
결정적 노이즈로 '실제' ROE를 생성해 일관된 결과를 만든다.
"""
from __future__ import annotations

import random

from core.database import get_connection
from core.logger import log
from modules.backtest.accuracy_evaluator import evaluate, save_backtest_result

# 추천 임계(연환산 ROE %) / '좋은 결과' 기준(연환산 ROE %)
RECOMMEND_THRESHOLD = 8.0
GOOD_OUTCOME = 10.0


def _seed(start_date: str, end_date: str) -> int:
    return abs(hash(f"{start_date}|{end_date}")) % (2 ** 31)


def run_backtest(start_date: str, end_date: str,
                 recommend_threshold: float = RECOMMEND_THRESHOLD,
                 good_outcome: float = GOOD_OUTCOME,
                 save: bool = True) -> dict:
    """기간 백테스트 실행 -> 정확도 리포트.

    Returns: evaluate() 결과 + period/run_id.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT item_id, annualized_roe FROM scenario_results
           WHERE is_recommended=1 ORDER BY item_id"""
    ).fetchall()
    conn.close()

    rng = random.Random(_seed(start_date, end_date))
    predictions: list[bool] = []
    actuals: list[bool] = []
    actual_roes: list[float] = []

    for r in rows:
        pred_roe = r["annualized_roe"] or 0.0
        recommended = pred_roe >= recommend_threshold
        # 결정적 '실제' ROE: 예측 + 약한 양(+) 편향 노이즈
        noise = rng.gauss(2.0, 8.0)
        actual_roe = pred_roe + noise
        actual_good = actual_roe >= good_outcome

        predictions.append(recommended)
        actuals.append(actual_good)
        actual_roes.append(round(actual_roe, 2))

    metrics = evaluate(predictions, actuals, actual_roes)
    metrics["period"] = {"start": start_date, "end": end_date}
    metrics["sample"] = len(rows)

    if save and rows:
        metrics["run_id"] = save_backtest_result(metrics, start_date, end_date)

    log.info(f"[backtest] {start_date}~{end_date}: "
             f"{len(rows)}건, 정확도 {metrics['accuracy']*100:.1f}%")
    return metrics


def auto_adjust_weights(report: dict, base_weights: dict | None = None,
                        step: float = 0.05) -> dict:
    """FP/FN 비중에 따라 시나리오 가중치 미세 조정(±step).

    - False Positive 많음(정밀도 낮음) -> 보수적(단타↓, 실거주↑)
    - False Negative 많음(재현율 낮음) -> 공격적(단타↑)
    """
    w = dict(base_weights or {"short_sale": 0.30, "rental": 0.40, "residence": 0.30})
    fp = report.get("false_positive", 0)
    fn = report.get("false_negative", 0)

    if fp > fn:
        w["short_sale"] = max(0.1, w["short_sale"] - step)
        w["residence"] = min(0.6, w["residence"] + step)
        direction = "conservative"
    elif fn > fp:
        w["short_sale"] = min(0.6, w["short_sale"] + step)
        w["residence"] = max(0.1, w["residence"] - step)
        direction = "aggressive"
    else:
        direction = "neutral"

    total = sum(w.values()) or 1.0
    w = {k: round(v / total, 4) for k, v in w.items()}
    return {"weights": w, "direction": direction}
