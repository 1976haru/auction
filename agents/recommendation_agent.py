"""
agents/recommendation_agent.py
추천 오케스트레이터.
- intent 정규화 -> 후보 조회 -> 시세/위험/신뢰도/선호 점수화 -> 정렬 -> 등급 부여
- 각 결과는 점수 근거와 등급을 포함한다.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from agents.confidence_agent import compute_confidence, get_confidence
from agents.intent_understanding_agent import understand
from agents.legal_risk_agent import analyze_item_risk
from agents.natural_language_agent import save_task
from agents.preference_learning_agent import (
    get_preferences,
    preference_match_score,
)
from agents.price_analysis_agent import analyze_item_price
from core.database import get_connection, init_db
from core.logger import log
from core.utils import days_until, safe_json
from modules.profit_calculator import calc_profit
from modules.risk.keyword_analyzer import get_risk_flags, get_risk_level


RISK_LEVEL_RANK = {"low": 1, "medium": 2, "high": 3, "unknown": 2, "very_low": 0}


def _filter_by_intent(items: list[dict], intent: dict, pref: dict) -> list[dict]:
    """후보 1차 필터링. 사용자 선호의 min_profit/min_roi 도 함께 적용."""
    f = intent.get("filters", {})
    risk_max = f.get("risk_level_max", "medium")
    risk_max_rank = RISK_LEVEL_RANK.get(risk_max, 2)
    excludes = set((f.get("exclude_keywords") or []) + (pref.get("exclude_keywords") or []))
    bid_within = f.get("bid_within_days")
    include_high = f.get("include_high_risk", False)
    enforce_pref = f.get("enforce_preferences", True)

    regions = intent.get("regions") or intent.get("regions_default") or []
    types = intent.get("item_types") or intent.get("item_types_default") or []
    src_types = intent.get("source_types") or ["auction", "public_sale"]

    min_profit = pref.get("min_profit_man", 0) if enforce_pref else 0
    min_roi = pref.get("min_roi", 0) if enforce_pref else 0  # 0~1 비율

    out = []
    for it in items:
        if it.get("source") not in src_types:
            continue
        if regions and not any(r in (it.get("address_full") or "") for r in regions):
            continue
        if types and it.get("item_type") not in types:
            continue
        rl = it.get("_risk_level", "unknown")
        if not include_high and RISK_LEVEL_RANK.get(rl, 2) > risk_max_rank:
            continue
        if excludes:
            flag_types = {fl["flag_type"] for fl in it.get("_flags", [])}
            if flag_types & excludes:
                continue
        if bid_within is not None:
            d = days_until(it.get("bid_date"))
            if d is None or d < 0 or d > bid_within:
                continue

        # 감정가 거품 / 최저가가 시세 이상 -> 후보 제외 (high-risk 옵션 켜져도 적용)
        pa = it.get("_price") or {}
        if pa.get("appraisal_inflated"):
            it["_excluded_reason"] = "감정가/최저가가 시세보다 비정상적으로 높음"
            continue

        # 사용자 선호 최저 수익 임계
        profit = it.get("_profit_info", {}).get("profit", 0)
        roi = it.get("_profit_info", {}).get("roi", 0)
        if min_profit and profit < min_profit:
            continue
        if min_roi and roi / 100.0 < min_roi:
            continue

        out.append(it)
    return out


def _grade_for(score: float, has_critical_gap: bool) -> str:
    if has_critical_gap:
        return "X"
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def _score_item(item: dict, profit_info: dict, conf: dict, pref: dict) -> dict:
    profit = profit_info.get("profit", 0)
    roi = profit_info.get("roi", 0)
    risk_level = item.get("_risk_level", "unknown")
    bid_days = days_until(item.get("bid_date"))
    price_analysis = item.get("_price") or {}

    # 1) 시세차익 (35점)
    profit_pts = 0
    if profit > 0:
        profit_pts = min(35, profit / 1000)
    # 2) 시세 신뢰도 (15점)
    price_conf_pts = (conf.get("price_confidence", 0) or 0) * 15
    # 3) 위험도 (20점)
    risk_pts = {"low": 20, "medium": 12, "high": 4}.get(risk_level, 10)
    # 4) 입찰기일 (10점)
    if bid_days is None:
        bid_pts = 4
    elif bid_days < 0:
        bid_pts = 0
    elif bid_days <= 7:
        bid_pts = 10
    elif bid_days <= 14:
        bid_pts = 7
    elif bid_days <= 30:
        bid_pts = 5
    else:
        bid_pts = 3
    # 5) 사용자 선호 (10점)
    pref_pts, pref_reasons = preference_match_score(item, pref)
    # 6) 데이터 완성도 (10점)
    data_pts = (conf.get("overall_confidence", 0) or 0) * 10

    total = round(profit_pts + price_conf_pts + risk_pts + bid_pts + pref_pts + data_pts, 2)

    # 등급 X 자동 부여 조건 (어느 하나라도 해당)
    market = profit_info.get("market_price", 0)
    min_bid = item.get("min_bid_price", 0)
    critical_reasons: list[str] = []
    if market <= 0:
        critical_reasons.append("시세 추정 실패")
    if price_analysis.get("appraisal_inflated"):
        critical_reasons.append("감정가/최저가가 시세보다 비정상적으로 높음")
    if min_bid and market and min_bid > market:
        critical_reasons.append(f"최저가({min_bid:,})가 추정 시세({market:,})보다 높음")
    if risk_level == "high" and profit < 5000:
        critical_reasons.append("고위험 + 차익 부족")
    if profit < 0:
        critical_reasons.append("최저가 입찰조차 음수 차익")

    grade = "X" if critical_reasons else _grade_for(total, False)

    breakdown = {
        "profit_pts": round(profit_pts, 2),
        "price_conf_pts": round(price_conf_pts, 2),
        "risk_pts": round(risk_pts, 2),
        "bid_pts": round(bid_pts, 2),
        "pref_pts": round(pref_pts, 2),
        "data_pts": round(data_pts, 2),
        "preference_reasons": pref_reasons,
        "critical_reasons": critical_reasons,
    }
    return {"score": total, "grade": grade, "breakdown": breakdown}


def _enrich(items: list[dict]) -> list[dict]:
    """각 item에 _flags, _risk_level, _confidence, _price 등을 붙인다."""
    enriched = []
    for it in items:
        iid = it["id"]
        # 분석 결과 보장 - 없으면 즉시 계산
        if not get_confidence(iid):
            analyze_item_price(iid)
            analyze_item_risk(iid)
            compute_confidence(iid)
        it["_flags"] = get_risk_flags(iid)
        it["_risk_level"] = get_risk_level(iid)
        it["_confidence"] = get_confidence(iid) or {}
        # 시세
        from modules.valuation.price_matcher import get_price_analysis
        pa = get_price_analysis(iid) or {}
        it["_price"] = pa
        market = pa.get("market_price_estimate") or int(it.get("appraisal_price", 0) * 0.95)
        it["_market_price"] = market
        it["_profit_info"] = calc_profit(int(market), int(it.get("min_bid_price", 0) or 0),
                                          it.get("item_type", "아파트"))
        enriched.append(it)
    return enriched


def _sort(items: list[dict], sort_by: str) -> list[dict]:
    if sort_by == "expected_profit":
        return sorted(items, key=lambda x: x["_profit_info"]["profit"], reverse=True)
    if sort_by == "expected_roi":
        return sorted(items, key=lambda x: x["_profit_info"]["roi"], reverse=True)
    if sort_by == "risk":
        return sorted(items, key=lambda x: RISK_LEVEL_RANK.get(x["_risk_level"], 2))
    if sort_by == "bid_date":
        return sorted(items, key=lambda x: days_until(x.get("bid_date")) or 9999)
    return items


def recommend(user_input: str, n: int | None = None) -> dict:
    init_db()
    intent = understand(user_input)
    task_id = save_task(user_input, intent)
    pref = get_preferences()
    limit = n or intent.get("limit", 5)
    sort_by = intent.get("sort_by", "expected_profit")

    log.info(f"[추천] task={task_id} intent={json.dumps(intent, ensure_ascii=False)[:150]}")

    conn = get_connection()
    rows = conn.execute("SELECT * FROM items WHERE status='active'").fetchall()
    conn.close()
    items = [dict(r) for r in rows]
    items = _enrich(items)
    items = _filter_by_intent(items, intent, pref)
    items = _sort(items, sort_by)

    results = []
    for it in items:
        scoring = _score_item(it, it["_profit_info"], it["_confidence"], pref)
        results.append({
            "item": {k: v for k, v in it.items() if not k.startswith("_")},
            "profit_estimate": it["_profit_info"]["profit"],
            "roi_estimate": it["_profit_info"]["roi"],
            "risk_score": max((f["severity"] for f in it["_flags"]), default=0),
            "risk_level": it["_risk_level"],
            "market_price": it["_market_price"],
            "confidence": it["_confidence"],
            "score": scoring["score"],
            "grade": scoring["grade"],
            "score_breakdown": scoring["breakdown"],
            "cost_breakdown": it["_profit_info"]["cost_breakdown"],
        })

    # 점수 정렬
    results.sort(key=lambda r: r["score"], reverse=True)
    top = results[:limit]
    _save_results(task_id, top)

    return {
        "task_id": task_id,
        "intent": intent,
        "preferences": pref,
        "results": top,
        "total_found": len(results),
    }


def _save_results(task_id: int, results: list[dict]) -> None:
    init_db()
    conn = get_connection()
    c = conn.cursor()
    for i, r in enumerate(results, 1):
        c.execute("""
            INSERT INTO recommendation_results
                (task_id, item_id, rank, score, grade,
                 profit_estimate, roi_estimate, score_breakdown)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id, r["item"]["id"], i, r["score"], r["grade"],
            r["profit_estimate"], r["roi_estimate"],
            safe_json(r["score_breakdown"]),
        ))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "시세차익 가장 큰 물건 5개 찾아줘"
    res = recommend(q)
    print(f"\n=== 추천 (총 {res['total_found']}건 중 상위 {len(res['results'])}건) ===")
    for i, r in enumerate(res["results"], 1):
        item = r["item"]
        print(
            f"{i}. [{r['grade']}] {item.get('address_full', '미상')[:40]} | "
            f"차익 {r['profit_estimate']:,}만원 | "
            f"ROI {r['roi_estimate']:.1f}% | "
            f"위험 {r['risk_level']} | 점수 {r['score']:.1f}"
        )
