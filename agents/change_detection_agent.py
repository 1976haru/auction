"""
agents/change_detection_agent.py
직전 스냅샷과 비교해 관심물건의 변화를 감지한다.
"""
from __future__ import annotations

import json
from typing import Any

from core.database import get_connection, init_db
from core.logger import log
from core.utils import safe_json, today_str


def _take_snapshot(item: dict) -> dict:
    return {
        "min_bid_price": item.get("min_bid_price"),
        "fail_count": item.get("fail_count"),
        "bid_date": item.get("bid_date"),
        "status": item.get("status"),
        "is_watched": item.get("is_watched"),
    }


def _previous_snapshot(item_id: int) -> dict | None:
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM item_snapshots WHERE item_id=? ORDER BY id DESC LIMIT 1",
        (item_id,),
    ).fetchone()
    conn.close()
    if not row:
        return None
    try:
        return json.loads(row["snapshot_json"])
    except Exception:
        return None


def _save_snapshot(item_id: int, snap: dict) -> None:
    conn = get_connection()
    conn.execute("""
        INSERT INTO item_snapshots (item_id, snapshot_json, snapshot_date)
        VALUES (?, ?, ?)
    """, (item_id, safe_json(snap), today_str()))
    conn.commit()
    conn.close()


def _diff(prev: dict, cur: dict) -> list[dict]:
    events = []
    if prev.get("min_bid_price") != cur.get("min_bid_price"):
        events.append({
            "event_type": "price_change",
            "old_value": str(prev.get("min_bid_price")),
            "new_value": str(cur.get("min_bid_price")),
            "severity": "info",
            "message": "최저가 변경됨",
        })
    if prev.get("fail_count") != cur.get("fail_count"):
        events.append({
            "event_type": "fail_count_change",
            "old_value": str(prev.get("fail_count")),
            "new_value": str(cur.get("fail_count")),
            "severity": "info",
            "message": "유찰횟수 변경됨",
        })
    if prev.get("bid_date") != cur.get("bid_date"):
        events.append({
            "event_type": "bid_date_change",
            "old_value": str(prev.get("bid_date")),
            "new_value": str(cur.get("bid_date")),
            "severity": "info",
            "message": "입찰기일 변경됨",
        })
    if prev.get("status") != cur.get("status"):
        events.append({
            "event_type": "status_change",
            "old_value": str(prev.get("status")),
            "new_value": str(cur.get("status")),
            "severity": "warning",
            "message": "상태 변경됨",
        })
    return events


def detect_changes(only_watched: bool = False) -> list[dict]:
    init_db()
    conn = get_connection()
    q = "SELECT * FROM items"
    if only_watched:
        q += " WHERE is_watched=1"
    rows = conn.execute(q).fetchall()
    conn.close()

    all_events: list[dict] = []
    for r in rows:
        item = dict(r)
        cur = _take_snapshot(item)
        prev = _previous_snapshot(item["id"])
        if prev:
            events = _diff(prev, cur)
            for e in events:
                e["item_id"] = item["id"]
                _record_event(item["id"], e)
                all_events.append(e)
        _save_snapshot(item["id"], cur)
    log.info(f"[change] {len(all_events)}건 변화 감지")
    return all_events


def _record_event(item_id: int, event: dict) -> None:
    conn = get_connection()
    conn.execute("""
        INSERT INTO change_events
            (item_id, event_type, old_value, new_value, severity, message)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        item_id, event["event_type"], event.get("old_value"), event.get("new_value"),
        event.get("severity", "info"), event.get("message", ""),
    ))
    conn.commit()
    conn.close()


def list_recent_events(limit: int = 50) -> list[dict]:
    conn = get_connection()
    rows = conn.execute("""
        SELECT e.*, i.address_full
        FROM change_events e LEFT JOIN items i ON i.id=e.item_id
        ORDER BY e.id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
