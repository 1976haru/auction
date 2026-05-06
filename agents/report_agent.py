"""
agents/report_agent.py
물건별 종합 리포트 생성기 - Markdown / dict 형태로 반환.
"""
from __future__ import annotations

from typing import Any

from agents.reasoning_report_agent import build_reasoning


def build_item_report(result_entry: dict) -> dict:
    reasoning = build_reasoning(result_entry)
    return {
        "summary": reasoning,
        "item": result_entry["item"],
        "profit_estimate": result_entry.get("profit_estimate"),
        "roi_estimate": result_entry.get("roi_estimate"),
        "risk_level": result_entry.get("risk_level"),
        "score": result_entry.get("score"),
        "grade": result_entry.get("grade"),
    }


def render_markdown(report: dict) -> str:
    item = report["item"]
    s = report["summary"]
    lines = [
        f"# {s['headline']}",
        "",
        f"- 종류: {item.get('item_type', '미상')} | 면적 {item.get('area_m2', '-')}㎡",
        f"- 감정가: {item.get('appraisal_price', 0):,}만원",
        f"- 최저가: {item.get('min_bid_price', 0):,}만원 | 유찰: {item.get('fail_count', 0)}회",
        f"- 매각기일: {item.get('bid_date', '미정')}",
        f"- 예상 시세차익: {report.get('profit_estimate', 0):,}만원 / ROI {report.get('roi_estimate', 0):.1f}%",
        f"- 위험 등급: {report.get('risk_level', 'unknown')}",
        f"- 종합 점수: {report.get('score', 0):.1f} / 등급 {report.get('grade')}",
        "",
        "## 추천 이유",
    ]
    for r in s["reasons"]:
        lines.append(f"- {r}")
    if s["warnings"]:
        lines.append("\n## 주의 사항")
        for w in s["warnings"]:
            lines.append(f"- {w}")
    if s.get("additional_checks"):
        lines.append("\n## 추가 확인사항")
        for c in s["additional_checks"]:
            lines.append(f"- {c}")
    if s.get("field_checklist"):
        lines.append("\n## 현장조사 체크리스트")
        for c in s["field_checklist"][:8]:
            lines.append(f"- {c}")
    if s.get("bid_recommendation") and "bids" in (s["bid_recommendation"] or {}):
        bids = s["bid_recommendation"]["bids"]
        lines.append("\n## 추천 입찰가 범위")
        for k in ("conservative", "standard", "aggressive"):
            b = bids[k]
            lines.append(f"- {b['label']}: {b['price']:,}만원 (ROI {b['roi']:.1f}%)")

    lines.append("\n---")
    lines.append(s["disclaimer"])
    return "\n".join(lines)
