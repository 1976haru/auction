"""
scripts/export_static_dashboard.py

GitHub Pages 정적 대시보드용 JSON 을 생성한다.

우선순위:
1) 기존 SQLite DB 가 있고 items 가 있으면 → DB 에서 추출
2) DB 가 비어 있으면 → mock 파이프라인을 mock-only 로 한 번 돌려서 추출
3) 그래도 실패하면 → 자체 hard-coded sample 로 fallback

산출:
    docs/data/mock_dashboard.json

각 item 에는 검색/필터/상세보기를 위한 다음 필드를 모두 포함한다:
    id, source, title, address, region, item_type, case_no,
    appraisal_price, min_bid_price, minimum_price, market_price,
    expected_profit, expected_profit_rate, risk_level, risk_flags,
    recommendation_score, recommendation_grade, confidence_score,
    bid_date, fail_count, recommendation_reason, warnings,
    next_actions, checklist, detail_summary
"""
from __future__ import annotations

import json
import os
import random
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "auction_agent.db"
OUT_PATH = ROOT / "docs" / "data" / "mock_dashboard.json"
SAMPLE_LIMIT = 120
TOP_LIMIT = 5


# ── 유틸 ──────────────────────────────────────────────────────────
_REGION_RE = re.compile(r"^(?P<si>\S+?(?:특별시|광역시|특별자치시|도|특별자치도|시|군|구))")


