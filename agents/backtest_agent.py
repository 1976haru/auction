"""
agents/backtest_agent.py
추천 정확도 백테스트.

방법
- recommendation_results (예측: profit_estimate / roi_estimate / grade) 와
  outcome_simulations (실제 mock 결과: simulated_profit / simulated_profit_rate)
  를 item_id 기준 매칭해서 그룹별 통계 계산.
- mock 환경에서는 simulated 값이 "실제"를 대신한다. 실제 API 연결 후
  실 낙찰가/매도가가 들어오면 동일 로직으로 검증 가능.

산출 통계 (등급별)
- count / win_rate(profit > 0) / mean_actual_profit / median_actual_profit
- mean_actual_roi / mean_pred_profit / mean_pred_error (|pred - actual|)
- mean_relative_error (예측 대비 실제 차이의 비율)
"""
from __future__ import annotations

import json
import statistics
from typing import Any

from agents.outcome_simulation_agent import simulate_for_item
from core.database import get_connection, init_db
from core.logger import log
from core.utils import now_iso, safe_json


SCENARIO_FOR_BACKTEST = "standard"


def evaluate_all_items() -> list[dict]:
    """모든 active 매물에 대해 점수/등급을 계산해서 반환.
    recommendation_results 에 저장하지 않고 메모리만 사용.
    user preferences 의 min_profit/min_roi 필터는 적용하지 않는다 (전체 분포 평가)."""
    from agents.preference_learning_agent import get_preferences
    from agents.recommendation_agent import (
        _enrich,
        _filter_by_intent,
        _score_item,
    )
    from core.database import get_connection
    from modules.profit_calculator import calc_profit

    init_db()
    conn = get_connection()
    rows = conn.execute("SELECT * FROM items WHERE status='active'").fetchall()
    conn.close()
    items = [dict(r) for r in rows]
    items = _enrich(items)

    pref = get_preferences()
    # 백테스트에서는 user preference 강제 임계값을 끈다 (전수 평가)
    intent = {
        "intent": "backtest_all",
        "source_types": ["auction", "public_sale"],
        "regions": [], "item_types": [],
        "filters": {
            "risk_level_max": "high",
            "exclude_keywords": [],
            "include_high_risk": True,
            "only_active": True,
            "bid_within_days": None,
            "has_market_price": False,
            "enforce_preferences": False,
        },
    }
    items = _filter_by_intent(items, intent, pref)

    out = []
    for it in items:
        scoring = _score_item(it, it["_profit_info"], it["_confidence"], pref)
        out.append({
            "item_id": it["id"],
            "address_full": it.get("address_full"),
            "item_type": it.get("item_type"),
            "grade": scoring["grade"],
            "score": scoring["score"],
            "profit_estimate": it["_profit_info"]["profit"],
            "roi_estimate": it["_profit_info"]["roi"],
            "risk_level": it["_risk_level"],
            "market_price": it["_market_price"],
            "min_bid_price": it.get("min_bid_price"),
        })
    return out


