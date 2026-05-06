"""
scripts/seed_sample_data.py
MVP 확인용 샘플 데이터 — 경매 3건 + 공매 3건
"""
import os
import sys
import json

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.database import get_connection, upsert_item, init_db
from core.logger import log

SAMPLE_ITEMS = [
    # ── 경매 3건 ─────────────────────────────────────────────
    {
        "source": "auction",
        "case_no": "2024타경12345",
        "mgmt_no": None,
        "item_type": "아파트",
        "address_full": "서울특별시 마포구 망원동 123-45 OO아파트 12층",
        "address_si": "서울특별시",
        "address_gu": "마포구",
        "address_dong": "망원동",
        "address_detail": "12층 1201호",
        "appraisal_price": 85000,   # 8.5억
        "min_bid_price":   59500,   # 5.95억 (유찰2회 70%)
        "fail_count": 2,
        "area_m2": 59.8,
        "floor": "12",
        "total_floor": "20",
        "bid_date": "2025-07-15",
        "status": "active",
        "court_name": "서울서부지방법원",
        "raw_json": json.dumps({"note": "샘플 데이터"}, ensure_ascii=False),
    },
    {
        "source": "auction",
        "case_no": "2024타경67890",
        "mgmt_no": None,
        "item_type": "오피스텔",
        "address_full": "서울특별시 강남구 역삼동 456 OO오피스텔 8층",
        "address_si": "서울특별시",
        "address_gu": "강남구",
        "address_dong": "역삼동",
        "address_detail": "8층 802호",
        "appraisal_price": 45000,   # 4.5억
        "min_bid_price":   31500,   # 3.15억 (70%)
        "fail_count": 1,
        "area_m2": 33.0,
        "floor": "8",
        "total_floor": "15",
        "bid_date": "2025-07-22",
        "status": "active",
        "court_name": "서울중앙지방법원",
        "raw_json": json.dumps({"note": "샘플 데이터"}, ensure_ascii=False),
    },
    {
        "source": "auction",
        "case_no": "2024타경11111",
        "mgmt_no": None,
        "item_type": "빌라",
        "address_full": "경기도 수원시 영통구 매탄동 789 OO빌라 3층",
        "address_si": "경기도",
        "address_gu": "수원시 영통구",
        "address_dong": "매탄동",
        "address_detail": "3층 301호",
        "appraisal_price": 22000,   # 2.2억
        "min_bid_price":   15400,   # 1.54억 (유찰2회)
        "fail_count": 2,
        "area_m2": 49.5,
        "floor": "3",
        "total_floor": "5",
        "bid_date": "2025-07-29",
        "status": "active",
        "court_name": "수원지방법원",
        "raw_json": json.dumps({"note": "샘플 데이터"}, ensure_ascii=False),
    },

    # ── 공매 3건 ─────────────────────────────────────────────
    {
        "source": "public_sale",
        "case_no": None,
        "mgmt_no": "PS-2024-00001",
        "item_type": "아파트",
        "address_full": "서울특별시 노원구 상계동 101 OO아파트 5층",
        "address_si": "서울특별시",
        "address_gu": "노원구",
        "address_dong": "상계동",
        "address_detail": "5층 502호",
        "appraisal_price": 38000,   # 3.8억
        "min_bid_price":   34200,   # 3.42억 (90%)
        "fail_count": 0,
        "area_m2": 84.0,
        "floor": "5",
        "total_floor": "14",
        "bid_date": "2025-07-10~2025-07-12",
        "status": "active",
        "court_name": None,
        "raw_json": json.dumps({"note": "온비드 샘플", "source_site": "onbid"}, ensure_ascii=False),
    },
    {
        "source": "public_sale",
        "case_no": None,
        "mgmt_no": "PS-2024-00002",
        "item_type": "상가",
        "address_full": "경기도 성남시 분당구 정자동 222 1층 101호",
        "address_si": "경기도",
        "address_gu": "성남시 분당구",
        "address_dong": "정자동",
        "address_detail": "1층 101호",
        "appraisal_price": 120000,  # 12억
        "min_bid_price":   96000,   # 9.6억 (80%)
        "fail_count": 1,
        "area_m2": 55.2,
        "floor": "1",
        "total_floor": "10",
        "bid_date": "2025-07-17~2025-07-19",
        "status": "active",
        "court_name": None,
        "raw_json": json.dumps({"note": "온비드 샘플"}, ensure_ascii=False),
    },
    {
        "source": "public_sale",
        "case_no": None,
        "mgmt_no": "PS-2024-00003",
        "item_type": "빌라",
        "address_full": "인천광역시 연수구 송도동 333 OO빌라 2층",
        "address_si": "인천광역시",
        "address_gu": "연수구",
        "address_dong": "송도동",
        "address_detail": "2층 201호",
        "appraisal_price": 28000,   # 2.8억
        "min_bid_price":   22400,   # 2.24억 (80%)
        "fail_count": 1,
        "area_m2": 62.0,
        "floor": "2",
        "total_floor": "4",
        "bid_date": "2025-07-24~2025-07-26",
        "status": "active",
        "court_name": None,
        "raw_json": json.dumps({"note": "온비드 샘플"}, ensure_ascii=False),
    },
]

# 샘플 실거래가 데이터
SAMPLE_PRICES = [
    # item_id는 upsert 후 매핑
    {"item_idx": 0, "trade_price": 78000, "area_m2": 59.8, "trade_date": "2025-04-15"},
    {"item_idx": 0, "trade_price": 80000, "area_m2": 59.8, "trade_date": "2025-02-20"},
    {"item_idx": 1, "trade_price": 43000, "area_m2": 33.0, "trade_date": "2025-03-10"},
    {"item_idx": 2, "trade_price": 21000, "area_m2": 49.5, "trade_date": "2025-01-05"},
    {"item_idx": 3, "trade_price": 37500, "area_m2": 84.0, "trade_date": "2025-05-01"},
]


def seed():
    init_db()
    log.info("[시드] 샘플 데이터 입력 시작")

    item_ids = []
    for item in SAMPLE_ITEMS:
        item_id = upsert_item(item)
        item_ids.append(item_id)
        log.info(f"[시드] 저장: id={item_id} | {item['address_full'][:30]}")

    # 실거래가 샘플 입력
    conn = get_connection()
    c = conn.cursor()
    for p in SAMPLE_PRICES:
        item_id = item_ids[p["item_idx"]]
        c.execute("""
            INSERT OR IGNORE INTO price_records
                (item_id, trade_price, area_m2, trade_date, source)
            VALUES (?, ?, ?, ?, 'sample')
        """, (item_id, p["trade_price"], p["area_m2"], p["trade_date"]))
    conn.commit()
    conn.close()

    print(f"\n✅ 샘플 데이터 입력 완료!")
    print(f"   경매 3건 + 공매 3건 = 총 {len(SAMPLE_ITEMS)}건")
    print(f"   실거래가 샘플 {len(SAMPLE_PRICES)}건")
    print(f"\n다음 명령어로 대시보드를 열어보세요:")
    print(f"   streamlit run dashboard/app.py")


if __name__ == "__main__":
    seed()
