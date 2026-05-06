"""
scripts/run_stress_test.py
mock 데이터 다량 생성 + 추천/분석 반복 실행 후 처리 시간 기록.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agents.confidence_agent import compute_all as compute_conf
from agents.legal_risk_agent import analyze_all as analyze_risk
from agents.price_analysis_agent import analyze_all as analyze_price
from agents.recommendation_agent import recommend
from core.database import get_connection, init_db, reset_db
from core.logger import log
from core.utils import ensure_dir, export_path, safe_json
from scripts.generate_mock_data import generate as gen_mock


SAMPLE_QUERIES = [
    "시세차익 큰 물건 5개 찾아줘",
    "위험 낮은 물건 3개",
    "수익률 높은 공매 물건 10개",
    "서울 아파트 중 입찰기일 7일 이내",
    "유치권 있는 물건은 제외해줘",
    "고위험이어도 차익 큰 것 보여줘",
    "내가 좋아할 만한 물건 있어?",
    "오늘 뭐부터 봐야 돼?",
    "요즘 괜찮은 거 있어?",
    "공매만 보고 수익률 높은 물건 5개",
]


def _save_result(scenario: str, item_count: int, query_count: int,
                 elapsed: float, success: bool, details: dict,
                 error: str = None) -> None:
    init_db()
    conn = get_connection()
    conn.execute("""
        INSERT INTO stress_test_results
            (scenario, item_count, query_count, elapsed_sec,
             success, error_message, details_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (scenario, item_count, query_count, elapsed,
          1 if success else 0, error, safe_json(details)))
    conn.commit()
    conn.close()


def run(count: int = 1000, queries: int = 20, reset: bool = True,
        scenario: str = "default") -> dict:
    started = time.time()
    if reset:
        reset_db()
    init_db()

    t0 = time.time()
    gen_mock(count=count, seed=42, reset=False)
    t_gen = time.time() - t0

    t0 = time.time()
    n_price = analyze_price()
    t_price = time.time() - t0

    t0 = time.time()
    n_risk = analyze_risk()
    t_risk = time.time() - t0

    t0 = time.time()
    n_conf = compute_conf()
    t_conf = time.time() - t0

    t0 = time.time()
    rnd = random.Random(0)
    qresults = []
    for i in range(queries):
        q = rnd.choice(SAMPLE_QUERIES)
        r = recommend(q, n=5)
        qresults.append({"query": q, "found": r["total_found"], "returned": len(r["results"])})
    t_query = time.time() - t0

    elapsed = time.time() - started
    details = {
        "scenario": scenario,
        "count": count,
        "queries": queries,
        "n_price_analyzed": n_price,
        "n_risk_analyzed": n_risk,
        "n_confidence": n_conf,
        "elapsed": {
            "total": round(elapsed, 2),
            "generate": round(t_gen, 2),
            "price": round(t_price, 2),
            "risk": round(t_risk, 2),
            "confidence": round(t_conf, 2),
            "queries": round(t_query, 2),
        },
        "queries_summary": qresults[:20],
    }
    _save_result(scenario, count, queries, elapsed, True, details)

    # export
    ensure_dir(os.path.dirname(export_path("stress_test_report.json")))
    out_path = export_path("stress_test_report.json")
    import json as _json
    with open(out_path, "w", encoding="utf-8") as f:
        _json.dump(details, f, ensure_ascii=False, indent=2, default=str)

    log.info(f"[stress] {scenario} {count}건 / {queries}쿼리 / {elapsed:.2f}s")
    print("\n=== 스트레스 테스트 요약 ===")
    print(f"시나리오: {scenario}")
    print(f"총 소요: {elapsed:.2f}s (생성 {t_gen:.2f}s / 가격 {t_price:.2f}s / "
          f"위험 {t_risk:.2f}s / 신뢰 {t_conf:.2f}s / 쿼리 {t_query:.2f}s)")
    print(f"리포트: {out_path}")
    return details


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=1000)
    p.add_argument("--queries", type=int, default=20)
    p.add_argument("--scenario", type=str, default="default")
    p.add_argument("--no-reset", action="store_true")
    args = p.parse_args()
    run(count=args.count, queries=args.queries, reset=not args.no_reset,
        scenario=args.scenario)


if __name__ == "__main__":
    main()
