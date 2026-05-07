"""
scripts/run_backtest.py
추천 정확도 백테스트 CLI.

사용:
    python scripts/run_backtest.py
    python scripts/run_backtest.py --scenario aggressive
    python scripts/run_backtest.py --grades A,B
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agents.backtest_agent import backtest, backtest_all_items, grade_ordering_check  # noqa: E402
from core.utils import ensure_dir, export_path  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="standard",
                   choices=["conservative", "standard", "aggressive"])
    p.add_argument("--mode", default="all", choices=["all", "recommended"],
                   help="all=전체 매물 평가 (기본) / recommended=과거 추천 매물만")
    p.add_argument("--grades", default=None,
                   help="콤마 구분 (예: A,B). recommended 모드에서만 적용.")
    args = p.parse_args()

    if args.mode == "all":
        report = backtest_all_items(scenario=args.scenario)
    else:
        only = [g.strip() for g in args.grades.split(",")] if args.grades else None
        report = backtest(scenario=args.scenario, only_grades=only)
    ordering = grade_ordering_check(report)

    ensure_dir(os.path.dirname(export_path("backtest_report.json")))
    out_path = export_path("backtest_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"report": report, "ordering": ordering},
                   f, ensure_ascii=False, indent=2, default=str)

    print("=" * 70)
    print(f"백테스트 리포트 (mode={args.mode}, scenario={args.scenario})")
    print("=" * 70)
    print(f"\n전체 매칭: {report['total_pairs']}건")
    if report.get("overall"):
        o = report["overall"]
        print(f"전체 승률: {o['win_rate']}% ({o['count']}건)")
        ap = o["actual_profit"]
        print(f"실제 손익: 평균 {ap['mean']:+,.0f}만원 / 중앙값 {ap['median']:+,.0f}만원 "
              f"/ 범위 [{ap['min']:+,.0f} ~ {ap['max']:+,.0f}]")
        ae = o["abs_error"]
        print(f"예측 절대 오차: 평균 {ae['mean']:,.0f}만원 / 중앙값 {ae['median']:,.0f}만원")

    print(f"\n[등급별 통계]")
    print(f"{'등급':>4} {'건수':>5} {'승률':>7} {'평균 실제':>12} {'평균 예측':>12} {'평균 오차':>12} {'rel err%':>9}")
    print("-" * 70)
    for g in ["A", "B", "C", "D", "X"]:
        s = report["grades"].get(g)
        if not s or s["count"] == 0:
            continue
        ap = s["actual_profit"]
        pp = s["pred_profit"]
        ae = s["abs_error"]
        re_pct = s["relative_error_pct"]
        print(f"{g:>4} {s['count']:>5} {s['win_rate']:>6.1f}% "
              f"{ap['mean']:>+12,.0f} {pp['mean']:>+12,.0f} "
              f"{ae['mean']:>12,.0f} {re_pct['mean']:>8.1f}%")

    print(f"\n[등급 순서 검증]")
    print(f"단조 감소: {'OK' if ordering['monotonic_decreasing'] else 'FAIL'}")
    for g, m in ordering["grade_means"].items():
        print(f"  {g} 평균 실제 수익: {m:+,.0f}만원")
    print(f"\n리포트 저장: {out_path}")


if __name__ == "__main__":
    main()
