"""
agents/alert_agent.py
이벤트 수집 -> 알림 후보 생성 -> 중복 제거 -> 채널 발송 (현재는 텔레그램, mock 콘솔 fallback).

알림 종류
- new_recommendation : 어제 대비 새로 등장한 A/B 등급 추천 매물
- imminent_bid      : 관심물건이거나 추천 후보인 매물 중 입찰기일 임박
- watch_change      : 관심 매물에 발생한 가격/유찰/기일/상태 변경 이벤트
- daily_briefing    : 오늘의 브리핑 한줄 요약

중복 제거 키 (dedupe_key) = "{alert_type}|{item_id}|{date}|{payload_hash}"
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from agents.preference_learning_agent import get_preferences
from core.database import get_connection, init_db
from core.logger import log
from core.utils import days_until, now_iso, today_str
from modules.alerts.telegram import send_message


GRADE_RANK = {"A": 1, "B": 2, "C": 3, "D": 4, "X": 5}


def _hash(payload: Any) -> str:
    s = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def _dedupe_key(alert_type: str, item_id: int | None, payload: Any) -> str:
    return f"{alert_type}|{item_id or 0}|{today_str()}|{_hash(payload)}"


def _is_already_sent(dedupe_key: str) -> bool:
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM alert_log WHERE dedupe_key=? AND status='sent'",
        (dedupe_key,),
    ).fetchone()
    conn.close()
    return row is not None


def _record_alert(alert: dict, status: str, error: str | None = None) -> None:
    init_db()
    conn = get_connection()
    conn.execute("""
        INSERT INTO alert_log
            (alert_type, item_id, dedupe_key, priority, title, body, channel, sent_at, status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(dedupe_key) DO UPDATE SET
            status=excluded.status, sent_at=excluded.sent_at, error_message=excluded.error_message
    """, (
        alert["alert_type"], alert.get("item_id"), alert["dedupe_key"],
        alert.get("priority", "medium"), alert.get("title"),
        alert.get("body"), alert.get("channel", "telegram"),
        now_iso() if status == "sent" else None,
        status, error,
    ))
    conn.commit()
    conn.close()


# ── 알림 수집기 ─────────────────────────────────────────────────────

def _collect_new_recommendations(min_grade: str, only_watched: bool) -> list[dict]:
    """가장 최근 브리핑의 top_picks 중 어제 브리핑에 없던 A/B 추천 매물."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM daily_briefings ORDER BY id DESC LIMIT 2
    """).fetchall()
    conn.close()
    if not rows:
        return []
    today = dict(rows[0])
    yesterday = dict(rows[1]) if len(rows) > 1 else None

    try:
        today_picks = json.loads(today["top_picks_json"] or "[]")
    except Exception:
        today_picks = []
    yesterday_ids = set()
    if yesterday:
        try:
            for r in json.loads(yesterday["top_picks_json"] or "[]"):
                yesterday_ids.add(r["item"]["id"])
        except Exception:
            pass

    threshold = GRADE_RANK.get(min_grade, 2)
    out = []
    for r in today_picks:
        if GRADE_RANK.get(r.get("grade"), 9) > threshold:
            continue
        item_id = r["item"]["id"]
        if item_id in yesterday_ids:
            continue  # 어제도 있던 매물 -> 새 알림 아님
        if only_watched and not r["item"].get("is_watched"):
            continue
        addr = r["item"].get("address_full", "")
        body = (
            f"[새 추천 {r['grade']}등급] {addr}\n"
            f"예상차익 {r.get('profit_estimate', 0):,}만원 / ROI {r.get('roi_estimate', 0):.1f}%\n"
            f"위험 {r.get('risk_level', 'unknown')} / 점수 {r.get('score', 0):.1f}\n"
            f"매각기일 {r['item'].get('bid_date', '미정')}"
        )
        out.append({
            "alert_type": "new_recommendation",
            "item_id": item_id,
            "title": f"[새 추천 {r['grade']}] {addr[:30]}",
            "body": body,
            "priority": "high" if r["grade"] == "A" else "medium",
            "payload": {"grade": r["grade"], "score": r.get("score")},
        })
    return out


def _collect_imminent_bids(within_days: int, min_grade: str, only_watched: bool) -> list[dict]:
    """입찰기일 임박 매물 알림."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT i.*,
               (SELECT MAX(severity) FROM risk_flags WHERE item_id=i.id) as max_severity,
               (SELECT risk_level FROM risk_flags WHERE item_id=i.id ORDER BY severity DESC LIMIT 1) as risk_level
        FROM items i
        WHERE i.status='active'
    """).fetchall()
    conn.close()
    out = []
    for row in rows:
        it = dict(row)
        days = days_until(it.get("bid_date"))
        if days is None or days < 0 or days > within_days:
            continue
        if only_watched and not it.get("is_watched"):
            continue
        body = (
            f"[입찰기일 임박] {it.get('address_full', '')}\n"
            f"D-{days} 남음 (매각기일 {it.get('bid_date')})\n"
            f"최저가 {it.get('min_bid_price', 0):,}만원 / 위험 {it.get('risk_level', 'unknown')}"
        )
        out.append({
            "alert_type": "imminent_bid",
            "item_id": it["id"],
            "title": f"[D-{days}] {it.get('address_full', '')[:30]}",
            "body": body,
            "priority": "high" if days <= 1 else "medium",
            "payload": {"days": days, "bid_date": it.get("bid_date")},
        })
    return out


def _collect_watch_changes() -> list[dict]:
    """관심 매물에 발생한 최근 24시간 내 변경 이벤트."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT e.*, i.address_full, i.is_watched
        FROM change_events e LEFT JOIN items i ON i.id=e.item_id
        WHERE i.is_watched=1
          AND datetime(e.created_at) >= datetime('now','-1 day','localtime')
        ORDER BY e.id DESC
    """).fetchall()
    conn.close()
    out = []
    for row in rows:
        e = dict(row)
        body = (
            f"[관심 매물 변경] {e.get('address_full', '')}\n"
            f"{e.get('event_type')}: {e.get('old_value')} -> {e.get('new_value')}\n"
            f"{e.get('message', '')}"
        )
        out.append({
            "alert_type": "watch_change",
            "item_id": e["item_id"],
            "title": f"[{e['event_type']}] {e.get('address_full', '')[:30]}",
            "body": body,
            "priority": e.get("severity", "info"),
            "payload": {"event_type": e["event_type"], "old": e["old_value"], "new": e["new_value"]},
        })
    return out


def _collect_briefing_summary() -> list[dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM daily_briefings WHERE run_date=? ORDER BY id DESC LIMIT 1",
        (today_str(),),
    ).fetchone()
    conn.close()
    if not row:
        return []
    b = dict(row)
    return [{
        "alert_type": "daily_briefing",
        "item_id": None,
        "title": f"오늘의 브리핑 ({b['run_date']})",
        "body": b["summary"] or "",
        "priority": "low",
        "payload": {"run_date": b["run_date"], "candidate_items": b["candidate_items"]},
    }]


# ── 메인 디스패처 ───────────────────────────────────────────────────

def collect_pending_alerts(pref: dict | None = None) -> list[dict]:
    pref = pref or get_preferences()
    if not pref.get("alerts_enabled", True):
        return []

    alerts: list[dict] = []
    alerts.extend(_collect_new_recommendations(
        min_grade=pref.get("alert_min_grade", "B"),
        only_watched=pref.get("alert_only_watched", False),
    ))
    alerts.extend(_collect_imminent_bids(
        within_days=pref.get("alert_imminent_days", 3),
        min_grade=pref.get("alert_min_grade", "B"),
        only_watched=pref.get("alert_only_watched", False),
    ))
    alerts.extend(_collect_watch_changes())
    if pref.get("alert_include_briefing", True):
        alerts.extend(_collect_briefing_summary())

    for a in alerts:
        a["dedupe_key"] = _dedupe_key(a["alert_type"], a.get("item_id"), a.get("payload"))
    return alerts


def dispatch_alerts(pref: dict | None = None, dry_run: bool = False) -> dict:
    """알림 수집 후 미발송 분만 채널로 보낸다.

    Returns:
        {"collected": int, "sent": int, "skipped": int, "failed": int, "details": [...]}
    """
    pref = pref or get_preferences()
    alerts = collect_pending_alerts(pref)

    sent = 0
    skipped = 0
    failed = 0
    details = []
    for a in alerts:
        if _is_already_sent(a["dedupe_key"]):
            skipped += 1
            details.append({"key": a["dedupe_key"], "status": "skipped"})
            continue
        if dry_run:
            details.append({"key": a["dedupe_key"], "status": "dry_run", "title": a["title"]})
            continue
        text = f"<b>{a['title']}</b>\n{a['body']}"
        ok = send_message(text)
        if ok:
            _record_alert(a, "sent")
            sent += 1
            details.append({"key": a["dedupe_key"], "status": "sent", "title": a["title"]})
        else:
            _record_alert(a, "failed", "send_message returned False")
            failed += 1
            details.append({"key": a["dedupe_key"], "status": "failed", "title": a["title"]})

    log.info(f"[alert] collected={len(alerts)} sent={sent} skipped={skipped} failed={failed}")
    return {
        "collected": len(alerts),
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "details": details,
    }


def list_recent_alerts(limit: int = 50) -> list[dict]:
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM alert_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
