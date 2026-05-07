"""
scripts/run_daily_pipeline.py
전체 일일 파이프라인. Mock-first.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agents.agent_orchestrator import run_full_analysis  # noqa: E402
from core.database import get_connection, init_db, reset_db  # noqa: E402
from core.logger import log  # noqa: E402
from core.utils import ensure_dir, export_path, now_iso, safe_json  # noqa: E402
from scripts.generate_mock_data import generate as gen_mock  # noqa: E402


def _record_run(run_type: str, status: str, total_items: int,
                elapsed_sec: float, summary: dict, started_at: str) -> None:
    init_db()
    conn = get_connection()
    conn.execute("""
        INSERT INTO pipeline_runs
            (run_type, status, total_items, elapsed_sec,
             summary_json, started_at, finished_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        run_type, status, total_items, elapsed_sec,
        safe_json(summary), started_at, now_iso(),
    ))
    conn.commit()
    conn.close()


def _export_top(top_picks: list[dict]) -> dict:
    ensure_dir(os.path.dirname(export_path("daily_recommendations.json")))
    paths = {}
    # JSON
    json_path = export_path("daily_recommendations.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(top_picks, f, ensure_ascii=False, indent=2, default=str)
    paths["json"] = json_path
    # CSV (utf-8-sig + CRLF — Excel 호환)
    csv_path = export_path("daily_recommendations.csv")
    headers = [
        "rank", "grade", "score", "address", "item_type",
        "appraisal_price", "min_bid_price", "market_price",
        "profit_estimate", "roi_estimate", "risk_level", "bid_date",
    ]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(",".join(headers) + "\r\n")
        for i, r in enumerate(top_picks, 1):
            it = r.get("item", {})
            row = [
                str(i), r.get("grade", ""), f"{r.get('score', 0):.1f}",
                str(it.get("address_full", "")).replace(",", " "),
                str(it.get("item_type", "")),
                str(it.get("appraisal_price", 0)),
                str(it.get("min_bid_price", 0)),
                str(r.get("market_price", 0)),
                str(r.get("profit_estimate", 0)),
                f"{r.get('roi_estimate', 0):.2f}",
                str(r.get("risk_level", "")),
                str(it.get("bid_date", "")),
            ]
            f.write(",".join(row) + "\r\n")
    paths["csv"] = csv_path
    # Markdown
    md_path = export_path("daily_recommendations.md")
    lines = ["# 오늘의 추천 TOP 5", ""]
    for i, r in enumerate(top_picks, 1):
        it = r.get("item", {})
        lines.append(
            f"{i}. **[{r.get('grade')}]** {it.get('address_full', '미상')}\n"
            f"   - 차익 {r.get('profit_estimate', 0):,}만원 / ROI {r.get('roi_estimate', 0):.1f}%\n"
            f"   - 위험 {r.get('risk_level')} / 점수 {r.get('score', 0):.1f}\n"
            f"   - 최저가 {it.get('min_bid_price', 0):,}만원 | 매각기일 {it.get('bid_date', '미정')}"
        )
    lines.append("\n참고용 결과이며 권리·시세는 직접 확인이 필요합니다.")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    paths["md"] = md_path
    return paths


def run_pipeline(use_mock: bool = True, count: int = 100,
                 top: int = 5, reset: bool = False,
                 query: str = "시세차익 큰 물건 5개 찾아줘") -> dict:
    started_at = now_iso()
    started = time.time()

    if reset:
        log.info("[pipeline] DB 리셋")
        reset_db()
    else:
        init_db()

    log.info("[pipeline] mock 데이터 생성")
    gen_mock(count=count, seed=42, reset=False)

    # 데이터 생성 후 전체 분석
    summary = run_full_analysis(top_query=query)
    elapsed = time.time() - started

    # 상위 N건 export
    paths = _export_top(summary["top_picks"][:top])
    summary["exports"] = paths
    summary["elapsed_sec"] = round(elapsed, 2)

    init_db()
    conn = get_connection()
    total_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    conn.close()

    _record_run("daily_pipeline", "ok", total_items, elapsed, summary, started_at)

    # 콘솔 요약
    print("\n=== 오늘의 파이프라인 요약 ===")
    print(f"전체 물건: {total_items}건")
    print(f"분석 완료: 시세 {summary['price_analyzed']}건 / 위험 {summary['risk_analyzed']}건")
    print(f"오늘 액션: {summary['actions_planned']}건 / 변경 감지 {summary['changes_detected']}건")
    print(f"브리핑: {summary['briefing_summary']}")
    if summary.get("alerts"):
        a = summary["alerts"]
        print(f"알림: 발송 {a['sent']}건 / 스킵 {a['skipped']}건 / 실패 {a['failed']}건")
    print(f"파일: {paths}")
    print(f"소요 {elapsed:.2f}초\n")
    return summary


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mock", action="store_true", default=True)
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--top", type=int, default=5)
    p.add_argument("--reset", action="store_true")
    p.add_argument("--query", type=str, default="시세차익 큰 물건 5개 찾아줘")
    args = p.parse_args()
    run_pipeline(use_mock=args.mock, count=args.count, top=args.top,
                 reset=args.reset, query=args.query)


if __name__ == "__main__":
    main()
