"""
agents/compare_agent.py
물건 비교용 데이터 수집기. 2-5개 매물의 통계를 동일 스키마로 정리해 반환한다.

각 매물의 비교 항목
- 기본정보: 주소, 종류, 면적, 층, 매각기일, 유찰
- 가격:    감정가, 최저가, 추정 시세, 최저가/시세 비율, 거래량, 시세 신뢰도
- 위험:    등급(low/medium/high), 키워드 수, 핵심 키워드 (top 3)
- 신뢰도:  시세/권리/문서/주소/종합
- 손익:    예상 차익, 예상 ROI, 보수/기준/공격 입찰가
- 추천:    종합 점수, 등급, A/B/C/D/X
- 액션:    오늘 할 일 수, 추가 확인사항 수
"""
from __future__ import annotations

from typing import Any

from agents.bidding_agent import get_bid_recommendation
from agents.confidence_agent import get_confidence
from agents.risk_checklist_agent import get_checklist
from core.database import get_connection, init_db
from core.utils import days_until
from modules.profit_calculator import calc_profit
from modules.risk.keyword_analyzer import get_risk_flags, get_risk_level
from modules.valuation.price_matcher import get_price_analysis


def _evaluate_score_for_item(iid: int) -> tuple[float | None, str | None]:
    """recommendation_results 에 없으면 즉시 점수 계산. 비교용 fallback."""
    try:
        from agents.backtest_agent import evaluate_all_items
        for e in evaluate_all_items():
            if e["item_id"] == iid:
                return float(e["score"]), str(e["grade"])
    except Exception:
        pass
    return None, None


def collect_compare_data(item_ids: list[int]) -> list[dict]:
    """item_ids 순서대로 비교 데이터를 반환한다."""
    if not item_ids:
        return []
    init_db()
    conn = get_connection()
    placeholders = ",".join("?" * len(item_ids))
    rows = conn.execute(
        f"SELECT * FROM items WHERE id IN ({placeholders})", item_ids
    ).fetchall()
    by_id = {r["id"]: dict(r) for r in rows}

    out = []
    for iid in item_ids:
        item = by_id.get(iid)
        if not item:
            continue
        pa = get_price_analysis(iid) or {}
        flags = get_risk_flags(iid)
        conf = get_confidence(iid) or {}
        cl = get_checklist(iid)
        market = pa.get("market_price_estimate") or int(item.get("appraisal_price", 0) * 0.95)
        pinfo = calc_profit(int(market or 0), int(item.get("min_bid_price", 0) or 0),
                            item.get("item_type", "아파트"))
        bid = get_bid_recommendation(iid)
        bid_days = days_until(item.get("bid_date"))

        # 추천 점수 (가장 최근). 없으면 backtest_agent 의 evaluate_all_items 로 보강.
        rec_row = conn.execute("""
            SELECT score, grade FROM recommendation_results
            WHERE item_id=? ORDER BY id DESC LIMIT 1
        """, (iid,)).fetchone()
        if rec_row:
            score = rec_row["score"]
            grade = rec_row["grade"]
        else:
            score, grade = _evaluate_score_for_item(iid)
        action_count = conn.execute(
            "SELECT COUNT(*) FROM action_items WHERE item_id=?", (iid,)
        ).fetchone()[0]

        out.append({
            "id": iid,
            "address_full": item.get("address_full"),
            "item_type": item.get("item_type"),
            "area_m2": item.get("area_m2"),
            "floor": item.get("floor"),
            "total_floor": item.get("total_floor"),
            "bid_date": item.get("bid_date"),
            "bid_days_left": bid_days,
            "fail_count": item.get("fail_count"),
            "is_watched": bool(item.get("is_watched")),
            "source": item.get("source"),

            "appraisal_price": item.get("appraisal_price"),
            "min_bid_price": item.get("min_bid_price"),
            "market_price_estimate": market,
            "minimum_to_market_ratio": pa.get("minimum_to_market_ratio"),
            "appraisal_to_market_ratio": pa.get("appraisal_to_market_ratio"),
            "transaction_count": pa.get("transaction_count"),
            "price_confidence": pa.get("confidence"),
            "appraisal_inflated": bool(pa.get("appraisal_inflated")),

            "risk_level": get_risk_level(iid),
            "risk_flag_count": len(flags),
            "top_flags": [f["flag_type"] for f in flags[:3]],
            "max_severity": max((f["severity"] for f in flags), default=0),

            "price_conf_num": conf.get("price_confidence"),
            "legal_conf_num": conf.get("legal_risk_confidence"),
            "doc_conf_num": conf.get("document_confidence"),
            "addr_conf_num": conf.get("address_match_confidence"),
            "overall_conf_num": conf.get("overall_confidence"),

            "profit_estimate": pinfo.get("profit"),
            "roi_estimate": pinfo.get("roi"),
            "total_cost": pinfo.get("total_cost"),
            "bid_conservative": bid.get("bids", {}).get("conservative", {}).get("price") if "bids" in bid else None,
            "bid_standard": bid.get("bids", {}).get("standard", {}).get("price") if "bids" in bid else None,
            "bid_aggressive": bid.get("bids", {}).get("aggressive", {}).get("price") if "bids" in bid else None,

            "score": score,
            "grade": grade,

            "action_count": action_count,
            "checklist_count": len(cl),
        })
    conn.close()
    return out


