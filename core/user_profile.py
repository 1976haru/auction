"""
core/user_profile.py
사용자 프로필(.env) 로드 + 자본 적정성 판정 + 선호도 점수/학습.

자기자본 5천~2억 기준. .env의 USER_* 변수를 읽으며, 없으면 합리적 기본값을 쓴다.
선호 학습은 user_feedback 테이블(action)을 집계해 가중한다.
"""
from __future__ import annotations

import os

import core.config as _config  # noqa: F401  (.env 로드 보장)
from core.database import get_connection, init_db
from core.logger import log

# 기본 프로필 (modules/scenarios/_common.DEFAULT_PROFILE 와 정합)
_DEFAULTS = {
    "capital_max": 200_000_000,
    "capital_min": 50_000_000,
    "annual_income": 60_000_000,
    "other_debt_monthly": 300_000,
    "loan_available": 500_000_000,
    "loan_rate": 0.04,
    "ltv": 0.70,
    "dsr": 0.40,
    "loan_years": 30,
    "scenario_weights": {"short_sale": 0.30, "rental": 0.40, "residence": 0.30},
    "risk_appetite": "medium",
    "min_roi": 0.08,
    "max_risk_score": 6,
    "max_inherit_cost": 10_000_000,
    "interest_regions": [],
    "annual_appreciation": 0.03,
    "is_one_house": True,
}


def _getenv(key: str):
    v = os.getenv(key)
    return v if (v is not None and v != "") else None


def _to_int(v, default):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def _to_float(v, default):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _parse_weights(v) -> dict:
    """'0.3,0.4,0.3' -> {short_sale, rental, residence}. 합으로 정규화."""
    if not v:
        return dict(_DEFAULTS["scenario_weights"])
    parts = [p.strip() for p in str(v).split(",") if p.strip()]
    try:
        nums = [float(p) for p in parts][:3]
    except ValueError:
        return dict(_DEFAULTS["scenario_weights"])
    if len(nums) < 3:
        return dict(_DEFAULTS["scenario_weights"])
    total = sum(nums) or 1.0
    keys = ["short_sale", "rental", "residence"]
    return {k: round(n / total, 4) for k, n in zip(keys, nums)}


def load_user_profile() -> dict:
    """USER_* 환경변수 기반 프로필. 누락 시 기본값."""
    p = dict(_DEFAULTS)
    p["capital_max"] = _to_int(_getenv("USER_CAPITAL_MAX"), p["capital_max"])
    p["capital_min"] = _to_int(_getenv("USER_CAPITAL_MIN"), p["capital_min"])
    p["annual_income"] = _to_int(_getenv("USER_ANNUAL_INCOME"), p["annual_income"])
    p["other_debt_monthly"] = _to_int(_getenv("USER_OTHER_DEBT_MONTHLY"), p["other_debt_monthly"])
    p["loan_available"] = _to_int(_getenv("USER_LOAN_AVAILABLE"), p["loan_available"])
    p["scenario_weights"] = _parse_weights(_getenv("USER_SCENARIO_WEIGHTS"))
    p["risk_appetite"] = _getenv("USER_RISK_APPETITE") or p["risk_appetite"]
    p["min_roi"] = _to_float(_getenv("USER_MIN_ROI"), p["min_roi"])
    p["max_risk_score"] = _to_int(_getenv("USER_MAX_RISK_SCORE"), p["max_risk_score"])
    p["max_inherit_cost"] = _to_int(_getenv("USER_MAX_INHERIT_COST"), p["max_inherit_cost"])
    p["annual_appreciation"] = _to_float(_getenv("USER_ANNUAL_APPRECIATION"), p["annual_appreciation"])

    regions = _getenv("USER_INTEREST_REGIONS")
    if regions:
        p["interest_regions"] = [r.strip() for r in regions.split(",") if r.strip()]
    return p


# ── 선호 학습 (user_feedback 집계) ─────────────────────────
_POSITIVE_ACTIONS = ("watch", "like", "bid", "interested")


def update_preference(item_id: int | None, action: str, note: str = "") -> None:
    """사용자 상호작용 기록(학습 신호). user_feedback 테이블 사용."""
    init_db()
    conn = get_connection()
    conn.execute(
        "INSERT INTO user_feedback (item_id, action, note) VALUES (?, ?, ?)",
        (item_id, action, note),
    )
    conn.commit()
    conn.close()
    log.info(f"[profile] 선호 학습 기록: item={item_id}, action={action}")


