"""
modules/risk/monte_carlo.py
몬테카를로 시뮬레이션(기본 10,000회)으로 ROE 분포 추정.
매도가/명도비용 등 불확실 변수를 샘플링한다. 금액 단위는 원(₩).
시드 고정 시 동일 결과를 보장한다.
"""
from __future__ import annotations

import numpy as np

from core.database import get_connection, init_db
from core.logger import log
from modules.finance.tax_calculator import calc_acquisition_tax
from modules.scenarios import _common as C

# 재매각 모델 가정
_HOLD_YEARS = 1.0
_TRANSFER_RATE = 0.60   # 1~2년 보유 가정 단일세율(벡터화)


def run_monte_carlo(item_id: int, bid_price: int, n: int = 10000, seed: int = 42,
                    user_profile: dict | None = None, item: dict | None = None) -> dict:
    profile = C.load_profile(user_profile)
    item = item or C.get_item(item_id)
    item_type = item.get("item_type") or "주택"

    market = C.market_price_won(item)
    base_evict = C.eviction_cost_won(item_id, item)
    loan = C.get_loan(bid_price, profile)

    acq = calc_acquisition_tax(bid_price, item_type)["tax"]
    finance_cost = int(loan["monthly_payment"] * (_HOLD_YEARS * 12) * 0.6)

    rng = np.random.default_rng(seed)
    # 매도가: 시세 중심 정규분포(표준편차 8%), 0.7~1.3배로 클립
    sale = rng.normal(market, market * 0.08, n)
    sale = np.clip(sale, market * 0.7, market * 1.3)
    # 명도비용: 기준 중심, 표준편차 30%, 음수 방지
    evict = np.clip(rng.normal(base_evict, base_evict * 0.3 + 1, n), 0, None)

    gain = sale - bid_price
    transfer = np.where(gain > 0, gain * _TRANSFER_RATE, 0.0)
    net = gain - acq - evict - finance_cost - transfer

    equity = max(1, (bid_price - loan["max_loan"]) + acq + base_evict)
    roe = net / equity * 100

    pcts = {f"p{p}": round(float(np.percentile(roe, p)), 2) for p in (10, 25, 50, 75, 90)}
    loss_prob = float(np.mean(roe < 0))
    worst_net = float(np.percentile(net, 10))
    worst_case_loss = int(abs(min(0.0, worst_net)))

    counts, edges = np.histogram(roe, bins=20)

    result = {
        "item_id": item_id,
        "bid_price": bid_price,
        "iterations": n,
        "mean_roe": round(float(np.mean(roe)), 2),
        "median_roe": round(float(np.median(roe)), 2),
        "std_roe": round(float(np.std(roe)), 2),
        "percentiles": pcts,
        "loss_probability": round(loss_prob, 4),
        "worst_case_loss": worst_case_loss,
        "histogram": {
            "counts": counts.tolist(),
            "bin_edges": [round(float(e), 2) for e in edges],
        },
    }

    # items 테이블 저장
    init_db()
    conn = get_connection()
    conn.execute(
        "UPDATE items SET expected_roe=?, loss_probability=?, worst_case_loss=? WHERE id=?",
        (result["mean_roe"], result["loss_probability"], worst_case_loss, item_id),
    )
    conn.commit()
    conn.close()

    log.info(
        f"[risk] item_id={item_id} 몬테카를로 {n}회 -> "
        f"기댓값 ROE {result['mean_roe']}%, 손실확률 {loss_prob*100:.1f}%"
    )
    return result