def _extract_region(address: str | None) -> str:
    if not address:
        return "기타"
    s = address.split()
    return s[0] if s else "기타"


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
    try:
        auction_count = conn.execute(
            "SELECT COUNT(*) FROM items WHERE status='active' AND source='auction'"
        ).fetchone()[0]
        public_count = conn.execute(
            "SELECT COUNT(*) FROM items WHERE status='active' AND source='public_sale'"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        auction_count = public_count = 0
    return {
        "total_items": total,
        "analyzed_items": analyzed,
        "high_risk_items": high_risk,
        "avg_confidence": round(avg_conf, 3),
        "auction_count": auction_count,
        "public_sale_count": public_count,
    }


# ── item-level enrichment ────────────────────────────────────────
def _flags_for(conn: sqlite3.Connection, item_id: int) -> list[dict]:
    try:
        rows = conn.execute(
            "SELECT keyword, flag_type, risk_level, severity, description "
            "FROM risk_flags WHERE item_id=? ORDER BY "
            "CASE risk_level WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END "
            "LIMIT 8",
            (item_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def _price_analysis_for(conn: sqlite3.Connection, item_id: int) -> dict[str, Any] | None:
    try:
        row = conn.execute(
            "SELECT market_price_estimate, transaction_count, "
            "minimum_to_market_ratio, appraisal_to_market_ratio "
            "FROM price_analyses WHERE item_id=? ORDER BY id DESC LIMIT 1",
            (item_id,),
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None


def _confidence_for(conn: sqlite3.Connection, item_id: int) -> float | None:
    try:
        row = conn.execute(
            "SELECT overall_confidence FROM confidence_scores "
            "WHERE item_id=? ORDER BY id DESC LIMIT 1",
            (item_id,),
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else None
    except sqlite3.OperationalError:
        return None


def _change_events_for(conn: sqlite3.Connection, item_id: int, days: int = 7) -> list[dict]:
    try:
        rows = conn.execute(
            """
            SELECT event_type, old_value, new_value, severity, message, created_at
            FROM change_events
            WHERE item_id=? AND created_at >= datetime('now', ?, 'localtime')
            ORDER BY id DESC LIMIT 5
            """,
            (item_id, f"-{days} days"),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def _is_new_item(conn: sqlite3.Connection, item_id: int, hours: int = 48) -> bool:
    try:
        row = conn.execute(
            "SELECT created_at FROM items WHERE id=?", (item_id,)
        ).fetchone()
    except sqlite3.OperationalError:
        return False
    if not row or not row["created_at"]:
        return False
    try:
        dt = datetime.fromisoformat(row["created_at"])
    except Exception:
        return False
    return (datetime.now() - dt) <= timedelta(hours=hours)


def _change_tags_from_events(events: list[dict], is_new: bool) -> list[dict]:
    """change_events 와 신규 여부에서 카드용 배지 태그 목록을 추출한다."""
    tags: list[dict] = []
    seen: set[str] = set()

    def add(key: str, label: str):
        if key in seen:
            return
        seen.add(key)
        tags.append({"key": key, "label": label})

    if is_new:
        add("new", "신규")
    for ev in events:
        et = ev.get("event_type")
        if et == "price_change":
            try:
                old = float(ev.get("old_value") or 0)
                new = float(ev.get("new_value") or 0)
            except (TypeError, ValueError):
                old = new = 0
            if old and new and new < old:
                add("price_drop", "최저가 인하")
            elif old and new and new > old:
                add("price_up", "최저가 인상")
        elif et == "fail_count_change":
            add("fail_inc", "유찰 추가")
        elif et == "bid_date_change":
            add("bid_date", "기일 변경")
        elif et == "status_change":
            add("status", "상태 변경")
    return tags[:4]


def _checklist_from_flags(flags: list[dict]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    rules = {
        "전입세대": "전입세대열람으로 대항력 임차인 여부 확인",
        "임차인": "임차인 보증금/대항력/계약일자 확인",
        "대항력": "대항력 임차인 인수 여부 검토",
        "유치권": "유치권 신고 내역 및 점유 사실 확인",
        "법정지상권": "법정지상권 성립 여부와 토지/건물 분리 확인",
        "위반건축물": "위반건축물 등재 사실 + 시정명령 확인",
        "점유자 미상": "현장 방문으로 점유자 신원·점유 형태 확인",
        "명도": "명도 협의/소송 비용/기간 산정",
        "관리비 체납": "관리비 체납액 인수 범위 확인",
        "선순위임차인": "선순위임차인 보증금 인수 여부 확인",
    }
    for f in flags:
        kw = (f.get("keyword") or "").strip()
        for k, msg in rules.items():
            if k in kw and msg not in seen:
                out.append(msg)
                seen.add(msg)
                break
    if not out:
        out = ["등기부등본 최신본 확인", "현장조사 1회"]
    return out[:6]


def _next_actions_default(source: str | None, risk_level: str, days_left: int | None) -> list[str]:
    actions: list[str] = []
    if risk_level == "high":
        actions.append("등기부등본 재확인")
    if source == "auction":
        actions.append("매각기일 확인")
    else:
        actions.append("입찰기간 확인")
    if days_left is not None and days_left <= 7:
        actions.append(f"입찰기일 D-{max(days_left, 0)} 임박")
    actions.append("현장조사 1회")
    return actions


def _grade_from_score(score: float | None) -> str:
    if score is None:
        return "C"
    if score >= 75:
        return "A"
    if score >= 60:
        return "B"
    if score >= 45:
        return "C"
    if score >= 30:
        return "D"
    return "X"


def _days_left(bid_date: str | None) -> int | None:
    if not bid_date:
        return None
    s = bid_date.split("~")[0].strip()
    try:
        d = datetime.fromisoformat(s).date()
    except Exception:
        return None
    return (d - datetime.now().date()).days


def _items_sample(conn: sqlite3.Connection, limit: int = SAMPLE_LIMIT,
                  picks_by_id: dict[int, dict] | None = None) -> list[dict]:
    """모든 분석 데이터를 합쳐서 검색/필터에 쓸 수 있는 형태로 변환."""
    rows = conn.execute(
        """
        SELECT i.id, i.source, i.case_no, i.address_full, i.address_si, i.address_gu,
               i.item_type, i.appraisal_price, i.min_bid_price, i.fail_count, i.bid_date
        FROM items i
        WHERE i.status='active'
        ORDER BY i.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    # 한 번에 대량 시드된 경우(예: 방금 mock 100건 생성) 모두 created_at 가
    # 최근이라 "신규" 표식이 의미를 잃는다. 이런 경우엔 신규 배지 자체를 비활성한다.
    try:
        fresh_count = conn.execute(
            "SELECT COUNT(*) FROM items WHERE status='active' AND "
            "created_at >= datetime('now','-48 hours','localtime')"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        fresh_count = 0
    treat_new = (len(rows) > 0) and (fresh_count < len(rows) * 0.5)
    out = []
    for r in rows:
        item_id = r["id"]
        flags = _flags_for(conn, item_id)
        risk_level = "low"
        for fl in flags:
            if fl.get("risk_level") == "high":
                risk_level = "high"
                break
            if fl.get("risk_level") == "medium" and risk_level != "high":
                risk_level = "medium"

        pa = _price_analysis_for(conn, item_id) or {}
        market = pa.get("market_price_estimate") or 0
        appr = r["appraisal_price"] or 0
        minb = r["min_bid_price"] or 0
        repair = int(appr * 0.01)
        eviction = int(appr * 0.005) if risk_level != "low" else 0
        expected_profit = int(market - minb - repair - eviction) if market else 0
        expected_profit_rate = round((expected_profit / minb * 100), 1) if minb else 0.0

        # 점수: 추천 결과가 있으면 그대로 사용, 없으면 차익+위험 휴리스틱
        pick = (picks_by_id or {}).get(item_id) or {}
        score = pick.get("score")
        grade = pick.get("grade")
        rec_reason = pick.get("reason")
        if score is None:
            base = max(min(expected_profit_rate, 80) * 0.8, 0)
            risk_bonus = {"low": 15, "medium": 5, "high": -5}.get(risk_level, 0)
            score = round(min(95, max(5, base + risk_bonus)), 1)
        if grade is None:
            grade = _grade_from_score(score)

        confidence = _confidence_for(conn, item_id)
        if confidence is None:
            confidence = 0.7 if pa else 0.55

        days_left = _days_left(r["bid_date"])
        warnings_list = [f["keyword"] for f in flags if f.get("risk_level") == "high"][:4]
        if rec_reason is None:
            if expected_profit > 0 and risk_level == "low":
                rec_reason = f"차익 {expected_profit:,}만원 추정 + 위험 낮음"
            elif expected_profit > 0:
                rec_reason = f"차익 {expected_profit:,}만원 추정 ({risk_level} 위험)"
            else:
                rec_reason = f"시세 매칭 표본 부족, {risk_level} 위험"

        title = r["address_full"] or "주소 미상"
        region = r["address_si"] or _extract_region(r["address_full"])
        next_actions = _next_actions_default(r["source"], risk_level, days_left)
        checklist = _checklist_from_flags(flags)
        events = _change_events_for(conn, item_id)
        is_new = treat_new and _is_new_item(conn, item_id)
        change_tags = _change_tags_from_events(events, is_new)
        # mock 환경에서는 change_events 가 비어 있는 경우가 많아
        # item_id 해시 기반으로 일부 매물에만 데모용 태그를 부여한다.
        if not change_tags:
            h = (item_id * 2654435761) & 0xFFFFFFFF
            if (h % 100) < 18:
                pool = ["new", "price_drop", "bid_date", "fail_inc"]
                key = pool[(h >> 8) % len(pool)]
                label_map = {"new": "신규", "price_drop": "최저가 인하",
                             "bid_date": "기일 변경", "fail_inc": "유찰 추가"}
                change_tags = [{"key": key, "label": label_map[key]}]
                if key == "new":
                    is_new = True

        # 상세 요약 (1줄)
        detail = (
            f"감정가 {appr:,}만원 / 최저가 {minb:,}만원"
            + (f" / 추정시세 {int(market):,}만원" if market else "")
            + (f" / 차익 {expected_profit:,}만원" if expected_profit else "")
            + f" / 위험 {risk_level} / 신뢰도 {confidence:.2f}"
        )

        out.append({
            "id": item_id,
            "source": r["source"],
            "case_no": r["case_no"],
            "title": title,
            "address": r["address_full"],
            "region": region,
            "item_type": r["item_type"],
            "appraisal_price": appr,
            "min_bid_price": minb,
            "minimum_price": minb,
            "market_price": int(market) if market else 0,
            "expected_profit": expected_profit,
            "expected_profit_rate": expected_profit_rate,
            "fail_count": r["fail_count"],
            "bid_date": r["bid_date"],
            "days_left": days_left,
            "risk_level": risk_level,
            "risk_flags": [{
                "keyword": fl.get("keyword"),
                "flag_type": fl.get("flag_type"),
                "risk_level": fl.get("risk_level"),
                "severity": fl.get("severity"),
                "description": fl.get("description"),
            } for fl in flags],
            "recommendation_score": float(score),
            "recommendation_grade": grade,
            "confidence_score": round(float(confidence), 3),
            "recommendation_reason": rec_reason,
            "warnings": warnings_list,
            "next_actions": next_actions,
            "checklist": checklist,
            "detail_summary": detail,
            "change_events": events,
            "change_tags": change_tags,
            "is_new": is_new,
        })
    return out


def _picks_by_id(conn: sqlite3.Connection) -> dict[int, dict]:
    try:
        row = conn.execute(
            "SELECT top_picks_json FROM daily_briefings ORDER BY id DESC LIMIT 1"
        ).fetchone()
    except sqlite3.OperationalError:
        return {}
    if not row or not row["top_picks_json"]:
        return {}
    try:
        picks = json.loads(row["top_picks_json"])
    except Exception:
        return {}
    out: dict[int, dict] = {}
    for r in picks:
        it = r.get("item") or {}
        iid = it.get("id")
        if iid is None:
            continue
        breakdown = r.get("score_breakdown") or {}
        critical = breakdown.get("critical_reasons") or []
        pref = breakdown.get("preference_reasons") or []
        score = r.get("score") or 0
        grade = r.get("grade") or _grade_from_score(score)
        reason = " · ".join(filter(None, [
            f"점수 {score:.1f} ({grade}등급)",
            "선호 매칭: " + ", ".join(pref[:2]) if pref else None,
        ])) or f"{grade} 등급 추천"
        if critical:
            reason = " / ".join(critical[:2])
        out[iid] = {"score": float(score), "grade": grade, "reason": reason,
                    "warnings": critical, "market_price": r.get("market_price"),
                    "profit_estimate": r.get("profit_estimate"),
                    "roi_estimate": r.get("roi_estimate")}
    return out


def _recommendations_from_items(items: list[dict], limit: int = TOP_LIMIT) -> list[dict]:
    """enriched item 리스트에서 점수 기준 상위를 뽑아 일관된 추천 카드 형태로 반환."""
    sorted_items = sorted(items, key=lambda it: it.get("recommendation_score") or 0, reverse=True)
    out: list[dict] = []
    for i, it in enumerate(sorted_items[:limit], 1):
        out.append({
            "rank": i,
            "item_id": it["id"],
            "source": it["source"],
            "title": it["title"],
            "address": it["address"],
            "region": it["region"],
            "item_type": it["item_type"],
            "case_no": it.get("case_no"),
            "min_bid_price": it["min_bid_price"],
            "minimum_price": it["min_bid_price"],
            "market_price": it["market_price"],
            "expected_profit": it["expected_profit"],
            "expected_profit_rate": it["expected_profit_rate"],
            "risk_level": it["risk_level"],
            "recommendation_score": it["recommendation_score"],
            "recommendation_grade": it["recommendation_grade"],
            "recommendation_reason": it["recommendation_reason"],
            "next_actions": it["next_actions"],
            "warnings": it["warnings"],
            "confidence_score": it["confidence_score"],
            "bid_date": it["bid_date"],
        })
    return out


def _action_items_from_db(conn: sqlite3.Connection, limit: int = 8) -> list[dict]:
    try:
        rows = conn.execute(
            """
            SELECT a.priority, a.title, a.detail, a.due_date,
                   i.address_full, i.item_type, i.id
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
            "item_id": r["id"],
            "item_type": r["item_type"],
        }
        for r in rows
    ]


def _risk_summary_from_items(items: list[dict]) -> dict[str, Any]:
    out = {"low": 0, "medium": 0, "high": 0}
    flag_counts: dict[str, int] = {}
    for it in items:
        out[it["risk_level"]] = out.get(it["risk_level"], 0) + 1
        for fl in it.get("risk_flags") or []:
            kw = fl.get("keyword")
            if kw:
                flag_counts[kw] = flag_counts.get(kw, 0) + 1
    top_flags = sorted(flag_counts.items(), key=lambda x: -x[1])[:8]
    out["top_flags"] = [{"keyword": k, "count": v} for k, v in top_flags]
    return out


def _confidence_summary_from_db(conn: sqlite3.Connection) -> dict[str, Any]:
    try:
        row = conn.execute(
            """
            SELECT AVG(price_confidence) p, AVG(legal_risk_confidence) r,
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
        "note": "Mock 파이프라인 결과 평균 — 운영 시 실거래/문서 매칭 결과로 대체",
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


# ── Hard fallback ─────────────────────────────────────────────────
FALLBACK_REGIONS = [
    "서울특별시", "경기도", "인천광역시", "부산광역시", "대전광역시",
    "대구광역시", "광주광역시", "울산특별시", "세종특별자치시", "강원특별자치도",
]
FALLBACK_GU = {
    "서울특별시": ["강남구", "송파구", "마포구", "강서구", "관악구", "강북구", "영등포구"],
    "경기도": ["성남시 분당구", "수원시 영통구", "안양시 동안구", "용인시 수지구"],
    "인천광역시": ["남동구", "연수구", "부평구"],
    "부산광역시": ["해운대구", "수영구", "남구"],
    "대전광역시": ["서구", "유성구"],
    "대구광역시": ["수성구", "달서구"],
    "광주광역시": ["북구", "남구"],
    "울산특별시": ["남구", "북구"],
    "세종특별자치시": [""],
    "강원특별자치도": ["춘천시", "원주시"],
}
FALLBACK_TYPES = ["아파트", "오피스텔", "빌라", "상가", "토지"]
KEYWORD_POOL = [
    "임차인", "전입세대", "대항력", "유치권", "법정지상권",
    "위반건축물", "관리비 체납", "선순위임차인", "점유자 미상", "명도",
]


def _fallback_items(rnd: random.Random, n: int = 100) -> list[dict]:
    today = datetime.now().date()
    items: list[dict] = []
    for i in range(1, n + 1):
        region = rnd.choice(FALLBACK_REGIONS)
        gu = rnd.choice(FALLBACK_GU.get(region) or [""])
        addr = f"{region} {gu} {rnd.randrange(10, 999)}".strip().replace("  ", " ")
        appr = rnd.randrange(8000, 200000)
        ratio = rnd.uniform(0.55, 0.95)
        minb = int(appr * ratio)
        market = int(appr * rnd.uniform(0.85, 1.4))
        repair = int(appr * 0.01)
        evict = int(appr * 0.005)
        profit = market - minb - repair - evict
        roi = round(profit / minb * 100, 1) if minb else 0.0
        risk = rnd.choices(["low", "medium", "high"], weights=[3, 4, 3])[0]
        flags: list[dict] = []
        if risk != "low":
            for kw in rnd.sample(KEYWORD_POOL, k=rnd.randrange(1, 4)):
                flags.append({
                    "keyword": kw,
                    "flag_type": kw,
                    "risk_level": "high" if risk == "high" else "medium",
                    "severity": rnd.randrange(3, 9),
                    "description": f"{kw} 관련 항목 확인 필요",
                })
        days_offset = rnd.randrange(-2, 35)
        bid_start = today + timedelta(days=days_offset)
        bid_end = bid_start + timedelta(days=2)
        bid_date = f"{bid_start.isoformat()}~{bid_end.isoformat()}"
        score = round(min(95, max(5, min(roi, 80) * 0.8 +
                                  {"low": 15, "medium": 5, "high": -5}[risk])), 1)
        grade = _grade_from_score(score)
        confidence = round(rnd.uniform(0.55, 0.92), 3)
        warnings_list = [f["keyword"] for f in flags if f["risk_level"] == "high"][:4]
        item_type = rnd.choice(FALLBACK_TYPES)
        source = rnd.choice(["auction", "public_sale"])
        case_no = (f"2025타경{rnd.randrange(1000, 9999)}" if source == "auction"
                   else f"2025-{rnd.randrange(1000, 9999):04d}")
        rec_reason = (
            f"차익 {profit:,}만원 추정 ({risk} 위험)"
            if profit > 0 else f"시세 매칭 부족, {risk} 위험"
        )
        next_actions = _next_actions_default(source, risk, days_offset)
        checklist = _checklist_from_flags(flags)
        detail = (
            f"감정가 {appr:,}만원 / 최저가 {minb:,}만원"
            f" / 추정시세 {market:,}만원 / 차익 {profit:,}만원"
            f" / 위험 {risk} / 신뢰도 {confidence}"
        )
        # 일부 매물에 변화 태그를 합성해 정적 대시보드에서도 배지가 보이게 한다.
        change_pool = [
            ("new", "신규"),
            ("price_drop", "최저가 인하"),
            ("bid_date", "기일 변경"),
            ("fail_inc", "유찰 추가"),
        ]
        change_tags: list[dict] = []
        if rnd.random() < 0.18:
            kvs = rnd.sample(change_pool, k=rnd.randrange(1, 3))
            change_tags = [{"key": k, "label": v} for k, v in kvs]
        is_new = any(t["key"] == "new" for t in change_tags)
        synthetic_events: list[dict] = []
        for t in change_tags:
            if t["key"] == "price_drop":
                synthetic_events.append({
                    "event_type": "price_change",
                    "old_value": str(int(minb * rnd.uniform(1.05, 1.15))),
                    "new_value": str(minb), "severity": "info",
                    "message": "최저가 인하", "created_at": today.isoformat(),
                })
            elif t["key"] == "bid_date":
                synthetic_events.append({
                    "event_type": "bid_date_change",
                    "old_value": "이전 기일", "new_value": bid_date,
                    "severity": "info", "message": "입찰기일 변경",
                    "created_at": today.isoformat(),
                })
            elif t["key"] == "fail_inc":
                synthetic_events.append({
                    "event_type": "fail_count_change",
                    "old_value": "0", "new_value": "1",
                    "severity": "info", "message": "유찰 1회 추가",
                    "created_at": today.isoformat(),
                })

        items.append({
            "id": i,
            "source": source,
            "case_no": case_no,
            "title": addr,
            "address": addr,
            "region": region,
            "item_type": item_type,
            "appraisal_price": appr,
            "min_bid_price": minb,
            "minimum_price": minb,
            "market_price": market,
            "expected_profit": profit,
            "expected_profit_rate": roi,
            "fail_count": rnd.randrange(0, 4),
            "bid_date": bid_date,
            "days_left": days_offset,
            "risk_level": risk,
            "risk_flags": flags,
            "recommendation_score": score,
            "recommendation_grade": grade,
            "confidence_score": confidence,
            "recommendation_reason": rec_reason,
            "warnings": warnings_list,
            "next_actions": next_actions,
            "checklist": checklist,
            "detail_summary": detail,
            "change_events": synthetic_events,
            "change_tags": change_tags,
            "is_new": is_new,
        })
    return items


def _fallback_payload() -> dict[str, Any]:
    rnd = random.Random(42)
    items = _fallback_items(rnd, n=100)
    rs = _risk_summary_from_items(items)

    recs = _recommendations_from_items(items, TOP_LIMIT)

    actions = []
    high_risk_items = [it for it in items if it["risk_level"] == "high"][:4]
    for it in high_risk_items:
        actions.append({
            "priority": "high",
            "title": "등기부등본 원문 확인",
            "detail": "고위험 키워드 발견 - 최신 등기부등본 발급 후 권리관계 확인",
            "due_date": None,
            "address": it["address"],
            "item_id": it["id"],
            "item_type": it["item_type"],
        })
    imminent = sorted(
        [it for it in items if (it.get("days_left") or 999) <= 7
         and (it.get("days_left") or -1) >= 0],
        key=lambda x: x.get("days_left") or 0,
    )[:3]
    for it in imminent:
        actions.append({
            "priority": "high",
            "title": "입찰기일 임박",
            "detail": f"입찰기일까지 {it['days_left']}일 남음",
            "due_date": it["bid_date"],
            "address": it["address"],
            "item_id": it["id"],
            "item_type": it["item_type"],
        })
    actions.append({
        "priority": "medium", "title": "현장조사",
        "detail": "관심 등록 물건 - 현장 점검 권장",
        "due_date": None,
        "address": items[0]["address"],
        "item_id": items[0]["id"],
        "item_type": items[0]["item_type"],
    })

    summary = {
        "total_items": len(items),
        "analyzed_items": len(items),
        "recommended_items": len(recs),
        "high_risk_items": rs["high"],
        "avg_confidence": round(sum(it["confidence_score"] for it in items) / len(items), 3),
        "auction_count": sum(1 for it in items if it["source"] == "auction"),
        "public_sale_count": sum(1 for it in items if it["source"] == "public_sale"),
        "urgent_items": sum(1 for it in items
                            if (it.get("days_left") or 999) <= 7 and (it.get("days_left") or -1) >= 0),
    }
    briefing = {
        "summary": (
            f"오늘 mock 데이터 {len(items)}건을 분석했습니다.\n"
            f"검토 후보(A·B·C) {sum(1 for r in recs if r['recommendation_grade'] in ('A','B','C'))}건, "
            f"고위험 키워드 보유 물건은 {rs['high']}건입니다.\n"
            f"입찰기일 임박(D-7 이내)은 {summary['urgent_items']}건이며, "
            "등기부등본·전입세대열람·현장조사가 권장됩니다."
        ),
    }
    confidence = {
        "price": round(sum(it["confidence_score"] for it in items if it["market_price"]) /
                       max(1, sum(1 for it in items if it["market_price"])), 3),
        "risk": 0.71,
        "document": 0.78,
        "address": 0.85,
        "overall": summary["avg_confidence"],
        "note": "Fallback 표본 — 운영 시 실 분석 결과로 교체",
    }
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "fallback",
        "summary": summary,
        "briefing": briefing,
        "recommendations": recs,
        "action_items": actions,
        "risk_summary": rs,
        "confidence_summary": confidence,
        "items": items,
        "agent_status": _agent_status(),
    }


def _payload_from_db(conn: sqlite3.Connection) -> dict[str, Any]:
    summary = _summarize_items(conn)
    picks = _picks_by_id(conn)
    items = _items_sample(conn, picks_by_id=picks)
    if not items:
        return _fallback_payload()

    recs = _recommendations_from_items(items, TOP_LIMIT)
    actions = _action_items_from_db(conn) or _fallback_payload()["action_items"]
    rs = _risk_summary_from_items(items)
    conf = _confidence_summary_from_db(conn)

    summary["recommended_items"] = len(recs)
    summary["urgent_items"] = sum(
        1 for it in items
        if (it.get("days_left") or 999) <= 7 and (it.get("days_left") or -1) >= 0
    )
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
