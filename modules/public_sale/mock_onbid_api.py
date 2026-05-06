"""
modules/public_sale/mock_onbid_api.py
온비드 공매 mock API.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

REGIONS = [
    ("서울특별시", "강북구", "수유동"),
    ("서울특별시", "관악구", "봉천동"),
    ("서울특별시", "영등포구", "여의도동"),
    ("경기도", "용인시", "수지구"),
    ("경기도", "안양시", "동안구"),
    ("인천광역시", "남동구", "구월동"),
    ("부산광역시", "남구", "대연동"),
    ("대전광역시", "서구", "둔산동"),
    ("대구광역시", "수성구", "범어동"),
    ("광주광역시", "북구", "운암동"),
]

TYPES = ["아파트", "오피스텔", "빌라", "상가", "토지"]


def _bid_period(rnd: random.Random) -> str:
    start = datetime.now() + timedelta(days=rnd.randint(-2, 30))
    end = start + timedelta(days=2)
    return f"{start:%Y-%m-%d}~{end:%Y-%m-%d}"


def list_public_sale_items(count: int = 50, seed: int | None = 42) -> list[dict]:
    rnd = random.Random(seed)
    items: list[dict] = []
    for i in range(count):
        si, gu, dong = rnd.choice(REGIONS)
        item_type = rnd.choice(TYPES)
        appraisal = rnd.choice([12000, 24000, 36000, 50000, 80000, 110000, 150000])
        fail_count = rnd.choices([0, 1, 2], weights=[5, 3, 2])[0]
        ratio = max(0.6, 0.92 - 0.12 * fail_count)
        min_bid = int(appraisal * ratio)
        items.append({
            "source": "public_sale",
            "case_no": None,
            "mgmt_no": f"PS-{rnd.randint(2023, 2025)}-{rnd.randint(10000, 99999)}",
            "item_type": item_type,
            "address_full": f"{si} {gu} {dong} {rnd.randint(1, 500)}",
            "address_si": si,
            "address_gu": gu,
            "address_dong": dong,
            "address_detail": f"{rnd.randint(1, 15)}층 {rnd.randint(101, 1520)}호",
            "appraisal_price": appraisal,
            "min_bid_price": min_bid,
            "fail_count": fail_count,
            "area_m2": round(rnd.uniform(25, 130), 2),
            "floor": str(rnd.randint(1, 15)),
            "total_floor": str(rnd.randint(3, 25)),
            "bid_date": _bid_period(rnd),
            "status": "active",
            "court_name": None,
        })
    return items


def get_public_sale_detail(mgmt_no: str, seed: int | None = None) -> dict:
    rnd = random.Random(hash(mgmt_no) ^ (seed or 0))
    return {
        "mgmt_no": mgmt_no,
        "bid_period": _bid_period(rnd),
        "fail_count": rnd.randint(0, 2),
        "memo": "(mock) 공매 상세조회 응답",
    }
