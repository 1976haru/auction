"""
modules/valuation/mock_molit_api.py
국토부 실거래가 API의 mock 응답 생성기.
주소+물건유형으로 가짜 실거래 데이터를 만든다.
일부 케이스는 데이터 부족(거래량 0~1)으로 의도적으로 만들어 신뢰도 저하 시뮬.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any


def _seed_for(address: str, item_type: str) -> int:
    return abs(hash(f"{address}|{item_type}")) % (2**31)


def fetch_trades(address: str, item_type: str, area_m2: float = 0,
                 seed: int | None = None) -> list[dict]:
    """address/type으로 mock 실거래 목록 반환."""
    s = seed if seed is not None else _seed_for(address, item_type)
    rnd = random.Random(s)

    # 데이터 부족 시뮬 약 15%
    if rnd.random() < 0.15:
        n = rnd.randint(0, 1)
    else:
        n = rnd.randint(3, 12)

    base = {
        "아파트":   [50000, 70000, 90000, 120000],
        "오피스텔": [25000, 35000, 45000],
        "빌라":     [18000, 22000, 30000],
        "상가":     [80000, 110000, 160000],
        "토지":     [10000, 30000, 60000],
    }
    pool = base.get(item_type, [40000, 60000, 80000])
    center = rnd.choice(pool)

    out: list[dict] = []
    for i in range(n):
        days = rnd.randint(10, 360)
        price = int(center * rnd.uniform(0.85, 1.15))
        out.append({
            "complex_name": "(mock 단지)",
            "area_m2": round((area_m2 or rnd.uniform(40, 100)) + rnd.uniform(-3, 3), 2),
            "trade_price": price,
            "trade_date": (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d"),
            "address_dong": address.split()[-2] if len(address.split()) >= 2 else "",
            "source": "mock_molit",
        })
    return out


def summarize_trades(trades: list[dict]) -> dict:
    """거래 목록 -> 요약 통계."""
    if not trades:
        return {
            "avg_price_6m": 0,
            "avg_price_12m": 0,
            "max_price": 0,
            "min_price": 0,
            "transaction_count": 0,
            "data_shortage": True,
        }
    now = datetime.now()
    six = [t for t in trades if (now - datetime.strptime(t["trade_date"], "%Y-%m-%d")).days <= 180]
    twelve = trades
    prices_6 = [t["trade_price"] for t in six]
    prices_12 = [t["trade_price"] for t in twelve]
    return {
        "avg_price_6m": int(sum(prices_6) / len(prices_6)) if prices_6 else 0,
        "avg_price_12m": int(sum(prices_12) / len(prices_12)) if prices_12 else 0,
        "max_price": max(prices_12),
        "min_price": min(prices_12),
        "transaction_count": len(prices_12),
        "data_shortage": len(prices_12) < 2,
    }
