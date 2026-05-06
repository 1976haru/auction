"""
agents/daily_recommendation_agent.py
일일 추천 + 알림 발송 (mock 모드에서는 콘솔 출력).
"""
from __future__ import annotations

from agents.recommendation_agent import recommend
from core.alerts import send_daily_report
from core.logger import log
from modules.alerts.telegram import send_message, format_briefing


DEFAULT_QUERY = "위험 낮고 시세차익 큰 물건 5개 찾아줘"


def run_daily(query: str = DEFAULT_QUERY) -> dict:
    log.info(f"[일일추천] {query}")
    result = recommend(query, n=5)
    if result["results"]:
        send_daily_report(result["results"])
    else:
        send_message("오늘 조건에 맞는 추천 물건이 없습니다.")
    return result


def run_daily_full_pipeline(query: str = DEFAULT_QUERY):
    """전체 파이프라인 - mock-first."""
    from scripts.run_daily_pipeline import run_pipeline
    return run_pipeline(use_mock=True, count=100, top=5, query=query)


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or DEFAULT_QUERY
    run_daily(q)
