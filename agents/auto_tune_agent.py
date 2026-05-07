"""
agents/auto_tune_agent.py
추천 가중치 자동 튜닝 - grid search.

전략
- WEIGHTS_DEFAULT 의 핵심 키 몇 개에 대해 작은 grid 정의
- Cartesian product 돌리며 backtest_all_items(weights=...) 호출
- quality_score() 로 평가 후 정렬
- 최상위 가중치를 tuned_weights 테이블에 저장 (선택적으로 활성화)

quality_score 정의
- 등급 단조감소 OK 면 +100
- A->B->C->D 인접 mean profit 차이의 합 (구분이 클수록 좋음)
- A 등급 win_rate >= 95% 면 +30, 아니면 0
- X 등급 mean profit < 0 (필터 정상 작동) 면 +30
"""
from __future__ import annotations

import itertools
import json
from typing import Any

from core.database import get_connection, init_db
from core.logger import log
from core.utils import safe_json


# 작은 grid - 너무 크면 시간 폭발. 핵심 4개 변수만.
DEFAULT_GRID = {
    "profit_max": [35, 40, 45, 50],
    "profit_divisor": [1500, 2000, 2500],
    "risk_low": [16, 20, 24],
    "risk_high": [2, 4, 6],
    "grade_a_cutoff": [70, 75, 80],
    "grade_b_cutoff": [55, 60, 65],
}


def quality_score(report: dict, ordering: dict) -> float:
    """백테스트 결과 dict 와 ordering dict 로 가중치 품질 평가.

    높을수록 좋음. 음수도 가능 (나쁜 경우).
    """
    score = 0.0
    grades = report.get("grades", {})

    # 1) 단조 감소 보너스
    if ordering.get("monotonic_decreasing"):
        score += 100

    # 2) 인접 등급 평균 손익 차이 합 (구분력)
    means = ordering.get("grade_means", {})
    order = ["A", "B", "C", "D"]
    valid = [(g, means[g]) for g in order if g in means]
    if len(valid) >= 2:
        gap_sum = sum(
            valid[i][1] - valid[i + 1][1] for i in range(len(valid) - 1)
        )
        # 평균 1만원당 0.001 점 (스케일 조정)
        score += gap_sum * 0.001

    # 3) A 등급 승률 95% 이상이면 보너스
    a = grades.get("A") or {}
    if a.get("count", 0) > 0 and a.get("win_rate", 0) >= 95:
        score += 30

    # 4) X 등급이 손실 매물 잘 걸러주면 보너스
    x = grades.get("X") or {}
    if x.get("count", 0) > 0 and x.get("actual_profit", {}).get("mean", 0) < 0:
        score += 30

    # 5) A 등급 표본이 너무 적으면 페널티 (3건 미만)
    if a.get("count", 0) > 0 and a.get("count") < 3:
        score -= 20

    return round(score, 3)


def evaluate_weights(weights: dict, scenario: str = "standard") -> dict:
    """단일 가중치 조합 평가 - 백테스트 + quality."""
    from agents.backtest_agent import backtest_all_items, grade_ordering_check
    report = backtest_all_items(scenario=scenario, weights=weights)
    ordering = grade_ordering_check(report)
    q = quality_score(report, ordering)
    return {
        "weights": weights,
        "quality": q,
        "report": report,
        "ordering": ordering,
    }


def grid_search(grid: dict[str, list] | None = None,
                 scenario: str = "standard",
                 max_combos: int = 100) -> list[dict]:
    """작은 grid 로 가중치 탐색. 결과를 quality 내림차순 정렬해 반환."""
    grid = grid or DEFAULT_GRID
    keys = list(grid.keys())
    combos = list(itertools.product(*(grid[k] for k in keys)))
    if len(combos) > max_combos:
        log.info(f"[autotune] {len(combos)}개 -> {max_combos}개 샘플링")
        # 선형 샘플링
        step = len(combos) / max_combos
        combos = [combos[int(i * step)] for i in range(max_combos)]

    log.info(f"[autotune] {len(combos)} combos 평가 시작")
    from agents.recommendation_agent import WEIGHTS_DEFAULT
    out: list[dict] = []
    for i, combo in enumerate(combos):
        w = dict(WEIGHTS_DEFAULT)
        for k, v in zip(keys, combo):
            w[k] = v
        try:
            result = evaluate_weights(w, scenario=scenario)
            out.append(result)
        except Exception as e:
            log.warning(f"[autotune] combo {i} 실패: {e}")
        if (i + 1) % 20 == 0:
            log.info(f"[autotune] {i + 1}/{len(combos)} 완료")
    out.sort(key=lambda r: r["quality"], reverse=True)
    return out


def save_tuned_weights(weights: dict, quality: float,
                        notes: str = "", activate: bool = False) -> int:
    init_db()
    conn = get_connection()
    if activate:
        conn.execute("UPDATE tuned_weights SET is_active=0")
    cur = conn.execute("""
        INSERT INTO tuned_weights (weights_json, quality_score, notes, is_active)
        VALUES (?, ?, ?, ?)
    """, (safe_json(weights), quality, notes, 1 if activate else 0))
    rid = cur.lastrowid
    conn.commit()
    conn.close()
    log.info(f"[autotune] tuned_weights #{rid} saved (active={activate})")
    return int(rid)


def list_tuned_weights(limit: int = 30) -> list[dict]:
    init_db()
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM tuned_weights ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def activate_weights(tuned_id: int) -> bool:
    init_db()
    conn = get_connection()
    conn.execute("UPDATE tuned_weights SET is_active=0")
    conn.execute("UPDATE tuned_weights SET is_active=1 WHERE id=?", (tuned_id,))
    conn.commit()
    conn.close()
    log.info(f"[autotune] tuned_weights #{tuned_id} activated")
    return True


def deactivate_all() -> None:
    init_db()
    conn = get_connection()
    conn.execute("UPDATE tuned_weights SET is_active=0")
    conn.commit()
    conn.close()


def get_active_weights() -> dict:
    """활성화된 가중치를 dict 로 반환. 없으면 default."""
    from agents.recommendation_agent import _load_active_weights
    return _load_active_weights()
