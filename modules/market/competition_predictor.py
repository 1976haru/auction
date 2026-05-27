"""
modules/market/competition_predictor.py
입찰자 수 예측 + 예상 낙찰가 추정.
유찰 횟수를 기준으로 한 뒤 인기/기피 요소로 가감산한다.
"""
from __future__ import annotations

from core.logger import log

# 유찰 횟수 -> 기본 입찰자 수
BASE_BIDDERS = {0: 5, 1: 4, 2: 3}  # 3회 이상은 2명


def _base_by_fail(fail_count: int) -> int:
    return BASE_BIDDERS.get(int(fail_count or 0), 2)


def _winning_multiplier(bidders: int) -> float:
    if bidders >= 5:
        return 1.15
    if bidders >= 3:
        return 1.08
    if bidders == 2:
        return 1.03
    return 1.01


def _level(bidders: int) -> str:
    if bidders >= 6:
        return "fierce"
    if bidders >= 4:
        return "high"
    if bidders >= 2:
        return "medium"
    return "low"


def predict_competition(item: dict) -> dict:
    """입찰자 수/낙찰가 예측.

    item 권장 키:
      fail_count, min_bid_price, market_price(시세, 동일 단위), item_type,
      location_total(입지 점수), eviction_difficulty,
      near_station(역세권 도보5분, bool), is_new(신축, bool),
      has_lien, has_priority_tenant, is_share (bool)
    """
    fail_count = int(item.get("fail_count") or 0)
    bidders = _base_by_fail(fail_count)
    factors: list[str] = [f"유찰 {fail_count}회 기준 {bidders}명"]

    loc = item.get("location_total")
    min_bid = item.get("min_bid_price") or 0
    market = item.get("market_price") or 0

    # ── 인기 요소 (+) ──
    if item.get("near_station"):
        bidders += 3
        factors.append("역세권(도보 5분) +3")
    if loc is not None and loc >= 80:
        bidders += 2
        factors.append("입지 80점+ +2")
    if item.get("is_new"):
        bidders += 2
        factors.append("신축(10년 이내) +2")
    if market and min_bid and min_bid <= market * 0.70:
        bidders += 3
        factors.append("최저가 시세 70% 이하 +3")

    # ── 기피 요소 (-) ──
    if item.get("has_lien"):
        bidders -= 2
        factors.append("유치권/법정지상권 -2")
    if item.get("has_priority_tenant"):
        bidders -= 2
        factors.append("대항력 임차인 -2")
    if item.get("is_share"):
        bidders -= 3
        factors.append("지분 매각 -3")
    if (item.get("eviction_difficulty") or 0) >= 7:
        bidders -= 1
        factors.append("명도 난이도 7+ -1")
    if loc is not None and loc <= 40:
        bidders -= 1
        factors.append("입지 40점 이하 -1")

    bidders = max(1, bidders)
    mult = _winning_multiplier(bidders)
    expected_winning_price = int(round(min_bid * mult)) if min_bid else 0
    expected_winning_ratio = round(mult, 3)

    result = {
        "estimated_bidders": bidders,
        "confidence_low": max(1, bidders - 1),
        "confidence_high": bidders + 2,
        "expected_winning_price": expected_winning_price,
        "expected_winning_ratio": expected_winning_ratio,
        "competition_level": _level(bidders),
        "factors": factors,
    }
    log.info(
        f"[market] 입찰자 예측 ~{bidders}명({result['competition_level']}), "
        f"예상 낙찰배수 {mult}"
    )
    return result
