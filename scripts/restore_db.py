"""
scripts/restore_db.py
gzip 백업 파일에서 SQLite DB 복원.

사용
    python scripts/restore_db.py --src data/exports/db_backup_20260507.db.gz
    python scripts/restore_db.py --src backup.db.gz --force

기본은 DB_PATH 가 비어있을 때만 복원. --force 로 덮어쓰기.
"""
from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import config  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--src", required=True, help="압축 백업 파일 경로")
    p.add_argument("--force", action="store_true",
                   help="기존 DB 덮어쓰기")
    args = p.parse_args()

    if not os.path.exists(args.src):
        print(f"[X] 백업 파일 없음: {args.src}")
        sys.exit(1)

    dst = config.DB_PATH
    if os.path.exists(dst) and not args.force:
        print(f"[X] 기존 DB 존재: {dst}. 덮어쓰려면 --force 추가.")
        sys.exit(1)

    db_dir = os.path.dirname(dst)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    src_size = os.path.getsize(args.src)
    with gzip.open(args.src, "rb") as fin, open(dst, "wb") as fout:
        shutil.copyfileobj(fin, fout, length=64 * 1024)
    out_size = os.path.getsize(dst)
    print(f"[OK] {args.src} -> {dst}")
    print(f"  압축 {src_size:,} bytes -> 복원 {out_size:,} bytes")


if __name__ == "__main__":
    main()
