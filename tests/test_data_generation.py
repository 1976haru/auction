"""
tests/test_data_generation.py — Mock 데이터 v2 + 시나리오 export (블록 11)
"""
import json


def test_seed_law_codes_and_school():
    from scripts.seed_law_codes import seed as seed_law
    from scripts.seed_school_data import seed as seed_school
    from core.database import get_connection
    n_law = seed_law()
    n_school = seed_school()
    assert n_law == 35
    assert n_school >= 5
    conn = get_connection()
    assert conn.execute("SELECT COUNT(*) FROM law_codes").fetchone()[0] == 35
    # 멱등성: 재실행해도 35 유지
    seed_law()
    assert conn.execute("SELECT COUNT(*) FROM law_codes").fetchone()[0] == 35
    conn.close()


def test_generate_with_analysis_creates_scenarios():
    """소량 생성 + 분석 -> 각 물건에 시나리오 3건."""
    from scripts.generate_mock_data import generate
    from core.database import get_connection
    res = generate(count=12, seed=42, reset=True, analyze=True)
    assert res["items"] == 12
    assert res["analysis"]["processed"] == 12

    conn = get_connection()
    n_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    n_scen = conn.execute("SELECT COUNT(*) FROM scenario_results").fetchone()[0]
    n_with = conn.execute(
        "SELECT COUNT(DISTINCT item_id) FROM scenario_results").fetchone()[0]
    conn.close()
    assert n_with == n_items          # 모든 물건에 시나리오
    assert n_scen == n_items * 3      # 물건당 3개 시나리오


def test_export_scenarios_json_serializable():
    from scripts.generate_mock_data import generate
    from scripts.export_scenarios_json import build
    generate(count=10, seed=7, reset=True, analyze=True)
    data = build()
    # JSON 직렬화 성공
    s = json.dumps(data, ensure_ascii=False)
    assert len(s) > 0
    assert data["summary"]["total_items"] == 10
    assert "by_scenario" in data["summary"]
    # 첫 item에 scenarios 3종
    first = data["items"][0]
    assert set(first["scenarios"].keys()) == {"short_sale", "rental", "residence"}
    assert "location" in first and "risk" in first