def _fetch_pairs(scenario: str = SCENARIO_FOR_BACKTEST,
                 only_grades: list[str] | None = None) -> list[dict]:
    """예측-실제 짝을 반환. 동일 item_id 의 가장 최근 시뮬 1건과 짝지움."""
    init_db()
    conn = get_connection()
    grade_filter = ""
    params: list = [scenario]
    if only_grades:
        placeholders = ",".join("?" * len(only_grades))
        grade_filter = f" AND r.grade IN ({placeholders})"
        params.extend(only_grades)
    rows = conn.execute(f"""
        SELECT
            r.item_id, r.grade, r.score, r.profit_estimate, r.roi_estimate,
            i.address_full, i.item_type, i.source,
            s.simulated_bid_price, s.simulated_sale_price,
            s.simulated_profit, s.simulated_profit_rate
        FROM recommendation_results r
        LEFT JOIN items i ON i.id = r.item_id
        LEFT JOIN (
            SELECT item_id, scenario_name, simulated_bid_price, simulated_sale_price,
                   simulated_profit, simulated_profit_rate,
                   ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY id DESC) AS rn
            FROM outcome_simulations
            WHERE scenario_name = ?
        ) s ON s.item_id = r.item_id AND s.rn = 1
        WHERE s.simulated_profit IS NOT NULL
          {grade_filter}
        ORDER BY r.grade, r.score DESC
    """, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def ensure_simulations_for_recs(scenario: str = SCENARIO_FOR_BACKTEST) -> int:
    """추천 매물 중 시뮬이 없는 것들에 대해 자동 생성."""
    init_db()
    conn = get_connection()
    rows = conn.execute(f"""
        SELECT DISTINCT r.item_id
        FROM recommendation_results r
        WHERE r.item_id NOT IN (
            SELECT DISTINCT item_id FROM outcome_simulations
            WHERE scenario_name = ?
        )
    """, (scenario,)).fetchall()
    conn.close()
    n = 0
    for r in rows:
        simulate_for_item(r["item_id"], scenario=scenario, seed=r["item_id"])
        n += 1
    log.info(f"[backtest] {n}건 시뮬레이션 자동 생성")
    return n


def _stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "mean": round(statistics.mean(values), 2),
        "median": round(statistics.median(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "stdev": round(statistics.stdev(values), 2) if len(values) > 1 else 0.0,
    }


def _group_by_grade(pairs: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for p in pairs:
        grade = p.get("grade") or "?"
        out.setdefault(grade, []).append(p)
    return out


def ensure_simulations_for_items(item_ids: list[int],
                                  scenario: str = SCENARIO_FOR_BACKTEST) -> int:
    """주어진 매물에 시뮬이 없으면 생성."""
    init_db()
    conn = get_connection()
    placeholders = ",".join("?" * len(item_ids)) if item_ids else "''"
    rows = conn.execute(f"""
        SELECT DISTINCT item_id FROM outcome_simulations
        WHERE scenario_name = ? AND item_id IN ({placeholders})
    """, [scenario, *item_ids]).fetchall() if item_ids else []
    have = {r["item_id"] for r in rows}
    conn.close()
    n = 0
    for iid in item_ids:
        if iid in have:
            continue
        simulate_for_item(iid, scenario=scenario, seed=iid)
        n += 1
    log.info(f"[backtest] {n}건 시뮬레이션 자동 생성 (item-level)")
    return n


def backtest_all_items(scenario: str = SCENARIO_FOR_BACKTEST) -> dict:
    """전체 매물 단위 백테스트 (recommendation_results 에 의존하지 않음).
    수많은 데이터 포인트를 모아 등급별 통계의 신뢰성을 높임."""
    evaluations = evaluate_all_items()
    item_ids = [e["item_id"] for e in evaluations]
    ensure_simulations_for_items(item_ids, scenario)

    # 시뮬 결과를 다시 fetch
    init_db()
    conn = get_connection()
    placeholders = ",".join("?" * len(item_ids)) if item_ids else "''"
    sims = {} if not item_ids else {
        r["item_id"]: dict(r) for r in conn.execute(f"""
            SELECT item_id, simulated_profit, simulated_profit_rate,
                   simulated_bid_price, simulated_sale_price
            FROM outcome_simulations
            WHERE scenario_name = ? AND item_id IN ({placeholders})
        """, [scenario, *item_ids]).fetchall()
    }
    conn.close()

    pairs = []
    for e in evaluations:
        s = sims.get(e["item_id"])
        if not s:
            continue
        pairs.append({**e, **{
            "simulated_profit": s["simulated_profit"],
            "simulated_profit_rate": s["simulated_profit_rate"],
            "simulated_bid_price": s["simulated_bid_price"],
            "simulated_sale_price": s["simulated_sale_price"],
        }})

    return _build_report(pairs, scenario, "all_items")


def backtest(scenario: str = SCENARIO_FOR_BACKTEST,
             only_grades: list[str] | None = None) -> dict:
    """등급별 적중률/평균/오차 통계 - recommendation_results 기반 (이전 추천 매물만)."""
    ensure_simulations_for_recs(scenario)
    pairs = _fetch_pairs(scenario, only_grades=only_grades)
    return _build_report(pairs, scenario, "recommended")


def _build_report(pairs: list[dict], scenario: str, mode: str) -> dict:
    grouped = _group_by_grade(pairs)

    overall = {
        "scenario": scenario,
        "mode": mode,
        "total_pairs": len(pairs),
        "grades": {},
    }

    for grade in sorted(grouped.keys()):
        rows = grouped[grade]
        actual_profits = [float(r["simulated_profit"]) for r in rows]
        pred_profits = [float(r["profit_estimate"] or 0) for r in rows]
        actual_rois = [float(r["simulated_profit_rate"] or 0) for r in rows]
        wins = sum(1 for p in actual_profits if p > 0)
        errors = [abs(pp - ap) for pp, ap in zip(pred_profits, actual_profits)]
        rel_errors = [
            (abs(pp - ap) / max(abs(ap), 1)) if ap != 0 else 0
            for pp, ap in zip(pred_profits, actual_profits)
        ]
        overall["grades"][grade] = {
            "count": len(rows),
            "win_rate": round(wins / len(rows) * 100, 1) if rows else 0.0,
            "actual_profit": _stats(actual_profits),
            "actual_roi": _stats(actual_rois),
            "pred_profit": _stats(pred_profits),
            "abs_error": _stats(errors),
            "relative_error_pct": _stats([r * 100 for r in rel_errors]),
        }

    # 전체 통계 추가
    if pairs:
        all_actual = [float(r["simulated_profit"]) for r in pairs]
        all_pred = [float(r["profit_estimate"] or 0) for r in pairs]
        all_errors = [abs(p - a) for p, a in zip(all_pred, all_actual)]
        wins = sum(1 for p in all_actual if p > 0)
        overall["overall"] = {
            "count": len(pairs),
            "win_rate": round(wins / len(pairs) * 100, 1),
            "actual_profit": _stats(all_actual),
            "abs_error": _stats(all_errors),
        }

    return overall


def grade_ordering_check(report: dict) -> dict:
    """A > B > C 등급 순서대로 평균 actual_profit이 떨어지는지 검증."""
    grades = ["A", "B", "C", "D", "X"]
    means: dict[str, float] = {}
    for g in grades:
        gd = report["grades"].get(g)
        if gd and gd["actual_profit"].get("count", 0) > 0:
            means[g] = gd["actual_profit"]["mean"]
    valid = [(g, means[g]) for g in grades if g in means]
    monotonic = all(valid[i][1] >= valid[i + 1][1] for i in range(len(valid) - 1))
    return {
        "monotonic_decreasing": monotonic,
        "grade_means": means,
        "note": "A->B->C->D 순서로 평균 실제 수익이 단조감소해야 추천 로직이 등급을 유효하게 구분한다고 볼 수 있다.",
    }


def fetch_pred_actual_pairs(scenario: str = SCENARIO_FOR_BACKTEST,
                            limit: int = 500) -> list[dict]:
    """대시보드 산점도용 (예측, 실제) 쌍 반환."""
    pairs = _fetch_pairs(scenario)
    return pairs[:limit]


# ── 시계열 추적 (backtest_runs 테이블) ─────────────────────────────


def save_backtest_run(report: dict, ordering: dict | None = None) -> int:
    """백테스트 결과를 backtest_runs 테이블에 누적 저장."""
    init_db()
    grades = report.get("grades", {})
    overall = report.get("overall", {})

    def gd(g, key):
        s = grades.get(g) or {}
        if key == "count":
            return s.get("count")
        if key == "winrate":
            return s.get("win_rate")
        if key == "mean":
            ap = s.get("actual_profit") or {}
            return ap.get("mean")
        return None

    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO backtest_runs (
            run_date, scenario, mode,
            total_pairs, overall_win_rate, overall_mean_profit,
            a_count, a_mean, a_winrate,
            b_count, b_mean, b_winrate,
            c_count, c_mean, c_winrate,
            d_count, d_mean, d_winrate,
            x_count, x_mean, x_winrate,
            monotonic_decreasing,
            report_json, ordering_json
        ) VALUES (
            datetime('now','localtime'), ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?,
            ?, ?
        )
    """, (
        report.get("scenario"), report.get("mode"),
        report.get("total_pairs"),
        overall.get("win_rate"),
        (overall.get("actual_profit") or {}).get("mean"),
        gd("A", "count"), gd("A", "mean"), gd("A", "winrate"),
        gd("B", "count"), gd("B", "mean"), gd("B", "winrate"),
        gd("C", "count"), gd("C", "mean"), gd("C", "winrate"),
        gd("D", "count"), gd("D", "mean"), gd("D", "winrate"),
        gd("X", "count"), gd("X", "mean"), gd("X", "winrate"),
        1 if (ordering or {}).get("monotonic_decreasing") else 0,
        safe_json(report), safe_json(ordering or {}),
    ))
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    log.info(f"[backtest] run #{rid} saved (scenario={report.get('scenario')}, mode={report.get('mode')})")
    return int(rid)


def list_backtest_runs(limit: int = 50, scenario: str | None = None,
                        mode: str | None = None) -> list[dict]:
    """누적된 백테스트 기록 (최신순)."""
    init_db()
    conn = get_connection()
    q = "SELECT * FROM backtest_runs WHERE 1=1"
    params: list = []
    if scenario:
        q += " AND scenario = ?"
        params.append(scenario)
    if mode:
        q += " AND mode = ?"
        params.append(mode)
    q += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def history_chart_series(limit: int = 50, scenario: str | None = "standard",
                          mode: str | None = "all_items") -> list[dict]:
    """차트용 시계열 (오래된 순). run_date / mean profit / win_rate / 등급별 mean."""
    runs = list(reversed(list_backtest_runs(limit=limit, scenario=scenario, mode=mode)))
    out = []
    for r in runs:
        out.append({
            "run_date": r["run_date"],
            "total_pairs": r["total_pairs"],
            "overall_win_rate": r["overall_win_rate"] or 0,
            "overall_mean_profit": r["overall_mean_profit"] or 0,
            "a_mean": r["a_mean"] or 0,
            "b_mean": r["b_mean"] or 0,
            "c_mean": r["c_mean"] or 0,
            "d_mean": r["d_mean"] or 0,
            "x_mean": r["x_mean"] or 0,
            "monotonic": bool(r["monotonic_decreasing"]),
        })
    return out
