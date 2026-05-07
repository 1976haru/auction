"""
scripts/populate_real_data.py
실 API 로 매물/시세 데이터를 채워 DB 에 넣는다.

전제
- .env 또는 .streamlit/secrets.toml 에 USE_MOCK_APIS=false + PUBLIC_DATA_SERVICE_KEY 설정
- 키가 없으면 자동으로 mock fallback (정상 동작 보장)

사용
    python scripts/populate_real_data.py --count 50
    python scripts/populate_real_data.py --count 100 --reset
"""
from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.config import PUBLIC_DATA_KEY, USE_MOCK_APIS  # noqa: E402
from core.database import init_db, reset_db, upsert_item  # noqa: E402
from core.logger import log  # noqa: E402


def populate(count: int = 50, reset: bool = False) -> dict:
    if reset:
        reset_db()
    else:
        init_db()

    if USE_MOCK_APIS or not PUBLIC_DATA_KEY:
        log.warning("[real-populate] USE_MOCK_APIS=true 또는 PUBLIC_DATA_KEY 없음 - mock 데이터로 대체")
        from scripts.generate_mock_data import generate
        return generate(count=count, seed=42, reset=False)

    # 실 API 호출
    from modules.public_sale.real_onbid_api import list_public_sale_items as real_onbid

    items = real_onbid(count=count)
    saved = 0
    for it in items:
        try:
            upsert_item(it)
            saved += 1
        except Exception as e:
            log.warning(f"[real-populate] upsert 실패: {e}")

    # 문서 mock 으로 채움 (real 문서 다운로드는 별도 작업)
    from modules.documents.mock_documents import populate_documents
    docs = populate_documents(seed=42)

    log.info(f"[real-populate] real items={saved} mock docs={docs}")
    return {"items": saved, "documents": docs, "source": "real_onbid"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--count", type=int, default=50)
    p.add_argument("--reset", action="store_true")
    args = p.parse_args()
    res = populate(count=args.count, reset=args.reset)
    print(f"\n[OK] 데이터 적재 완료 (source={res.get('source', 'mock')})")
    print(f"  - items: {res['items']}건")
    print(f"  - documents: {res.get('documents', 0)}건")


if __name__ == "__main__":
    main()
