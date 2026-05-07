"""
scripts/backup_db.py
SQLite DB 를 gzip 백업.

사용
    python scripts/backup_db.py
    python scripts/backup_db.py --out my_backup.db.gz

Streamlit Cloud ephemeral fs 환경에서 주기적으로 다운받아 보관 후
필요 시 restore_db.py 로 복원. Turso 사용 중이면 이 스크립트는 의미 없음.
"""
from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import config  # noqa: E402
from core.utils import ensure_dir, export_path  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", help="출력 파일 (기본 data/exports/db_backup_<TS>.db.gz)")
    args = p.parse_args()

    src = config.DB_PATH
    if not os.path.exists(src):
        print(f"[X] DB 파일 없음: {src}")
        sys.exit(1)

    if args.out:
        out_path = args.out
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ensure_dir(os.path.dirname(export_path("db_backup.db.gz")))
        out_path = export_path(f"db_backup_{ts}.db.gz")

    src_size = os.path.getsize(src)
    with open(src, "rb") as fin, gzip.open(out_path, "wb", compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout, length=64 * 1024)
    out_size = os.path.getsize(out_path)
    ratio = (1 - out_size / src_size) * 100 if src_size else 0
    print(f"[OK] {out_path}")
    print(f"  원본 {src_size:,} bytes -> 압축 {out_size:,} bytes "
          f"({ratio:+.1f}% 감소)")


if __name__ == "__main__":
    main()
