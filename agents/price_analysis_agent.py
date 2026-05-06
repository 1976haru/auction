"""
agents/price_analysis_agent.py
실거래가 매칭 + 신뢰도 산정.
"""
from __future__ import annotations

from typing import Any

from core.database import get_connection
from core.logger import log
from modules.valuation.price_matcher import (
    match_price,
    save_price_analysis,
    get_price_analysis,
)


def analyze_item_price(item_id: int) -> dict:
    conn = get_connection()
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if not row:
        return {"error": f"item_id={item_id} 없음"}

    item = dict(row)
    result = match_price(item)
    save_price_analysis(item_id, result)
    log.info(
        f"[가격분석] item_id={item_id} avg6m={result['avg_price_6m']:,} "
        f"conf={result['confidence']}"
    )
    return result


def analyze_all() -> int:
    conn = get_connection()
    rows = conn.execute("SELECT id FROM items WHERE status='active'").fetchall()
    conn.close()
    n = 0
    for r in rows:
        analyze_item_price(int(r["id"]))
        n += 1
    return n


def get_summary(item_id: int) -> dict | None:
    return get_price_analysis(item_id)
