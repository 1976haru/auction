"""
modules/location/school_scorer.py
학군 점수 (최대 25점). 초/중/고 근접 + 유명 학군 보너스.
"""
from __future__ import annotations

from core.database import get_connection
from modules.location._mockutil import seeded_rng, use_real_kakao

MAX_SCORE = 25

# 유명 학군 보너스 (school_districts 테이블이 비어있을 때의 fallback)
_FALLBACK_DISTRICTS: dict[str, int] = {
    "강남구": 4, "서초구": 4, "양천구": 4, "노원구": 4, "분당": 4, "송파구": 3,
}


def _district_bonus(address: str | None) -> tuple[int, str | None]:
    if not address:
        return 0, None
    # DB 우선
    try:
        conn = get_connection()
        rows = conn.execute(
            "SELECT sigungu, dong, district_name, bonus_points FROM school_districts"
        ).fetchall()
        conn.close()
        for r in rows:
            key = (r["dong"] or r["sigungu"] or "")
            if key and key in address:
                return int(r["bonus_points"] or 0), r["district_name"]
    except Exception:
        pass
    for key, bonus in _FALLBACK_DISTRICTS.items():
        if key in address:
            return bonus, f"{key} 학군"
    return 0, None


def score_school(lat: float, lng: float, address: str | None = None) -> dict:
    if use_real_kakao():
        pass  # 실 API 경로는 블록 15에서 연결

    rng = seeded_rng("school", round(lat, 4), round(lng, 4))
    score = 0
    detail: list[str] = []

    if rng.random() < 0.85:  # 초등학교 1km 이내
        score += 8
        detail.append("초등학교 근접 +8")
    if rng.random() < 0.7:   # 중학교 1.5km 이내
        score += 8
        detail.append("중학교 근접 +8")
    if rng.random() < 0.6:   # 고등학교 2km 이내
        score += 5
        detail.append("고등학교 근접 +5")

    bonus, district = _district_bonus(address)
    if bonus:
        score += bonus
        detail.append(f"{district} +{bonus}")

    score = min(MAX_SCORE, score)
    return {
        "score": score,
        "max": MAX_SCORE,
        "school_district": district or "일반 학군",
        "notes": detail or ["주변 학교 정보 부족"],
    }
