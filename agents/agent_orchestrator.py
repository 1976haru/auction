"""
agents/agent_orchestrator.py
에이전트들을 정해진 순서로 실행하는 오케스트레이터.
"""
from __future__ import annotations

import time
from typing import Any

from agents.action_planner_agent import plan_actions
from agents.alert_agent import dispatch_alerts
from agents.change_detection_agent import detect_changes
from agents.confidence_agent import compute_all as compute_confidence_all
from agents.daily_briefing_agent import generate_briefing
from agents.legal_risk_agent import analyze_all as analyze_risk_all
from agents.outcome_simulation_agent import simulate_top
from agents.preference_learning_agent import learn_preferences
from agents.price_analysis_agent import analyze_all as analyze_price_all
from agents.recommendation_agent import recommend
from agents.risk_checklist_agent import generate_for_all
from core.database import get_connection, init_db
from core.logger import log
from core.utils import now_iso, safe_json


def run_full_analysis(top_query: str = "시세차익 큰 물건 5개 찾아줘") -> dict:
    """수집 후 호출 - 전체 분석 + 추천 + 브리핑 파이프라인."""
    init_db()
    started = time.time()

    log.info("[orchestrator] price analysis")
    n_price = analyze_price_all()
    log.info("[orchestrator] risk analysis")
    n_risk = analyze_risk_all()
    log.info("[orchestrator] checklist")
    n_check = generate_for_all()
    log.info("[orchestrator] confidence")
    n_conf = compute_confidence_all()
    log.info("[orchestrator] preferences")
    pref = learn_preferences()
    log.info("[orchestrator] change detection")
    changes = detect_changes()
    log.info("[orchestrator] action planning")
    n_actions = plan_actions()
    log.info("[orchestrator] briefing")
    briefing = generate_briefing(top_query=top_query)
    log.info("[orchestrator] simulation (top)")
    sims = simulate_top(briefing["top_picks"][:5])
    log.info("[orchestrator] alerts")
    alerts = dispatch_alerts(pref)

    elapsed = time.time() - started

    summary = {
        "started_at": now_iso(),
        "elapsed_sec": round(elapsed, 2),
        "price_analyzed": n_price,
        "risk_analyzed": n_risk,
        "checklists": n_check,
        "confidence_scored": n_conf,
        "preferences": pref,
        "changes_detected": len(changes),
        "actions_planned": n_actions,
        "top_picks": briefing["top_picks"],
        "briefing_summary": briefing["summary"],
        "simulations": len(sims),
        "alerts": alerts,
    }
    return summary


def quick_recommend(query: str, n: int = 5) -> dict:
    return recommend(query, n=n)
