"""
agents/bidding_agent.py
입찰가 추천 에이전트 - 보수/기준/공격 시뮬레이션.
"""
from __future__ import annotations

from typing import Any

from core.database import get_connection
from core.logger import log
from modules.profit_calculator import calc_profit, recommend_bid_prices
from modules.valuation.price_matcher import get_price_analysis


def get_bid_recommendation(item_id: int, target_roi: float = 10.0) -> dict:
    conn = get_connection()
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if not row:
        return {"error": f"item_id={item_id} 없음"}

    item = dict(row)
    pa = get_price_analysis(item_id)
    market = (pa or {}).get("market_price_estimate") or int(item.get("appraisal_price", 0) * 0.95)

    if market <= 0:
        return {"error": "시세 데이터 없음", "note": "시세 매칭 후 다시 시도하세요."}

    bids = recommend_bid_prices(int(market), item.get("item_type", "아파트"), target_roi)
    for key in ("conservative", "standard", "aggressive"):
        bid_price = bids[key]["price"]
        info = calc_profit(int(market), bid_price, item.get("item_type", "아파트"))
        bids[key].update({
            "profit": info["profit"], "roi": info["roi"], "total_cost": info["total_cost"],
        })

    return {
        "item_id": item_id,
        "address": item.get("address_full", "미상"),
        "item_type": item.get("item_type", "미상"),
        "appraisal": item.get("appraisal_price", 0),
        "min_bid": item.get("min_bid_price", 0),
        "market_price": int(market),
        "bids": bids,
        "disclaimer": "입찰가는 추정치이며 실제 결정은 본인 판단입니다.",
    }


def format_bid_report(rec: dict) -> str:
    if "error" in rec:
        return f"[X] 오류: {rec['error']}"
    bids = rec["bids"]
    return (
        f"[{rec['item_type']}] {rec['address']}\n"
        f"감정가 {rec['appraisal']:,}만원 | 최저가 {rec['min_bid']:,}만원\n"
        f"추정 시세 {rec['market_price']:,}만원\n"
        f"보수 {bids['conservative']['price']:,}만원 (ROI {bids['conservative']['roi']:.1f}%)\n"
        f"기준 {bids['standard']['price']:,}만원 (ROI {bids['standard']['roi']:.1f}%)\n"
        f"공격 {bids['aggressive']['price']:,}만원 (ROI {bids['aggressive']['roi']:.1f}%)\n"
        f"{rec['disclaimer']}"
    )
