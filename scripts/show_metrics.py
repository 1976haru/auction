"""
scripts/show_metrics.py
지난 N시간 시스템 메트릭 요약 + 임계값 점검 출력.
사용: python scripts/show_metrics.py [--hours 24]
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.observability import get_summary, check_thresholds  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=int, default=24)
    args = p.parse_args()

    summary = get_summary(hours=args.hours)
    bar = "=" * 45
    print(bar)
    print(f"시스템 메트릭 ({args.hours}시간)")
    print(bar)
    if not summary:
        print("기록된 메트릭이 없습니다.")
    for name, s in sorted(summary.items()):
        print(f"  {name:<28} count={s['count']:<4} avg={s['avg']} last={s['last']}")
    print("-" * 45)

    alerts = check_thresholds()
    if alerts:
        print("임계값 알림:")
        for a in alerts:
            print(f"  [{a['severity'].upper()}] {a['name']}: {a['message']}")
    else:
        print("임계값 알림: 없음 (정상)")
    print(bar)


if __name__ == "__main__":
    main()
