"""
scripts/validate_static_dashboard.py

GitHub Pages 정적 대시보드 산출물의 무결성 검사.
- docs/data/mock_dashboard.json
- docs/feed.xml
필수 키 / 타입 / 범위 / 추천-아이템 매칭 / RSS 구조를 종합 검증한다.

사용:
    python scripts/validate_static_dashboard.py            # 검증만
    python scripts/validate_static_dashboard.py --export   # 검증 전에 export 실행

CI 의 inline Python 을 대체. 실패 시 비-0 종료 코드.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "docs" / "data" / "mock_dashboard.json"
RSS_PATH = ROOT / "docs" / "feed.xml"


# ── 단정 헬퍼 ────────────────────────────────
class ValidationError(Exception):
    pass


def _assert(cond: bool, msg: str) -> None:
    if not cond:
        raise ValidationError(msg)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ── 검증 본체 ────────────────────────────────
TOP_LEVEL_KEYS = (
    "summary", "items", "recommendations", "agent_status",
    "risk_summary", "confidence_summary",
)

ITEM_REQUIRED = (
    "id", "source", "address", "item_type",
    "min_bid_price", "expected_profit", "expected_profit_rate",
    "recommendation_score", "recommendation_grade",
    "risk_level", "confidence_score", "case_no", "region",
    "checklist", "next_actions", "detail_summary",
)


def validate_json(payload: dict) -> dict:
    """JSON payload 검증. 검사 통과 시 통계 dict 반환."""
    _assert(isinstance(payload, dict), "JSON payload 가 object 가 아님")

    for k in TOP_LEVEL_KEYS:
        _assert(k in payload, f"top-level 키 누락: {k}")

    items = payload.get("items")
    _assert(isinstance(items, list) and len(items) >= 1,
            "items 가 비어 있음 (>= 1 필요)")

    # 각 item 필수 필드 + 타입 검사 (모든 item)
    for i, it in enumerate(items):
        _assert(isinstance(it, dict), f"items[{i}] 가 object 가 아님")
        for k in ITEM_REQUIRED:
            _assert(k in it, f"items[{i}] 필드 누락: {k}")

        # 숫자 범위
        _assert(_is_num(it.get("min_bid_price", 0)) and it["min_bid_price"] >= 0,
                f"items[{i}].min_bid_price 가 숫자/양수가 아님: {it.get('min_bid_price')!r}")
        _assert(_is_num(it.get("recommendation_score", 0)),
                f"items[{i}].recommendation_score 가 숫자가 아님")
        score = it["recommendation_score"]
        _assert(0 <= score <= 100,
                f"items[{i}].recommendation_score 범위 이탈: {score}")
        _assert(it.get("recommendation_grade") in ("A", "B", "C", "D", "X"),
                f"items[{i}].recommendation_grade 무효: {it.get('recommendation_grade')!r}")
        _assert(it.get("risk_level") in ("low", "medium", "high"),
                f"items[{i}].risk_level 무효: {it.get('risk_level')!r}")
        conf = it.get("confidence_score")
        _assert(_is_num(conf) and 0 <= conf <= 1,
                f"items[{i}].confidence_score 범위 이탈: {conf!r}")

        # 배열 필드는 list 타입
        _assert(isinstance(it["checklist"], list),
                f"items[{i}].checklist 가 리스트가 아님")
        _assert(isinstance(it["next_actions"], list),
                f"items[{i}].next_actions 가 리스트가 아님")

    # recommendations 의 item_id 가 items 안에 존재해야 (일관성)
    ids = {it["id"] for it in items if "id" in it}
    recs = payload.get("recommendations", [])
    _assert(isinstance(recs, list) and len(recs) >= 1,
            "recommendations 가 비어 있음 (>= 1 필요)")
    bad_recs = [r for r in recs
                if r.get("item_id") is not None and r["item_id"] not in ids]
    if bad_recs:
        bad_ids = [r.get("item_id") for r in bad_recs]
        raise ValidationError(
            f"recommendations 에 items 에 없는 item_id 가 있음: {bad_ids}"
        )

    summary = payload.get("summary", {})
    _assert(isinstance(summary, dict), "summary 가 object 가 아님")
    _assert(_is_num(summary.get("total_items", 0)),
            "summary.total_items 가 숫자가 아님")

    return {
        "items": len(items),
        "recommendations": len(recs),
        "summary_total": summary.get("total_items"),
        "first_item_keys": len(items[0].keys()),
    }


def validate_rss(path: Path) -> dict:
    if not path.exists():
        return {"present": False, "items": 0}
    tree = ET.parse(path)
    ch = tree.getroot().find("channel")
    _assert(ch is not None, "RSS 에 <channel> 이 없음")
    items = ch.findall("item")
    _assert(len(items) >= 1, "RSS 에 <item> 이 없음")
    for it in items[:3]:
        for tag in ("title", "link", "guid", "pubDate", "description"):
            _assert(it.find(tag) is not None,
                    f"RSS item 에 <{tag}> 누락")
    return {"present": True, "items": len(items)}


def main() -> int:
    # Windows 콘솔에서도 한글·특수기호가 깨지지 않게 UTF-8 강제
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    p = argparse.ArgumentParser()
    p.add_argument("--export", action="store_true",
                   help="검증 전에 export_static_dashboard.py 를 먼저 실행")
    args = p.parse_args()

    if args.export:
        sys.path.insert(0, str(ROOT))
        from scripts.export_static_dashboard import export
        export()

    try:
        _assert(JSON_PATH.exists(), f"JSON 파일이 없음: {JSON_PATH}")
        payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
        json_stats = validate_json(payload)
        rss_stats = validate_rss(RSS_PATH)
    except ValidationError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"[ERROR] 예기치 못한 오류: {e}", file=sys.stderr)
        return 2

    print(
        f"[OK] {JSON_PATH.relative_to(ROOT)} — "
        f"items={json_stats['items']} "
        f"recs={json_stats['recommendations']} "
        f"summary.total_items={json_stats['summary_total']} "
        f"keys/item={json_stats['first_item_keys']}"
    )
    if rss_stats["present"]:
        print(f"[OK] {RSS_PATH.relative_to(ROOT)} — items={rss_stats['items']}")
    else:
        print(f"[skip] {RSS_PATH.relative_to(ROOT)} 가 없음 (선택 산출물)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
