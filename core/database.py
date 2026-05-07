"""
core/database.py
SQLite DB 초기화 + 공통 연결.
모든 모듈은 여기서 import해서 사용한다.

특징
- 기존 items 스키마와 호환되도록 unique_key 마이그레이션 유지
- 능동형 에이전트용 추가 테이블 모두 포함
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any

from core import config as _config
from core.logger import log


ITEM_COLUMNS = [
    "source", "case_no", "mgmt_no", "item_type",
    "address_full", "address_si", "address_gu", "address_dong", "address_detail",
    "appraisal_price", "min_bid_price", "fail_count",
    "area_m2", "floor", "total_floor", "bid_date",
    "status", "court_name", "raw_json",
]


def get_connection() -> sqlite3.Connection:
    db_path = _config.DB_PATH
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def build_unique_key(data: dict[str, Any]) -> str:
    source = str(data.get("source") or "unknown").strip()
    case_no = str(data.get("case_no") or "").strip()
    mgmt_no = str(data.get("mgmt_no") or "").strip()

    if case_no or mgmt_no:
        return f"{source}|case={case_no}|mgmt={mgmt_no}"

    fallback = "|".join(
        str(data.get(k) or "").strip()
        for k in ["address_full", "item_type", "bid_date"]
    )
    return f"{source}|fallback={fallback}"


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, ddl: str) -> None:
    if column_name not in _table_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def _migrate_items_table(conn: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "items" not in tables:
        return
    _ensure_column(conn, "items", "unique_key", "unique_key TEXT")
    rows = conn.execute("SELECT * FROM items WHERE unique_key IS NULL OR unique_key = ''").fetchall()
    for row in rows:
        data = dict(row)
        conn.execute(
            "UPDATE items SET unique_key=? WHERE id=?",
            (build_unique_key(data), data["id"]),
        )
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_items_unique_key ON items(unique_key)")


def init_db() -> None:
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        unique_key      TEXT NOT NULL UNIQUE,
        source          TEXT NOT NULL,
        case_no         TEXT,
        mgmt_no         TEXT,
        item_type       TEXT,
        address_full    TEXT,
        address_si      TEXT,
        address_gu      TEXT,
        address_dong    TEXT,
        address_detail  TEXT,
        appraisal_price INTEGER,
        min_bid_price   INTEGER,
        fail_count      INTEGER DEFAULT 0,
        area_m2         REAL,
        floor           TEXT,
        total_floor     TEXT,
        bid_date        TEXT,
        status          TEXT DEFAULT 'active',
        court_name      TEXT,
        is_watched      INTEGER DEFAULT 0,
        raw_json        TEXT,
        created_at      TEXT DEFAULT (datetime('now','localtime')),
        updated_at      TEXT DEFAULT (datetime('now','localtime'))
    )""")
    _migrate_items_table(conn)

    c.execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id         INTEGER REFERENCES items(id) ON DELETE CASCADE,
        doc_type        TEXT,
        file_url        TEXT,
        file_path       TEXT,
        is_disclosed    INTEGER DEFAULT 1,
        extracted_text  TEXT,
        summary         TEXT,
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    )""")
    _ensure_column(conn, "documents", "is_disclosed", "is_disclosed INTEGER DEFAULT 1")

    c.execute("""
    CREATE TABLE IF NOT EXISTS price_records (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id         INTEGER REFERENCES items(id) ON DELETE CASCADE,
        address_dong    TEXT,
        complex_name    TEXT,
        area_m2         REAL,
        trade_price     INTEGER,
        trade_date      TEXT,
        source          TEXT DEFAULT 'molit',
        created_at      TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(item_id, trade_price, area_m2, trade_date, source)
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS price_analyses (
        id                       INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id                  INTEGER UNIQUE REFERENCES items(id) ON DELETE CASCADE,
        avg_price_6m             INTEGER,
        avg_price_12m            INTEGER,
        market_price_estimate    INTEGER,
        minimum_to_market_ratio  REAL,
        appraisal_to_market_ratio REAL,
        transaction_count        INTEGER,
        confidence               TEXT,
        confidence_reason        TEXT,
        data_shortage            INTEGER DEFAULT 0,
        appraisal_inflated       INTEGER DEFAULT 0,
        inflation_warnings_json  TEXT,
        created_at               TEXT DEFAULT (datetime('now','localtime'))
    )""")
    _ensure_column(conn, "price_analyses", "appraisal_inflated", "appraisal_inflated INTEGER DEFAULT 0")
    _ensure_column(conn, "price_analyses", "inflation_warnings_json", "inflation_warnings_json TEXT")

    c.execute("""
    CREATE TABLE IF NOT EXISTS risk_flags (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id         INTEGER REFERENCES items(id) ON DELETE CASCADE,
        flag_type       TEXT,
        keyword         TEXT,
        risk_level      TEXT,
        description     TEXT,
        severity        INTEGER DEFAULT 5,
        source_text     TEXT,
        source          TEXT,
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    )""")
    _ensure_column(conn, "risk_flags", "keyword", "keyword TEXT")
    _ensure_column(conn, "risk_flags", "risk_level", "risk_level TEXT")
    _ensure_column(conn, "risk_flags", "source_text", "source_text TEXT")

    c.execute("""
    CREATE TABLE IF NOT EXISTS risk_checklists (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id         INTEGER REFERENCES items(id) ON DELETE CASCADE,
        flag_type       TEXT,
        item_text       TEXT,
        priority        TEXT DEFAULT 'medium',
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS agent_tasks (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_input      TEXT,
        parsed_intent   TEXT,
        agent_name      TEXT,
        status          TEXT DEFAULT 'pending',
        result_json     TEXT,
        error_message   TEXT,
        created_at      TEXT DEFAULT (datetime('now','localtime')),
        finished_at     TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS recommendation_results (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id         INTEGER REFERENCES agent_tasks(id) ON DELETE CASCADE,
        item_id         INTEGER REFERENCES items(id) ON DELETE CASCADE,
        rank            INTEGER,
        score           REAL,
        grade           TEXT,
        reason          TEXT,
        profit_estimate INTEGER,
        roi_estimate    REAL,
        score_breakdown TEXT,
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    )""")
    _ensure_column(conn, "recommendation_results", "grade", "grade TEXT")
    _ensure_column(conn, "recommendation_results", "score_breakdown", "score_breakdown TEXT")

    c.execute("""
    CREATE TABLE IF NOT EXISTS user_preferences (
        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
        regions_json         TEXT,
        item_types_json      TEXT,
        max_risk_level       TEXT DEFAULT 'medium',
        min_profit_man       INTEGER,
        min_roi              REAL,
        exclude_keywords     TEXT,
        notes                TEXT,
        alerts_enabled       INTEGER DEFAULT 1,
        alert_channel        TEXT DEFAULT 'telegram',
        alert_min_grade      TEXT DEFAULT 'B',
        alert_imminent_days  INTEGER DEFAULT 3,
        alert_only_watched   INTEGER DEFAULT 0,
        alert_include_briefing INTEGER DEFAULT 1,
        updated_at           TEXT DEFAULT (datetime('now','localtime'))
    )""")
    _ensure_column(conn, "user_preferences", "alerts_enabled", "alerts_enabled INTEGER DEFAULT 1")
    _ensure_column(conn, "user_preferences", "alert_channel", "alert_channel TEXT DEFAULT 'telegram'")
    _ensure_column(conn, "user_preferences", "alert_channels_json", "alert_channels_json TEXT")
    _ensure_column(conn, "user_preferences", "alert_min_grade", "alert_min_grade TEXT DEFAULT 'B'")
    _ensure_column(conn, "user_preferences", "alert_imminent_days", "alert_imminent_days INTEGER DEFAULT 3")
    _ensure_column(conn, "user_preferences", "alert_only_watched", "alert_only_watched INTEGER DEFAULT 0")
    _ensure_column(conn, "user_preferences", "alert_include_briefing", "alert_include_briefing INTEGER DEFAULT 1")

    c.execute("""
    CREATE TABLE IF NOT EXISTS alert_log (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_type      TEXT NOT NULL,
        item_id         INTEGER,
        dedupe_key      TEXT NOT NULL UNIQUE,
        priority        TEXT DEFAULT 'medium',
        title           TEXT,
        body            TEXT,
        channel         TEXT,
        sent_at         TEXT,
        status          TEXT DEFAULT 'pending',
        error_message   TEXT,
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_log_type ON alert_log(alert_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_log_item ON alert_log(item_id)")

    c.execute("""
    CREATE TABLE IF NOT EXISTS user_feedback (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id         INTEGER REFERENCES items(id) ON DELETE CASCADE,
        action          TEXT,
        note            TEXT,
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS daily_briefings (
        id                 INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date           TEXT,
        total_items        INTEGER,
        analyzed_items     INTEGER,
        matched_items      INTEGER,
        candidate_items    INTEGER,
        high_risk_items    INTEGER,
        top_picks_json     TEXT,
        warning_picks_json TEXT,
        summary            TEXT,
        delta_json         TEXT,
        insufficient       INTEGER DEFAULT 0,
        created_at         TEXT DEFAULT (datetime('now','localtime'))
    )""")
    _ensure_column(conn, "daily_briefings", "warning_picks_json", "warning_picks_json TEXT")
    _ensure_column(conn, "daily_briefings", "insufficient", "insufficient INTEGER DEFAULT 0")

    c.execute("""
    CREATE TABLE IF NOT EXISTS action_items (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id         INTEGER REFERENCES items(id) ON DELETE CASCADE,
        action_type     TEXT,
        priority        TEXT DEFAULT 'medium',
        title           TEXT,
        detail          TEXT,
        due_date        TEXT,
        status          TEXT DEFAULT 'open',
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS change_events (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id         INTEGER REFERENCES items(id) ON DELETE CASCADE,
        event_type      TEXT,
        old_value       TEXT,
        new_value       TEXT,
        severity        TEXT DEFAULT 'info',
        message         TEXT,
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS confidence_scores (
        id                       INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id                  INTEGER UNIQUE REFERENCES items(id) ON DELETE CASCADE,
        price_confidence         REAL,
        legal_risk_confidence    REAL,
        document_confidence      REAL,
        address_match_confidence REAL,
        overall_confidence       REAL,
        reasons_json             TEXT,
        created_at               TEXT DEFAULT (datetime('now','localtime'))
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS outcome_simulations (
        id                       INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id                  INTEGER REFERENCES items(id) ON DELETE CASCADE,
        scenario_name            TEXT,
        simulated_bid_price      INTEGER,
        simulated_sale_price     INTEGER,
        simulated_total_cost     INTEGER,
        simulated_profit         INTEGER,
        simulated_profit_rate    REAL,
        result_json              TEXT,
        created_at               TEXT DEFAULT (datetime('now','localtime'))
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        run_type        TEXT,
        status          TEXT,
        total_items     INTEGER,
        elapsed_sec     REAL,
        summary_json    TEXT,
        started_at      TEXT,
        finished_at     TEXT,
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS stress_test_results (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        scenario        TEXT,
        item_count      INTEGER,
        query_count     INTEGER,
        elapsed_sec     REAL,
        success         INTEGER,
        error_message   TEXT,
        details_json    TEXT,
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS item_snapshots (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id         INTEGER REFERENCES items(id) ON DELETE CASCADE,
        snapshot_json   TEXT,
        snapshot_date   TEXT,
        created_at      TEXT DEFAULT (datetime('now','localtime'))
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS backtest_runs (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        run_date              TEXT,
        scenario              TEXT,
        mode                  TEXT,
        total_pairs           INTEGER,
        overall_win_rate      REAL,
        overall_mean_profit   REAL,
        a_count               INTEGER, a_mean REAL, a_winrate REAL,
        b_count               INTEGER, b_mean REAL, b_winrate REAL,
        c_count               INTEGER, c_mean REAL, c_winrate REAL,
        d_count               INTEGER, d_mean REAL, d_winrate REAL,
        x_count               INTEGER, x_mean REAL, x_winrate REAL,
        monotonic_decreasing  INTEGER,
        report_json           TEXT,
        ordering_json         TEXT,
        created_at            TEXT DEFAULT (datetime('now','localtime'))
    )""")

    conn.commit()
    conn.close()
    log.info(f"DB 초기화 완료: {_config.DB_PATH}")


def reset_db() -> None:
    """모든 데이터 삭제 (DROP 후 재생성). FK 제약을 잠시 끄고 진행."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys=OFF")
    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]
    for t in tables:
        try:
            cur.execute(f"DROP TABLE IF EXISTS {t}")
        except Exception:
            pass
    conn.commit()
    cur.execute("PRAGMA foreign_keys=ON")
    conn.close()
    init_db()
    log.info("DB 리셋 완료")


def _normalize_item_data(data: dict[str, Any]) -> dict[str, Any]:
    normalized = {key: None for key in ITEM_COLUMNS}
    normalized.update(data)
    normalized["source"] = normalized.get("source") or "unknown"
    normalized["status"] = normalized.get("status") or "active"
    normalized["fail_count"] = normalized.get("fail_count") or 0
    normalized["unique_key"] = build_unique_key(normalized)
    return normalized


def upsert_item(data: dict[str, Any]) -> int:
    init_db()
    payload = _normalize_item_data(data)

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO items (
            unique_key,
            source, case_no, mgmt_no, item_type,
            address_full, address_si, address_gu, address_dong, address_detail,
            appraisal_price, min_bid_price, fail_count,
            area_m2, floor, total_floor, bid_date,
            status, court_name, raw_json
        ) VALUES (
            :unique_key,
            :source, :case_no, :mgmt_no, :item_type,
            :address_full, :address_si, :address_gu, :address_dong, :address_detail,
            :appraisal_price, :min_bid_price, :fail_count,
            :area_m2, :floor, :total_floor, :bid_date,
            :status, :court_name, :raw_json
        )
        ON CONFLICT(unique_key) DO UPDATE SET
            source          = excluded.source,
            case_no         = excluded.case_no,
            mgmt_no         = excluded.mgmt_no,
            item_type       = excluded.item_type,
            address_full    = excluded.address_full,
            address_si      = excluded.address_si,
            address_gu      = excluded.address_gu,
            address_dong    = excluded.address_dong,
            address_detail  = excluded.address_detail,
            appraisal_price = excluded.appraisal_price,
            min_bid_price   = excluded.min_bid_price,
            fail_count      = excluded.fail_count,
            area_m2         = excluded.area_m2,
            floor           = excluded.floor,
            total_floor     = excluded.total_floor,
            bid_date        = excluded.bid_date,
            status          = excluded.status,
            court_name      = excluded.court_name,
            raw_json        = excluded.raw_json,
            updated_at      = datetime('now','localtime')
    """, payload)

    row = c.execute("SELECT id FROM items WHERE unique_key=?", (payload["unique_key"],)).fetchone()
    conn.commit()
    conn.close()
    return int(row["id"])
