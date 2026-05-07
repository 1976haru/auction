"""
modules/auction/crawler.py
법원경매정보 (courtauction.go.kr) Playwright 크롤러.

설계 원칙
- selector 는 SELECTORS dict 에 모아둔다. 사이트 변경 시 한 곳만 수정.
- validate_site_selectors() 로 selector 가 살아있는지 1회 검증 가능.
- crawl_auction_list() 는 실패해도 예외를 위로 던지지 않고 [] 반환.
- 요청 간 RATE_LIMIT_SECONDS 만큼 대기 (서버 부하 방지).
- Playwright 미설치 환경에서는 import 자체는 성공하고 호출 시점에 안내 후 [] 반환.

selector 업데이트 워크플로
1) python scripts/check_court_auction.py
2) FAIL 표시된 selector 확인 -> 브라우저로 사이트 직접 열어 selector 새로 추출
3) SELECTORS dict 의 해당 키만 수정
4) 다시 check_court_auction.py 실행해서 OK 확인
5) git commit
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from core.config import TARGET_REGIONS, TARGET_TYPES
from core.database import upsert_item
from core.logger import log

try:
    from playwright.async_api import (  # type: ignore
        TimeoutError as PWTimeout,
        async_playwright,
    )
    _HAS_PLAYWRIGHT = True
except ImportError:
    async_playwright = None  # type: ignore
    PWTimeout = Exception  # type: ignore
    _HAS_PLAYWRIGHT = False


BASE_URL = "https://www.courtauction.go.kr"
SEARCH_URL = f"{BASE_URL}/RetrieveRealEstMulList.laf"
RATE_LIMIT_SECONDS = 3
PAGE_TIMEOUT_MS = 30_000

# ── selector 모음 ──────────────────────────────────────────────────
# 사이트 구조 변경 시 이 dict 만 수정하면 됨.
SELECTORS: dict[str, str] = {
    # 검색 페이지
    "region_select":     "select[name='cortSdCode']",
    "item_type_select":  "select[name='estatRealGbnCode']",
    "search_button":     "input[type='button'][value='검색']",
    # 검색 결과 테이블
    "result_table":      "table.Ltbl_list",
    "result_row":        "table.Ltbl_list tbody tr",
    "result_cells":      "td",
    # 상세 페이지 (선택적)
    "detail_link":       "a.viewDetail",
}


# ── 코드 매핑 (사이트 확인 후 검증 권장) ────────────────────────────
REGION_CODE = {
    "서울특별시": "B000201",
    "인천광역시": "B000202",
    "경기도":     "B000203",
    "부산광역시": "B000209",
    "대전광역시": "B000204",
    "광주광역시": "B000205",
    "대구광역시": "B000206",
    "울산광역시": "B000207",
}

ITEM_TYPE_CODE = {
    "아파트":   "010001",
    "오피스텔": "010002",
    "빌라":     "010003",
    "단독주택": "010004",
}


def _region_to_code(region: str) -> str:
    return REGION_CODE.get(region, "")


def _item_type_to_code(item_type: str) -> str:
    return ITEM_TYPE_CODE.get(item_type, "")


def _parse_price(price_str: str) -> int:
    """가격 문자열 -> 만원 (예: '5억 9,500만원' -> 59500)."""
    if not price_str:
        return 0
    try:
        cleaned = price_str.replace(",", "").replace(" ", "")
        total = 0
        if "억" in cleaned:
            parts = cleaned.split("억")
            total += int(parts[0]) * 10000
            cleaned = parts[1] if len(parts) > 1 else ""
        if "만원" in cleaned:
            num_part = cleaned.replace("만원", "")
            total += int(num_part) if num_part.isdigit() else 0
        return total
    except (ValueError, IndexError):
        return 0


async def _select_dropdown(page, selector: str, value: str) -> bool:
    if not value:
        return False
    try:
        await page.select_option(selector, value=value)
        return True
    except Exception as e:
        log.warning(f"[crawler] select 실패 selector={selector} value={value}: {e}")
        return False


async def _search_page(page, region: str, item_type_code: str) -> list[dict]:
    """검색 결과 페이지 파싱."""
    items: list[dict] = []
    try:
        await page.goto(SEARCH_URL, wait_until="networkidle",
                          timeout=PAGE_TIMEOUT_MS)
        await asyncio.sleep(2)

        await _select_dropdown(page, SELECTORS["region_select"],
                                _region_to_code(region))
        await asyncio.sleep(1)
        await _select_dropdown(page, SELECTORS["item_type_select"], item_type_code)

        try:
            await page.click(SELECTORS["search_button"])
        except Exception as e:
            log.warning(f"[crawler] 검색 버튼 클릭 실패: {e}")
            return []
        await asyncio.sleep(3)

        rows = await page.query_selector_all(SELECTORS["result_row"])
        for row in rows[:10]:
            try:
                cells = await row.query_selector_all(SELECTORS["result_cells"])
                if len(cells) < 5:
                    continue
                texts = [await c.inner_text() for c in cells]
                items.append({
                    "case_no":      texts[0].strip() if len(texts) > 0 else "",
                    "court_name":   texts[1].strip() if len(texts) > 1 else "",
                    "address_full": texts[2].strip() if len(texts) > 2 else "",
                    "appraisal_str": texts[3].strip() if len(texts) > 3 else "0",
                    "min_bid_str":   texts[4].strip() if len(texts) > 4 else "0",
                    "bid_date":     texts[5].strip() if len(texts) > 5 else "",
                })
            except Exception as e:
                log.debug(f"[crawler] 행 파싱 오류: {e}")
                continue
    except PWTimeout:
        log.warning(f"[crawler] 페이지 타임아웃: {region}")
    except Exception as e:
        log.error(f"[crawler] 오류: {e}")
    return items


async def crawl_auction_list(max_items: int = 20) -> int:
    """경매 목록 수집 메인 함수. 반환: 저장 건수."""
    if not _HAS_PLAYWRIGHT:
        log.warning(
            "[crawler] playwright 미설치. "
            "pip install playwright && playwright install chromium 후 재시도."
        )
        return 0

    saved = 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        try:
            for region in TARGET_REGIONS:
                for item_type in TARGET_TYPES:
                    code = _item_type_to_code(item_type)
                    if not code:
                        continue
                    log.info(f"[crawler] {region} / {item_type} 수집 중...")
                    raw_items = await _search_page(page, region, code)
                    for raw in raw_items:
                        data = {
                            "source":         "auction",
                            "case_no":        raw.get("case_no", ""),
                            "mgmt_no":        None,
                            "item_type":      item_type,
                            "address_full":   raw.get("address_full", ""),
                            "address_si":     region,
                            "address_gu":     "",
                            "address_dong":   "",
                            "address_detail": "",
                            "appraisal_price": _parse_price(raw.get("appraisal_str", "")),
                            "min_bid_price":   _parse_price(raw.get("min_bid_str", "")),
                            "fail_count":     0,
                            "area_m2":        None,
                            "floor":          None,
                            "total_floor":    None,
                            "bid_date":       raw.get("bid_date", ""),
                            "status":         "active",
                            "court_name":     raw.get("court_name", ""),
                            "raw_json":       json.dumps(raw, ensure_ascii=False),
                        }
                        item_id = upsert_item(data)
                        if item_id:
                            saved += 1
                        if saved >= max_items:
                            break
                    await asyncio.sleep(RATE_LIMIT_SECONDS)
                    if saved >= max_items:
                        break
                if saved >= max_items:
                    break
        finally:
            await browser.close()

    log.info(f"[crawler] 경매 수집 완료: {saved}건")
    return saved


def run_crawl(max_items: int = 20) -> int:
    """동기 래퍼."""
    return asyncio.run(crawl_auction_list(max_items))


# ── selector 검증 ─────────────────────────────────────────────────


async def _validate_async() -> dict:
    """검색 페이지를 한 번 열어 핵심 selector 가 존재하는지 확인."""
    if not _HAS_PLAYWRIGHT:
        return {
            "ok": False,
            "playwright_installed": False,
            "details": [],
            "note": "playwright 미설치. pip install playwright && playwright install chromium",
        }

    details = []
    success_count = 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            await page.goto(SEARCH_URL, wait_until="networkidle",
                              timeout=PAGE_TIMEOUT_MS)
            for key, sel in SELECTORS.items():
                try:
                    el = await page.query_selector(sel)
                    found = el is not None
                except Exception:
                    found = False
                details.append({"key": key, "selector": sel, "found": found})
                if found:
                    success_count += 1
        except Exception as e:
            return {
                "ok": False, "playwright_installed": True,
                "details": details,
                "note": f"페이지 접근 실패: {e}",
            }
        finally:
            await browser.close()
    return {
        "ok": success_count == len(SELECTORS),
        "playwright_installed": True,
        "found_count": success_count,
        "total": len(SELECTORS),
        "details": details,
        "note": "모든 selector 발견" if success_count == len(SELECTORS)
                 else f"{success_count}/{len(SELECTORS)} 만 발견 - SELECTORS dict 업데이트 필요",
    }


def validate_site_selectors() -> dict:
    """동기 wrapper. 사이트에 1회 접속해 selector 검증."""
    return asyncio.run(_validate_async())
