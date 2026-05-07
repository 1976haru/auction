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
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(",".join(headers) + "\r\n")
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
            ]) + "\r\n")

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


def _write_csv(path: str, headers: list[str], rows: list[dict]) -> None:
    """dict 리스트를 CSV로 저장. utf-8-sig (BOM 포함) 으로 저장해서 Excel
    더블클릭 시 한글이 자동으로 정상 표시되도록 한다."""
    def esc(v):
        s = "" if v is None else str(v)
        if "," in s or "\n" in s or '"' in s:
            return '"' + s.replace('"', '""').replace("\n", " ") + '"'
        return s
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(",".join(headers) + "\r\n")
        for d in rows:
            f.write(",".join(esc(d.get(h)) for h in headers) + "\r\n")


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
    json_path = export_path("action_items.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    csv_path = export_path("action_items.csv")
    _write_csv(csv_path,
               ["id", "item_id", "address_full", "item_type", "action_type",
                "priority", "title", "detail", "due_date", "status", "created_at"],
               data)
    return {"json": json_path, "csv": csv_path}


def export_high_risk() -> dict:
    init_db()
    conn = get_connection()
    rows = conn.execute("""
        SELECT i.id, i.address_full, i.item_type, i.min_bid_price,
               i.appraisal_price, i.bid_date,
               GROUP_CONCAT(r.flag_type, '|') as flags,
               MAX(r.severity) as max_severity
        FROM items i JOIN risk_flags r ON r.item_id=i.id
        WHERE r.risk_level='high'
        GROUP BY i.id
    """).fetchall()
    conn.close()
    data = [dict(r) for r in rows]
    json_path = export_path("high_risk_items.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    csv_path = export_path("high_risk_items.csv")
    _write_csv(csv_path,
               ["id", "address_full", "item_type", "appraisal_price",
                "min_bid_price", "bid_date", "flags", "max_severity"],
               data)
    return {"json": json_path, "csv": csv_path}


def export_items_full() -> dict:
    """전체 물건 + 분석 결과 통합 CSV."""
    init_db()
    conn = get_connection()
    rows = conn.execute("""
        SELECT i.id, i.source, i.case_no, i.mgmt_no, i.item_type,
               i.address_full, i.address_si, i.address_gu,
               i.appraisal_price, i.min_bid_price, i.fail_count,
               i.area_m2, i.floor, i.bid_date, i.is_watched,
               pa.market_price_estimate, pa.minimum_to_market_ratio,
               pa.appraisal_to_market_ratio, pa.transaction_count,
               pa.confidence as price_confidence,
               pa.appraisal_inflated, pa.data_shortage,
               cs.overall_confidence,
               cs.legal_risk_confidence,
               cs.document_confidence,
               (SELECT GROUP_CONCAT(flag_type, '|') FROM risk_flags WHERE item_id=i.id) as risk_flags,
               (SELECT MAX(risk_level) FROM risk_flags WHERE item_id=i.id) as max_risk_level
        FROM items i
        LEFT JOIN price_analyses pa ON pa.item_id=i.id
        LEFT JOIN confidence_scores cs ON cs.item_id=i.id
        ORDER BY i.id
    """).fetchall()
    conn.close()
    data = [dict(r) for r in rows]
    csv_path = export_path("items_full.csv")
    _write_csv(csv_path,
               ["id", "source", "case_no", "mgmt_no", "item_type",
                "address_full", "address_si", "address_gu",
                "appraisal_price", "min_bid_price", "fail_count",
                "area_m2", "floor", "bid_date", "is_watched",
                "market_price_estimate", "minimum_to_market_ratio",
                "appraisal_to_market_ratio", "transaction_count",
                "price_confidence", "appraisal_inflated", "data_shortage",
                "overall_confidence", "legal_risk_confidence", "document_confidence",
                "risk_flags", "max_risk_level"],
               data)
    return {"csv": csv_path, "rows": len(data)}


def export_simulations() -> dict:
    """outcome_simulations CSV."""
    init_db()
    conn = get_connection()
    rows = conn.execute("""
        SELECT s.*, i.address_full, i.item_type
        FROM outcome_simulations s LEFT JOIN items i ON i.id=s.item_id
        ORDER BY s.id DESC
    """).fetchall()
    conn.close()
    data = [dict(r) for r in rows]
    csv_path = export_path("outcome_simulations.csv")
    _write_csv(csv_path,
               ["id", "item_id", "address_full", "item_type", "scenario_name",
                "simulated_bid_price", "simulated_sale_price",
                "simulated_total_cost", "simulated_profit",
                "simulated_profit_rate", "created_at"],
               data)
    return {"csv": csv_path, "rows": len(data)}


def export_briefings() -> dict:
    """daily_briefings CSV (요약 메트릭만)."""
    init_db()
    conn = get_connection()
    rows = conn.execute("""
        SELECT id, run_date, total_items, analyzed_items, matched_items,
               candidate_items, high_risk_items, insufficient, summary
        FROM daily_briefings ORDER BY id DESC
    """).fetchall()
    conn.close()
    data = [dict(r) for r in rows]
    csv_path = export_path("daily_briefings.csv")
    _write_csv(csv_path,
               ["id", "run_date", "total_items", "analyzed_items", "matched_items",
                "candidate_items", "high_risk_items", "insufficient", "summary"],
               data)
    return {"csv": csv_path, "rows": len(data)}


def export_all() -> dict:
    out = {}
    out["recommendations"] = export_top_recommendations()
    out["actions"] = export_actions()
    out["high_risk"] = export_high_risk()
    out["items_full"] = export_items_full()
    out["simulations"] = export_simulations()
    out["briefings"] = export_briefings()
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--target", choices=["all", "recommendations", "actions",
                                         "high_risk", "items_full",
                                         "simulations", "briefings"],
                   default="all")
    args = p.parse_args()
    target_map = {
        "all": export_all,
        "recommendations": export_top_recommendations,
        "actions": export_actions,
        "high_risk": export_high_risk,
        "items_full": export_items_full,
        "simulations": export_simulations,
        "briefings": export_briefings,
    }
    out = target_map[args.target]()
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
