"""
agents/monitoring_agent.py
운영 모니터링: pipeline_runs / alert_log / stress_test_results / DB 헬스 / 이상 감지.

대시보드의 "운영 모니터링" 탭이 사용한다.
"""
from __future__ import annotations

import os
import statistics
from typing import Any

from core.config import DB_PATH
from core.database import get_connection, init_db
from core.logger import log


# ── 단순 history 조회 ────────────────────────────────────────────


def get_pipeline_history(limit: int = 30) -> list[dict]:
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, run_type, status, total_items, elapsed_sec, "
        "started_at, finished_at, created_at "
        "FROM pipeline_runs ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_alert_history(limit: int = 100) -> list[dict]:
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM alert_log ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stress_history(limit: int = 30) -> list[dict]:
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, scenario, item_count, query_count, elapsed_sec, "
        "success, error_message, created_at "
        "FROM stress_test_results ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── DB 헬스 (테이블별 행수 + 파일 크기) ───────────────────────────


def db_health() -> dict:
    init_db()
    conn = get_connection()
    tables = [
        r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]
    counts: dict[str, int] = {}
    for t in tables:
        try:
            c = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            counts[t] = int(c)
        except Exception as e:
            log.warning(f"[monitoring] {t} count 실패: {e}")
            counts[t] = -1
    conn.close()
    size_bytes = 0
    try:
        if os.path.exists(DB_PATH):
            size_bytes = os.path.getsize(DB_PATH)
    except OSError:
        pass
    return {
        "tables": counts,
        "total_rows": sum(v for v in counts.values() if v > 0),
        "table_count": len(tables),
        "db_path": DB_PATH,
        "db_size_bytes": size_bytes,
        "db_size_kb": round(size_bytes / 1024, 1),
    }


# ── 알림 통계 ────────────────────────────────────────────────────


def alert_summary(limit: int = 1000) -> dict:
    """채널별/상태별/타입별 카운트 집계."""
    init_db()
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM alert_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    by_channel: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for r in rows:
        ch = r["channel"] or "(unknown)"
        st = r["status"] or "(unknown)"
        at = r["alert_type"] or "(unknown)"
        by_channel[ch] = by_channel.get(ch, 0) + 1
        by_status[st] = by_status.get(st, 0) + 1
        by_type[at] = by_type.get(at, 0) + 1
    return {
        "total": len(rows),
        "by_channel": by_channel,
        "by_status": by_status,
        "by_type": by_type,
    }


# ── 이상 감지 ────────────────────────────────────────────────────


def detect_anomalies() -> list[dict]:
    """최근 운영 데이터에서 이상 징후를 감지.

    Returns: [{"severity": "warning|info", "message": "..."}, ...]
    """
    issues: list[dict] = []

    # 1. 마지막 파이프라인이 평소보다 2배 이상 느려졌나?
    runs = get_pipeline_history(20)
    if len(runs) >= 5:
        elapsed = [r["elapsed_sec"] for r in runs if r["elapsed_sec"]]
        if elapsed:
            recent = elapsed[0]
            avg_prev = statistics.mean(elapsed[1:6]) if len(elapsed) > 1 else recent
            if recent > avg_prev * 2 and recent > 10:
                issues.append({
                    "severity": "warning",
                    "message": (
                        f"최근 파이프라인 {recent:.1f}s 가 직전 5회 평균 "
                        f"{avg_prev:.1f}s 의 2배 이상으로 느려짐"
                    ),
                })

    # 2. 마지막 파이프라인이 실패였나?
    if runs and runs[0].get("status") and runs[0]["status"] != "ok":
        issues.append({
            "severity": "warning",
            "message": f"마지막 파이프라인 status={runs[0]['status']}",
        })

    # 3. 알림 실패율이 높나?
    summary = alert_summary(limit=100)
    sent = summary["by_status"].get("sent", 0)
    failed = summary["by_status"].get("failed", 0)
    total = sent + failed
    if total >= 10 and failed / total > 0.2:
        issues.append({
            "severity": "warning",
            "message": f"최근 알림 실패율 {failed / total * 100:.1f}% ({failed}/{total})",
        })

    # 4. 24시간 이상 새 파이프라인이 없으면
    if runs:
        latest = runs[0]
        latest_at = latest.get("created_at")
        if latest_at:
            from datetime import datetime
            try:
                dt = datetime.strptime(latest_at, "%Y-%m-%d %H:%M:%S")
                hours = (datetime.now() - dt).total_seconds() / 3600
                if hours > 24:
                    issues.append({
                        "severity": "info",
                        "message": f"마지막 파이프라인 실행 후 {hours:.1f}시간 경과",
                    })
            except Exception:
                pass

    # 5. DB 파일이 비정상적으로 큼? (50MB 초과)
    health = db_health()
    if health["db_size_kb"] > 50_000:
        issues.append({
            "severity": "info",
            "message": f"DB 크기 {health['db_size_kb'] / 1024:.1f} MB - 정리/아카이브 검토",
        })

    return issues


# ── 시계열 차트용 ────────────────────────────────────────────────


def pipeline_timeline_series(limit: int = 30) -> list[dict]:
    """오래된 순으로 시간 + 처리량 + 소요시간 반환."""
    runs = list(reversed(get_pipeline_history(limit)))
    return [{
        "created_at": r.get("created_at"),
        "elapsed_sec": r.get("elapsed_sec") or 0,
        "total_items": r.get("total_items") or 0,
        "status": r.get("status") or "unknown",
    } for r in runs]


def alert_timeline_series(limit: int = 200) -> list[dict]:
    """일자별 알림 발송 카운트 (sent / failed 분리)."""
    init_db()
    conn = get_connection()
    rows = conn.execute("""
        SELECT date(created_at) AS day,
               SUM(CASE WHEN status='sent' THEN 1 ELSE 0 END) AS sent,
               SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed
        FROM alert_log
        WHERE created_at IS NOT NULL
        GROUP BY date(created_at)
        ORDER BY day ASC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
