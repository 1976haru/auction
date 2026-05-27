"""
modules/backtest — 추천 알고리즘 정확도 검증 (precision/recall/F1).

기존 agents/backtest_agent(등급별 수익 백테스트)와 별개로,
"추천 여부 vs 실제 좋은 결과"의 분류 정확도를 측정한다.
mock 모드에서는 결정적 actual을 생성해 일관된 결과를 보장한다.
"""
from __future__ import annotations

from modules.backtest.historical_runner import run_backtest, auto_adjust_weights
from modules.backtest.accuracy_evaluator import evaluate, save_backtest_result

__all__ = ["run_backtest", "auto_adjust_weights", "evaluate", "save_backtest_result"]
