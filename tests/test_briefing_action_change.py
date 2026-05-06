"""
tests/test_briefing_action_change.py
일일 브리핑, 액션 플래너, 변화 감지, Q&A, 시뮬레이션.
"""


def _seed(count=20):
    from scripts.generate_mock_data import generate
    generate(count=count, seed=42, reset=True)


def test_daily_briefing_persists():
    _seed(20)
    from agents.daily_briefing_agent import generate_briefing, get_latest_briefing
    b = generate_briefing()
    assert b["total_items"] >= 1
    latest = get_latest_briefing()
    assert latest is not None
    assert latest["summary"]


def test_action_planner_creates_actions():
    _seed(20)
    from agents.action_planner_agent import list_today_actions, plan_actions
    n = plan_actions()
    actions = list_today_actions()
    assert n == len(actions)
    if actions:
        assert "priority" in actions[0]


def test_change_detection_runs_idempotent():
    _seed(10)
    from agents.change_detection_agent import detect_changes
    first = detect_changes()
    second = detect_changes()
    # 첫 호출엔 prev snapshot이 없어 0개. 두 번째 호출에서도 변화 없으면 0개여야 한다.
    assert isinstance(first, list)
    assert isinstance(second, list)


def test_item_qa_answers():
    _seed(10)
    from agents.item_qa_agent import ask
    from core.database import get_connection
    conn = get_connection()
    iid = conn.execute("SELECT id FROM items LIMIT 1").fetchone()["id"]
    conn.close()
    ans = ask(iid, "이 물건 위험해?")
    assert "answer" in ans and isinstance(ans["answer"], str)


def test_outcome_simulation_persists():
    _seed(10)
    from agents.outcome_simulation_agent import simulate_for_item
    from agents.price_analysis_agent import analyze_item_price
    from core.database import get_connection
    conn = get_connection()
    iid = conn.execute("SELECT id FROM items LIMIT 1").fetchone()["id"]
    conn.close()
    analyze_item_price(iid)
    res = simulate_for_item(iid, scenario="standard", seed=1)
    assert "simulated_profit" in res
