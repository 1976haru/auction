"""
modules/location/amenity_scorer.py
생활편의 점수 (최대 20점). 마트/병원/공원/은행/편의점 근접.
"""
from __future__ import annotations

from modules.location._mockutil import seeded_rng, use_real_kakao

MAX_SCORE = 20

# (라벨, 점수, mock 존재확률)
_AMENITIES = [
    ("대형마트 1km 이내", 5, 0.6),
    ("종합병원 2km 이내", 5, 0.5),
    ("공원 1km 이내", 4, 0.7),
    ("은행 500m 이내", 3, 0.8),
    ("편의점 200m 이내", 3, 0.92),
]


def score_amenity(lat: float, lng: float) -> dict:
    if use_real_kakao():
        pass  # 실 API 경로는 블록 15에서 연결

    rng = seeded_rng("amenity", round(lat, 4), round(lng, 4))
    score = 0
    detail: list[str] = []
    for label, pts, prob in _AMENITIES:
        if rng.random() < prob:
            score += pts
            detail.append(f"{label} +{pts}")

    score = min(MAX_SCORE, score)
    return {
        "score": score,
        "max": MAX_SCORE,
        "notes": detail or ["주변 편의시설 부족"],
    }
