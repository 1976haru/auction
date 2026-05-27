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
from modules.alerts.dispatcher import send_to_channels


GRADE_RANK = {"A": 1, "B": 2, "C": 3, "D": 4, "X": 5}


def _hash(payload: Any) -> str:
    s = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:12]


def _dedupe_key(alert_type: str, item_id: int | None, payload: Any,
                channel: str = "*") -> str:
    """채널별 dedup. 같은 알림이라도 telegram 과 slack 은 각각 1회씩 발송."""
    return f"{alert_type}|{item_id or 0}|{channel}|{today_str()}|{_hash(payload)}"


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


def _collect_operational_anomalies() -> list[dict]:
    """운영 모니터링 이상 감지를 알림 후보로 변환.

    detect_anomalies() 가 반환하는 [{severity, message}] 를 알림 dict 로 변환.
    severity warning -> alert priority high, info -> low.
    payload 에 message 그대로 들어가 dedup 키 일관됨 (같은 메시지는 재전송 안 됨).
    """
    try:
        from agents.monitoring_agent import detect_anomalies
    except Exception:
        return []
    issues = detect_anomalies()
    out = []
    for it in issues:
        severity = it.get("severity", "info")
        msg = it.get("message", "")
        out.append({
            "alert_type": "operational_anomaly",
            "item_id": None,
            "title": f"[운영 이상] {msg[:50]}",
            "body": msg,
            "priority": "high" if severity == "warning" else "low",
            "payload": {"severity": severity, "message": msg},
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
    if pref.get("alert_include_ops", True):
        alerts.extend(_collect_operational_anomalies())
    if pref.get("alert_include_briefing", True):
        alerts.extend(_collect_briefing_summary())

    # 채널 무관 base key (preview 용). 실제 발송 시 채널별 key 생성.
    for a in alerts:
        a["dedupe_key"] = _dedupe_key(a["alert_type"], a.get("item_id"),
                                       a.get("payload"))
    return alerts


def dispatch_alerts(pref: dict | None = None, dry_run: bool = False) -> dict:
    """알림 수집 후 사용자가 선택한 모든 채널에 발송.

    multi-channel 동작:
    - 사용자 선호 alert_channels 리스트의 각 채널에 fanout
    - 채널별 dedup 키로 같은 채널에 중복 발송 방지
    - 각 채널별 send 결과를 alert_log 에 별도 행으로 기록

    Returns:
        {collected, sent, skipped, failed, details, channels}
    """
    pref = pref or get_preferences()
    channels = pref.get("alert_channels") or [pref.get("alert_channel", "telegram")]
    alerts = collect_pending_alerts(pref)

    sent = 0
    skipped = 0
    failed = 0
    details = []
    for a in alerts:
        text = f"<b>{a['title']}</b>\n{a['body']}"
        if dry_run:
            details.append({
                "title": a["title"], "status": "dry_run",
                "channels": channels,
            })
            continue
        # 채널별로 dedup + 발송
        per_channel: dict[str, str] = {}
        for ch in channels:
            ch_key = _dedupe_key(a["alert_type"], a.get("item_id"),
                                  a.get("payload"), channel=ch)
            entry = {**a, "dedupe_key": ch_key, "channel": ch}
            if _is_already_sent(ch_key):
                skipped += 1
                per_channel[ch] = "skipped"
                continue
            results = send_to_channels(text, channels=[ch])
            ok = results.get(ch, False)
            if ok:
                _record_alert(entry, "sent")
                sent += 1
                per_channel[ch] = "sent"
            else:
                _record_alert(entry, "failed", f"send_to_channels[{ch}]=False")
                failed += 1
                per_channel[ch] = "failed"
        details.append({"title": a["title"], "channels": per_channel})

    log.info(
        f"[alert] alerts={len(alerts)} channels={channels} "
        f"sent={sent} skipped={skipped} failed={failed}"
    )
    return {
        "collected": len(alerts),
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "channels": channels,
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


# ════════════════════════════════════════════════════════════
# 블록 14 — 알림 트리거 8종
# ════════════════════════════════════════════════════════════
def _profile():
    try:
        from core.user_profile import load_user_profile
        return load_user_profile()
    except Exception:
        return {}


def _trig_new_item_match(pref: dict) -> list[dict]:
    """신규 물건 + 조건 매칭(어제 이후 추가, 자본 가능, 추천 점수 70+)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT i.id, i.address_full, i.item_type, s.score, s.annualized_roe, s.scenario
           FROM items i JOIN scenario_results s ON s.item_id=i.id
           WHERE s.is_recommended=1 AND s.affordable=1 AND s.score>=70
             AND (i.created_at >= datetime('now','-1 day') OR i.created_at IS NULL)
           ORDER BY s.score DESC LIMIT 10"""
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        out.append({
            "alert_type": "new_item_match", "item_id": r["id"],
            "title": f"🆕 신규 추천 {str(r['address_full'] or '')[:24]}",
            "body": (f"[신규 추천] {r['address_full']}\n"
                     f"추천 시나리오 {r['scenario']} / 연환산 {r['annualized_roe']:.0f}% / 점수 {r['score']:.0f}"),
            "priority": "high", "payload": {"score": r["score"]},
        })
    return out


def _trig_price_drop(pref: dict) -> list[dict]:
    """관심 물건 최저가 5%+ 인하(change_events 기반)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT c.item_id, c.old_value, c.new_value, i.address_full
           FROM change_events c JOIN items i ON i.id=c.item_id
           WHERE c.event_type LIKE '%price%' AND i.is_watched=1
             AND c.created_at >= datetime('now','-2 day')"""
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        try:
            old = float(r["old_value"]); new = float(r["new_value"])
        except (TypeError, ValueError):
            continue
        if old > 0 and (old - new) / old >= 0.05:
            out.append({
                "alert_type": "price_drop", "item_id": r["item_id"],
                "title": f"📉 가격 인하 {str(r['address_full'] or '')[:24]}",
                "body": f"[관심물건 인하] {r['address_full']}\n{old:,.0f} → {new:,.0f}만원",
                "priority": "high", "payload": {"old": old, "new": new},
            })
    return out


def _trig_deadline(pref: dict) -> list[dict]:
    """관심 물건 입찰 D-3."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, address_full, bid_date, min_bid_price FROM items WHERE is_watched=1"
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = days_until(r["bid_date"])
        if d == 3:
            out.append({
                "alert_type": "deadline_approaching", "item_id": r["id"],
                "title": f"⏰ 입찰 D-3 {str(r['address_full'] or '')[:24]}",
                "body": f"[입찰 D-3] {r['address_full']}\n매각기일 {r['bid_date']} / 최저가 {r['min_bid_price']:,}만원",
                "priority": "high", "payload": {"bid_date": r["bid_date"]},
            })
    return out


def _trig_bid_result(pref: dict) -> list[dict]:
    """관심 물건 낙찰 결과(bid_results 테이블 있을 때만)."""
    conn = get_connection()
    has = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='bid_results'"
    ).fetchone()
    out = []
    if has:
        rows = conn.execute(
            """SELECT b.item_id, b.winning_price, b.bidders, i.address_full
               FROM bid_results b JOIN items i ON i.id=b.item_id
               WHERE i.is_watched=1 AND b.created_at >= datetime('now','-2 day')"""
        ).fetchall()
        for r in rows:
            out.append({
                "alert_type": "bid_result", "item_id": r["item_id"],
                "title": f"🏆 낙찰결과 {str(r['address_full'] or '')[:24]}",
                "body": f"[낙찰결과] {r['address_full']}\n낙찰가 {r['winning_price']:,}만원 / 응찰 {r['bidders']}명",
                "priority": "medium", "payload": {},
            })
    conn.close()
    return out


def _trig_weekly_calendar(pref: dict) -> list[dict]:
    """다음 주 입찰 일정 캘린더."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, address_full, bid_date FROM items "
        "WHERE status='active' AND bid_date IS NOT NULL"
    ).fetchall()
    conn.close()
    upcoming = []
    for r in rows:
        d = days_until(r["bid_date"])
        if d is not None and 0 <= d <= 7:
            upcoming.append((d, r["bid_date"], r["address_full"]))
    if not upcoming:
        return []
    upcoming.sort()
    lines = "\n".join(f"D-{d} {bd} {str(a or '')[:24]}" for d, bd, a in upcoming[:15])
    return [{
        "alert_type": "weekly_calendar", "item_id": None,
        "title": f"📅 다음 주 입찰 일정 {len(upcoming)}건",
        "body": f"[다음 주 입찰 일정]\n{lines}",
        "priority": "low", "payload": {"count": len(upcoming)},
    }]


def _trig_monthly_report(pref: dict) -> list[dict]:
    """월간 리포트(지난 30일 추천 통계)."""
    conn = get_connection()
    n_rec = conn.execute(
        "SELECT COUNT(*) FROM scenario_results WHERE is_recommended=1"
    ).fetchone()[0]
    n_afford = conn.execute(
        "SELECT COUNT(DISTINCT item_id) FROM scenario_results WHERE affordable=1"
    ).fetchone()[0]
    conn.close()
    return [{
        "alert_type": "monthly_report", "item_id": None,
        "title": "📊 월간 리포트",
        "body": (f"[월간 리포트]\n추천 시나리오 {n_rec}건 / 자본 가능 물건 {n_afford}건"),
        "priority": "low", "payload": {"recommended": n_rec},
    }]


def _trig_market_signal(pref: dict) -> list[dict]:
    """관심 지역 시장 시그널(중립이 아닐 때)."""
    prof = _profile()
    regions = prof.get("interest_regions") or []
    out = []
    try:
        from modules.market import detect_signals
    except Exception:
        return out
    seen = set()
    for region in regions[:5]:
        parts = region.split()
        sido = parts[0] if parts else region
        sigungu = parts[1] if len(parts) > 1 else None
        key = (sido, sigungu)
        if key in seen:
            continue
        seen.add(key)
        sig = detect_signals(sido, sigungu)
        if sig["overall_signal"] != "neutral":
            out.append({
                "alert_type": "market_signal", "item_id": None,
                "title": f"📡 시장 시그널 [{region}] {sig['overall_signal']}",
                "body": f"[시장 시그널] {region}\n{sig['recommendation']}",
                "priority": "medium",
                "payload": {"signal": sig["overall_signal"], "region": region},
            })
    return out


def _trig_scenario_opportunity(pref: dict) -> list[dict]:
    """선호 시나리오(가중치 0.4+) 매칭 + 연환산 ROE 20%+."""
    prof = _profile()
    weights = prof.get("scenario_weights") or {}
    preferred = [s for s, w in weights.items() if w >= 0.4]
    if not preferred:
        return []
    placeholders = ",".join("?" for _ in preferred)
    conn = get_connection()
    rows = conn.execute(
        f"""SELECT s.item_id, s.scenario, s.annualized_roe, i.address_full
            FROM scenario_results s JOIN items i ON i.id=s.item_id
            WHERE s.scenario IN ({placeholders}) AND s.annualized_roe>=20
              AND s.affordable=1
            ORDER BY s.annualized_roe DESC LIMIT 10""",
        preferred,
    ).fetchall()
    conn.close()
    label = {"short_sale": "단타", "rental": "임대", "residence": "실거주"}
    out = []
    for r in rows:
        out.append({
            "alert_type": "scenario_opportunity", "item_id": r["item_id"],
            "title": f"💡 [{label.get(r['scenario'], r['scenario'])}] 기회 {str(r['address_full'] or '')[:20]}",
            "body": (f"[{label.get(r['scenario'], r['scenario'])} 기회] {r['address_full']}\n"
                     f"연환산 ROE {r['annualized_roe']:.0f}%"),
            "priority": "high", "payload": {"scenario": r["scenario"]},
        })
    return out


TRIGGERS = {
    "new_item_match": _trig_new_item_match,
    "price_drop": _trig_price_drop,
    "deadline_approaching": _trig_deadline,
    "bid_result": _trig_bid_result,
    "weekly_calendar": _trig_weekly_calendar,
    "monthly_report": _trig_monthly_report,
    "market_signal": _trig_market_signal,
    "scenario_opportunity": _trig_scenario_opportunity,
}
# 매일 실행: 1,2,3,4,7,8 / 주간: 5 / 월간: 6
DAILY_TRIGGERS = ["new_item_match", "price_drop", "deadline_approaching",
                  "bid_result", "market_signal", "scenario_opportunity"]


def check_triggers(triggers: list[str] | None = None, pref: dict | None = None) -> list[dict]:
    """지정 트리거(기본 8종 전부) 조건 검사 -> 알림 dict 리스트(dedupe_key 포함)."""
    init_db()
    pref = pref or get_preferences()
    names = triggers or list(TRIGGERS.keys())
    alerts: list[dict] = []
    for name in names:
        fn = TRIGGERS.get(name)
        if not fn:
            continue
        try:
            for a in fn(pref):
                a["dedupe_key"] = _dedupe_key(a["alert_type"], a.get("item_id"),
                                              a.get("payload"))
                alerts.append(a)
        except Exception as e:
            log.warning(f"[alert] 트리거 {name} 검사 실패: {e}")
    return alerts


def send_trigger(trigger_type: str, data: dict, dry_run: bool = False) -> dict:
    """단일 트리거 알림 발송(중복 방지). backtest_report 등 ad-hoc 포함."""
    init_db()
    if trigger_type == "backtest_report":
        m = data or {}
        alert = {
            "alert_type": "backtest_report", "item_id": None,
            "title": "📊 주간 백테스트 리포트",
            "body": (f"[백테스트] 정확도 {m.get('accuracy', 0)*100:.1f}% / "
                     f"F1 {m.get('f1_score', 0)*100:.1f}%\n"
                     f"추천 평균 ROE {m.get('avg_roe_recommended', 0):.1f}%"),
            "priority": "low", "payload": {"accuracy": m.get("accuracy")},
        }
    else:
        alert = {
            "alert_type": trigger_type, "item_id": data.get("item_id"),
            "title": data.get("title", f"[{trigger_type}]"),
            "body": data.get("body", ""),
            "priority": data.get("priority", "medium"),
            "payload": data.get("payload", {}),
        }
    pref = get_preferences()
    channels = pref.get("alert_channels") or [pref.get("alert_channel", "telegram")]
    text = f"<b>{alert['title']}</b>\n{alert['body']}"
    result = {"trigger": trigger_type, "sent": 0, "skipped": 0, "failed": 0}
    for ch in channels:
        key = _dedupe_key(alert["alert_type"], alert.get("item_id"), alert.get("payload"), channel=ch)
        entry = {**alert, "dedupe_key": key, "channel": ch}
        if _is_already_sent(key):
            result["skipped"] += 1
            continue
        if dry_run:
            continue
        ok = send_to_channels(text, channels=[ch]).get(ch, False)
        _record_alert(entry, "sent" if ok else "failed",
                      None if ok else f"send[{ch}]=False")
        result["sent" if ok else "failed"] += 1
    return result


def run_triggers(triggers: list[str] | None = None, pref: dict | None = None,
                 dry_run: bool = False) -> dict:
    """트리거 검사 + 채널 발송(중복 방지)."""
    pref = pref or get_preferences()
    channels = pref.get("alert_channels") or [pref.get("alert_channel", "telegram")]
    alerts = check_triggers(triggers, pref)
    sent = skipped = failed = 0
    for a in alerts:
        text = f"<b>{a['title']}</b>\n{a['body']}"
        for ch in channels:
            key = _dedupe_key(a["alert_type"], a.get("item_id"), a.get("payload"), channel=ch)
            entry = {**a, "dedupe_key": key, "channel": ch}
            if _is_already_sent(key):
                skipped += 1
                continue
            if dry_run:
                continue
            ok = send_to_channels(text, channels=[ch]).get(ch, False)
            _record_alert(entry, "sent" if ok else "failed",
                          None if ok else f"send[{ch}]=False")
            if ok:
                sent += 1
            else:
                failed += 1
    return {"collected": len(alerts), "sent": sent, "skipped": skipped,
            "failed": failed, "channels": channels}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="알림 트리거 실행")
    p.add_argument("--trigger", default=None,
                   help="단일 트리거 이름(없으면 일일 트리거 전체)")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if args.trigger == "backtest_report":
        try:
            from modules.backtest import run_backtest
            metrics = run_backtest("2024-01-01", "2024-07-01", save=False)
        except Exception:
            metrics = {}
        print(send_trigger("backtest_report", metrics, dry_run=args.dry_run))
    elif args.trigger:
        print(run_triggers([args.trigger], dry_run=args.dry_run))
    else:
        print(run_triggers(DAILY_TRIGGERS, dry_run=args.dry_run))
