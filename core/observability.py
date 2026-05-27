"""
core/observability.py
운영 메트릭 기록/조회 + 임계값 알림. metrics 테이블 사용.

사용:
    from core.observability import record_metric, track_metric, get_summary
    record_metric("api_call_count", 1, {"api": "kakao"})

    @track_metric("pipeline.duration")
    def run(): ...
"""
from __future__ import annotations

import functools
import json
import os
import time
from typing import Any, Callable

from core import config
from core.database import get_connection, init_db
from core.logger import log


def record_metric(name: str, value: float, tags: dict | None = None) -> None:
    try:
        init_db()
        conn = get_connection()
        conn.execute(
            "INSERT INTO metrics (name, value, tags) VALUES (?, ?, ?)",
            (name, float(value), json.dumps(tags, ensure_ascii=False) if tags else None),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning(f"[observability] record_metric 실패: {e}")


def get_metrics(name: str, hours: int = 24) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT name, value, tags, timestamp FROM metrics
           WHERE name=? AND timestamp >= datetime('now','localtime', ?)
           ORDER BY timestamp DESC""",
        (name, f"-{int(hours)} hours"),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("tags"):
            try:
                d["tags"] = json.loads(d["tags"])
            except Exception:
                pass
        out.append(d)
    return out


def get_summary(hours: int = 24) -> dict:
    """지난 N시간 메트릭 이름별 집계(count/avg/min/max/last)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT name, COUNT(*) AS n, AVG(value) AS avg, MIN(value) AS min,
                  MAX(value) AS max, SUM(value) AS sum
           FROM metrics WHERE timestamp >= datetime('now','localtime', ?)
           GROUP BY name""",
        (f"-{int(hours)} hours",),
    ).fetchall()
    summary = {}
    for r in rows:
        last = conn.execute(
            "SELECT value, timestamp FROM metrics WHERE name=? ORDER BY id DESC LIMIT 1",
            (r["name"],),
        ).fetchone()
        summary[r["name"]] = {
            "count": r["n"],
            "avg": round(r["avg"], 2) if r["avg"] is not None else None,
            "min": r["min"], "max": r["max"], "sum": r["sum"],
            "last": last["value"] if last else None,
            "last_at": last["timestamp"] if last else None,
        }
    conn.close()
    return summary


def track_metric(name: str) -> Callable:
    """함수 실행 시간을 metric으로 기록하는 데코레이터."""
    def deco(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any):
            started = time.time()
            ok = True
            try:
                return fn(*args, **kwargs)
            except Exception:
                ok = False
                raise
            finally:
                record_metric(name, round(time.time() - started, 3), {"ok": ok})
        return wrapper
    return deco


# ── 임계값 알림 ────────────────────────────────────────────
DEFAULT_THRESHOLDS = {
    "pipeline_idle_hours": 1,        # 파이프라인 1시간+ 미실행
    "api_error_rate": 0.10,          # API 오류율 10%+
    "claude_daily_cost_usd": 5.0,    # Claude 일일 비용 $5+
    "db_size_mb": 100,               # DB 100MB+
}


def check_thresholds(thresholds: dict | None = None) -> list[dict]:
    """임계값 초과 항목 리스트 반환."""
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    alerts: list[dict] = []

    # 1) 파이프라인 미실행
    last_pipe = get_metrics("pipeline_duration_seconds", hours=24)
    if last_pipe:
        from datetime import datetime
        try:
            last_at = datetime.fromisoformat(last_pipe[0]["timestamp"])
            idle_h = (datetime.now() - last_at).total_seconds() / 3600
            if idle_h > th["pipeline_idle_hours"]:
                alerts.append({"name": "pipeline_idle",
                               "message": f"파이프라인 {idle_h:.1f}시간 미실행",
                               "severity": "warning"})
        except Exception:
            pass

    # 2) API 오류율
    summ = get_summary(hours=24)
    calls = summ.get("api_call_count", {}).get("sum") or 0
    errors = summ.get("api_error_count", {}).get("sum") or 0
    if calls and (errors / calls) > th["api_error_rate"]:
        alerts.append({"name": "api_error_rate",
                       "message": f"API 오류율 {errors/calls*100:.1f}%",
                       "severity": "critical"})

    # 3) Claude 비용
    cost = summ.get("claude_api_cost_estimate", {}).get("sum") or 0
    if cost > th["claude_daily_cost_usd"]:
        alerts.append({"name": "claude_cost",
                       "message": f"Claude 일일 비용 ${cost:.2f}",
                       "severity": "warning"})

    # 4) DB 크기
    try:
        size_mb = os.path.getsize(config.DB_PATH) / (1024 * 1024)
        if size_mb > th["db_size_mb"]:
            alerts.append({"name": "db_size",
                           "message": f"DB 크기 {size_mb:.1f}MB",
                           "severity": "warning"})
    except OSError:
        pass

    return alerts
