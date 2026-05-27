"""
modules/location/transit_scorer.py
교통 점수 (최대 30점). 가까운 지하철역 도보시간(분당 80m) 기준.
"""
from __future__ import annotations

from modules.location._mockutil import seeded_rng, use_real_kakao

MAX_SCORE = 30


def _score_by_walk(walk_min: float) -> int:
    if walk_min <= 5:
        return 30
    if walk_min <= 10:
        return 24
    if walk_min <= 15:
        return 18
    if walk_min <= 20:
        return 12
    return 6


def score_transit(lat: float, lng: float) -> dict:
    if use_real_kakao():
        # 실 API 경로는 블록 15에서 캐시와 함께 연결. 현재는 mock과 동일 구조.
        pass

    rng = seeded_rng("transit", round(lat, 4), round(lng, 4))
    distance_m = rng.randint(200, 1800)         # 가장 가까운 역까지 거리
    walk_min = round(distance_m / 80, 1)         # 분당 80m
    score = _score_by_walk(walk_min)

    bonus = 0
    notes: list[str] = []
    is_transfer = rng.random() < 0.25
    is_gtx = rng.random() < 0.08
    if is_transfer:
        bonus += 3
        notes.append("환승역 +3")
    if is_gtx:
        bonus += 5
        notes.append("GTX 정차역 +5")

    score = min(MAX_SCORE, score + bonus)
    station = rng.choice(["망원역", "합정역", "왕십리역", "수서역", "선릉역", "야탑역", "정자역"])

    return {
        "score": score,
        "max": MAX_SCORE,
        "nearest_subway": f"{station} 도보 {round(walk_min)}분",
        "walk_minutes": walk_min,
        "distance_m": distance_m,
        "notes": notes or ["역세권 보정 없음"],
    }
