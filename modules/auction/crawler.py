"""
modules/auction/crawler.py
법원경매정보 Playwright 크롤러
주의: 과도한 요청 금지, 요청 간 2~3초 대기 유지
"""
import asyncio
import json
import time
from core.config import TARGET_REGIONS, TARGET_TYPES
from core.database import upsert_item
from core.logger import log

# Playwright는 실제 크롤링 시에만 필요. mock-first 모드에서는 사용하지 않는다.
try:
    from playwright.async_api import async_playwright, TimeoutError as PWTimeout  # type: ignore
    _HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover
    async_playwright = None  # type: ignore
    PWTimeout = Exception  # type: ignore
    _HAS_PLAYWRIGHT = False

BASE_URL = "https://www.courtauction.go.kr"
SEARCH_URL = f"{BASE_URL}/RetrieveRealEstMulList.laf"


async def _search_page(page, region: str, item_type_code: str, page_no: int = 1) -> list[dict]:
    """검색 결과 페이지 파싱"""
    items = []
    try:
        await page.goto(SEARCH_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)  # 서버 부하 방지

        # 지역 선택 (실제 셀렉터는 사이트 구조에 맞게 수정 필요)
        try:
            await page.select_option("select[name='cortSdCode']", value=_region_to_code(region))
            await asyncio.sleep(1)
        except Exception:
            log.warning(f"[크롤러] 지역 선택 실패: {region}")

        # 물건 종류 선택
        try:
            await page.select_option("select[name='estatRealGbnCode']", value=item_type_code)
        except Exception:
            pass

        # 검색 버튼 클릭
        await page.click("input[type='button'][value='검색']")
        await asyncio.sleep(3)

        # 목록 파싱 (실제 테이블 구조에 맞게 수정)
        rows = await page.query_selector_all("table.Ltbl_list tbody tr")
        for row in rows[:10]:  # 초기에는 10건만
            try:
                cells = await row.query_selector_all("td")
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
                log.debug(f"[크롤러] 행 파싱 오류: {e}")
                continue

    except PWTimeout:
        log.warning(f"[크롤러] 페이지 타임아웃: {region}")
    except Exception as e:
        log.error(f"[크롤러] 오류: {e}")

    return items


def _region_to_code(region: str) -> str:
    """지역명 → 법원 코드 (사이트 확인 후 업데이트 필요)"""
    mapping = {
        "서울특별시": "B000201",
        "경기도":     "B000203",
        "인천광역시": "B000202",
        "부산광역시": "B000209",
    }
    return mapping.get(region, "")


def _item_type_to_code(item_type: str) -> str:
    """물건 종류 → 코드"""
    mapping = {
        "아파트":   "010001",
        "오피스텔": "010002",
        "빌라":     "010003",
        "단독주택": "010004",
    }
    return mapping.get(item_type, "")


def _parse_price(price_str: str) -> int:
    """가격 문자열 → 만원 (예: '5억 9,500만원' → 59500)"""
    if not price_str:
        return 0
    try:
        cleaned = price_str.replace(",", "").replace(" ", "")
        total = 0
        if "억" in cleaned:
            parts = cleaned.split("억")
            total += int(parts[0]) * 10000
            cleaned = parts[1]
        if "만원" in cleaned:
            num_part = cleaned.replace("만원", "")
            total += int(num_part) if num_part else 0
        return total
    except (ValueError, IndexError):
        return 0


async def crawl_auction_list(max_items: int = 20) -> int:
    """경매 목록 수집 메인 함수 (실제 크롤링)"""
    if not _HAS_PLAYWRIGHT:
        log.warning("[crawler] playwright 미설치 - 실제 크롤링 불가. mock_auction_api 사용.")
        return 0
    saved = 0
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = await context.new_page()

        for region in TARGET_REGIONS:
            for item_type in TARGET_TYPES:
                code = _item_type_to_code(item_type)
                if not code:
                    continue
                log.info(f"[크롤러] {region} / {item_type} 수집 중...")
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

                await asyncio.sleep(2)  # 서버 부하 방지
                if saved >= max_items:
                    break

        await browser.close()

    log.info(f"[크롤러] 경매 수집 완료: {saved}건")
    return saved


def run_crawl(max_items: int = 20):
    """동기 래퍼 (GitHub Actions 등에서 호출용)"""
    return asyncio.run(crawl_auction_list(max_items))
