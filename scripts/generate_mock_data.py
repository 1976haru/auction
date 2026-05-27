"""
scripts/generate_mock_data.py
경매·공매 mock 데이터를 만들어 DB에 저장한다.
사용 예:
    python scripts/generate_mock_data.py --count 100 --seed 42
    python scripts/generate_mock_data.py --count 500 --seed 42 --reset
"""
from __future__ import annotations

import argparse
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.database import init_db, reset_db, upsert_item  # noqa: E402
from core.logger import log  # noqa: E402
from modules.auction.mock_auction_api import list_auction_items  # noqa: E402
from modules.public_sale.mock_onbid_api import list_public_sale_items  # noqa: E402
from modules.documents.mock_documents import populate_documents  # noqa: E402


def _seed_reference_data() -> dict:
    """법정동코드/학군 기준 데이터 입력."""
    from scripts.seed_law_codes import seed as seed_law
    from scripts.seed_school_data import seed as seed_school
    return {"law_codes": seed_law(), "school_districts": seed_school()}


def _analyze_items(limit: int | None = None) -> dict:
    """생성된 물건에 대해 v2 통합 분석(시나리오/리스크 등) 실행."""
    from agents.orchestrator import run_pipeline
    return run_pipeline(limit=limit)


def generate(count: int = 100, seed: int = 42, reset: bool = False,
             analyze: bool = False) -> dict:
    if reset:
        reset_db()
    else:
        init_db()

    auction_count = count // 2
    public_count = count - auction_count

    auctions = list_auction_items(count=auction_count, seed=seed)
    publics = list_public_sale_items(count=public_count, seed=seed + 1)

    saved = 0
    for item in auctions + publics:
        upsert_item(item)
        saved += 1

    docs = populate_documents(seed=seed)
    result = {"items": saved, "documents": docs}

    if analyze:
        result["reference"] = _seed_reference_data()
        result["analysis"] = _analyze_items()

    log.info(f"[mock-data] items={saved} docs={docs} analyze={analyze}")
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--reset", action="store_true")
    p.add_argument("--analyze", action="store_true",
                   help="생성 후 v2 통합 분석(시나리오/리스크) 실행 + 기준데이터 seed")
    args = p.parse_args()

    result = generate(count=args.count, seed=args.seed, reset=args.reset,
                      analyze=args.analyze)
    print(f"\n[OK] mock 데이터 생성 완료")
    print(f"  - 물건 {result['items']}건")
    print(f"  - 문서 {result['documents']}건")
    if result.get("analysis"):
        print(f"  - 분석 {result['analysis']['processed']}건 "
              f"(오류 {result['analysis']['errors']}, {result['analysis']['elapsed_sec']}s)")
        print(f"  - 기준데이터: 법정동 {result['reference']['law_codes']} / "
              f"학군 {result['reference']['school_districts']}")


if __name__ == "__main__":
    main()
