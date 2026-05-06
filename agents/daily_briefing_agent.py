"""
agents/daily_briefing_agent.py
오늘의 브리핑 생성기.
"""
from __future__ import annotations

from typing import Any

from agents.recommendation_agent import recommend
from core.database import get_connection, init_db
from core.logger import log
from core.utils import now_iso, safe_json, today_str


def _stats() -> dict:
    init_db()
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM items WHERE status='active'").fetchone()[0]
    analyzed = conn.execute(
        "SELECT COUNT(DISTINCT item_id) FROM price_analyses"
    ).fetchone()[0]
    matched = conn.execute(
        "SELECT COUNT(*) FROM price_analyses WHERE transaction_count > 0"
    ).fetchone()[0]
    high_risk = conn.execute(
        "SELECT COUNT(DISTINCT item_id) FROM risk_flags WHERE risk_level='high'"
    ).fetchone()[0]
    docs = conn.execute("SELECT COUNT(*) FROM documents WHERE is_disclosed=0").fetchone()[0]
    conn.close()
    return {
        "total": total,
        "analyzed": analyzed,
        "matched": matched,
        "high_risk": high_risk,
        "undisclosed_docs": docs,
    }


def _delta_vs_yesterday(today: dict) -> dict:
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM daily_briefings WHERE run_date < ? ORDER BY run_date DESC LIMIT 1",
        (today_str(),),
    ).fetchone()
    conn.close()
    if not row:
        return {"new_items": today["total"], "note": "이전 브리핑 없음"}
    prev_total = row["total_items"] or 0
    return {
        "prev_total": prev_total,
        "delta": today["total"] - prev_total,
        "note": "어제 브리핑 대비",
    }


def generate_briefing(top_query: str = "시세차익 큰 물건 5개 찾아줘") -> dict:
    log.info("[briefing] 생성 시작")
    stats = _stats()
    rec = recommend(top_query, n=5)
    candidate = rec["total_found"]
    delta = _delta_vs_yesterday(stats)

    summary = (
        f"오늘의 경매·공매 브리핑입니다.\n"
        f"총 {stats['total']}건을 확인했고, 실거래가 매칭 가능 물건은 {stats['matched']}건입니다.\n"
        f"고위험 키워드 보유 물건은 {stats['high_risk']}건이며, "
        f"검토 후보는 {candidate}건입니다.\n"
        f"오늘 우선 볼 물건은 {len(rec['results'])}건입니다."
    )

    briefing = {
        "run_date": today_str(),
        "total_items": stats["total"],
        "analyzed_items": stats["analyzed"],
        "matched_items": stats["matched"],
        "candidate_items": candidate,
        "high_risk_items": stats["high_risk"],
        "top_picks": rec["results"],
        "summary": summary,
        "delta": delta,
        "generated_at": now_iso(),
    }

    init_db()
    conn = get_connection()
    conn.execute("""
        INSERT INTO daily_briefings
            (run_date, total_items, analyzed_items, matched_items,
             candidate_items, high_risk_items, top_picks_json,
             summary, delta_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        briefing["run_date"], stats["total"], stats["analyzed"], stats["matched"],
        candidate, stats["high_risk"], safe_json(briefing["top_picks"]),
        summary, safe_json(delta),
    ))
    conn.commit()
    conn.close()
    return briefing


def get_latest_briefing() -> dict | None:
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM daily_briefings ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None
