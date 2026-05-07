"""
scripts/export_report.py
매물 PDF 리포트 생성 CLI.

사용
    python scripts/export_report.py --item-id 63
    python scripts/export_report.py --item-id 63 --out my_report.pdf
    python scripts/export_report.py --top 5  # 오늘 브리핑 TOP 5 묶음
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agents.pdf_report_agent import generate_item_report_pdf, generate_top_picks_pdf
from core.database import get_connection
from core.utils import ensure_dir, export_path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--item-id", type=int, help="단일 매물 id")
    p.add_argument("--top", type=int,
                   help="오늘 브리핑 TOP N 매물 묶음 PDF (1-15)")
    p.add_argument("--out", type=str,
                   help="출력 경로 (기본 data/exports/...)")
    args = p.parse_args()

    if not args.item_id and not args.top:
        p.error("--item-id 또는 --top 중 하나를 지정")

    ensure_dir(os.path.dirname(export_path("report.pdf")))

    if args.item_id:
        pdf = generate_item_report_pdf(args.item_id)
        out = args.out or export_path(f"report_item_{args.item_id}.pdf")
        with open(out, "wb") as f:
            f.write(pdf)
        print(f"[OK] {out} ({len(pdf):,} bytes)")
        return

    # TOP N 묶음
    conn = get_connection()
    row = conn.execute(
        "SELECT top_picks_json FROM daily_briefings ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        print("최신 브리핑 없음. `python scripts/run_daily_pipeline.py` 먼저 실행")
        sys.exit(1)
    picks = json.loads(row["top_picks_json"] or "[]")[:args.top]
    if not picks:
        print("브리핑 top_picks 비어있음")
        sys.exit(1)
    ids = [p["item"]["id"] for p in picks]
    pdf = generate_top_picks_pdf(ids)
    out = args.out or export_path(f"report_top_{len(ids)}.pdf")
    with open(out, "wb") as f:
        f.write(pdf)
    print(f"[OK] {out} ({len(pdf):,} bytes, 매물 {len(ids)}건)")


if __name__ == "__main__":
    main()
