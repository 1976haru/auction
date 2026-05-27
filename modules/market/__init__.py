"""
modules/market — 시장 분석 엔진

- competition_predictor: 입찰자 수 / 예상 낙찰가 예측
- winning_rate_stats: 지역·유형·유찰횟수별 낙찰가율 통계
- historical_cases: 유사 과거 낙찰 사례
- market_signal: 시장 시그널(상승/하락/중립)

실데이터가 부족하면 합리적 기본값/결정적 mock으로 동작한다.
"""
from __future__ import annotations

from modules.market.competition_predictor import predict_competition
from modules.market.winning_rate_stats import get_winning_rate
from modules.market.historical_cases import find_similar_cases
from modules.market.market_signal import detect_signals

__all__ = [
    "predict_competition",
    "get_winning_rate",
    "find_similar_cases",
    "detect_signals",
]
