"""
modules/scenarios — 시나리오 시뮬레이터 (v2.0 핵심)

단타(short_sale) / 임대(rental) / 실거주(residence) 3개 시나리오를 통합 비교하고
사용자 자본·가중치에 따라 최적 시나리오를 추천한다.

앞선 모듈(legal/eviction/location/market/finance/valuation)을 통합한다.
단위: 입력 item 가격은 만원, 내부 계산은 원(₩).
"""
from __future__ import annotations

from modules.scenarios.short_term_sale import simulate_short_sale
from modules.scenarios.long_term_rental import simulate_rental
from modules.scenarios.owner_residence import simulate_residence
from modules.scenarios.scenario_comparator import compare_scenarios

__all__ = [
    "simulate_short_sale",
    "simulate_rental",
    "simulate_residence",
    "compare_scenarios",
]
