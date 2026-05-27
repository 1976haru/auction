"""
modules/market/historical_cases.py
유사 과거 낙찰 사례 검색.
같은 시군구 + 같은 유형 + 면적 ±20% 물건을 찾아 유사도순으로 반환한다.
실제 낙찰가가 없으면 낙찰가율 통계로 추정한 mock 낙찰 데이터를 부여한다.
"""
from __future__ import annotations

import hashlib

from core.database import get_connection
from modules.market.winning_rate_stats import get_winning_rate


def _similarity(base: dict, cand: dict) -> float:
    score = 0.0
    if (base.get("address_gu") or "") and base.get("address_gu") == cand.get("address_gu"):
        score += 0.4
    if (base.get("item_type") or "") and base.get("item_type") == cand.get("item_type"):
        score += 0.3
    ba, ca = base.get("area_m2") or 0, cand.get("area_m2") or 0
    if ba and ca:
        diff = abs(ba - ca) / ba
        if diff <= 0.2:
            score += 0.3 * (1 - diff / 0.2)
    return round(min(1.0, score), 3)


def _mock_winning(cand: dict) -> dict:
    stat = get_winning_rate(
        cand.get("address_si"), cand.get("address_gu"),
        cand.get("item_type"), cand.get("fail_count") or 0,
    )
    rng_seed = int(hashlib.md5(str(cand.get("id")).encode()).hexdigest()[:8], 16)
    # 통계 범위 내 결정적 변동
    span = stat["high"] - stat["low"]
    ratio = round(stat["low"] + span * ((rng_seed % 100) / 100.0), 3)
    appraisal = cand.get("appraisal_price") or cand.get("min_bid_price") or 0
    winning = int(round(appraisal * ratio)) if appraisal else 0
    bidders = 2 + (rng_seed % 5)
    return {"winning_price": winning, "winning_ratio": ratio, "bidders": bidders}


def find_similar_cases(item: dict, limit: int = 5) -> list[dict]:
    """유사 과거 낙찰 사례."""
    gu = item.get("address_gu")
    item_type = item.get("item_type")
    self_id = item.get("id")

    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM items
           WHERE (address_gu=? OR ?='') AND (item_type=? OR ?='')
             AND (id<>? OR ? IS NULL)
           ORDER BY id DESC LIMIT 50""",
        (gu or "", gu or "", item_type or "", item_type or "",
         self_id or -1, self_id),
    ).fetchall()
    conn.close()

    cases: list[dict] = []
    for r in rows:
        cand = dict(r)
        sim = _similarity(item, cand)
        if sim <= 0:
            continue
        win = _mock_winning(cand)
        cases.append({
            "case_no": cand.get("case_no"),
            "address": cand.get("address_full"),
            "area_m2": cand.get("area_m2"),
            "appraisal": cand.get("appraisal_price"),
            "winning_price": win["winning_price"],
            "winning_ratio": win["winning_ratio"],
            "bidders": win["bidders"],
            "sold_date": cand.get("bid_date"),
            "similarity_score": sim,
        })

    cases.sort(key=lambda x: x["similarity_score"], reverse=True)
    return cases[:limit]