def _learned_weights() -> tuple[dict, dict]:
    """긍정 상호작용한 물건의 (구, 유형) 빈도 -> 가중치."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT i.address_gu AS gu, i.item_type AS it
           FROM user_feedback f JOIN items i ON i.id = f.item_id
           WHERE f.action IN ('watch','like','bid','interested')"""
    ).fetchall()
    conn.close()
    gu_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    for r in rows:
        if r["gu"]:
            gu_counts[r["gu"]] = gu_counts.get(r["gu"], 0) + 1
        if r["it"]:
            type_counts[r["it"]] = type_counts.get(r["it"], 0) + 1
    return gu_counts, type_counts


def get_preference_score(item: dict, profile: dict | None = None) -> float:
    """0~1 선호 점수. 관심지역/ROI/리스크 + 학습 가중."""
    profile = profile or load_user_profile()
    addr = item.get("address_full") or ""
    gu = item.get("address_gu") or ""

    score = 0.0
    # 관심 지역
    regions = profile.get("interest_regions") or []
    if regions:
        score += 0.4 if any(r in addr or r in gu for r in regions) else 0.0
    else:
        score += 0.2  # 관심 지역 미설정 시 중립

    # 수익성
    roe = item.get("expected_roe")
    if roe is not None and roe >= profile["min_roi"] * 100:
        score += 0.3

    # 리스크
    loss = item.get("loss_probability")
    if loss is not None and loss <= 0.30:
        score += 0.3

    # 학습 가중(긍정 상호작용한 구/유형) — 최대 +0.2
    try:
        gu_counts, type_counts = _learned_weights()
        bonus = 0.0
        if gu and gu_counts.get(gu):
            bonus += 0.1
        if item.get("item_type") and type_counts.get(item.get("item_type")):
            bonus += 0.1
        score += bonus
    except Exception:
        pass

    return round(min(1.0, score), 3)


# ── 자본 적정성 ────────────────────────────────────────────
def affordability_by_scenario(item_id: int, profile: dict | None = None) -> dict:
    """시나리오별 자본 적정성. scenario_results 우선, 없으면 시나리오 계산."""
    profile = profile or load_user_profile()
    conn = get_connection()
    rows = conn.execute(
        "SELECT scenario, capital_needed, affordable, annualized_roe "
        "FROM scenario_results WHERE item_id=?", (item_id,)
    ).fetchall()
    conn.close()

    if not rows:
        from modules.scenarios import compare_scenarios
        res = compare_scenarios(item_id, profile)
        out = {}
        for name, v in res["scenarios"].items():
            out[name] = {
                "capital_needed": v["capital_needed"],
                "affordable": v["affordable"],
                "annualized_roe": v["annualized_roe"],
            }
        return out

    return {r["scenario"]: {
        "capital_needed": r["capital_needed"],
        "affordable": bool(r["affordable"]),
        "annualized_roe": r["annualized_roe"],
    } for r in rows}


def can_afford(item_id: int, profile: dict | None = None) -> bool:
    """어느 한 시나리오라도 자본으로 매수 가능하면 True."""
    aff = affordability_by_scenario(item_id, profile)
    return any(v["affordable"] for v in aff.values())


def recommend_for_user(profile: dict | None = None, limit: int = 5) -> list[dict]:
    """자본 가능 + 선호 점수 순 추천."""
    profile = profile or load_user_profile()
    conn = get_connection()
    items = [dict(r) for r in conn.execute(
        "SELECT * FROM items WHERE status='active' OR status IS NULL"
    ).fetchall()]
    conn.close()

    ranked: list[dict] = []
    for it in items:
        if not can_afford(it["id"], profile):
            continue
        aff = affordability_by_scenario(it["id"], profile)
        best = max(aff, key=lambda s: aff[s]["annualized_roe"] if aff[s]["affordable"] else -1e9)
        pref = get_preference_score(it, profile)
        ranked.append({
            "item_id": it["id"],
            "address": it.get("address_full"),
            "item_type": it.get("item_type"),
            "best_scenario": best,
            "annualized_roe": aff[best]["annualized_roe"],
            "capital_needed": aff[best]["capital_needed"],
            "preference_score": pref,
        })

    # 정렬: 선호점수 → 연환산 ROE → item_id (안정적)
    ranked.sort(key=lambda x: (x["preference_score"], x["annualized_roe"], -x["item_id"]),
                reverse=True)
    return ranked[:limit]
