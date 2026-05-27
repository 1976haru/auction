"""
modules/scenarios/scenario_comparator.py
3개 시나리오(단타/임대/실거주) 통합 비교 + 추천. v2.0 핵심.
USE_AI=true 시 추천 이유/주의사항을 Claude로 자연어 생성(실패 시 규칙 기반).
"""
from __future__ import annotations

import json

from core.database import get_connection, init_db
from core.logger import log
from modules.scenarios import _common as C
from modules.scenarios.short_term_sale import simulate_short_sale
from modules.scenarios.long_term_rental import simulate_rental
from modules.scenarios.owner_residence import simulate_residence

_LABELS = {"short_sale": "단타", "rental": "임대", "residence": "실거주"}


def _appropriate_bid(item: dict, profile: dict) -> int:
    """사용자 자본 + 시장 예측 기반 적정 입찰가(원)."""
    min_bid_won = (item.get("min_bid_price") or 0) * C.WON_PER_MAN

    # 시장 경쟁 예측의 예상 낙찰가(만원 단위 → 원)
    expected_won = 0
    try:
        from modules.market.competition_predictor import predict_competition
        comp = predict_competition({
            "fail_count": item.get("fail_count") or 0,
            "min_bid_price": item.get("min_bid_price") or 0,
            "item_type": item.get("item_type"),
        })
        expected_won = (comp.get("expected_winning_price") or 0) * C.WON_PER_MAN
    except Exception:
        pass

    bid = expected_won or int(min_bid_won * 1.05) or 100_000_000
    return bid


def compare_scenarios(item_id: int, user_profile: dict | None = None) -> dict:
    profile = C.load_profile(user_profile)
    item = C.get_item(item_id)
    if not item:
        return {"error": f"item {item_id} not found"}

    bid_price = _appropriate_bid(item, profile)

    scenarios = {
        "short_sale": simulate_short_sale(item_id, bid_price, profile, item),
        "rental": simulate_rental(item_id, bid_price, profile, item=item),
        "residence": simulate_residence(item_id, bid_price, profile, item),
    }

    # 저장
    _save(item_id, scenarios)

    # 가중 점수
    weights = profile.get("scenario_weights") or {}
    weighted = sum(scenarios[s]["score"] * weights.get(s, 1 / 3) for s in scenarios)

    # 추천: 자본 가능 시나리오 우선, 그중 최고 점수
    affordable = {s: v for s, v in scenarios.items() if v["affordable"]}
    pool = affordable or scenarios
    best = max(pool, key=lambda s: pool[s]["score"])
    best_v = scenarios[best]

    comparison_table = _build_table(scenarios)
    recommendation = _build_recommendation(item, best, best_v, bid_price, weighted)

    result = {
        "item_id": item_id,
        "bid_price": bid_price,
        "scenarios": scenarios,
        "comparison_table": comparison_table,
        "best_scenario": best,
        "weighted_score": round(weighted, 1),
        "recommendation": recommendation,
    }
    log.info(
        f"[scenarios] item_id={item_id} 추천={best} "
        f"(단타 {scenarios['short_sale']['score']}/임대 {scenarios['rental']['score']}/"
        f"실거주 {scenarios['residence']['score']})"
    )
    return result


def _save(item_id: int, scenarios: dict) -> None:
    init_db()
    conn = get_connection()
    conn.execute("DELETE FROM scenario_results WHERE item_id=?", (item_id,))
    # 추천 시나리오 표시용
    best = max(scenarios, key=lambda s: scenarios[s]["score"])
    for name, v in scenarios.items():
        conn.execute(
            """INSERT INTO scenario_results
               (item_id, scenario, bid_price, capital_needed, holding_months,
                net_return, roe, annualized_roe, score, is_recommended,
                affordable, result_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item_id, name, v["bid_price"], v["capital_needed"], v["holding_months"],
             v["net_return"], v["roe"], v["annualized_roe"], v["score"],
             1 if name == best else 0, 1 if v["affordable"] else 0,
             json.dumps(v, ensure_ascii=False)),
        )
    conn.commit()
    conn.close()


def _build_table(scenarios: dict) -> list[dict]:
    def cap_man(s):
        return f"{scenarios[s]['capital_needed'] // C.WON_PER_MAN:,}만"

    def roe(s):
        return f"{scenarios[s]['roe']:.0f}%"

    def ann(s):
        return f"{scenarios[s]['annualized_roe']:.0f}%"

    rows = [
        {"label": "자기자본", "short_sale": cap_man("short_sale"),
         "rental": cap_man("rental"), "residence": cap_man("residence")},
        {"label": "보유기간",
         "short_sale": f"{scenarios['short_sale']['holding_months']}개월",
         "rental": f"{scenarios['rental']['holding_months']}개월",
         "residence": f"{scenarios['residence']['holding_months']}개월"},
        {"label": "ROE", "short_sale": roe("short_sale"),
         "rental": roe("rental"), "residence": roe("residence")},
        {"label": "연환산", "short_sale": ann("short_sale"),
         "rental": ann("rental"), "residence": ann("residence")},
    ]
    return rows


def _build_recommendation(item: dict, best: str, best_v: dict,
                          bid_price: int, weighted: float) -> dict:
    bid_man = bid_price // C.WON_PER_MAN
    reason = f"{_LABELS[best]} 시나리오 점수 최고 (연환산 ROE {best_v['annualized_roe']:.0f}%)"
    caution = best_v["notes"][0] if best_v.get("notes") else "현장 확인 필요"

    # USE_AI=true 시 자연어 보강
    try:
        from core import config
        if config.USE_AI and not config.USE_MOCK_APIS and config.ANTHROPIC_API_KEY:
            from core.ai_client import call_claude
            prompt = (
                f"경매 물건 {item.get('address_full')} ({item.get('item_type')}).\n"
                f"추천 시나리오: {_LABELS[best]}, 연환산 ROE {best_v['annualized_roe']:.0f}%.\n"
                "추천 이유 1문장과 주의사항 1문장을 단정 표현 없이 작성."
            )
            txt = call_claude(prompt, max_tokens=300)
            if isinstance(txt, str) and txt and "오류" not in txt:
                reason = txt.strip()[:200]
    except Exception:
        pass

    return {
        "score": round(best_v["score"], 1),
        "reason": reason,
        "caution": caution,
        "bid_range": {
            "min": int(bid_man * 0.99),
            "max": int(bid_man * 1.01),
            "unit": "만원",
        },
    }
