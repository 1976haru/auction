"""
modules/valuation/price_matcher.py
시세 매칭 + 신뢰도 산정.
"""
from __future__ import annotations

import json
from typing import Any

from core.config import USE_MOCK_APIS
from core.database import get_connection, init_db
from core.logger import log
from core.utils import safe_json
from modules.valuation.mock_molit_api import fetch_trades, summarize_trades


def _confidence(transaction_count: int, addr_match: bool, type_match: bool) -> tuple[str, str]:
    if not addr_match or not type_match:
        return "very_low", "주소 매칭 실패 또는 물건 유형 불일치"
    if transaction_count >= 5:
        return "high", "거래 5건 이상, 동일 유형/지역"
    if transaction_count >= 2:
        return "medium", "거래 2~4건"
    if transaction_count >= 1:
        return "low", "거래 1건 이하"
    return "very_low", "실거래 데이터 없음"


def match_price(item: dict[str, Any], use_mock: bool | None = None) -> dict:
    use_mock = USE_MOCK_APIS if use_mock is None else use_mock
    address = item.get("address_full", "")
    item_type = item.get("item_type", "")
    area = float(item.get("area_m2") or 0)

    if use_mock:
        trades = fetch_trades(address, item_type, area_m2=area)
    else:
        trades = []  # 실제 API 연동은 인터페이스 자리만 확보
    summary = summarize_trades(trades)

    market_price = summary["avg_price_6m"] or summary["avg_price_12m"]
    if market_price == 0 and item.get("appraisal_price"):
        market_price = int(item["appraisal_price"] * 0.95)

    minimum_to_market = (item.get("min_bid_price", 0) / market_price) if market_price else 0
    appraisal_to_market = (item.get("appraisal_price", 0) / market_price) if market_price else 0

    addr_match = bool(address)
    type_match = bool(item_type)
    conf, reason = _confidence(summary["transaction_count"], addr_match, type_match)

    # 감정가 거품 감지 (시세 대비 과대평가만 거름. 저평가는 매수자 우호).
    inflation_warning: list[str] = []
    if appraisal_to_market and appraisal_to_market > 1.5:
        inflation_warning.append(
            f"감정가가 시세의 {appraisal_to_market * 100:.0f}% - 비정상적으로 높음"
        )
    if minimum_to_market and minimum_to_market > 1.2:
        inflation_warning.append(
            f"최저가가 시세의 {minimum_to_market * 100:.0f}% - 시세 이상으로 책정됨"
        )
    # 시세 대비 감정가가 매우 낮은 케이스(0.5 미만)는 mock 한계일 수 있어
    # data_quality_warning 별도로 표시하지만 inflation 필터로는 막지 않는다.
    data_quality_warnings: list[str] = []
    if appraisal_to_market and 0 < appraisal_to_market < 0.5:
        data_quality_warnings.append(
            f"감정가가 시세의 {appraisal_to_market * 100:.0f}% - mock 데이터 한계 가능 (실제로는 매수자 우호)"
        )

    return {
        "trades": trades,
        "avg_price_6m": summary["avg_price_6m"],
        "avg_price_12m": summary["avg_price_12m"],
        "max_price": summary["max_price"],
        "min_price": summary["min_price"],
        "transaction_count": summary["transaction_count"],
        "market_price_estimate": market_price,
        "minimum_to_market_ratio": round(minimum_to_market, 3),
        "appraisal_to_market_ratio": round(appraisal_to_market, 3),
        "data_shortage": summary["data_shortage"],
        "appraisal_inflated": bool(inflation_warning),
        "inflation_warnings": inflation_warning,
        "data_quality_warnings": data_quality_warnings,
        "confidence": conf,
        "confidence_reason": reason,
        "address_match": addr_match,
        "type_match": type_match,
    }


def save_price_analysis(item_id: int, result: dict) -> None:
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO price_analyses (
            item_id, avg_price_6m, avg_price_12m,
            market_price_estimate, minimum_to_market_ratio,
            appraisal_to_market_ratio, transaction_count,
            confidence, confidence_reason, data_shortage,
            appraisal_inflated, inflation_warnings_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(item_id) DO UPDATE SET
            avg_price_6m=excluded.avg_price_6m,
            avg_price_12m=excluded.avg_price_12m,
            market_price_estimate=excluded.market_price_estimate,
            minimum_to_market_ratio=excluded.minimum_to_market_ratio,
            appraisal_to_market_ratio=excluded.appraisal_to_market_ratio,
            transaction_count=excluded.transaction_count,
            confidence=excluded.confidence,
            confidence_reason=excluded.confidence_reason,
            data_shortage=excluded.data_shortage,
            appraisal_inflated=excluded.appraisal_inflated,
            inflation_warnings_json=excluded.inflation_warnings_json,
            created_at=datetime('now','localtime')
    """, (
        item_id,
        result["avg_price_6m"], result["avg_price_12m"],
        result["market_price_estimate"], result["minimum_to_market_ratio"],
        result["appraisal_to_market_ratio"], result["transaction_count"],
        result["confidence"], result["confidence_reason"],
        1 if result["data_shortage"] else 0,
        1 if result.get("appraisal_inflated") else 0,
        safe_json(result.get("inflation_warnings", [])),
    ))
    # 거래 내역 저장 (최대 20건)
    for t in (result.get("trades") or [])[:20]:
        c.execute("""
            INSERT OR IGNORE INTO price_records
                (item_id, address_dong, complex_name, area_m2, trade_price, trade_date, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (item_id, t.get("address_dong"), t.get("complex_name"),
              t.get("area_m2"), t.get("trade_price"), t.get("trade_date"),
              t.get("source", "mock_molit")))
    conn.commit()
    conn.close()


def get_price_analysis(item_id: int) -> dict | None:
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM price_analyses WHERE item_id=?", (item_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None
