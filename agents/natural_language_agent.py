"""
agents/natural_language_agent.py
자연어 입력 -> 검색 의도 JSON 변환.
USE_AI=false 또는 USE_MOCK_APIS=true 일 때는 규칙 기반 + mock_parse_natural_language 사용.
"""
from __future__ import annotations

import json

from core.ai_client import parse_natural_language as ai_parse
from core.database import get_connection, init_db
from core.logger import log
from core.mock_api import mock_parse_natural_language

EXAMPLE_SENTENCES = [
    "시세차익 가장 많은 물건 5개만 찾아줘",
    "공매만 보고 수익률 높은 물건 10개",
    "서울 아파트 중 위험 낮은 물건 3개",
    "입찰기일 7일 이내 물건 중 저평가된 것만 보여줘",
    "유치권 있는 물건은 제외해줘",
    "고위험이어도 시세차익 큰 물건 보여줘",
    "이번 주 입찰 가능한 것만 보여줘",
    "공매 차량 말고 부동산만 보여줘",
    "요즘 괜찮은 거 있어?",
    "오늘 뭐부터 봐야 돼?",
    "내가 좋아할 만한 물건 있어?",
]


def parse_intent(user_input: str) -> dict:
    log.info(f"[NL] 입력: {user_input}")
    try:
        result = ai_parse(user_input)
        if isinstance(result, dict) and result.get("intent"):
            return result
    except Exception as e:
        log.warning(f"[NL] AI 파싱 실패 -> mock: {e}")
    return mock_parse_natural_language(user_input)


def save_task(user_input: str, parsed: dict) -> int:
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO agent_tasks (user_input, parsed_intent, agent_name, status)
        VALUES (?, ?, 'NaturalLanguageAgent', 'done')
    """, (user_input, json.dumps(parsed, ensure_ascii=False)))
    task_id = c.lastrowid
    conn.commit()
    conn.close()
    return task_id


# 하위 호환 — 기존 테스트가 _rule_based_parse를 import 하기 때문에 유지
def _rule_based_parse(user_input: str) -> dict:
    """legacy 형식의 검색조건 dict 반환 (하위 호환용)."""
    parsed = mock_parse_natural_language(user_input)
    sort_map = {
        "expected_profit": "profit",
        "expected_roi": "roi",
        "risk": "risk",
    }
    risk_to_score = {"low": 4, "medium": 7, "high": 10}
    legacy = {
        "intent": "추천",
        "sort_by": sort_map.get(parsed.get("sort_by"), "profit"),
        "limit": parsed.get("limit", 5),
        "filters": {
            "regions": parsed.get("regions", []),
            "item_types": parsed.get("item_types", []),
            "min_fail_count": 0,
            "max_risk_score": risk_to_score.get(parsed["filters"].get("risk_level_max"), 10),
            "min_roi": None,
            "source": (
                parsed.get("source_types")[0]
                if len(parsed.get("source_types", [])) == 1 else "all"
            ),
        }
    }
    return legacy
