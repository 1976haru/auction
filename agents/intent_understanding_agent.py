"""
agents/intent_understanding_agent.py
NL 결과를 받아 모호한 표현을 해석하고 기본값을 채워 검색 가능한 형태로 정규화한다.
"""
from __future__ import annotations

from typing import Any

from agents.natural_language_agent import parse_intent
from core.config import TARGET_REGIONS, TARGET_TYPES


DEFAULT_FILTERS = {
    "risk_level_max": "medium",
    "exclude_keywords": [],
    "include_high_risk": False,
    "only_active": True,
    "bid_within_days": None,
    "has_market_price": True,
}


def _ensure(intent: dict[str, Any]) -> dict[str, Any]:
    intent.setdefault("intent", "find_top_profit_items")
    intent.setdefault("source_types", ["auction", "public_sale"])
    intent.setdefault("regions", [])
    intent.setdefault("item_types", [])
    intent.setdefault("sort_by", "expected_profit")
    intent.setdefault("limit", 5)
    f = intent.setdefault("filters", {})
    for k, v in DEFAULT_FILTERS.items():
        f.setdefault(k, v)
    intent.setdefault("assumptions", [])
    return intent


def understand(user_input: str) -> dict:
    """자연어 -> 정규화된 intent."""
    intent = parse_intent(user_input)
    intent = _ensure(intent)

    # 애매한 의도 처리
    if intent["intent"] == "soft_recommend":
        # 요즘 괜찮은 거 있어?
        intent["sort_by"] = "expected_profit"
        intent["filters"]["risk_level_max"] = "medium"
        intent["filters"]["has_market_price"] = True
        intent["limit"] = max(intent.get("limit") or 5, 5)
        if "(soft) 최근 신규 + 위험 낮음 + 시세차익 큼" not in intent["assumptions"]:
            intent["assumptions"].append("(soft) 최근 신규 + 위험 낮음 + 시세차익 큼")

    if intent["intent"] == "daily_action_focus":
        intent["sort_by"] = "bid_date"
        intent["filters"]["bid_within_days"] = 7
        intent["assumptions"].append("(daily) 입찰기일 임박 + 액션아이템 우선")

    if intent["intent"] == "personalized_recommend":
        intent["assumptions"].append("(personal) 사용자 선호 학습 결과 반영 예정")

    # 비어있는 지역은 사용자 관심 지역으로
    if not intent["regions"]:
        intent["regions_default"] = TARGET_REGIONS
    if not intent["item_types"]:
        intent["item_types_default"] = TARGET_TYPES

    return intent


if __name__ == "__main__":
    import json
    import sys
    q = " ".join(sys.argv[1:]) or "요즘 괜찮은 거 있어?"
    print(json.dumps(understand(q), ensure_ascii=False, indent=2))
