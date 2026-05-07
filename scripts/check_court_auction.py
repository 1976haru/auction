"""
scripts/check_court_auction.py
법원경매 사이트(courtauction.go.kr) selector 헬스체크.

사용
    python scripts/check_court_auction.py
    python scripts/check_court_auction.py --json

전제: pip install playwright && playwright install chromium

selector 가 깨지면 어느 키가 사이트 변경됐는지 알려준다. SELECTORS dict 만
수정하면 크롤러 전체가 다시 동작.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true", help="JSON 출력")
    args = p.parse_args()

    from modules.auction.crawler import SELECTORS, validate_site_selectors

    print("=" * 60)
    print("법원경매 사이트 selector 헬스체크")
    print("=" * 60)
    print(f"\n현재 SELECTORS ({len(SELECTORS)}개):")
    for k, v in SELECTORS.items():
        print(f"  {k:<22} = {v}")
    print()

    print("사이트 접속 검증 중... (3-10초 소요, headless)")
    result = validate_site_selectors()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if not result.get("playwright_installed"):
        print(f"\n[X] {result['note']}")
        print("\n해결: pip install playwright && playwright install chromium")
        return

    if result.get("ok"):
        print(f"\n[OK] 모든 selector 정상 ({result['found_count']}/{result['total']})")
    else:
        print(f"\n[!] {result['note']}")

    print("\n[selector 검증 결과]")
    for d in result.get("details", []):
        mark = "OK  " if d["found"] else "FAIL"
        print(f"  [{mark}] {d['key']:<22} {d['selector']}")

    print("\nselector 가 FAIL 인 경우:")
    print("  1. 브라우저로 https://www.courtauction.go.kr 접속")
    print("  2. F12 개발자 도구 -> Elements 패널에서 해당 요소 우클릭 -> Copy selector")
    print("  3. modules/auction/crawler.py 의 SELECTORS dict 해당 키 수정")
    print("  4. python scripts/check_court_auction.py 로 재검증")


if __name__ == "__main__":
    main()
