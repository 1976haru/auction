"""
agents/preference_learning_agent.py
관심물건/피드백을 보고 사용자 선호를 추정한다.
"""
from __future__ import annotations

import json
from typing import Any

from core.config import (
    DEFAULT_MIN_PROFIT_MAN,
    DEFAULT_MIN_ROI,
    TARGET_REGIONS,
    TARGET_TYPES,
)
from core.database import get_connection, init_db
from core.logger import log
from core.utils import loads, safe_json


DEFAULT_PREF = {
    "regions": [],
    "item_types": ["아파트", "오피스텔", "빌라"],
    "max_risk_level": "medium",
    "min_profit_man": DEFAULT_MIN_PROFIT_MAN,
    "min_roi": DEFAULT_MIN_ROI,
    "exclude_keywords": [],
    "notes": "기본값 (선호 데이터 없음)",
}


def _load_watchlist() -> list[dict]:
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM items WHERE is_watched=1"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _load_feedback() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT f.*, i.address_si, i.address_gu, i.item_type "
        "FROM user_feedback f LEFT JOIN items i ON i.id=f.item_id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def learn_preferences() -> dict:
    """관심물건/피드백 -> 추정 선호."""
    pref = dict(DEFAULT_PREF)

    watch = _load_watchlist()
    fb = _load_feedback()

    if not watch and not fb:
        save_preferences(pref)
        return pref

    region_count: dict[str, int] = {}
    type_count: dict[str, int] = {}
    excludes: set[str] = set()

    for item in watch:
        si = item.get("address_si") or ""
        if si:
            region_count[si] = region_count.get(si, 0) + 1
        t = item.get("item_type") or ""
        if t:
            type_count[t] = type_count.get(t, 0) + 1

    for f in fb:
        if f.get("action") in ("ignore", "exclude"):
            t = f.get("item_type")
            if t:
                excludes.add(t)
        elif f.get("action") in ("like", "watch"):
            si = f.get("address_si")
            if si:
                region_count[si] = region_count.get(si, 0) + 1

    if region_count:
        pref["regions"] = sorted(region_count, key=region_count.get, reverse=True)[:5]
    if type_count:
        pref["item_types"] = sorted(type_count, key=type_count.get, reverse=True)[:5]
    if excludes:
        pref["exclude_keywords"] = sorted(excludes)
    pref["notes"] = (
        f"watchlist={len(watch)}건, feedback={len(fb)}건 기반 추정"
    )

    save_preferences(pref)
    return pref


def save_preferences(pref: dict) -> None:
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM user_preferences")
    c.execute("""
        INSERT INTO user_preferences
            (regions_json, item_types_json, max_risk_level,
             min_profit_man, min_roi, exclude_keywords, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        safe_json(pref.get("regions", [])),
        safe_json(pref.get("item_types", [])),
        pref.get("max_risk_level", "medium"),
        int(pref.get("min_profit_man", DEFAULT_MIN_PROFIT_MAN)),
        float(pref.get("min_roi", DEFAULT_MIN_ROI)),
        safe_json(pref.get("exclude_keywords", [])),
        pref.get("notes", ""),
    ))
    conn.commit()
    conn.close()


def get_preferences() -> dict:
    init_db()
    conn = get_connection()
    row = conn.execute("SELECT * FROM user_preferences ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    if not row:
        return dict(DEFAULT_PREF)
    return {
        "regions": loads(row["regions_json"], []),
        "item_types": loads(row["item_types_json"], DEFAULT_PREF["item_types"]),
        "max_risk_level": row["max_risk_level"] or "medium",
        "min_profit_man": int(row["min_profit_man"] or DEFAULT_MIN_PROFIT_MAN),
        "min_roi": float(row["min_roi"] or DEFAULT_MIN_ROI),
        "exclude_keywords": loads(row["exclude_keywords"], []),
        "notes": row["notes"] or "",
    }


def preference_match_score(item: dict, pref: dict | None = None) -> tuple[int, list[str]]:
    """선호 일치도 0~10. 추천점수에 가중되는 raw 점수."""
    pref = pref or get_preferences()
    score = 0
    reasons: list[str] = []

    region_pref = set(pref.get("regions") or [])
    if region_pref:
        if item.get("address_si") in region_pref or item.get("address_gu") in region_pref:
            score += 4
            reasons.append("선호 지역 일치")
    else:
        # 선호가 없는 경우 사용자 관심 지역 default
        if item.get("address_si") in TARGET_REGIONS:
            score += 2

    type_pref = set(pref.get("item_types") or TARGET_TYPES)
    if item.get("item_type") in type_pref:
        score += 3
        reasons.append("선호 유형 일치")

    return min(score, 10), reasons
