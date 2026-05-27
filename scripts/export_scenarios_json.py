"""
scripts/export_scenarios_json.py
scenario_results / location_scores / items / risk를 모아 정적 JSON으로 export.
블록 12 UI(시나리오 비교 카드)가 소비한다.
사용: python scripts/export_scenarios_json.py [--out docs/data/scenarios.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.database import get_connection  # noqa: E402
from core.logger import log  # noqa: E402

DEFAULT_OUT = os.path.join(ROOT, "docs", "data", "scenarios.json")
CAPITAL_MAX = 200_000_000  # 기본 자기자본 상한(2억)


def _scenarios_for(conn, item_id: int) -> dict:
    rows = conn.execute(
        "SELECT scenario, bid_price, capital_needed, holding_months, net_return, "
        "roe, annualized_roe, score, is_recommended, affordable "
        "FROM scenario_results WHERE item_id=?", (item_id,)
    ).fetchall()
    return {r["scenario"]: dict(r) for r in rows}


def _location_for(conn, item_id: int) -> dict | None:
    row = conn.execute(
        "SELECT transit, school, amenity, development, environment, total, grade, "
        "nearest_subway, school_district, development_news "
        "FROM location_scores WHERE item_id=?", (item_id,)
    ).fetchone()
    return dict(row) if row else None


def build(limit: int | None = None) -> dict:
    conn = get_connection()
    item_rows = conn.execute(
        "SELECT id, address_full, item_type, min_bid_price, appraisal_price, area_m2, "
        "fail_count, expected_roe, loss_probability, worst_case_loss, "
        "eviction_difficulty, eviction_cost_estimate "
        "FROM items WHERE EXISTS (SELECT 1 FROM scenario_results s WHERE s.item_id=items.id) "
        "ORDER BY id" + (f" LIMIT {int(limit)}" if limit else "")
    ).fetchall()

    items: list[dict] = []
    roe_acc = {"short_sale": [], "rental": [], "residence": []}
    affordable_count = 0

    for r in item_rows:
        it = dict(r)
        scenarios = _scenarios_for(conn, it["id"])
        location = _location_for(conn, it["id"])
        recommended = next((s for s, v in scenarios.items() if v.get("is_recommended")), None)
        any_afford = any(v.get("affordable") for v in scenarios.values())
        if any_afford:
            affordable_count += 1
        for s, v in scenarios.items():
            if v.get("annualized_roe") is not None:
                roe_acc[s].append(v["annualized_roe"])

        items.append({
            "item_id": it["id"],
            "address": it.get("address_full"),
            "item_type": it.get("item_type"),
            "min_bid_price": it.get("min_bid_price"),
            "appraisal_price": it.get("appraisal_price"),
            "area_m2": it.get("area_m2"),
            "scenarios": scenarios,
            "best_scenario": recommended,
            "affordable": any_afford,
            "location": location,
            "risk": {
                "expected_roe": it.get("expected_roe"),
                "loss_probability": it.get("loss_probability"),
                "worst_case_loss": it.get("worst_case_loss"),
            },
            "eviction": {
                "difficulty": it.get("eviction_difficulty"),
                "cost_estimate": it.get("eviction_cost_estimate"),
            },
        })

    def _avg(xs):
        return round(sum(xs) / len(xs), 2) if xs else None

    def _top(scen, n=5):
        ranked = sorted(
            (i for i in items if scen in i["scenarios"]),
            key=lambda i: i["scenarios"][scen].get("score") or 0, reverse=True)
        return [{"item_id": i["item_id"], "address": i["address"],
                 "annualized_roe": i["scenarios"][scen].get("annualized_roe"),
                 "score": i["scenarios"][scen].get("score")} for i in ranked[:n]]

    summary = {
        "total_items": len(items),
        "by_scenario": {
            "short_sale_avg_roe": _avg(roe_acc["short_sale"]),
            "rental_avg_roe": _avg(roe_acc["rental"]),
            "residence_avg_roe": _avg(roe_acc["residence"]),
        },
        "affordable_count": affordable_count,
        "capital_max": CAPITAL_MAX,
        "top_per_scenario": {
            "short_sale": _top("short_sale"),
            "rental": _top("rental"),
            "residence": _top("residence"),
        },
    }
    conn.close()
    return {"items": items, "summary": summary}


def export(out_path: str = DEFAULT_OUT, limit: int | None = None) -> dict:
    data = build(limit=limit)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    log.info(f"[export] scenarios.json -> {out_path} ({len(data['items'])} items)")
    return data


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=DEFAULT_OUT)
    p.add_argument("--limit", type=int, default=None)
    args = p.parse_args()
    data = export(args.out, args.limit)
    size = os.path.getsize(args.out)
    print(f"[OK] scenarios.json export 완료: {len(data['items'])}건, {size:,} bytes")
    print(f"  by_scenario: {data['summary']['by_scenario']}")
    print(f"  affordable: {data['summary']['affordable_count']}건")


if __name__ == "__main__":
    main()
