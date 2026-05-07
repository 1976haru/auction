"""
modules/valuation/real_molit_api.py
국토부 실거래가 실 API 어댑터.

mock_molit_api 와 동일한 시그니처:
    fetch_trades(address, item_type, area_m2=0, seed=None) -> list[dict]

내부적으로 modules.price.molit_api 의 fetch_apt_trades 를 호출.
키 없으면 빈 리스트 + 경고. 호출 실패 시 빈 리스트 (price_matcher 가 mock fallback).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from core.config import PUBLIC_DATA_KEY
from core.logger import log


# 시/구 추출용 매핑 - molit_api.get_region_code 와 동일
def _parse_si_gu(address: str) -> tuple[str, str]:
    """주소 문자열에서 (시, 구) 추출."""
    if not address:
        return ("", "")
    parts = address.strip().split()
    if len(parts) < 2:
        return ("", "")
    si = parts[0]
    gu = parts[1] if len(parts) >= 2 else ""
    # "수원시 영통구" 처럼 시+구 두 토큰인 경우 처리
    if len(parts) >= 3 and ("시" in parts[1] and "구" in parts[2]):
        gu = f"{parts[1]} {parts[2]}"
    return (si, gu)


def fetch_trades(address: str, item_type: str, area_m2: float = 0,
                 seed: int | None = None, months_back: int = 6) -> list[dict]:
    """실 국토부 API 호출 - mock과 동일한 스키마 반환.

    mock_molit_api.fetch_trades 와 호환되는 시그니처. seed 파라미터는
    mock 호환을 위해 받지만 실제로는 사용하지 않음.

    Returns:
        [{complex_name, area_m2, trade_price, trade_date, address_dong, source}, ...]
    """
    if not PUBLIC_DATA_KEY:
        log.warning("[molit_real] PUBLIC_DATA_KEY 없음 -> 빈 결과")
        return []
    if item_type not in ("아파트", "빌라", "오피스텔"):
        # 국토부 API는 아파트/빌라만 지원. 그 외는 빈 결과.
        log.info(f"[molit_real] {item_type} 미지원 - 빈 결과")
        return []

    si, gu = _parse_si_gu(address)
    if not si or not gu:
        log.warning(f"[molit_real] 주소 파싱 실패: {address}")
        return []

    try:
        from modules.price.molit_api import (
            APT_URL,
            VILLA_URL,
            fetch_apt_trades,
            get_region_code,
        )
    except ImportError as e:
        log.warning(f"[molit_real] molit_api import 실패: {e}")
        return []

    region_code = get_region_code(si, gu)
    if not region_code:
        log.info(f"[molit_real] 지역코드 매핑 없음: {si} {gu}")
        return []

    out: list[dict] = []
    now = datetime.now()
    for i in range(months_back):
        ym = (now - timedelta(days=30 * i)).strftime("%Y%m")
        try:
            trades = fetch_apt_trades(region_code, ym)
        except Exception as e:
            log.warning(f"[molit_real] {ym} 조회 실패: {e}")
            continue
        # 면적 필터 (±10㎡)
        if area_m2:
            trades = [t for t in trades if abs(t.get("area_m2", 0) - area_m2) <= 10]
        for t in trades:
            t["source"] = "molit_real"
            out.append(t)

    log.info(f"[molit_real] {address} -> {len(out)}건 (real API)")
    return out
