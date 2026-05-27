"""
tests/test_eviction.py — 명도 분석 엔진 (블록 3)
"""
from core.database import upsert_item


def _make_item(item_type="빌라", min_bid=30000):
    return upsert_item({
        "source": "test", "case_no": f"2024타경{min_bid}", "item_type": item_type,
        "address_full": "서울특별시 마포구 망원동 1-1", "address_gu": "마포구",
        "min_bid_price": min_bid,
    })


def test_difficulty_matrix_ranges():
    """모든 유형 난이도가 1~10 범위, 매트릭스 순서 유지."""
    from modules.eviction.difficulty_estimator import evaluate_difficulty, OCCUPANT_TYPES
    scores = {t: evaluate_difficulty(t, {})["difficulty"] for t in OCCUPANT_TYPES}
    for t, s in scores.items():
        assert 1 <= s <= 10, (t, s)
    assert scores["vacant"] < scores["owner"] < scores["tenant_no_priority"]
    assert scores["tenant_with_priority"] > scores["tenant_no_priority"]


def test_classify_from_tenant_hint():
    """임차인 대항력 hint -> tenant_with_priority / no_priority."""
    from modules.eviction.difficulty_estimator import classify_occupant
    item_id = _make_item()
    assert classify_occupant(item_id, {"tenant": {"has_priority": True}}) == "tenant_with_priority"
    assert classify_occupant(item_id, {"tenant": {"has_priority": False}}) == "tenant_no_priority"
    assert classify_occupant(item_id, {"vacant": True}) == "vacant"
    assert classify_occupant(item_id, {"lien": True}) == "lien_holder"


def test_cost_prediction_order():
    """공실 < 임차인무대항 < 유치권 비용/기간 순서."""
    from modules.eviction.cost_predictor import predict_cost
    vac = predict_cost("vacant", {})
    ten = predict_cost("tenant_no_priority", {})
    lien = predict_cost("lien_holder", {})
    assert vac["cost_max"] < ten["cost_max"] < lien["cost_max"]
    assert vac["duration_max_months"] <= ten["duration_max_months"] < lien["duration_max_months"]
    assert 0.0 <= lien["success_rate"] <= 1.0


def test_special_property_cost_adjustment():
    """상가는 빌라보다 비용 보정(+30%)."""
    from modules.eviction.cost_predictor import predict_cost
    villa = predict_cost("owner", {"item_type": "빌라"})
    store = predict_cost("owner", {"item_type": "상가"})
    assert store["cost_max"] > villa["cost_max"]


def test_analyze_eviction_persists_to_items():
    """analyze_eviction 결과가 items 컬럼에 저장."""
    from modules.eviction.cost_predictor import analyze_eviction
    from core.database import get_connection
    item_id = _make_item()
    result = analyze_eviction(item_id, hint={"tenant": {"has_priority": False}})
    assert result["occupant_type"] == "tenant_no_priority"
    assert "난이도" in result["summary"]

    conn = get_connection()
    row = conn.execute(
        "SELECT eviction_difficulty, eviction_cost_estimate, eviction_duration_months "
        "FROM items WHERE id=?", (item_id,)
    ).fetchone()
    conn.close()
    assert row["eviction_difficulty"] == result["difficulty"]
    assert row["eviction_cost_estimate"] == result["cost_estimate"]
    assert row["eviction_duration_months"] == result["duration_estimate_months"]
