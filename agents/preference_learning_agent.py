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
    # 알림 설정
    "alerts_enabled": True,
    "alert_channel": "telegram",                  # legacy 단일 채널
    "alert_channels": ["telegram"],               # multi-channel (이게 우선)
    "alert_min_grade": "B",
    "alert_imminent_days": 3,
    "alert_only_watched": False,
    "alert_include_briefing": True,
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
             min_profit_man, min_roi, exclude_keywords, notes,
             alerts_enabled, alert_channel, alert_channels_json,
             alert_min_grade, alert_imminent_days, alert_only_watched,
             alert_include_briefing)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        safe_json(pref.get("regions", [])),
        safe_json(pref.get("item_types", [])),
        pref.get("max_risk_level", "medium"),
        int(pref.get("min_profit_man", DEFAULT_MIN_PROFIT_MAN)),
        float(pref.get("min_roi", DEFAULT_MIN_ROI)),
        safe_json(pref.get("exclude_keywords", [])),
        pref.get("notes", ""),
        1 if pref.get("alerts_enabled", True) else 0,
        pref.get("alert_channel", "telegram"),
        safe_json(pref.get("alert_channels", ["telegram"])),
        pref.get("alert_min_grade", "B"),
        int(pref.get("alert_imminent_days", 3)),
        1 if pref.get("alert_only_watched", False) else 0,
        1 if pref.get("alert_include_briefing", True) else 0,
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
        "alerts_enabled": bool(row["alerts_enabled"]) if row["alerts_enabled"] is not None else True,
        "alert_channel": row["alert_channel"] or "telegram",
        "alert_channels": loads(row["alert_channels_json"], [row["alert_channel"] or "telegram"]),
        "alert_min_grade": row["alert_min_grade"] or "B",
        "alert_imminent_days": int(row["alert_imminent_days"] or 3),
        "alert_only_watched": bool(row["alert_only_watched"]),
        "alert_include_briefing": bool(row["alert_include_briefing"]) if row["alert_include_briefing"] is not None else True,
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
