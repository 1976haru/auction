"""
modules/location/total_scorer.py
5축 통합 입지 점수 계산 + location_scores 테이블 저장.
"""
from __future__ import annotations

import json

from core.database import get_connection, init_db
from core.logger import log
from modules.location.geocoder import geocode
from modules.location.transit_scorer import score_transit
from modules.location.school_scorer import score_school
from modules.location.amenity_scorer import score_amenity
from modules.location.development_scorer import score_development
from modules.location.environment_scorer import score_environment


def _grade(total: float) -> str:
    if total >= 80:
        return "우량 입지"
    if total >= 60:
        return "양호"
    if total >= 40:
        return "보통"
    return "주의"


def calculate_location_score(item_id: int, item_info: dict | None = None) -> dict:
    """item 주소로 5축 점수 산출 후 location_scores 저장.

    Returns: {transit, school, amenity, development, environment, total,
              grade, nearest_subway, school_district, development_news, ...}
    """
    if item_info is None:
        conn = get_connection()
        row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        conn.close()
        item_info = dict(row) if row else {}

    address = item_info.get("address_full") or item_info.get("address_gu") or ""
    sigungu = item_info.get("address_gu") or ""

    coords = geocode(address) or (37.5, 127.0)
    lat, lng = coords

    transit = score_transit(lat, lng)
    school = score_school(lat, lng, address)
    amenity = score_amenity(lat, lng)
    development = score_development(address, sigungu)
    environment = score_environment(lat, lng)

    total = (transit["score"] + school["score"] + amenity["score"]
             + development["score"] + environment["score"])
    grade = _grade(total)

    detail = {
        "transit": transit, "school": school, "amenity": amenity,
        "development": development, "environment": environment,
    }

    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM location_scores WHERE item_id=?", (item_id,))
    conn.execute(
        """INSERT INTO location_scores
           (item_id, latitude, longitude, transit, school, amenity, development,
            environment, total, grade, nearest_subway, school_district,
            development_news, detail_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (item_id, lat, lng, transit["score"], school["score"], amenity["score"],
         development["score"], environment["score"], total, grade,
         transit["nearest_subway"], school["school_district"],
         development["development_news"], json.dumps(detail, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()

    result = {
        "item_id": item_id,
        "transit": transit["score"], "school": school["score"],
        "amenity": amenity["score"], "development": development["score"],
        "environment": environment["score"],
        "total": total, "grade": grade,
        "nearest_subway": transit["nearest_subway"],
        "school_district": school["school_district"],
        "development_news": development["development_news"],
        "detail": detail,
    }
    log.info(
        f"[location] item_id={item_id} -> 입지 {total}/100 ({grade}) "
        f"[교통 {transit['score']}/학군 {school['score']}/생활 {amenity['score']}/"
        f"개발 {development['score']}/환경 {environment['score']}]"
    )
    return result


def get_location_score(item_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM location_scores WHERE item_id=?", (item_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    out = dict(row)
    if out.get("detail_json"):
        try:
            out["detail"] = json.loads(out["detail_json"])
        except Exception:
            pass
    return out
