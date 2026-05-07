"""
agents/item_qa_agent.py
물건별 Q&A. 풍부한 컨텍스트(아이템 + 분석 + 시세 트렌드 + 입찰가 + 백테스트 통계 +
peer 비교)를 모아 AI 또는 mock 에 질의한다.

설계 원칙
- 컨텍스트는 최대한 풍부하게 모은다. mock 답변도 그 컨텍스트를 활용해
  더 의미 있는 응답을 만든다.
- 실 Claude 호출 시에는 동일 컨텍스트가 prompt 에 들어가 답변 품질이 향상.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Any

from agents.confidence_agent import get_confidence
from core.ai_client import item_qa as ai_item_qa
from core.database import get_connection, init_db
from core.logger import log
from core.utils import days_until, loads, now_iso
from modules.documents.mock_documents import get_item_documents
from modules.profit_calculator import calc_profit
from modules.risk.keyword_analyzer import get_risk_flags
from modules.valuation.price_matcher import (
    get_price_analysis,
    get_trade_history,
    monthly_aggregate,
)

# 캐시 TTL (시간). 이 시간이 지나면 자동 무효화.
CACHE_TTL_HOURS = 24


def _peer_stats(item: dict) -> dict:
    """같은 시/구 + 유형의 다른 매물 통계."""
    si = item.get("address_si")
    gu = item.get("address_gu")
    item_type = item.get("item_type")
    if not si or not gu or not item_type:
        return {"count": 0}
    conn = get_connection()
    rows = conn.execute("""
        SELECT i.id, i.appraisal_price, i.min_bid_price, i.fail_count,
               pa.market_price_estimate, pa.appraisal_inflated
        FROM items i
        LEFT JOIN price_analyses pa ON pa.item_id = i.id
        WHERE i.address_si = ? AND i.address_gu = ? AND i.item_type = ?
          AND i.id != ?
    """, (si, gu, item_type, item["id"])).fetchall()
    conn.close()
    if not rows:
        return {"count": 0}
    rows = [dict(r) for r in rows]
    appraisals = [r["appraisal_price"] for r in rows if r.get("appraisal_price")]
    bids = [r["min_bid_price"] for r in rows if r.get("min_bid_price")]
    markets = [r["market_price_estimate"] for r in rows if r.get("market_price_estimate")]
    fails = [r["fail_count"] for r in rows if r.get("fail_count") is not None]
    return {
        "count": len(rows),
        "avg_appraisal": int(sum(appraisals) / len(appraisals)) if appraisals else 0,
        "avg_min_bid": int(sum(bids) / len(bids)) if bids else 0,
        "avg_market": int(sum(markets) / len(markets)) if markets else 0,
        "avg_fail_count": round(sum(fails) / len(fails), 2) if fails else 0,
        "inflated_count": sum(1 for r in rows if r.get("appraisal_inflated")),
    }


def _trend_summary(item_id: int) -> dict:
    """매물 단위 시세 트렌드 요약."""
    trades = get_trade_history(item_id)
    monthly = monthly_aggregate(trades)
    if not monthly:
        return {"months": 0, "trades": 0, "trend_pct": None}
    first = monthly[0]["avg_price"]
    last = monthly[-1]["avg_price"]
    trend_pct = ((last - first) / first * 100) if first else 0
    return {
        "months": len(monthly),
        "trades": len(trades),
        "first_avg": first,
        "last_avg": last,
        "trend_pct": round(trend_pct, 1),
        "direction": "상승" if trend_pct > 1 else ("하락" if trend_pct < -1 else "보합"),
    }


def _backtest_grade_summary(grade: str | None) -> dict:
    """현재 매물 등급에 해당하는 백테스트 통계 (가장 최근 run)."""
    if not grade:
        return {}
    conn = get_connection()
    row = conn.execute("""
        SELECT * FROM backtest_runs
        WHERE mode='all_items' AND scenario='standard'
        ORDER BY id DESC LIMIT 1
    """).fetchone()
    conn.close()
    if not row:
        return {}
    g = grade.lower()
    return {
        "run_date": row["run_date"],
        "grade": grade,
        "count": row[f"{g}_count"] if grade in ("A", "B", "C", "D", "X") else None,
        "mean_profit": row[f"{g}_mean"] if grade in ("A", "B", "C", "D", "X") else None,
        "win_rate": row[f"{g}_winrate"] if grade in ("A", "B", "C", "D", "X") else None,
    }


def _bid_recommendation(item_id: int) -> dict:
    """입찰가 추천 결과 요약 (보수/기준/공격)."""
    try:
        from agents.bidding_agent import get_bid_recommendation
        b = get_bid_recommendation(item_id)
        if "bids" not in b:
            return {}
        return {
            "market_price": b.get("market_price"),
            "conservative": b["bids"]["conservative"],
            "standard": b["bids"]["standard"],
            "aggressive": b["bids"]["aggressive"],
        }
    except Exception:
        return {}


def _latest_recommendation(item_id: int) -> dict:
    """최근 추천 점수/등급/분해."""
    conn = get_connection()
    row = conn.execute("""
        SELECT score, grade, score_breakdown FROM recommendation_results
        WHERE item_id=? ORDER BY id DESC LIMIT 1
    """, (item_id,)).fetchone()
    conn.close()
    if not row:
        return {}
    return {
        "score": row["score"],
        "grade": row["grade"],
        "breakdown": loads(row["score_breakdown"], {}),
    }


def _build_context(item_id: int) -> dict:
    conn = get_connection()
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    if not row:
        return {}
    item = dict(row)
    pa = get_price_analysis(item_id) or {}
    flags = get_risk_flags(item_id)
    conf = get_confidence(item_id) or {}
    docs = get_item_documents(item_id)

    market = pa.get("market_price_estimate") or int(item.get("appraisal_price", 0) * 0.95)
    pinfo = calc_profit(int(market or 0), int(item.get("min_bid_price", 0) or 0),
                        item.get("item_type", "아파트"))

    rec = _latest_recommendation(item_id)
    item.update({
        "price_analysis": pa,
        "risk_flags_summary": [
            {"type": f["flag_type"], "level": f["risk_level"]} for f in flags
        ],
        "risk_score": max((f["severity"] for f in flags), default=0),
        "confidence": conf,
        "documents": [
            {"type": d["doc_type"], "is_disclosed": bool(d["is_disclosed"])}
            for d in docs
        ],
        # 신규 컨텍스트
        "profit_estimate": pinfo.get("profit"),
        "roi_estimate": pinfo.get("roi"),
        "market_price": market,
        "bid_days_left": days_until(item.get("bid_date")),
        "trend": _trend_summary(item_id),
        "peer_stats": _peer_stats(item),
        "bid_recommendation": _bid_recommendation(item_id),
        "recommendation": rec,
        "backtest": _backtest_grade_summary(rec.get("grade")),
    })
    return item


# ── 캐싱 헬퍼 ────────────────────────────────────────────────────


def _normalize_question(q: str) -> str:
    """질문 정규화 - 공백/구두점 통일해 동의 표현 매칭률↑."""
    s = (q or "").strip().lower()
    s = re.sub(r"[?!.,;:\s]+", " ", s)
    return s.strip()


def _context_signature(ctx: dict) -> str:
    """컨텍스트 변화 추적용 짧은 시그니처. 핵심 지표 변하면 캐시 무효화."""
    parts = [
        str(ctx.get("appraisal_price")),
        str(ctx.get("min_bid_price")),
        str((ctx.get("recommendation") or {}).get("grade")),
        str(ctx.get("risk_score")),
        str(round((ctx.get("confidence") or {}).get("overall_confidence", 0) or 0, 2)),
        str(len(ctx.get("documents") or [])),
        str(ctx.get("bid_date")),
    ]
    raw = "|".join(parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _cache_key(item_id: int, q_norm: str, sig: str) -> str:
    raw = f"{item_id}|{q_norm}|{sig}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _cache_lookup(cache_key: str, ttl_hours: int = CACHE_TTL_HOURS) -> str | None:
    """TTL 내 캐시된 답변 반환. 없거나 만료면 None."""
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT answer, created_at, hit_count FROM qa_cache WHERE cache_key=?",
        (cache_key,),
    ).fetchone()
    if not row:
        conn.close()
        return None
    try:
        created = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() - created > timedelta(hours=ttl_hours):
            conn.close()
            return None
    except Exception:
        conn.close()
        return None
    # hit_count + last_used_at 갱신
    conn.execute(
        "UPDATE qa_cache SET hit_count=hit_count+1, last_used_at=? WHERE cache_key=?",
        (now_iso(), cache_key),
    )
    conn.commit()
    conn.close()
    return row["answer"]


def _cache_store(item_id: int, q_norm: str, sig: str,
                  cache_key: str, answer: str) -> None:
    init_db()
    conn = get_connection()
    conn.execute("""
        INSERT INTO qa_cache (item_id, question_norm, context_sig, cache_key,
                               answer, hit_count, last_used_at)
        VALUES (?, ?, ?, ?, ?, 0, ?)
        ON CONFLICT(cache_key) DO UPDATE SET
            answer=excluded.answer,
            last_used_at=excluded.last_used_at,
            created_at=datetime('now','localtime')
    """, (item_id, q_norm, sig, cache_key, answer, now_iso()))
    conn.commit()
    conn.close()


def clear_cache(item_id: int | None = None) -> int:
    """캐시 삭제. item_id=None 이면 전체. 삭제 행 수 반환."""
    init_db()
    conn = get_connection()
    if item_id is None:
        cur = conn.execute("DELETE FROM qa_cache")
    else:
        cur = conn.execute("DELETE FROM qa_cache WHERE item_id=?", (item_id,))
    n = cur.rowcount
    conn.commit()
    conn.close()
    log.info(f"[qa_cache] cleared {n} rows (item_id={item_id})")
    return int(n)


def cache_stats() -> dict:
    """캐시 사용 통계."""
    init_db()
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as total, SUM(hit_count) as total_hits, "
        "MAX(last_used_at) as last_used FROM qa_cache"
    ).fetchone()
    distinct_items = conn.execute(
        "SELECT COUNT(DISTINCT item_id) FROM qa_cache"
    ).fetchone()[0]
    conn.close()
    return {
        "entries": int(row["total"] or 0),
        "total_hits": int(row["total_hits"] or 0),
        "distinct_items": int(distinct_items or 0),
        "last_used_at": row["last_used"],
    }


# ── 메인 API ────────────────────────────────────────────────────


def ask(item_id: int, question: str, use_cache: bool = True,
        ttl_hours: int = CACHE_TTL_HOURS) -> dict:
    ctx = _build_context(item_id)
    if not ctx:
        return {"error": f"item_id={item_id} 없음"}

    q_norm = _normalize_question(question)
    sig = _context_signature(ctx)
    key = _cache_key(item_id, q_norm, sig)

    cached_answer = _cache_lookup(key, ttl_hours=ttl_hours) if use_cache else None
    if cached_answer is not None:
        answer = cached_answer
        cached = True
    else:
        answer = ai_item_qa(question, ctx)
        if use_cache:
            _cache_store(item_id, q_norm, sig, key, answer)
        cached = False

    return {
        "item_id": item_id,
        "question": question,
        "answer": answer,
        "cached": cached,
        "cache_key": key,
        "context_summary": {
            "address": ctx.get("address_full"),
            "grade": ctx.get("recommendation", {}).get("grade"),
            "score": ctx.get("recommendation", {}).get("score"),
            "risk_score": ctx.get("risk_score"),
            "confidence": ctx.get("confidence", {}).get("overall_confidence"),
            "trend_direction": ctx.get("trend", {}).get("direction"),
            "peer_count": ctx.get("peer_stats", {}).get("count"),
        },
        "context_keys": sorted([k for k in ctx.keys() if not k.startswith("_")]),
        "disclaimer": "참고용 답변이며, 법률·투자 판단은 직접 검토하세요.",
    }
