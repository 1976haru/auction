"""
scripts/run_auto_tune.py
추천 가중치 자동 튜닝 CLI - grid search.

사용
    python scripts/run_auto_tune.py
    python scripts/run_auto_tune.py --max 50 --apply
    python scripts/run_auto_tune.py --scenario aggressive
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agents.auto_tune_agent import grid_search, save_tuned_weights  # noqa: E402
from core.utils import ensure_dir, export_path  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--scenario", default="standard",
                   choices=["conservative", "standard", "aggressive"])
    p.add_argument("--max", type=int, default=50,
                   help="최대 평가 조합 수 (시간 제한)")
    p.add_argument("--apply", action="store_true",
                   help="최적 가중치를 즉시 활성화")
    p.add_argument("--top", type=int, default=10,
                   help="콘솔 출력 상위 N")
    args = p.parse_args()

    print("=" * 70)
    print(f"자동 튜닝 시작 (scenario={args.scenario}, max={args.max})")
    print("=" * 70)
    results = grid_search(scenario=args.scenario, max_combos=args.max)
    if not results:
        print("결과 없음 - 데이터/시뮬을 먼저 채우세요.")
        sys.exit(1)

    print(f"\n총 {len(results)}개 조합 평가 완료. 상위 {args.top}개:\n")
    print(f"{'rank':>4} {'quality':>8}  monot  {'A':>6} {'B':>6} {'C':>6} {'D':>6} {'X':>6}  weights")
    print("-" * 100)
    for i, r in enumerate(results[:args.top], 1):
        means = r["ordering"]["grade_means"]
        m = bool(r["ordering"]["monotonic_decreasing"])
        a = means.get("A", 0)
        b = means.get("B", 0)
        c = means.get("C", 0)
        d = means.get("D", 0)
        x = means.get("X", 0)
        w_str = ", ".join(
            f"{k.replace('grade_', '').replace('_cutoff', 'co')}={v}"
            for k, v in r["weights"].items()
            if k in ("profit_max", "profit_divisor", "risk_low", "risk_high",
                     "grade_a_cutoff", "grade_b_cutoff")
        )
        print(f"{i:>4} {r['quality']:>8.2f}  {('OK' if m else 'NO'):<5}  "
              f"{a:>+6.0f} {b:>+6.0f} {c:>+6.0f} {d:>+6.0f} {x:>+6.0f}  {w_str}")

    best = results[0]
    rid = save_tuned_weights(
        best["weights"], best["quality"],
        notes=f"grid_search top1 (scenario={args.scenario})",
        activate=args.apply,
    )
    print(f"\n최적 가중치 저장: tuned_weights #{rid}")
    if args.apply:
        print(f"활성화 완료 - 다음 추천 / 백테스트부터 새 가중치 적용")
    else:
        print(f"활성화는 안 됨. --apply 또는 대시보드에서 활성화하세요.")

    # 결과 export
    ensure_dir(os.path.dirname(export_path("auto_tune_report.json")))
    out_path = export_path("auto_tune_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "scenario": args.scenario,
            "evaluated": len(results),
            "top": [
                {"weights": r["weights"], "quality": r["quality"],
                 "monotonic": r["ordering"]["monotonic_decreasing"],
                 "grade_means": r["ordering"]["grade_means"]}
                for r in results[:args.top]
            ],
        }, f, ensure_ascii=False, indent=2, default=str)
    print(f"리포트: {out_path}")


if __name__ == "__main__":
    main()
