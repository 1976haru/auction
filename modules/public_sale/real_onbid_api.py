"""
modules/public_sale/real_onbid_api.py
온비드 공매 실 API 어댑터.

mock_onbid_api 와 동일한 시그니처:
    list_public_sale_items(count, seed) -> list[dict]
    get_public_sale_detail(mgmt_no, seed) -> dict

내부적으로 modules.public_sale.onbid_client 의 fetch_public_sale_list 사용.
키 없으면 빈 리스트.
"""
from __future__ import annotations

from typing import Any

from core.config import PUBLIC_DATA_KEY, TARGET_REGIONS
from core.logger import log


def list_public_sale_items(count: int = 50, seed: int | None = None) -> list[dict]:
    """실 온비드 API 호출. mock과 호환되는 dict 스키마로 변환."""
    if not PUBLIC_DATA_KEY:
        log.warning("[onbid_real] PUBLIC_DATA_KEY 없음 -> 빈 결과")
        return []
    try:
        from modules.public_sale.onbid_client import (
            _parse_price,
            fetch_public_sale_list,
        )
    except ImportError as e:
        log.warning(f"[onbid_real] onbid_client import 실패: {e}")
        return []

    out: list[dict] = []
    per_region = max(10, count // max(len(TARGET_REGIONS), 1))
    for region in TARGET_REGIONS:
        try:
            items = fetch_public_sale_list(region=region, page_size=per_region)
        except Exception as e:
            log.warning(f"[onbid_real] {region} 조회 실패: {e}")
            continue
        for raw in items:
            out.append({
                "source": "public_sale",
                "case_no": None,
                "mgmt_no": raw.get("pblsaleNo") or raw.get("mgtNo", ""),
                "item_type": raw.get("pblsaleKndNm", ""),
                "address_full": raw.get("cltrAddr", ""),
                "address_si": raw.get("sido", region),
                "address_gu": raw.get("sgg", ""),
                "address_dong": raw.get("umd", ""),
                "address_detail": raw.get("cltrAddrDtl", ""),
                "appraisal_price": _parse_price(raw.get("apprAmt")),
                "min_bid_price": _parse_price(raw.get("minumBidAmt") or raw.get("minBidAmt")),
                "fail_count": int(raw.get("bidFailNt", 0) or 0),
                "area_m2": float(raw.get("airSpc", 0) or 0),
                "floor": raw.get("flrNo", ""),
                "total_floor": raw.get("totFlrNo", ""),
                "bid_date": raw.get("bidBgnDt", ""),
                "status": "active",
                "court_name": None,
            })
        if len(out) >= count:
            break
    log.info(f"[onbid_real] 총 {len(out)}건 (real API)")
    return out[:count]


def get_public_sale_detail(mgmt_no: str, seed: int | None = None) -> dict:
    """실 온비드 상세조회는 onbid_client 에 미구현이라 stub.
    필요 시 별도 endpoint(`getPublicSaleDetail`) 호출 추가."""
    if not PUBLIC_DATA_KEY:
        return {"mgmt_no": mgmt_no, "memo": "(real) 키 없음"}
    return {"mgmt_no": mgmt_no, "memo": "(real) 상세조회 미구현"}
