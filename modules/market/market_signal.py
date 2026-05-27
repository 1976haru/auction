"""
modules/market/market_signal.py
시장 시그널 감지(상승/하락/중립).
실데이터(뉴스/금리/정책)가 없으면 지역 기반 결정적 mock 시그널을 반환한다.
"""
from __future__ import annotations

from modules.location._mockutil import seeded_rng
from modules.location.development_scorer import score_development


def detect_signals(sido: str | None, sigungu: str | None) -> dict:
    """지역 시장 시그널.

    Returns: {overall_signal, key_signals[], recommendation}
    """
    region = f"{sido or ''} {sigungu or ''}".strip()
    rng = seeded_rng("market_signal", region)
    key_signals: list[dict] = []

    # 1) 낙찰가율 변동(mock, ±%p)
    rate_delta = round(rng.uniform(-4, 4), 1)
    if abs(rate_delta) >= 3:
        key_signals.append({
            "type": "winning_rate_shift",
            "detail": f"전월 대비 낙찰가율 {rate_delta:+.1f}%p 변동",
            "direction": "up" if rate_delta > 0 else "down",
        })

    # 2) 거래량 변동(mock)
    volume_delta = rng.randint(-40, 50)
    if abs(volume_delta) >= 30:
        key_signals.append({
            "type": "volume_shift",
            "detail": f"전월 대비 거래량 {volume_delta:+d}%",
            "direction": "up" if volume_delta > 0 else "down",
        })

    # 3) 개발 호재(뉴스 검색 연동)
    dev = score_development(region, sigungu)
    if dev["news_count"] >= 5:
        key_signals.append({
            "type": "development",
            "detail": dev["development_news"],
            "direction": "up",
        })

    # 4) 금리/정책(mock)
    if rng.random() < 0.3:
        rate_hike = rng.random() < 0.5
        key_signals.append({
            "type": "interest_rate",
            "detail": "기준금리 " + ("인상 기조" if rate_hike else "인하 기조"),
            "direction": "down" if rate_hike else "up",
        })

    ups = sum(1 for s in key_signals if s.get("direction") == "up")
    downs = sum(1 for s in key_signals if s.get("direction") == "down")
    if ups - downs >= 1:
        overall = "bullish"
        rec = "수요 회복/호재 신호가 우세해 경쟁 심화 가능성이 있어 보입니다."
    elif downs - ups >= 1:
        overall = "bearish"
        rec = "약세 신호가 우세해 보수적 입찰가 접근이 필요해 보입니다."
    else:
        overall = "neutral"
        rec = "뚜렷한 방향성 신호가 적어 개별 물건 분석이 더 중요해 보입니다."

    return {
        "overall_signal": overall,
        "key_signals": key_signals,
        "recommendation": rec,
    }
