"""
modules/auction/mock_auction_api.py
법원경매 사이트 대체용 mock API.
실제 API/크롤링 인터페이스와 동일한 시그니처를 흉내낸다.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

REGIONS = [
    ("서울특별시", "강남구", "역삼동"),
    ("서울특별시", "마포구", "망원동"),
    ("서울특별시", "노원구", "상계동"),
    ("서울특별시", "송파구", "잠실동"),
    ("서울특별시", "성동구", "성수동"),
    ("경기도", "수원시", "매탄동"),
    ("경기도", "성남시", "정자동"),
    ("경기도", "고양시", "행신동"),
    ("인천광역시", "연수구", "송도동"),
    ("부산광역시", "해운대구", "우동"),
    ("대전광역시", "유성구", "관평동"),
]

TYPES = ["아파트", "오피스텔", "빌라", "상가", "토지"]
COURTS = ["서울중앙지방법원", "서울서부지방법원", "수원지방법원", "인천지방법원", "부산지방법원"]


def _new_case_no(rnd: random.Random) -> str:
    year = rnd.choice([2023, 2024, 2025])
    no = rnd.randint(10000, 99999)
    return f"{year}타경{no}"


def _bid_date(rnd: random.Random) -> str:
    days = rnd.randint(-3, 45)
    return (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")


def list_auction_items(count: int = 50, seed: int | None = 42) -> list[dict]:
    rnd = random.Random(seed)
    items: list[dict] = []
    for i in range(count):
        si, gu, dong = rnd.choice(REGIONS)
        item_type = rnd.choice(TYPES)
        appraisal = rnd.choice([15000, 22000, 30000, 45000, 65000, 85000, 120000, 180000])
        fail_count = rnd.choices([0, 1, 2, 3], weights=[3, 4, 2, 1])[0]
        ratio = max(0.55, 0.9 - 0.13 * fail_count)
        min_bid = int(appraisal * ratio)
        items.append({
            "source": "auction",
            "case_no": _new_case_no(rnd),
            "mgmt_no": None,
            "item_type": item_type,
            "address_full": f"{si} {gu} {dong} {rnd.randint(1, 999)}-{rnd.randint(1, 50)}",
            "address_si": si,
            "address_gu": gu,
            "address_dong": dong,
            "address_detail": f"{rnd.randint(1, 20)}층 {rnd.randint(101, 1820)}호",
            "appraisal_price": appraisal,
            "min_bid_price": min_bid,
            "fail_count": fail_count,
            "area_m2": round(rnd.uniform(33, 110), 2),
            "floor": str(rnd.randint(1, 20)),
            "total_floor": str(rnd.randint(5, 30)),
            "bid_date": _bid_date(rnd),
            "status": "active",
            "court_name": rnd.choice(COURTS),
        })
    return items


def get_auction_detail(case_no: str, seed: int | None = None) -> dict:
    rnd = random.Random(hash(case_no) ^ (seed or 0))
    return {
        "case_no": case_no,
        "court_name": rnd.choice(COURTS),
        "next_bid_date": _bid_date(rnd),
        "fail_count": rnd.randint(0, 3),
        "memo": "(mock) 상세조회 응답",
    }
