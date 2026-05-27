"""
core/cache.py
외부 API 응답 캐시 (api_cache 테이블). TTL 기반 만료.

TTL 권장값:
  - 카카오 geocoding: 30일(주소 좌표 불변)
  - 카카오 주변검색: 7일
  - 네이버 뉴스: 1일
  - 국토부 실거래가: 1일
  - 온비드 공매: 6시간
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from core.database import get_connection, init_db
from core.logger import log


def make_key(api_name: str, **params: Any) -> str:
    """api_name + 정규화 파라미터 -> 안정적 캐시 키(md5)."""
    norm = json.dumps(params, ensure_ascii=False, sort_keys=True, default=str)
    h = hashlib.md5(f"{api_name}|{norm}".encode("utf-8")).hexdigest()
    return f"{api_name}:{h}"


def cache_get(api_name: str, cache_key: str) -> dict | None:
    """유효(미만료) 캐시 반환. 없거나 만료면 None. hit_count 증가."""
    try:
        conn = get_connection()
        row = conn.execute(
            """SELECT id, payload_json FROM api_cache
               WHERE cache_key=? AND (expires_at IS NULL OR expires_at > datetime('now','localtime'))""",
            (cache_key,),
        ).fetchone()
        if not row:
            conn.close()
            return None
        conn.execute("UPDATE api_cache SET hit_count = hit_count + 1 WHERE id=?", (row["id"],))
        conn.commit()
        conn.close()
        return json.loads(row["payload_json"]) if row["payload_json"] else None
    except Exception as e:
        log.warning(f"[cache] get 실패: {e}")
        return None


def cache_set(api_name: str, cache_key: str, data: Any, ttl_hours: int = 24) -> None:
    """캐시 저장(기존 키 갱신). expires_at = now + ttl_hours."""
    try:
        init_db()
        conn = get_connection()
        conn.execute(
            """INSERT INTO api_cache (api_name, cache_key, payload_json, hit_count, expires_at)
               VALUES (?, ?, ?, 0, datetime('now','localtime', ?))
               ON CONFLICT(cache_key) DO UPDATE SET
                   api_name=excluded.api_name,
                   payload_json=excluded.payload_json,
                   created_at=datetime('now','localtime'),
                   expires_at=excluded.expires_at""",
            (api_name, cache_key, json.dumps(data, ensure_ascii=False),
             f"+{int(ttl_hours)} hours"),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.warning(f"[cache] set 실패: {e}")


def cache_invalidate(api_name: str, pattern: str | None = None) -> int:
    """api_name(+선택 패턴) 캐시 삭제. 삭제 건수 반환."""
    conn = get_connection()
    if pattern:
        cur = conn.execute(
            "DELETE FROM api_cache WHERE api_name=? AND cache_key LIKE ?",
            (api_name, f"%{pattern}%"),
        )
    else:
        cur = conn.execute("DELETE FROM api_cache WHERE api_name=?", (api_name,))
    n = cur.rowcount
    conn.commit()
    conn.close()
    return n


def cleanup_expired() -> int:
    """만료 캐시 정리. 삭제 건수 반환."""
    conn = get_connection()
    cur = conn.execute(
        "DELETE FROM api_cache WHERE expires_at IS NOT NULL AND expires_at <= datetime('now','localtime')"
    )
    n = cur.rowcount
    conn.commit()
    conn.close()
    if n:
        log.info(f"[cache] 만료 캐시 {n}건 정리")
    return n


def cache_stats() -> dict:
    """캐시 현황(총/유효/만료, api별 hit)."""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM api_cache").fetchone()[0]
    valid = conn.execute(
        "SELECT COUNT(*) FROM api_cache WHERE expires_at IS NULL OR expires_at > datetime('now','localtime')"
    ).fetchone()[0]
    by_api = conn.execute(
        "SELECT api_name, COUNT(*) AS n, SUM(hit_count) AS hits FROM api_cache GROUP BY api_name"
    ).fetchall()
    conn.close()
    return {
        "total": total,
        "valid": valid,
        "expired": total - valid,
        "by_api": {r["api_name"]: {"entries": r["n"], "hits": r["hits"] or 0} for r in by_api},
    }
