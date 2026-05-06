"""
agents/action_planner_agent.py
오늘 확인할 일(action items)을 자동 선정한다.
"""
from __future__ import annotations

from typing import Any

from core.database import get_connection, init_db
from core.logger import log
from core.utils import days_until, today_str
from modules.documents.mock_documents import get_item_documents
from modules.risk.keyword_analyzer import get_risk_flags
from modules.valuation.price_matcher import get_price_analysis


ACTION_TYPES = {
    "check_registry":       "등기부등본 원문 확인",
    "check_tenant":         "전입세대열람 확인",
    "field_visit":          "현장조사",
    "recalculate_bid":      "입찰가 재계산",
    "review_document":      "신규 공개 문서 확인",
    "watch_bid_date":       "입찰기일 임박 확인",
    "review_price_match":   "실거래가 매칭 재검토",
}


def _make_action(item_id: int, action_type: str, title: str,
                 detail: str, priority: str = "medium",
                 due_date: str | None = None) -> dict:
    return {
        "item_id": item_id, "action_type": action_type,
        "priority": priority, "title": title, "detail": detail,
        "due_date": due_date, "status": "open",
    }


def _build_for_item(item: dict) -> list[dict]:
    iid = item["id"]
    flags = get_risk_flags(iid)
    docs = get_item_documents(iid)
    pa = get_price_analysis(iid) or {}
    actions: list[dict] = []

    bd = days_until(item.get("bid_date"))
    if bd is not None and 0 <= bd <= 7:
        actions.append(_make_action(
            iid, "watch_bid_date", "입찰기일 임박",
            f"입찰기일까지 {bd}일 남음", priority="high",
            due_date=item.get("bid_date"),
        ))

    flag_types = {f["flag_type"] for f in flags}
    if {"임차인", "선순위임차인", "전입세대", "대항력"} & flag_types:
        actions.append(_make_action(
            iid, "check_tenant", "전입세대열람 확인",
            "임차인/대항력 관련 키워드 발견 - 전입세대열람 후 보증금 인수 여부 확인",
            priority="high",
        ))
    if any(f["risk_level"] == "high" for f in flags):
        actions.append(_make_action(
            iid, "check_registry", "등기부등본 원문 확인",
            "고위험 키워드 발견 - 최신 등기부등본 발급 후 권리관계 확인",
            priority="high",
        ))
    if any(d.get("is_disclosed") == 0 for d in docs):
        actions.append(_make_action(
            iid, "review_document", "신규 공개 문서 확인",
            "미공개 문서가 있어 공개 시 즉시 확인 필요", priority="medium",
        ))
    if pa.get("data_shortage"):
        actions.append(_make_action(
            iid, "review_price_match", "실거래가 매칭 재검토",
            "실거래가 데이터 부족 - 단지/지역 확장 매칭 재시도", priority="medium",
        ))
    if item.get("is_watched"):
        actions.append(_make_action(
            iid, "field_visit", "현장조사",
            "관심 등록 물건 - 현장 점검 권장", priority="medium",
        ))
    if pa.get("market_price_estimate") and item.get("min_bid_price"):
        gap = pa["market_price_estimate"] - item["min_bid_price"]
        if gap > 5000:
            actions.append(_make_action(
                iid, "recalculate_bid", "입찰가 재계산",
                f"시세-최저가 gap {gap:,}만원 - 입찰가 시뮬레이션 권장",
                priority="medium",
            ))
    return actions


def plan_actions() -> int:
    """전체 active 물건에 대해 오늘 할 일 생성."""
    init_db()
    conn = get_connection()
    rows = conn.execute("SELECT * FROM items WHERE status='active'").fetchall()
    conn.close()
    items = [dict(r) for r in rows]

    init_db()
    conn = get_connection()
    c = conn.cursor()
    # 오늘자 기존 항목은 일단 비워둠
    c.execute("DELETE FROM action_items WHERE date(created_at)=date('now','localtime')")
    total = 0
    for it in items:
        for a in _build_for_item(it):
            c.execute("""
                INSERT INTO action_items
                    (item_id, action_type, priority, title, detail, due_date, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                a["item_id"], a["action_type"], a["priority"],
                a["title"], a["detail"], a.get("due_date"), a["status"],
            ))
            total += 1
    conn.commit()
    conn.close()
    log.info(f"[action] {total}건 생성")
    return total


def list_today_actions(limit: int = 50) -> list[dict]:
    init_db()
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.*, i.address_full, i.item_type
        FROM action_items a
        LEFT JOIN items i ON i.id = a.item_id
        WHERE date(a.created_at) = date('now', 'localtime')
        ORDER BY CASE a.priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
