"""
scripts/export_static_dashboard.py

GitHub Pages 정적 대시보드용 JSON 을 생성한다.

우선순위:
1) 기존 SQLite DB 가 있고 items 가 있으면 → DB 에서 추출
2) DB 가 비어 있으면 → mock 파이프라인을 mock-only 로 한 번 돌려서 추출
3) 그래도 실패하면 → 자체 hard-coded sample 로 fallback

산출:
    docs/data/mock_dashboard.json
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "auction_agent.db"
OUT_PATH = ROOT / "docs" / "data" / "mock_dashboard.json"
SAMPLE_LIMIT = 30
TOP_LIMIT = 5


def _connect() -> sqlite3.Connection | None:
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _has_items(conn: sqlite3.Connection) -> bool:
    try:
        n = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        return n > 0
    except sqlite3.OperationalError:
        return False


def _ensure_db_seeded() -> bool:
    """DB 가 없거나 비어 있으면 mock 파이프라인을 한 번 돌려 채운다."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        from core.database import init_db
        from scripts.generate_mock_data import generate as gen_mock
        init_db()
        conn = _connect()
        if conn and _has_items(conn):
            conn.close()
            return True
        gen_mock(count=120, seed=42, reset=False)
        # 가능하면 분석까지 한 번
        try:
            from agents.legal_risk_agent import analyze_all as analyze_risk
            from agents.price_analysis_agent import analyze_all as analyze_price
            from agents.confidence_agent import compute_all as compute_conf
            analyze_price()
            analyze_risk()
            compute_conf()
        except Exception:
            pass
        return True
    except Exception as e:
        print(f"[warn] 자동 시드 실패: {e}", file=sys.stderr)
        return False


