"""
agents/watchlist_agent.py
관심 등록 매물 (is_watched=1) 모아보기 + 일괄 처리.

기능
- list_watched_items(): 관심 매물 + 컨텍스트 (점수/등급/위험/시세/액션수/최근 변경)
- toggle_watch(item_id, value): 단일 토글
- bulk_set_watch(item_ids, watched): 다수 일괄 처리
- watch_summary(): 카운트 / 등급 분포 / 총 예상 차익 / 임박 매물수
"""
from __future__ import annotations

from typing import Any

from agents.compare_agent import _evaluate_score_for_item
from core.database import get_connection, init_db
from core.logger import log
from core.utils import days_until
from modules.profit_calculator import calc_profit
from modules.risk.keyword_analyzer import get_risk_flags, get_risk_level
from modules.valuation.price_matcher import get_price_analysis


def toggle_watch(item_id: int, value: bool) -> bool:
    """단일 매물 관심 등록/해제."""
    init_db()
    conn = get_connection()
    conn.execute("UPDATE items SET is_watched=? WHERE id=?",
                  (1 if value else 0, item_id))
    conn.commit()
    conn.close()
    return value


def bulk_set_watch(item_ids: list[int], watched: bool) -> int:
    """다수 매물 일괄 처리. 영향 받은 행 수 반환."""
    if not item_ids:
        return 0
    init_db()
    conn = get_connection()
    placeholders = ",".join("?" * len(item_ids))
    cur = conn.execute(
        f"UPDATE items SET is_watched=? WHERE id IN ({placeholders})",
        [1 if watched else 0, *item_ids],
    )
    affected = cur.rowcount
    conn.commit()
    conn.close()
    log.info(f"[watchlist] bulk_set_watch n={len(item_ids)} watched={watched} affected={affected}")
    return affected


def list_watched_items() -> list[dict]:
    """관심 매물 목록 + 컨텍스트."""
    init_db()
    conn = get_connection()
    rows = conn.execute("""
        SELECT i.* FROM items i
        WHERE i.is_watched = 1
        ORDER BY i.bid_date ASC, i.id DESC
    """).fetchall()
    conn.close()
    out = []
    for r in rows:
        item = dict(r)
        iid = item["id"]
        pa = get_price_analysis(iid) or {}
        market = pa.get("market_price_estimate") or int(item.get("appraisal_price", 0) * 0.95)
        pinfo = calc_profit(int(market or 0), int(item.get("min_bid_price", 0) or 0),
                            item.get("item_type", "아파트"))
        flags = get_risk_flags(iid)
        # 점수/등급
        score, grade = None, None
        rec = _query_latest_recommendation(iid)
        if rec:
            score, grade = rec["score"], rec["grade"]
        else:
            score, grade = _evaluate_score_for_item(iid)
        # 액션 / 변경 / 알림 수
        ac = _count(iid, "SELECT COUNT(*) FROM action_items WHERE item_id=? AND status='open'")
        changes = _count(iid, "SELECT COUNT(*) FROM change_events WHERE item_id=? "
                              "AND datetime(created_at) >= datetime('now','-7 day','localtime')")
        alerts = _count(iid, "SELECT COUNT(*) FROM alert_log WHERE item_id=? AND status='sent'")
        out.append({
            **item,
            "market_price": market,
            "profit_estimate": pinfo.get("profit"),
            "roi_estimate": pinfo.get("roi"),
            "risk_level": get_risk_level(iid),
            "max_severity": max((f["severity"] for f in flags), default=0),
            "flag_count": len(flags),
            "appraisal_inflated": bool(pa.get("appraisal_inflated")),
            "transaction_count": pa.get("transaction_count"),
            "score": score,
            "grade": grade,
            "open_actions": ac,
            "recent_changes_7d": changes,
            "alerts_sent": alerts,
            "bid_days_left": days_until(item.get("bid_date")),
        })
    return out


def _count(item_id: int, sql: str) -> int:
    conn = get_connection()
    row = conn.execute(sql, (item_id,)).fetchone()
    conn.close()
    return int(row[0] or 0)


def _query_latest_recommendation(item_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT score, grade FROM recommendation_results WHERE item_id=? "
        "ORDER BY id DESC LIMIT 1",
        (item_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def watch_summary() -> dict:
    """관심 매물 요약 통계."""
    items = list_watched_items()
    if not items:
        return {
            "count": 0,
            "by_grade": {},
            "total_profit_estimate": 0,
            "imminent_count": 0,
            "high_risk_count": 0,
            "inflated_count": 0,
            "open_actions_total": 0,
        }
    by_grade: dict[str, int] = {}
    total_profit = 0
    imminent = 0
    high_risk = 0
    inflated = 0
    open_actions = 0
    for it in items:
        grade = it.get("grade") or "?"
        by_grade[grade] = by_grade.get(grade, 0) + 1
        total_profit += it.get("profit_estimate") or 0
        bd = it.get("bid_days_left")
        if bd is not None and 0 <= bd <= 7:
            imminent += 1
        if it.get("risk_level") == "high":
            high_risk += 1
        if it.get("appraisal_inflated"):
            inflated += 1
        open_actions += it.get("open_actions") or 0
    return {
        "count": len(items),
        "by_grade": by_grade,
        "total_profit_estimate": total_profit,
        "imminent_count": imminent,
        "high_risk_count": high_risk,
        "inflated_count": inflated,
        "open_actions_total": open_actions,
    }
