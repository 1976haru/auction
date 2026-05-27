"""
tests/test_agents.py — 에이전트 통합 (블록 10)
"""
from core.database import upsert_item


def _make_item(gu="마포구", min_bid=28000, appraisal=40000):
    return upsert_item({
        "source": "test", "case_no": f"2024타경{abs(hash((gu, min_bid))) % 99999}",
        "item_type": "아파트", "address_full": f"서울특별시 {gu} 망원동",
        "address_si": "서울특별시", "address_gu": gu, "area_m2": 84.0,
        "min_bid_price": min_bid, "appraisal_price": appraisal, "fail_count": 1,
    })


def test_key_agents_importable():
    """핵심 에이전트/오케스트레이터 import 성공."""
    import importlib
    for mod in [
        "agents.orchestrator", "agents.scenario_search",
        "agents.item_qa_agent", "agents.outcome_simulation_agent",
        "agents.preference_learning_agent", "agents.recommendation_agent",
        "agents.agent_orchestrator",
    ]:
        assert importlib.import_module(mod) is not None


def test_run_item_analysis_full_chain():
    """물건 1건 통합 분석: 시나리오 + 리스크까지 채워진다."""
    from agents.orchestrator import run_item_analysis
    item_id = _make_item()
    res = run_item_analysis(item_id)
    assert res["item_id"] == item_id
    steps = res["steps"]
    # 핵심 단계 존재
    assert "legal" in steps and "eviction" in steps and "location" in steps
    assert "scenarios" in steps and steps["scenarios"]["best"] in (
        "short_sale", "rental", "residence")
    assert "risk" in steps
    assert isinstance(res["errors"], list)


def test_run_pipeline_records_metric():
    """파이프라인이 N건 처리하고 metrics에 기록한다."""
    from agents.orchestrator import run_pipeline
    from core.database import get_connection
    ids = [_make_item(gu="마포구", min_bid=20000 + i * 1000) for i in range(3)]
    summary = run_pipeline(item_ids=ids)
    assert summary["processed"] == 3

    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM metrics WHERE name='items_processed_count' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row is not None and row["value"] == 3


def test_parse_scenario_query_patterns():
    from agents.scenario_search import parse_scenario_query
    assert parse_scenario_query("단타 수익률 20% 이상")["scenario"] == "short_sale"
    assert parse_scenario_query("단타 수익률 20% 이상")["min_roi"] == 20.0
    assert parse_scenario_query("임대수익률 5% 이상")["scenario"] == "rental"
    assert parse_scenario_query("내 자본으로 살 수 있는 물건")["affordable_only"] is True
    assert parse_scenario_query("위험 없는 물건")["low_risk"] is True
    assert parse_scenario_query("비과세 가능한 거")["tax_exempt"] is True


def test_scenario_search_returns_results():
    """분석 후 시나리오 검색이 매칭 물건을 반환."""
    from agents.orchestrator import run_item_analysis
    from agents.scenario_search import search_by_scenario
    item_id = _make_item()
    run_item_analysis(item_id)  # scenario_results 채움
    out = search_by_scenario("임대수익 좋은 물건", limit=10)
    assert "filter" in out and out["filter"]["scenario"] == "rental"
    assert isinstance(out["results"], list)


def test_qa_agent_answers():
    """item_qa_agent.ask가 답변 문자열을 반환(mock)."""
    from agents.item_qa_agent import ask
    item_id = _make_item()
    res = ask(item_id, "이 물건은 왜 추천돼?")
    # dict 또는 str 반환 허용
    answer = res.get("answer") if isinstance(res, dict) else res
    assert isinstance(answer, str) and len(answer) > 0
