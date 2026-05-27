"""
modules/location/environment_scorer.py
환경 점수 (기본 10점에서 가감). 부정 요소(-)/긍정 요소(+).
"""
from __future__ import annotations

from modules.location._mockutil import seeded_rng, use_real_kakao

MAX_SCORE = 10

# 부정 요소 (라벨, 감점, 확률)
_NEGATIVES = [
    ("고속도로 500m 이내", 3, 0.18),
    ("지상철도/지하철 지상구간 200m", 2, 0.15),
    ("공장/물류센터 1km", 2, 0.12),
    ("화장장/쓰레기처리시설 인근", 3, 0.05),
]
# 긍정 요소
_POSITIVES = [
    ("강/호수 도보 10분", 3, 0.2),
    ("큰 공원 도보 10분", 2, 0.3),
]


def score_environment(lat: float, lng: float) -> dict:
    if use_real_kakao():
        pass  # 실 API 경로는 블록 15에서 연결

    rng = seeded_rng("environment", round(lat, 4), round(lng, 4))
    score = MAX_SCORE
    detail: list[str] = []

    for label, penalty, prob in _NEGATIVES:
        if rng.random() < prob:
            score -= penalty
            detail.append(f"{label} -{penalty}")
    for label, bonus, prob in _POSITIVES:
        if rng.random() < prob:
            score += bonus
            detail.append(f"{label} +{bonus}")

    score = max(0, min(MAX_SCORE, score))
    return {
        "score": score,
        "max": MAX_SCORE,
        "notes": detail or ["환경 특이사항 없음"],
    }
