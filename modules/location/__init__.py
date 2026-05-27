"""
modules/location — 입지 분석 엔진 (5축 100점 스코어링)

축: 교통(30) + 학군(25) + 생활(20) + 개발(15) + 환경(10)

USE_MOCK_APIS=true 또는 KAKAO/NAVER 키 없음 -> 모든 함수가 결정적 mock 반환.
mock 값은 좌표/주소 해시 기반으로 동일 입력에 동일 결과를 보장한다.
"""
from __future__ import annotations

from modules.location.geocoder import geocode
from modules.location.transit_scorer import score_transit
from modules.location.school_scorer import score_school
from modules.location.amenity_scorer import score_amenity
from modules.location.development_scorer import score_development
from modules.location.environment_scorer import score_environment
from modules.location.total_scorer import calculate_location_score, get_location_score

__all__ = [
    "geocode",
    "score_transit",
    "score_school",
    "score_amenity",
    "score_development",
    "score_environment",
    "calculate_location_score",
    "get_location_score",
]
