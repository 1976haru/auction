"""
modules/eviction/cost_predictor.py
유형별 명도 예상 비용/기간/성공률 추정 + items 테이블 저장.

금액 단위는 원(₩). 기간은 개월. 모두 추정치이며 사안별 확인이 필요하다.
"""
from __future__ import annotations

from core.database import get_connection, init_db
from core.logger import log
from modules.eviction.difficulty_estimator import (
    classify_occupant,
    evaluate_difficulty,
    OCCUPANT_TYPES,
)

# 유형별 프로필: 비용(원) 범위, 기간(개월) 범위, 명도방법, 성공률
EVICTION_PROFILE: dict[str, dict] = {
    "vacant": {
        "cost": (0, 1_000_000), "duration": (0, 1),
        "method": "자진명도/단순 인도(공실)", "success_rate": 0.98,
    },
    "owner": {
        "cost": (1_000_000, 5_000_000), "duration": (1, 3),
        "method": "합의 시도 후 인도명령", "success_rate": 0.90,
    },
    "tenant_no_priority": {
        "cost": (2_000_000, 10_000_000), "duration": (2, 4),
        "method": "인도명령(낙찰 후 6개월 내 신청)", "success_rate": 0.88,
    },
    "tenant_with_priority": {
        "cost": (5_000_000, 20_000_000), "duration": (3, 8),
        "method": "보증금 인수 + 합의 명도", "success_rate": 0.70,
    },
    "lien_holder": {
        "cost": (5_000_000, 40_000_000), "duration": (6, 18),
        "method": "전문가 상담 → 협상/소송", "success_rate": 0.50,
    },
    "hostile": {
        "cost": (10_000_000, 30_000_000), "duration": (6, 12),
        "method": "강제집행(인도명령 → 집행)", "success_rate": 0.60,
    },
}


def predict_cost(occupant_type: str, item_info: dict | None = None) -> dict:
    """명도 비용/기간/성공률 추정 (가격/유형 보정 포함).

    Returns: {occupant_type, cost_min, cost_max, cost_estimate,
              duration_min_months, duration_max_months, duration_estimate_months,
              method, success_rate, notes}
    """
    item_info = item_info or {}
    if occupant_type not in EVICTION_PROFILE:
        occupant_type = "owner"

    prof = EVICTION_PROFILE[occupant_type]
    cost_min, cost_max = prof["cost"]
    dur_min, dur_max = prof["duration"]
    notes: list[str] = []

    # 보정: 상가/토지 등 특수물건은 비용 +30%
    item_type = item_info.get("item_type") or ""
    if any(t in item_type for t in ("상가", "토지", "공장", "사무실")):
        cost_min = int(cost_min * 1.3)
        cost_max = int(cost_max * 1.3)
        notes.append("특수물건(상가/토지 등) 비용 +30% 보정")

    # 보정: 대항력 임차인은 보증금 인수가 별도(여기 비용에는 미포함) - 안내
    if occupant_type == "tenant_with_priority":
        notes.append("대항력 임차인 보증금 인수액은 별도(권리분석 참조)")

    cost_estimate = (cost_min + cost_max) // 2
    duration_estimate = round((dur_min + dur_max) / 2)

    result = {
        "occupant_type": occupant_type,
        "cost_min": cost_min,
        "cost_max": cost_max,
        "cost_estimate": cost_estimate,
        "duration_min_months": dur_min,
        "duration_max_months": dur_max,
        "duration_estimate_months": duration_estimate,
        "method": prof["method"],
        "success_rate": prof["success_rate"],
        "notes": notes or ["표준 절차 진행 가능성 - 현장 확인 권장"],
    }
    return result


def analyze_eviction(
    item_id: int,
    occupant_type: str | None = None,
    item_info: dict | None = None,
    hint: dict | None = None,
) -> dict:
    """명도 종합 분석 + items 테이블 저장.

    Returns: {occupant_type, difficulty, level, cost_*, duration_*, method,
              success_rate, factors, notes, summary}
    """
    # 물건 정보 보강
    if item_info is None:
        conn = get_connection()
        row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        conn.close()
        item_info = dict(row) if row else {}

    if occupant_type not in OCCUPANT_TYPES:
        occupant_type = classify_occupant(item_id, hint)

    diff = evaluate_difficulty(occupant_type, item_info)
    cost = predict_cost(occupant_type, item_info)

    init_db()
    conn = get_connection()
    conn.execute(
        """UPDATE items SET eviction_difficulty=?, eviction_cost_estimate=?,
                  eviction_duration_months=? WHERE id=?""",
        (diff["difficulty"], cost["cost_estimate"],
         cost["duration_estimate_months"], item_id),
    )
    conn.commit()
    conn.close()

    summary = (
        f"{diff['label']} → 난이도 {diff['difficulty']}/10, "
        f"예상 {cost['duration_min_months']}~{cost['duration_max_months']}개월, "
        f"{cost['cost_min']:,}~{cost['cost_max']:,}원"
    )

    result = {
        **diff,
        **{k: cost[k] for k in (
            "cost_min", "cost_max", "cost_estimate",
            "duration_min_months", "duration_max_months", "duration_estimate_months",
            "method", "success_rate", "notes",
        )},
        "summary": summary,
    }
    log.info(f"[eviction] item_id={item_id} -> {summary}")
    return result
