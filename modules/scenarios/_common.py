"""
modules/scenarios/_common.py
시나리오 시뮬레이터 공통 헬퍼.

단위 주의: items 테이블의 가격(appraisal_price/min_bid_price)은 '만원' 단위.
금융 계산은 '원' 단위로 수행하므로 WON_PER_MAN(10,000)으로 환산한다.
"""
from __future__ import annotations

from core.logger import log

WON_PER_MAN = 10_000

# 기본 사용자 프로필 (자기자본 5천~2억). core.user_profile(블록 9) 있으면 그쪽 우선.
DEFAULT_PROFILE: dict = {
    "capital_max": 200_000_000,
    "capital_min": 50_000_000,
    "annual_income": 60_000_000,
    "other_debt_monthly": 300_000,
    "loan_rate": 0.04,
    "ltv": 0.70,
    "dsr": 0.40,
    "loan_years": 30,
    "scenario_weights": {"short_sale": 0.30, "rental": 0.40, "residence": 0.30},
    "annual_appreciation": 0.03,
    "is_one_house": True,
}

# 지역/유형별 임대수익률(cap rate)
_CAP_RATE_BY_TYPE = {
    "오피스텔": 0.050, "상가": 0.055, "빌라": 0.045, "단독": 0.040,
}


def load_profile(user_profile: dict | None = None) -> dict:
    """user_profile 우선, 없으면 core.user_profile, 없으면 DEFAULT_PROFILE."""
    if user_profile:
        merged = {**DEFAULT_PROFILE, **user_profile}
        return merged
    try:
        from core.user_profile import load_user_profile  # 블록 9
        prof = load_user_profile()
        if prof:
            return {**DEFAULT_PROFILE, **prof}
    except Exception:
        pass
    return dict(DEFAULT_PROFILE)


def get_item(item_id: int) -> dict:
    from core.database import get_connection
    conn = get_connection()
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    return dict(row) if row else {}


def market_price_won(item: dict) -> int:
    """시세(원) 추정. valuation.price_matcher 우선, 실패 시 감정가 기반."""
    est_man = 0
    try:
        from modules.valuation.price_matcher import match_price
        res = match_price(item)
        est_man = res.get("market_price_estimate") or 0
    except Exception as e:
        log.info(f"[scenarios] 시세 매칭 실패 -> 감정가 기반: {e}")

    # 감정가 대비 합리적 범위(60~140%)로 클램프 — mock 시세의 이상치 방지
    appraisal = item.get("appraisal_price") or item.get("min_bid_price") or 0
    if appraisal:
        lo, hi = appraisal * 0.6, appraisal * 1.4
        if not est_man or not (lo <= est_man <= hi):
            est_man = int(appraisal * 0.95)
    elif not est_man:
        est_man = item.get("min_bid_price") or 0
    return int(est_man * WON_PER_MAN)


def eviction_cost_won(item_id: int, item: dict | None = None) -> int:
    """명도 예상 비용(원). 저장값 우선, 없으면 명도 분석 1회 수행."""
    item = item or get_item(item_id)
    saved = item.get("eviction_cost_estimate")
    if saved:
        return int(saved)
    try:
        from modules.eviction import analyze_eviction
        return int(analyze_eviction(item_id, item_info=item)["cost_estimate"])
    except Exception:
        return 3_000_000


def location_total(item_id: int) -> int:
    """입지 총점(0~100). 저장값 우선, 없으면 계산."""
    try:
        from modules.location.total_scorer import get_location_score, calculate_location_score
        loc = get_location_score(item_id) or calculate_location_score(item_id)
        return int(loc.get("total") or 0)
    except Exception:
        return 50


def cap_rate(item_type: str | None, address: str | None) -> float:
    """임대수익률(연). 유형 우선, 아파트는 지역별 차등."""
    it = item_type or ""
    for key, rate in _CAP_RATE_BY_TYPE.items():
        if key in it:
            return rate
    # 아파트: 서울 3.5%, 그 외 수도권 4.0%
    if "서울" in (address or ""):
        return 0.035
    return 0.040


def market_premium(loc_total: int) -> float:
    """단타 매도 프리미엄(시세 대비). 입지에 따라 ±."""
    if loc_total >= 80:
        return 0.05
    if loc_total <= 40:
        return -0.03
    return 0.0


def get_loan(bid_won: int, profile: dict) -> dict:
    from modules.finance.loan_simulator import calc_max_loan
    return calc_max_loan(
        bid_won,
        annual_income=profile.get("annual_income", 0),
        existing_debt_monthly=profile.get("other_debt_monthly", 0),
        ltv=profile.get("ltv", 0.70),
        dsr_limit=profile.get("dsr", 0.40),
        annual_rate=profile.get("loan_rate", 0.04),
        years=profile.get("loan_years", 30),
    )


def roe_to_score(annualized_roe: float, affordable: bool) -> float:
    """연환산 ROE -> 0~100 점수. -20%~50% 구간을 0~100으로 매핑."""
    base = max(-20.0, min(50.0, annualized_roe))
    score = (base + 20) / 70 * 100
    if not affordable:
        score *= 0.4
    return round(score, 1)
