"""
modules/auction/real_auction_api.py
법원경매 실 어댑터 - mock_auction_api 와 동일한 시그니처:
    list_auction_items(count, seed) -> list[dict]

내부적으로 crawler.crawl_auction_list 를 호출하고 DB 에서 다시 읽어와 반환한다.
Playwright 미설치 또는 실패 시 빈 리스트.
"""
from __future__ import annotations

import asyncio
from typing import Any

from core.database import get_connection, init_db
from core.logger import log


def list_auction_items(count: int = 50, seed: int | None = None) -> list[dict]:
    """실 법원경매 사이트 크롤링 -> DB upsert -> 최근 source='auction' 매물 반환.

    seed 는 mock 호환을 위한 인자. 실제로는 사용 안 함.
    """
    try:
        from modules.auction.crawler import (
            _HAS_PLAYWRIGHT,
            crawl_auction_list,
        )
    except ImportError as e:
        log.warning(f"[auction_real] crawler import 실패: {e}")
        return []

    if not _HAS_PLAYWRIGHT:
        log.warning("[auction_real] playwright 미설치 - 빈 결과")
        return []

    try:
        saved = asyncio.run(crawl_auction_list(max_items=count))
    except Exception as e:
        log.warning(f"[auction_real] 크롤링 실패: {e}")
        saved = 0

    if saved == 0:
        log.info("[auction_real] 새로 저장된 매물 없음 - DB 캐시 fallback")

    # DB 에서 최근 auction 매물 가져와 mock 스키마와 동일하게 반환
    init_db()
    conn = get_connection()
    rows = conn.execute("""
        SELECT * FROM items
        WHERE source = 'auction'
        ORDER BY created_at DESC LIMIT ?
    """, (count,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_auction_detail(case_no: str, seed: int | None = None) -> dict:
    """실 상세조회는 별도 페이지 크롤링 필요 - 현재는 캐시 단순 조회."""
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM items WHERE source='auction' AND case_no=?",
        (case_no,),
    ).fetchone()
    conn.close()
    if row:
        return dict(row)
    return {"case_no": case_no, "memo": "(real) 상세 캐시 없음 - crawler 보강 필요"}
