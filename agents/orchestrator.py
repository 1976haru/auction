"""
agents/orchestrator.py
v2.0 물건별 통합 분석 오케스트레이터.

기존 agents/agent_orchestrator.py(집계형 run_full_analysis(top_query))와 별개로,
물건 1건에 대해 신규 분석 모듈을 정해진 순서로 실행한다:
  권리분석 → 명도 → 입지 → 시장 → 시나리오 → 리스크 → 몬테카를로

각 단계는 실패해도 다음 단계로 진행하며(graceful), 오류는 errors에 모은다.
metrics 테이블에 실행 시간/처리 건수를 기록한다.
"""
from __future__ import annotations

import time

from core.database import get_connection, init_db
from core.logger import log


def _record_metric(name: str, value: float, tags: dict | None = None) -> None:
    try:
        from core.observability import record_metric
        record_metric(name, value, tags)
    except Exception as e:
        log.warning(f"[orchestrator] metric 기록 실패: {e}")


def run_item_analysis(item_id: int, user_profile: dict | None = None) -> dict:
    """물건 1건 통합 분석. Returns: {item_id, steps{...}, errors[]}"""
    init_db()
    steps: dict = {}
    errors: list[str] = []

    conn = get_connection()
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if not row:
        return {"item_id": item_id, "error": "not found"}
    item = dict(row)

    # 1) 권리분석
    try:
        from modules.legal import (parse_rights, save_rights_timeline,
                                    identify_senior_right, calculate_inheritance)
        rights = parse_rights("", item_id)
        save_rights_timeline(item_id, rights)
        senior = identify_senior_right(item_id)
        inh = calculate_inheritance(item_id)
        steps["legal"] = {"rights": len(rights),
                          "senior": senior.get("right_type") if senior else None,
                          "inherit_total": inh["total_inherited"]}
    except Exception as e:
        errors.append(f"legal: {e}")

    # 2) 명도
    try:
        from modules.eviction import analyze_eviction
        ev = analyze_eviction(item_id, item_info=item)
        steps["eviction"] = {"difficulty": ev["difficulty"], "cost": ev["cost_estimate"]}
    except Exception as e:
        errors.append(f"eviction: {e}")

    # 3) 입지
    try:
        from modules.location.total_scorer import calculate_location_score
        loc = calculate_location_score(item_id, item)
        steps["location"] = {"total": loc["total"], "grade": loc["grade"]}
    except Exception as e:
        errors.append(f"location: {e}")

    # 4) 시장
    try:
        from modules.market import predict_competition, get_winning_rate
        loc_total = steps.get("location", {}).get("total")
        comp = predict_competition({**item, "location_total": loc_total})
        wr = get_winning_rate(item.get("address_si"), item.get("address_gu"),
                              item.get("item_type"), item.get("fail_count") or 0)
        steps["market"] = {"bidders": comp["estimated_bidders"],
                           "level": comp["competition_level"],
                           "winning_rate": wr["expected_rate"]}
    except Exception as e:
        errors.append(f"market: {e}")

    # 5) 시나리오 (핵심)
    bid_price = None
    try:
        from modules.scenarios import compare_scenarios
        sc = compare_scenarios(item_id, user_profile)
        bid_price = sc["bid_price"]
        steps["scenarios"] = {"best": sc["best_scenario"],
                              "weighted_score": sc["weighted_score"],
                              "bid_price": bid_price}
    except Exception as e:
        errors.append(f"scenarios: {e}")

    # 6~7) 리스크 + 몬테카를로
    try:
        from modules.risk import analyze_scenario_risk, run_monte_carlo
        if bid_price:
            sr = analyze_scenario_risk(item_id, bid_price, user_profile, item)
            mc = run_monte_carlo(item_id, bid_price, n=1000,
                                 user_profile=user_profile, item=item)
            steps["risk"] = {"mean_roe": mc["mean_roe"],
                             "loss_probability": mc["loss_probability"],
                             "scenario_mean_roe": sr["mean_roe"]}
    except Exception as e:
        errors.append(f"risk: {e}")

    return {"item_id": item_id, "steps": steps, "errors": errors}


def run_pipeline(item_ids: list[int] | None = None, limit: int | None = None,
                 user_profile: dict | None = None) -> dict:
    """전체(또는 지정) 활성 물건에 대해 run_item_analysis 실행 + 메트릭 기록."""
    init_db()
    started = time.time()

    if item_ids is None:
        conn = get_connection()
        q = "SELECT id FROM items WHERE status='active' OR status IS NULL ORDER BY id"
        if limit:
            q += f" LIMIT {int(limit)}"
        item_ids = [r["id"] for r in conn.execute(q).fetchall()]
        conn.close()

    processed = 0
    total_errors = 0
    for iid in item_ids:
        res = run_item_analysis(iid, user_profile)
        processed += 1
        total_errors += len(res.get("errors", []))

    elapsed = round(time.time() - started, 2)
    _record_metric("pipeline_duration_seconds", elapsed)
    _record_metric("items_processed_count", processed)
    _record_metric("errors_count", total_errors)

    summary = {
        "processed": processed,
        "errors": total_errors,
        "elapsed_sec": elapsed,
    }
    log.info(f"[orchestrator] v2 pipeline: {processed}건 처리, "
             f"오류 {total_errors}, {elapsed}s")
    return summary
