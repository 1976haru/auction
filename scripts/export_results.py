"""
scripts/export_results.py
DB의 추천/분석 결과를 CSV/JSON/Markdown으로 내보낸다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.database import get_connection, init_db
from core.utils import ensure_dir, export_path


def export_top_recommendations(limit: int = 20) -> dict:
    init_db()
    conn = get_connection()
    rows = conn.execute("""
        SELECT r.*, i.address_full, i.item_type, i.min_bid_price, i.bid_date
        FROM recommendation_results r
        LEFT JOIN items i ON i.id=r.item_id
        ORDER BY r.id DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    data = [dict(r) for r in rows]

    ensure_dir(os.path.dirname(export_path("recommendations.json")))
    json_path = export_path("recommendations.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    csv_path = export_path("recommendations.csv")
    headers = ["rank", "grade", "score", "address_full", "item_type",
               "min_bid_price", "profit_estimate", "roi_estimate", "bid_date"]
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write(",".join(headers) + "\n")
        for d in data:
            f.write(",".join([
                str(d.get("rank", "")),
                str(d.get("grade", "")),
                f"{(d.get('score') or 0):.1f}",
                str(d.get("address_full", "")).replace(",", " "),
                str(d.get("item_type", "")),
                str(d.get("min_bid_price", 0)),
                str(d.get("profit_estimate", 0)),
                f"{(d.get('roi_estimate') or 0):.2f}",
                str(d.get("bid_date", "")),
            ]) + "\n")

    md_path = export_path("recommendations.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# 추천 결과\n\n")
        for d in data:
            f.write(
                f"- [{d.get('grade')}] {d.get('address_full')} | "
                f"점수 {(d.get('score') or 0):.1f} | "
                f"차익 {d.get('profit_estimate', 0):,}만원 | "
                f"ROI {(d.get('roi_estimate') or 0):.1f}%\n"
            )

    return {"json": json_path, "csv": csv_path, "md": md_path}


def export_actions() -> dict:
    init_db()
    conn = get_connection()
    rows = conn.execute("""
        SELECT a.*, i.address_full, i.item_type
        FROM action_items a LEFT JOIN items i ON i.id=a.item_id
        ORDER BY a.id DESC
    """).fetchall()
    conn.close()
    data = [dict(r) for r in rows]
    ensure_dir(os.path.dirname(export_path("action_items.json")))
    p = export_path("action_items.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return {"json": p}


def export_high_risk() -> dict:
    init_db()
    conn = get_connection()
    rows = conn.execute("""
        SELECT i.id, i.address_full, i.item_type, i.min_bid_price,
               GROUP_CONCAT(r.flag_type, '|') as flags
        FROM items i JOIN risk_flags r ON r.item_id=i.id
        WHERE r.risk_level='high'
        GROUP BY i.id
    """).fetchall()
    conn.close()
    data = [dict(r) for r in rows]
    p = export_path("high_risk_items.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return {"json": p}


def export_all() -> dict:
    out = {}
    out["recommendations"] = export_top_recommendations()
    out["actions"] = export_actions()
    out["high_risk"] = export_high_risk()
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", choices=["all", "recommendations", "actions", "high_risk"],
                   default="all")
    args = p.parse_args()
    if args.target == "all":
        out = export_all()
    elif args.target == "recommendations":
        out = export_top_recommendations()
    elif args.target == "actions":
        out = export_actions()
    else:
        out = export_high_risk()
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
