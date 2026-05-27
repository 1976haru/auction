"""
modules/market/winning_rate_stats.py
지역·유형·유찰횟수별 낙찰가율 통계.
bid_results 테이블이 있으면 집계, 없으면 합리적 기본 범위를 사용한다.
"""
from __future__ import annotations

from core.database import get_connection

# (지역키, 유형) -> (낮은 낙찰가율, 높은 낙찰가율)  단위: 비율(0~1)
_DEFAULT_RANGES: dict[tuple[str, str], tuple[float, float]] = {
    ("서울강남", "아파트"): (0.92, 0.95),
    ("서울", "아파트"): (0.87, 0.92),
    ("경기", "아파트"): (0.85, 0.90),
    ("인천", "아파트"): (0.83, 0.88),
    ("지방", "아파트"): (0.75, 0.85),
}
_TYPE_RANGES: dict[str, tuple[float, float]] = {
    "오피스텔": (0.80, 0.85),
    "빌라": (0.78, 0.85),
    "상가": (0.65, 0.75),
    "토지": (0.60, 0.75),
    "단독": (0.72, 0.82),
}
_GANGNAM = ("강남", "서초", "송파")


def _region_key(sido: str | None, sigungu: str | None) -> str:
    s = (sido or "") + (sigungu or "")
    if "서울" in s and any(g in s for g in _GANGNAM):
        return "서울강남"
    if "서울" in s:
        return "서울"
    if "경기" in s:
        return "경기"
    if "인천" in s:
        return "인천"
    return "지방"


def _bid_results_table_exists(conn) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='bid_results'"
    ).fetchone()
    return row is not None


def get_winning_rate(
    sido: str | None,
    sigungu: str | None,
    item_type: str | None = "아파트",
    fail_count: int = 0,
) -> dict:
    """낙찰가율 통계.

    Returns: {expected_rate, low, high, sample_count, period_months, confidence, source}
    """
    item_type = item_type or "아파트"
    region_key = _region_key(sido, sigungu)

    # 1) 실데이터 집계 시도
    sample_count = 0
    agg_rate = None
    try:
        conn = get_connection()
        if _bid_results_table_exists(conn):
            row = conn.execute(
                """SELECT AVG(winning_ratio) AS r, COUNT(*) AS n
                   FROM bid_results
                   WHERE (sido=? OR ?='') AND (item_type=? OR ?='')""",
                (sido or "", sido or "", item_type, item_type),
            ).fetchone()
            if row and row["n"]:
                agg_rate = row["r"]
                sample_count = int(row["n"])
        conn.close()
    except Exception:
        pass

    if agg_rate and sample_count >= 5:
        low = round(agg_rate * 0.97, 3)
        high = round(agg_rate * 1.03, 3)
        expected = round(agg_rate, 3)
        confidence = 0.8
        source = "bid_results"
    else:
        # 2) 기본 범위
        rng = _DEFAULT_RANGES.get((region_key, item_type))
        if rng is None:
            rng = _TYPE_RANGES.get(item_type) or _DEFAULT_RANGES[(region_key, "아파트")] \
                if (region_key, "아파트") in _DEFAULT_RANGES else (0.75, 0.85)
        low, high = rng
        expected = round((low + high) / 2, 3)
        confidence = 0.5
        source = "default"

    # 유찰 횟수가 많을수록 낙찰가율 소폭 하락
    drop = min(0.06, 0.02 * int(fail_count or 0))
    expected = round(max(0.5, expected - drop), 3)

    return {
        "expected_rate": expected,
        "low": low,
        "high": high,
        "sample_count": sample_count,
        "period_months": 12,
        "confidence": confidence,
        "region_key": region_key,
        "source": source,
    }
