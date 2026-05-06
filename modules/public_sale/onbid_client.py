"""
modules/public_sale/onbid_client.py
온비드 공매 API 클라이언트
API 키: data.go.kr → 온비드 공매물건 검색 서비스 활용 신청
"""
import requests
import json
from core.config import PUBLIC_DATA_KEY, TARGET_REGIONS, TARGET_TYPES
from core.database import upsert_item
from core.logger import log

# 온비드 공매물건 목록 API
LIST_URL = "https://apis.data.go.kr/1160100/service/GetPublicSaleInfo/getPublicSaleList"
DETAIL_URL = "https://apis.data.go.kr/1160100/service/GetPublicSaleInfo/getPublicSaleDetail"


def fetch_public_sale_list(
    region: str = "",
    item_type: str = "",
    page: int = 1,
    page_size: int = 20,
) -> list[dict]:
    """공매 물건 목록 조회"""
    if not PUBLIC_DATA_KEY:
        log.warning("[공매] PUBLIC_DATA_KEY 없음 — 빈 결과")
        return []

    params = {
        "serviceKey": PUBLIC_DATA_KEY,
        "numOfRows":  page_size,
        "pageNo":     page,
        "type":       "json",
    }
    if region:
        params["sido"] = region
    if item_type:
        params["pblsaleSe"] = item_type

    try:
        resp = requests.get(LIST_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("response", {}).get("body", {}).get("items", {})
        if isinstance(items, dict):
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        log.info(f"[공매] 목록 조회: {len(items)}건")
        return items or []
    except Exception as e:
        log.error(f"[공매] API 오류: {e}")
        return []


def parse_and_save_item(raw: dict) -> int | None:
    """API 응답 → 정규화 → DB 저장. item_id 반환"""
    try:
        # 필드명은 실제 API 응답에 맞게 조정 필요
        data = {
            "source":         "public_sale",
            "case_no":        None,
            "mgmt_no":        raw.get("pblsaleNo") or raw.get("mgtNo", ""),
            "item_type":      raw.get("pblsaleKndNm", ""),
            "address_full":   raw.get("cltrAddr", ""),
            "address_si":     raw.get("sido", ""),
            "address_gu":     raw.get("sgg", ""),
            "address_dong":   raw.get("umd", ""),
            "address_detail": raw.get("cltrAddrDtl", ""),
            "appraisal_price": _parse_price(raw.get("apprAmt")),
            "min_bid_price":   _parse_price(raw.get("minumBidAmt") or raw.get("minBidAmt")),
            "fail_count":     int(raw.get("bidFailNt", 0) or 0),
            "area_m2":        float(raw.get("pblsaleSe", 0) or 0),
            "floor":          raw.get("flrNo", ""),
            "total_floor":    raw.get("totFlrNo", ""),
            "bid_date":       raw.get("bidBgnDt", ""),
            "status":         "active",
            "court_name":     None,
            "raw_json":       json.dumps(raw, ensure_ascii=False),
        }
        return upsert_item(data)
    except Exception as e:
        log.error(f"[공매] 파싱 오류: {e} / raw={raw}")
        return None


def _parse_price(val) -> int:
    """가격 문자열 → 만원 단위 정수"""
    if val is None:
        return 0
    try:
        return int(str(val).replace(",", "").replace(" ", "")) // 10000
    except ValueError:
        return 0


def collect_public_sales():
    """관심 지역·물건 종류 기준으로 공매 수집 후 DB 저장"""
    saved = 0
    for region in TARGET_REGIONS:
        items = fetch_public_sale_list(region=region, page_size=30)
        for raw in items:
            item_id = parse_and_save_item(raw)
            if item_id:
                saved += 1
    log.info(f"[공매] 총 {saved}건 저장 완료")
    return saved
