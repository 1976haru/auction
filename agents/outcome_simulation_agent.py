"""
agents/outcome_simulation_agent.py
추천 로직의 가상 성과를 검증하기 위한 mock 시뮬레이션.
"""
from __future__ import annotations

import random
from typing import Any

from core.database import get_connection, init_db
from core.logger import log
from core.utils import safe_json
from modules.profit_calculator import calc_profit
from modules.valuation.price_matcher import get_price_analysis


def simulate_for_item(item_id: int, scenario: str = "standard",
                      seed: int | None = None) -> dict:
    init_db()
    conn = get_connection()
    item = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if not item:
        return {"error": f"item_id={item_id} 없음"}
    item = dict(item)
    pa = get_price_analysis(item_id) or {}
    market = pa.get("market_price_estimate") or int(item.get("appraisal_price", 0) * 0.95)

    if scenario == "conservative":
        bid = int(item.get("min_bid_price", 0) * 1.0)
    elif scenario == "aggressive":
        bid = int(item.get("min_bid_price", 0) * 1.15)
    else:
        bid = int(item.get("min_bid_price", 0) * 1.05)

    rnd = random.Random(seed if seed is not None else item_id)
    sale_price = int(market * rnd.uniform(0.92, 1.08))

    info = calc_profit(sale_price, bid, item.get("item_type", "아파트"))
    result = {
        "item_id": item_id,
        "scenario_name": scenario,
        "simulated_bid_price": bid,
        "simulated_sale_price": sale_price,
        "simulated_total_cost": info["total_cost"],
        "simulated_profit": info["profit"],
        "simulated_profit_rate": info["roi"],
        "result_json": info,
    }
    _save(result)
    return result


def _save(r: dict) -> None:
    conn = get_connection()
    conn.execute("""
        INSERT INTO outcome_simulations
            (item_id, scenario_name, simulated_bid_price,
             simulated_sale_price, simulated_total_cost,
             simulated_profit, simulated_profit_rate, result_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        r["item_id"], r["scenario_name"], r["simulated_bid_price"],
        r["simulated_sale_price"], r["simulated_total_cost"],
        r["simulated_profit"], r["simulated_profit_rate"],
        safe_json(r["result_json"]),
    ))
    conn.commit()
    conn.close()


def simulate_top(top_picks: list[dict], scenario: str = "standard") -> list[dict]:
    out = []
    for r in top_picks:
        item = r.get("item", {})
        if not item.get("id"):
            continue
        out.append(simulate_for_item(item["id"], scenario=scenario))
    log.info(f"[simulation] {len(out)}건 ({scenario})")
    return out