_HIGHER_BETTER = {
    "profit_estimate", "roi_estimate", "transaction_count",
    "price_conf_num", "legal_conf_num", "doc_conf_num",
    "addr_conf_num", "overall_conf_num", "score",
}
_LOWER_BETTER = {
    "min_bid_price", "minimum_to_market_ratio", "appraisal_to_market_ratio",
    "max_severity", "risk_flag_count", "fail_count", "total_cost",
    "bid_days_left",
}


def annotate_best_worst(rows: list[dict]) -> dict[str, dict[int, str]]:
    """각 비교 항목별로 best/worst id 표시.

    Returns:
        { field: { item_id: 'best'|'worst' } }
    """
    if len(rows) < 2:
        return {}
    out: dict[str, dict[int, str]] = {}
    for field in _HIGHER_BETTER | _LOWER_BETTER:
        values = [(r["id"], r.get(field)) for r in rows if r.get(field) is not None]
        if len(values) < 2:
            continue
        higher_is_better = field in _HIGHER_BETTER
        # bid_days_left: 음수 무효화
        if field == "bid_days_left":
            values = [(i, v) for i, v in values if v is not None and v >= 0]
            if len(values) < 2:
                continue
        best_id, best_val = (max if higher_is_better else min)(values, key=lambda x: x[1])
        worst_id, worst_val = (min if higher_is_better else max)(values, key=lambda x: x[1])
        if best_id == worst_id:
            continue
        out.setdefault(field, {})[best_id] = "best"
        out.setdefault(field, {})[worst_id] = "worst"
    return out


def summarize_compare(rows: list[dict]) -> dict:
    """비교 결과를 한줄 요약."""
    if not rows:
        return {"summary": "비교 대상 없음"}
    sorted_by_score = sorted(rows, key=lambda r: r.get("score") or 0, reverse=True)
    sorted_by_profit = sorted(rows, key=lambda r: r.get("profit_estimate") or 0, reverse=True)
    sorted_by_risk = sorted(rows, key=lambda r: r.get("max_severity") or 0)
    best_overall = sorted_by_score[0]
    return {
        "best_score": {
            "id": best_overall["id"],
            "address": best_overall["address_full"],
            "score": best_overall.get("score"),
            "grade": best_overall.get("grade"),
        },
        "best_profit": {
            "id": sorted_by_profit[0]["id"],
            "address": sorted_by_profit[0]["address_full"],
            "profit": sorted_by_profit[0].get("profit_estimate"),
        },
        "lowest_risk": {
            "id": sorted_by_risk[0]["id"],
            "address": sorted_by_risk[0]["address_full"],
            "max_severity": sorted_by_risk[0].get("max_severity"),
        },
        "summary": (
            f"종합 추천: {best_overall['address_full']} (등급 "
            f"{best_overall.get('grade')}, 점수 {best_overall.get('score')})"
        ),
    }
