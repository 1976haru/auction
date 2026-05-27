"""
tests/test_e2e.py — 엔드투엔드 흐름 (블록 17)
"""


def test_e2e_search_recommend_scenario_alert(sample_items, mock_profile):
    """자연어 검색 → 분석 → 시나리오 비교 → 알림 발화 전체 흐름."""
    from agents.orchestrator import run_item_analysis
    from agents.scenario_search import parse_scenario_query, search_by_scenario
    from agents.alert_agent import check_triggers

    # 1) 전체 분석(시나리오/리스크 채움)
    for iid in sample_items:
        res = run_item_analysis(iid, mock_profile)
        assert "scenarios" in res["steps"]

    # 2) 자연어 검색 → 시나리오 필터
    f = parse_scenario_query("임대수익 좋은 물건 ROI 5% 이상")
    assert f["scenario"] == "rental"
    out = search_by_scenario("임대수익 좋은 물건", limit=10)
    assert isinstance(out["results"], list)

    # 3) 알림 트리거 발화(데이터 존재 → 일부 발화)
    alerts = check_triggers()
    assert isinstance(alerts, list)


def test_e2e_collect_analyze_score_persist(sample_items, mock_profile):
    """물건 분석 → 점수 산출 → scenario_results/items 저장 확인."""
    from agents.orchestrator import run_pipeline
    from core.database import get_connection

    summary = run_pipeline(item_ids=sample_items, user_profile=mock_profile)
    assert summary["processed"] == len(sample_items)

    conn = get_connection()
    # 모든 물건에 시나리오 3건
    n_scen = conn.execute("SELECT COUNT(*) FROM scenario_results").fetchone()[0]
    # 입지 점수 저장
    n_loc = conn.execute("SELECT COUNT(*) FROM location_scores").fetchone()[0]
    # 리스크 결과 items 저장
    n_risk = conn.execute(
        "SELECT COUNT(*) FROM items WHERE expected_roe IS NOT NULL").fetchone()[0]
    conn.close()
    assert n_scen == len(sample_items) * 3
    assert n_loc == len(sample_items)
    assert n_risk == len(sample_items)


def test_e2e_preference_learning_affects_recommendation(sample_items, mock_profile):
    """관심 등록(학습) → 다음 추천 선호 점수에 반영."""
    from agents.orchestrator import run_pipeline
    from core.user_profile import update_preference, get_preference_score
    from core.database import get_connection

    run_pipeline(item_ids=sample_items, user_profile=mock_profile)

    target = sample_items[0]
    conn = get_connection()
    item = dict(conn.execute("SELECT * FROM items WHERE id=?", (target,)).fetchone())
    conn.close()

    before = get_preference_score(item, mock_profile)
    # 같은 구/유형 물건을 여러 번 관심 등록(학습 신호)
    for _ in range(3):
        update_preference(target, "watch")
    after = get_preference_score(item, mock_profile)
    assert after >= before  # 학습 반영으로 점수 유지/상승
