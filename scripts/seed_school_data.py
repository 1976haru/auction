"""
scripts/seed_school_data.py
유명 학군 매핑을 school_districts 테이블에 입력(입지 학군 보너스용).
사용: python scripts/seed_school_data.py
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.database import get_connection, init_db  # noqa: E402
from core.logger import log  # noqa: E402

# (sido, sigungu, dong, district_name, bonus_points)
SCHOOL_DISTRICTS = [
    ("서울특별시", "강남구", "대치동", "강남 8학군", 4),
    ("서울특별시", "강남구", "도곡동", "강남 8학군", 4),
    ("서울특별시", "서초구", "반포동", "강남 8학군", 4),
    ("서울특별시", "양천구", "목동", "목동 학군", 4),
    ("서울특별시", "노원구", "중계동", "중계동 학군", 4),
    ("경기도", "성남시 분당구", "정자동", "분당 학군", 4),
    ("경기도", "안양시 동안구", "평촌동", "평촌 학군", 3),
    ("대구광역시", "수성구", "범어동", "수성 학군", 4),
]


def seed() -> int:
    init_db()
    conn = get_connection()
    c = conn.cursor()
    # 동일 동 중복 방지: dong 기준 정리
    for sido, sigungu, dong, name, bonus in SCHOOL_DISTRICTS:
        exists = c.execute(
            "SELECT id FROM school_districts WHERE sigungu=? AND dong=?",
            (sigungu, dong)
        ).fetchone()
        if exists:
            c.execute(
                "UPDATE school_districts SET district_name=?, bonus_points=? WHERE id=?",
                (name, bonus, exists["id"]),
            )
        else:
            c.execute(
                "INSERT INTO school_districts (sido, sigungu, dong, district_name, bonus_points)"
                " VALUES (?, ?, ?, ?, ?)",
                (sido, sigungu, dong, name, bonus),
            )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM school_districts").fetchone()[0]
    conn.close()
    log.info(f"[seed] school_districts {len(SCHOOL_DISTRICTS)}건 입력 (총 {n})")
    return len(SCHOOL_DISTRICTS)


if __name__ == "__main__":
    print(f"[OK] 학군 데이터 {seed()}건 입력 완료")
