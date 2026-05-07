"""
agents/reasoning_report_agent.py
추천 결과를 사람이 읽기 쉬운 추천 근거 텍스트로 변환한다.
"""
from __future__ import annotations

from typing import Any

from agents.bidding_agent import get_bid_recommendation
from agents.legal_risk_agent import analyze_item_risk
from agents.risk_checklist_agent import build_checklist
from core.utils import days_until, risk_emoji


def build_reasoning(result_entry: dict) -> dict:
    item = result_entry["item"]
    profit = result_entry.get("profit_estimate", 0)
    roi = result_entry.get("roi_estimate", 0)
    risk_level = result_entry.get("risk_level", "unknown")
    confidence = result_entry.get("confidence", {})
    breakdown = result_entry.get("score_breakdown", {})

    lines: list[str] = []

    # 한줄 판단
    grade = result_entry.get("grade", "C")
    headline = {
        "A": "적극 검토 후보",
        "B": "검토 후보",
        "C": "보류 후보",
        "D": "낮은 우선순위",
        "X": "고위험/데이터 부족 - 제외 권장",
    }.get(grade, "검토 후보")
    lines.append(f"[{grade}] {headline}: {item.get('address_full', '미상')}")

    # 추천 이유
    reasons = []
    if profit > 0:
        reasons.append(f"예상 시세차익 {profit:,}만원 (ROI {roi:.1f}%)")
    market = result_entry.get("market_price", 0)
    minbid = item.get("min_bid_price", 0)
    if market and minbid:
        gap = market - minbid
        reasons.append(f"최저가 대비 시세 차이 약 {gap:,}만원")
    if risk_level == "low":
        reasons.append("위험 키워드 등급: low (현재 자료 기준)")
    bd = days_until(item.get("bid_date"))
    if bd is not None and 0 <= bd <= 14:
        reasons.append(f"입찰기일 {bd}일 이내")
    if breakdown.get("preference_reasons"):
        reasons.extend(breakdown["preference_reasons"])

    # 주의 이유
    warnings = []
    if risk_level == "high":
        warnings.append("권리 위험 등급 high - 원문 확인 필요")
    if confidence.get("price_confidence", 1) < 0.5:
        warnings.append("실거래가 데이터 부족 - 시세 추정 신뢰도 낮음")
    if confidence.get("document_confidence", 1) < 0.5:
        warnings.append("핵심 문서 일부 미공개 - 추가 확인 필요")
    # 감정가/시세 거품 경고
    from modules.valuation.price_matcher import get_price_analysis
    pa = get_price_analysis(item.get("id")) if item.get("id") else None
    if pa and pa.get("appraisal_inflated"):
        from core.utils import loads as _loads
        for w in _loads(pa.get("inflation_warnings_json"), []):
            warnings.append(f"가격 이상치: {w}")
    # 추천 점수 분해의 critical_reasons도 노출
    for cr in (breakdown.get("critical_reasons") or []):
        warnings.append(f"제외 사유: {cr}")

    # 입찰가 범위
    bid_rec = get_bid_recommendation(item["id"]) if item.get("id") else None

    # 위험 체크리스트 (top 5)
    checklist_rows = build_checklist(item["id"]) if item.get("id") else []
    checklist_top = [c["item_text"] for c in checklist_rows[:8]]

    # 현장조사 체크리스트
    risk_rep = analyze_item_risk(item["id"]) if item.get("id") else {}

    return {
        "headline": lines[0],
        "reasons": reasons,
        "warnings": warnings,
        "bid_recommendation": bid_rec,
        "additional_checks": checklist_top,
        "field_checklist": risk_rep.get("field_checklist", []),
        "risk_emoji": risk_emoji(risk_level),
        "confidence": confidence,
        "data_warnings": confidence.get("reasons_json") or confidence.get("reasons") or [],
        "disclaimer": "투자/법률 단정 표현이 아닌 위험요소 체크리스트입니다. 최종 판단은 사용자가 별도 검토하세요.",
    }
