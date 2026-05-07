"""
scripts/clear_qa_cache.py
Q&A 캐시 통계 + 삭제 CLI.

사용
    python scripts/clear_qa_cache.py             # 통계만
    python scripts/clear_qa_cache.py --clear     # 전체 삭제
    python scripts/clear_qa_cache.py --item 63   # 특정 매물만
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agents.item_qa_agent import cache_stats, clear_cache  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--clear", action="store_true", help="캐시 전체 삭제")
    p.add_argument("--item", type=int, help="특정 매물 캐시만 삭제")
    args = p.parse_args()

    s = cache_stats()
    print("=" * 50)
    print("Q&A 캐시 현황")
    print("=" * 50)
    print(f"  엔트리 수: {s['entries']}")
    print(f"  총 히트: {s['total_hits']}")
    print(f"  매물 수: {s['distinct_items']}")
    print(f"  마지막 사용: {s['last_used_at'] or '-'}")

    if args.item is not None:
        n = clear_cache(item_id=args.item)
        print(f"\n[OK] item_id={args.item} 캐시 {n}건 삭제")
    elif args.clear:
        n = clear_cache()
        print(f"\n[OK] 전체 캐시 {n}건 삭제")


if __name__ == "__main__":
    main()
