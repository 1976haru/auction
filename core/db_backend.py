"""
core/db_backend.py
DB 연결 추상화.

- 기본: 로컬 SQLite (data/auction_agent.db)
- TURSO_DATABASE_URL + TURSO_AUTH_TOKEN 설정 시: Turso (libSQL Cloud)
  Turso 는 SQLite 호환 + 클라우드 지속성 + 무료 티어 (500GB 읽기/월).
  Streamlit Cloud 의 ephemeral fs 한계 해결용.

설치 (Turso 사용 시만):
    pip install libsql-experimental

연결 실패 시 자동으로 SQLite 로 fallback (warning log).
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any

from core import config as _config
from core.logger import log


def _try_turso_connection():
    """Turso 키가 설정되어 있고 libsql 패키지 설치돼 있으면 연결 반환. 아니면 None."""
    if not _config.TURSO_DATABASE_URL or not _config.TURSO_AUTH_TOKEN:
        return None
    try:
        import libsql_experimental as libsql  # type: ignore
    except ImportError:
        log.warning(
            "[db_backend] TURSO_DATABASE_URL 설정됐지만 libsql-experimental 미설치. "
            "pip install libsql-experimental 후 재시도. SQLite fallback."
        )
        return None
    try:
        conn = libsql.connect(
            "auction_agent.db",  # 로컬 캐시 파일 (libsql 내부)
            sync_url=_config.TURSO_DATABASE_URL,
            auth_token=_config.TURSO_AUTH_TOKEN,
        )
        # 첫 연결 시 sync
        try:
            conn.sync()
        except Exception as e:
            log.warning(f"[db_backend] Turso 초기 sync 실패 (계속 진행): {e}")
        return conn
    except Exception as e:
        log.warning(f"[db_backend] Turso 연결 실패 -> SQLite fallback: {e}")
        return None


def _sqlite_connection() -> sqlite3.Connection:
    db_path = _config.DB_PATH
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def get_backend_name() -> str:
    """현재 활성 backend 이름 반환 ('turso' | 'sqlite')."""
    if _config.TURSO_DATABASE_URL and _config.TURSO_AUTH_TOKEN:
        try:
            import libsql_experimental  # type: ignore
            return "turso"
        except ImportError:
            return "sqlite"
    return "sqlite"


def open_connection() -> Any:
    """현재 환경 기준 DB 연결을 반환."""
    turso = _try_turso_connection()
    if turso is not None:
        return turso
    return _sqlite_connection()
