"""
tests/test_db_backend.py
DB backend 추상화: SQLite/Turso 분기 + 백업/복원.
"""


def test_get_backend_name_sqlite_when_no_turso(monkeypatch):
    monkeypatch.setenv("TURSO_DATABASE_URL", "")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "")
    import importlib, core.config, core.db_backend
    importlib.reload(core.config)
    importlib.reload(core.db_backend)
    assert core.db_backend.get_backend_name() == "sqlite"


def test_open_connection_returns_sqlite_when_no_turso():
    import sqlite3
    from core.db_backend import open_connection
    conn = open_connection()
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_get_connection_uses_backend():
    import sqlite3
    from core.database import get_connection
    conn = get_connection()
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_db_init_works_through_backend():
    """기본 DB 초기화가 backend 경유해도 정상 동작."""
    from core.database import get_connection, init_db
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='items'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_backup_and_restore_round_trip(tmp_path, monkeypatch):
    """백업 -> DB 삭제 -> 복원 후 같은 데이터 보존."""
    import os
    from core.database import get_connection, init_db, upsert_item
    from core import config

    # 초기 데이터
    init_db()
    iid = upsert_item({
        "source": "auction", "case_no": "BACKUP_TEST",
        "item_type": "아파트",
        "address_full": "백업 테스트 주소",
        "appraisal_price": 50000, "min_bid_price": 30000,
        "bid_date": "2026-12-01",
    })
    assert iid > 0

    # 백업
    import gzip, shutil
    backup_path = tmp_path / "backup.db.gz"
    src = config.DB_PATH
    with open(src, "rb") as fin, gzip.open(backup_path, "wb") as fout:
        shutil.copyfileobj(fin, fout)
    assert backup_path.stat().st_size > 0

    # DB 삭제 (실제 conftest 가 다른 임시 DB 쓰니까 이 파일은 삭제 가능)
    if os.path.exists(src):
        os.remove(src)

    # 복원
    with gzip.open(backup_path, "rb") as fin, open(src, "wb") as fout:
        shutil.copyfileobj(fin, fout)
    assert os.path.getsize(src) > 0

    # 데이터 검증
    conn = get_connection()
    row = conn.execute(
        "SELECT case_no FROM items WHERE case_no='BACKUP_TEST'"
    ).fetchone()
    conn.close()
    assert row is not None


def test_check_apis_includes_turso():
    from scripts.check_apis import run_all
    res = run_all()
    assert "turso" in res["checks"]
    # 키 미설정 시 ok=True (SQLite 사용 정상)
    assert res["checks"]["turso"]["ok"] is True
    assert "TURSO" in res["checks"]["turso"]["note"] or "Turso" in res["checks"]["turso"]["note"]