def _summarize_items(conn: sqlite3.Connection) -> dict[str, Any]:
    total = conn.execute("SELECT COUNT(*) FROM items WHERE status='active'").fetchone()[0]
    try:
        analyzed = conn.execute(
            "SELECT COUNT(DISTINCT item_id) FROM price_analyses"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        analyzed = 0
    try:
        high_risk = conn.execute(
            "SELECT COUNT(DISTINCT item_id) FROM risk_flags WHERE risk_level='high'"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        high_risk = 0
    try:
        avg_conf_row = conn.execute(
            "SELECT AVG(overall_confidence) FROM confidence_scores"
        ).fetchone()
        avg_conf = float(avg_conf_row[0]) if avg_conf_row and avg_conf_row[0] is not None else 0.0
    except sqlite3.OperationalError:
        avg_conf = 0.0
    return {
        "total_items": total,
        "analyzed_items": analyzed,
        "high_risk_items": high_risk,
        "avg_confidence": round(avg_conf, 3),
    }


def _items_sample(conn: sqlite3.Connection, limit: int = SAMPLE_LIMIT) -> list[dict]:
    rows = conn.execute(
        """
        SELECT i.id, i.source, i.address_full, i.item_type,
               i.appraisal_price, i.min_bid_price, i.fail_count, i.bid_date,
               (SELECT risk_level FROM risk_flags r
                  WHERE r.item_id=i.id ORDER BY
                    CASE r.risk_level WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
                  LIMIT 1) AS risk_level
        FROM items i
        WHERE i.status='active'
        ORDER BY i.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "source": r["source"],
            "address": r["address_full"],
            "item_type": r["item_type"],
            "appraisal_price": r["appraisal_price"],
            "min_bid_price": r["min_bid_price"],
            "fail_count": r["fail_count"],
            "bid_date": r["bid_date"],
            "risk_level": r["risk_level"] or "medium",
        })
    return out


def _recommendations_from_db(conn: sqlite3.Connection, limit: int = TOP_LIMIT) -> list[dict]:
    """가장 최근 brief/recommendation_results 에서 가져온다."""
    try:
        row = conn.execute(
            "SELECT top_picks_json FROM daily_briefings ORDER BY id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    picks: list[dict] = []
    if row and row["top_picks_json"]:
        try:
            picks = json.loads(row["top_picks_json"])
        except Exception:
            picks = []

    recs: list[dict] = []
    for i, r in enumerate(picks[:limit], 1):
        it = r.get("item", {}) or {}
        score = r.get("score") or 0
        grade = r.get("grade", "C")
        risk_level = r.get("risk_level") or "medium"
        breakdown = r.get("score_breakdown") or {}
        critical = breakdown.get("critical_reasons") or []
        pref_reasons = breakdown.get("preference_reasons") or []
        reason = " · ".join(filter(None, [
            f"점수 {score:.1f} ({grade}등급)",
            "선호 매칭: " + ", ".join(pref_reasons[:2]) if pref_reasons else None,
        ])) or f"{grade} 등급 추천"
        next_actions = []
        if risk_level == "high":
            next_actions.append("등기부등본 재확인")
        if it.get("source") == "auction":
            next_actions.append("매각기일 확인")
        else:
            next_actions.append("입찰기간 확인")
        next_actions.append("현장조사 1회")
        recs.append({
            "rank": i,
            "item_id": it.get("id"),
            "source": it.get("source"),
            "title": it.get("address_full") or "주소 미상",
            "address": it.get("address_full"),
            "item_type": it.get("item_type"),
            "min_bid_price": it.get("min_bid_price"),
            "minimum_price": it.get("min_bid_price"),
            "market_price": r.get("market_price"),
            "expected_profit": r.get("profit_estimate"),
            "expected_profit_rate": r.get("roi_estimate"),
            "risk_level": risk_level,
            "recommendation_score": round(score, 1),
            "recommendation_grade": grade,
            "recommendation_reason": reason if not critical else " / ".join(critical[:2]),
            "next_actions": next_actions,
            "warnings": critical,
        })
    return recs


def _action_items_from_db(conn: sqlite3.Connection, limit: int = 8) -> list[dict]:
    try:
        rows = conn.execute(
            """
            SELECT a.priority, a.title, a.detail, a.due_date,
                   i.address_full, i.item_type
            FROM action_items a
            LEFT JOIN items i ON i.id=a.item_id
            WHERE a.status='open'
            ORDER BY CASE a.priority
                WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                a.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [
        {
            "priority": r["priority"] or "medium",
            "title": r["title"] or "",
            "detail": r["detail"] or "",
            "due_date": r["due_date"],
            "address": r["address_full"],
            "item_type": r["item_type"],
        }
        for r in rows
    ]


def _risk_summary_from_db(conn: sqlite3.Connection) -> dict[str, Any]:
    out = {"low": 0, "medium": 0, "high": 0, "top_flags": []}
    try:
        rows = conn.execute(
            """
            SELECT (
              SELECT risk_level FROM risk_flags r
                WHERE r.item_id=i.id
                ORDER BY CASE r.risk_level
                  WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
                LIMIT 1) AS top_risk
            FROM items i
            WHERE i.status='active'
            """
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    for r in rows:
        lvl = r["top_risk"] or "low"
        out[lvl] = out.get(lvl, 0) + 1
    try:
        flag_rows = conn.execute(
            """
            SELECT keyword, COUNT(*) AS cnt
            FROM risk_flags
            WHERE risk_level IN ('high','medium')
            GROUP BY keyword
            ORDER BY cnt DESC
            LIMIT 8
            """
        ).fetchall()
        out["top_flags"] = [{"keyword": r["keyword"], "count": r["cnt"]} for r in flag_rows]
    except sqlite3.OperationalError:
        pass
    return out


def _confidence_summary_from_db(conn: sqlite3.Connection) -> dict[str, Any]:
    try:
        row = conn.execute(
            """
            SELECT AVG(price_confidence) p, AVG(risk_confidence) r,
                   AVG(document_confidence) d, AVG(address_match_confidence) a,
                   AVG(overall_confidence) o
            FROM confidence_scores
            """
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if not row:
        return {"price": 0, "risk": 0, "document": 0, "address": 0, "overall": 0}
    return {
        "price": float(row["p"] or 0),
        "risk": float(row["r"] or 0),
        "document": float(row["d"] or 0),
        "address": float(row["a"] or 0),
        "overall": float(row["o"] or 0),
        "note": "Mock 파이프라인 결과 평균 — 운영시 실거래가/문서 매칭 결과로 대체",
    }


def _briefing_from_db(conn: sqlite3.Connection) -> dict[str, Any]:
    try:
        row = conn.execute(
            "SELECT run_date, summary, total_items, analyzed_items, matched_items, "
            "candidate_items, high_risk_items "
            "FROM daily_briefings ORDER BY id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        row = None
    if not row:
        return {}
    return {
        "run_date": row["run_date"],
        "summary": row["summary"],
        "matched_items": row["matched_items"],
        "candidate_items": row["candidate_items"],
    }


AGENT_LIST = [
    "Natural Language Agent",
    "Intent Understanding Agent",
    "Recommendation Agent",
    "Daily Briefing Agent",
    "Action Planner Agent",
    "Confidence Agent",
    "Risk Checklist Agent",
    "Reasoning Report Agent",
    "Preference Learning Agent",
    "Change Detection Agent",
    "Item Q&A Agent",
    "Outcome Simulation Agent",
    "Agent Orchestrator",
]


def _agent_status() -> list[dict]:
    return [{"name": n, "status": "OK"} for n in AGENT_LIST]


# ── Hard fallback (DB 시드 실패 시) ─────────────────────────────────────────
FALLBACK_RECS = [
    {
        "rank": 1, "source": "auction", "title": "서울특별시 강서구 화곡동 396",
        "address": "서울특별시 강서구 화곡동 396", "item_type": "아파트",
        "min_bid_price": 19200, "minimum_price": 19200, "market_price": 28000,
        "expected_profit": 7800, "expected_profit_rate": 35.4,
        "risk_level": "medium", "recommendation_score": 78.5, "recommendation_grade": "A",
        "recommendation_reason": "감정가 대비 시세 격차 큼 + 위험 키워드 보통",
        "next_actions": ["등기부등본 재확인", "매각기일 확인", "현장조사 1회"],
        "warnings": [],
    },
    {
        "rank": 2, "source": "public_sale", "title": "경기도 안양시 만안구 33",
        "address": "경기도 안양시 만안구 33", "item_type": "오피스텔",
        "min_bid_price": 14500, "minimum_price": 14500, "market_price": 21500,
        "expected_profit": 6100, "expected_profit_rate": 36.4,
        "risk_level": "low", "recommendation_score": 73.0, "recommendation_grade": "B",
        "recommendation_reason": "공매 + 위험 낮음 + 입찰기일 임박",
        "next_actions": ["입찰기간 확인", "현장조사 1회"],
        "warnings": [],
    },
    {
        "rank": 3, "source": "auction", "title": "서울특별시 송파구 잠실동 70",
        "address": "서울특별시 송파구 잠실동 70", "item_type": "아파트",
        "min_bid_price": 47200, "minimum_price": 47200, "market_price": 62000,
        "expected_profit": 12600, "expected_profit_rate": 24.0,
        "risk_level": "medium", "recommendation_score": 70.5, "recommendation_grade": "B",
        "recommendation_reason": "선호 지역 + 차익 큼",
        "next_actions": ["등기부등본 재확인", "매각기일 확인", "전입세대열람"],
        "warnings": ["임차인 키워드 발견"],
    },
    {
        "rank": 4, "source": "public_sale", "title": "인천광역시 남동구 구월동 255",
        "address": "인천광역시 남동구 구월동 255", "item_type": "빌라",
        "min_bid_price": 9800, "minimum_price": 9800, "market_price": 14200,
        "expected_profit": 3700, "expected_profit_rate": 33.0,
        "risk_level": "low", "recommendation_score": 66.0, "recommendation_grade": "B",
        "recommendation_reason": "수익률 높고 위험 낮음",
        "next_actions": ["입찰기간 확인", "현장조사 1회"],
        "warnings": [],
    },
    {
        "rank": 5, "source": "auction", "title": "부산광역시 해운대구 우동 349",
        "address": "부산광역시 해운대구 우동 349", "item_type": "상가",
        "min_bid_price": 18500, "minimum_price": 18500, "market_price": 22000,
        "expected_profit": 2400, "expected_profit_rate": 12.0,
        "risk_level": "medium", "recommendation_score": 55.5, "recommendation_grade": "C",
        "recommendation_reason": "차익은 작지만 데이터 신뢰도 양호",
        "next_actions": ["매각기일 확인", "현장조사 1회"],
        "warnings": [],
    },
]

FALLBACK_ACTIONS = [
    {"priority": "high", "title": "등기부등본 원문 확인",
     "detail": "고위험 키워드 발견 - 최신 등기부등본 발급 후 권리관계 확인",
     "address": "서울특별시 송파구 잠실동 70"},
    {"priority": "high", "title": "전입세대열람 확인",
     "detail": "임차인/대항력 관련 키워드 - 보증금 인수 여부 확인",
     "address": "서울특별시 송파구 잠실동 70"},
    {"priority": "high", "title": "입찰기일 임박",
     "detail": "입찰기일까지 2일 남음", "address": "부산광역시 해운대구 우동 349"},
    {"priority": "medium", "title": "현장조사", "detail": "관심 등록 물건 - 현장 점검 권장",
     "address": "서울특별시 강서구 화곡동 396"},
    {"priority": "medium", "title": "입찰가 재계산",
     "detail": "시세-최저가 gap 큼 - 입찰가 시뮬레이션 권장",
     "address": "경기도 안양시 만안구 33"},
    {"priority": "medium", "title": "신규 공개 문서 확인",
     "detail": "미공개 문서가 있어 공개 시 즉시 확인 필요",
     "address": "인천광역시 남동구 구월동 255"},
]

FALLBACK_ITEMS_REGIONS = ["서울특별시", "경기도", "인천광역시", "부산광역시", "대전광역시"]
FALLBACK_ITEMS_DONG = ["역삼동", "잠실동", "화곡동", "구월동", "우동", "둔산동", "서면", "분당동"]
FALLBACK_TYPES = ["아파트", "오피스텔", "빌라", "상가", "토지"]


def _fallback_payload() -> dict[str, Any]:
    rnd = random.Random(42)
    items = []
    for i in range(24):
        appr = rnd.randrange(8000, 90000)
        minb = int(appr * rnd.uniform(0.6, 0.95))
        items.append({
            "id": i + 1,
            "source": rnd.choice(["auction", "public_sale"]),
            "address": f"{rnd.choice(FALLBACK_ITEMS_REGIONS)} "
                       f"{rnd.choice(FALLBACK_ITEMS_DONG)} "
                       f"{rnd.randrange(10, 999)}",
            "item_type": rnd.choice(FALLBACK_TYPES),
            "appraisal_price": appr,
            "min_bid_price": minb,
            "fail_count": rnd.randrange(0, 4),
            "bid_date": (datetime.now() + timedelta(days=rnd.randrange(2, 30))).date().isoformat(),
            "risk_level": rnd.choices(["low", "medium", "high"], weights=[3, 5, 2])[0],
        })
    rs = {"low": 0, "medium": 0, "high": 0,
          "top_flags": [
              {"keyword": "임차인", "count": 8},
              {"keyword": "관리비 체납", "count": 5},
              {"keyword": "선순위임차인", "count": 3},
              {"keyword": "유치권", "count": 2},
              {"keyword": "법정지상권", "count": 1},
          ]}
    for it in items:
        rs[it["risk_level"]] += 1

    summary = {
        "total_items": 100,
        "analyzed_items": 100,
        "recommended_items": len(FALLBACK_RECS),
        "high_risk_items": rs["high"],
        "avg_confidence": 0.78,
    }
    briefing = {
        "summary": (
            "오늘 mock 데이터로 100건을 분석했습니다.\n"
            "검토 후보(A·B·C) 5건, 주의(D·X) 0건, 고위험 키워드 보유 물건은 "
            f"{rs['high']}건입니다.\n"
            "오늘 우선 볼 물건은 5건이며, 등기부등본·전입세대열람·현장조사 가 권장됩니다."
        ),
    }
    confidence = {
        "price": 0.82, "risk": 0.71, "document": 0.78,
        "address": 0.85, "overall": 0.78,
        "note": "Fallback 표본 — 실제 분석 결과 대신 데모 값",
    }
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "fallback",
        "summary": summary,
        "briefing": briefing,
        "recommendations": FALLBACK_RECS,
        "action_items": FALLBACK_ACTIONS,
        "risk_summary": rs,
        "confidence_summary": confidence,
        "items": items,
        "agent_status": _agent_status(),
    }


def _payload_from_db(conn: sqlite3.Connection) -> dict[str, Any]:
    summary = _summarize_items(conn)
    recs = _recommendations_from_db(conn)
    if len(recs) < TOP_LIMIT:
        # 브리핑 후보가 적으면 fallback 으로 5개 채워서 데모용 그리드 유지
        existing_ids = {r.get("item_id") for r in recs}
        for fb in FALLBACK_RECS:
            if len(recs) >= TOP_LIMIT:
                break
            r = dict(fb)
            r["rank"] = len(recs) + 1
            r["recommendation_reason"] = (r.get("recommendation_reason") or "") + " (샘플 보강)"
            recs.append(r)
    actions = _action_items_from_db(conn) or FALLBACK_ACTIONS
    rs = _risk_summary_from_db(conn)
    conf = _confidence_summary_from_db(conn)
    items = _items_sample(conn) or _fallback_payload()["items"]

    summary["recommended_items"] = len(recs)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "db",
        "summary": summary,
        "briefing": _briefing_from_db(conn) or {
            "summary": "DB 에서 추출한 mock 분석 결과입니다.",
        },
        "recommendations": recs,
        "action_items": actions,
        "risk_summary": rs,
        "confidence_summary": conf,
        "items": items,
        "agent_status": _agent_status(),
    }


def export() -> Path:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] | None = None

    conn = _connect()
    if conn and _has_items(conn):
        try:
            payload = _payload_from_db(conn)
        except Exception as e:
            print(f"[warn] DB 추출 실패: {e}", file=sys.stderr)
        finally:
            conn.close()

    if payload is None:
        # DB 가 없거나 비어 있음 → 시드 시도
        if _ensure_db_seeded():
            conn = _connect()
            if conn:
                try:
                    payload = _payload_from_db(conn)
                except Exception as e:
                    print(f"[warn] 시드 후 DB 추출 실패: {e}", file=sys.stderr)
                finally:
                    conn.close()

    if payload is None:
        print("[info] DB 추출 실패 → fallback 샘플 사용", file=sys.stderr)
        payload = _fallback_payload()

    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return OUT_PATH


def main() -> None:
    out = export()
    size = out.stat().st_size
    print(f"[OK] {out.relative_to(ROOT)} ({size:,} bytes)")


if __name__ == "__main__":
    main()
