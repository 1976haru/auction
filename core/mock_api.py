"""
core/mock_api.py
Claude / Telegram 등 외부 API의 Mock 응답 생성기.
USE_MOCK_APIS=true 일 때 ai_client / alerts 등이 여기를 사용한다.
"""
from __future__ import annotations

import json
import random
import re
from typing import Any

from core.logger import log


def mock_parse_natural_language(user_input: str) -> dict:
    """자연어 -> 검색조건 JSON. 규칙 기반 매핑."""
    text = (user_input or "").strip()
    intent = {
        "intent": "find_top_profit_items",
        "source_types": ["auction", "public_sale"],
        "regions": [],
        "item_types": [],
        "sort_by": "expected_profit",
        "limit": 5,
        "filters": {
            "risk_level_max": "medium",
            "exclude_keywords": [],
            "include_high_risk": False,
            "only_active": True,
            "bid_within_days": None,
            "has_market_price": True,
        },
        "assumptions": [],
    }

    if not text:
        intent["assumptions"].append("입력이 비어 있어 기본 조건을 적용했습니다")
        return intent

    m = re.search(r"(\d+)\s*개", text)
    if m:
        intent["limit"] = int(m.group(1))

    if any(k in text for k in ["수익률", "ROI", "roi"]):
        intent["sort_by"] = "expected_roi"
    elif any(k in text for k in ["시세차익", "차익", "수익"]):
        intent["sort_by"] = "expected_profit"
    elif any(k in text for k in ["위험 낮", "안전", "리스크 낮"]):
        intent["sort_by"] = "risk"

    region_table = ["서울", "경기", "인천", "부산", "대전", "광주", "대구", "강남", "마포", "성동", "송파", "분당"]
    for r in region_table:
        if r in text:
            intent["regions"].append(r)

    type_table = ["아파트", "오피스텔", "빌라", "상가", "토지", "단독주택"]
    for t in type_table:
        if t in text:
            intent["item_types"].append(t)

    if "공매" in text and "경매" not in text:
        intent["source_types"] = ["public_sale"]
    elif "경매" in text and "공매" not in text:
        intent["source_types"] = ["auction"]

    if "유치권" in text and ("제외" in text or "빼" in text):
        intent["filters"]["exclude_keywords"].append("유치권")
    if "고위험" in text:
        intent["filters"]["include_high_risk"] = True
        intent["filters"]["risk_level_max"] = "high"
    if "위험 낮" in text or "안전" in text:
        intent["filters"]["risk_level_max"] = "low"

    m = re.search(r"(\d+)\s*일\s*이내", text)
    if m:
        intent["filters"]["bid_within_days"] = int(m.group(1))
    if "이번 주" in text or "이번주" in text:
        intent["filters"]["bid_within_days"] = 7

    if "차량" in text and "말고" in text:
        intent["assumptions"].append("차량 공매 제외, 부동산만 포함")

    # 애매 표현
    if any(k in text for k in ["요즘", "괜찮은", "추천", "뭐가 좋"]):
        intent["intent"] = "soft_recommend"
        intent["assumptions"].append("애매한 요청 -> 최근 신규 + 위험 낮음 + 시세차익 큼 기본 적용")
    if "오늘 뭐" in text or "오늘 할 일" in text:
        intent["intent"] = "daily_action_focus"
        intent["assumptions"].append("daily briefing + action items 우선")
    if "내가 좋아할" in text:
        intent["intent"] = "personalized_recommend"
        intent["assumptions"].append("사용자 선호 기반 추천")

    if not intent["regions"]:
        intent["assumptions"].append("구체적 지역이 없어 전체 관심지역 기준으로 검색")
    if not intent["filters"]["include_high_risk"]:
        intent["assumptions"].append("고위험 물건은 기본 제외")

    return intent


def mock_analyze_risk(text: str, item_info: dict) -> dict:
    """문서 텍스트 기반 mock 위험분석."""
    text = text or ""
    risk_items = []
    score = 1
    severity_map = {
        "유치권": 9, "법정지상권": 8, "선순위임차인": 8, "대항력": 8,
        "지분매각": 7, "공유지분": 7, "농지취득자격증명": 7,
        "분묘기지권": 7, "전입세대": 5, "관리비 체납": 4,
        "위반건축물": 5, "임차인": 5, "점유자 미상": 5,
        "명도": 4, "공사대금": 6,
    }
    for kw, sev in severity_map.items():
        if kw in text:
            risk_items.append({
                "type": kw, "description": f"{kw} 관련 키워드 발견 - 추가 확인 필요",
                "severity": sev,
            })
            score = max(score, sev)
    return {
        "risk_score": score,
        "risk_items": risk_items,
        "summary": "(mock) 키워드 기반 1차 위험 평가 결과입니다. 원문 확인 필요.",
        "check_required": [
            "등기부등본 원문 확인 필요",
            "매각물건명세서 원문 확인 필요",
            "현황조사서 원문 확인 필요",
        ],
    }


def mock_summarize_document(text: str, doc_type: str) -> str:
    head = (text or "")[:80].replace("\n", " ")
    return (
        f"(mock 요약 / {doc_type}) {head}...\n"
        f"- 핵심 내용은 원문 확인 필요\n"
        f"- 권리관계 및 점유관계 확인이 필요할 수 있습니다"
    )


def mock_item_qa(question: str, context: dict) -> str:
    """item_qa_agent용 mock 답변. 풍부한 컨텍스트(트렌드/입찰가/peer/백테스트)를
    활용해 의미 있는 응답 생성."""
    addr = context.get("address_full", "이 물건")
    risk_score = context.get("risk_score", 0)
    profit = context.get("profit_estimate", 0) or 0
    roi = context.get("roi_estimate", 0) or 0
    grade = (context.get("recommendation") or {}).get("grade")
    score = (context.get("recommendation") or {}).get("score")
    trend = context.get("trend") or {}
    peers = context.get("peer_stats") or {}
    bid = context.get("bid_recommendation") or {}
    backtest = context.get("backtest") or {}
    bid_days = context.get("bid_days_left")

    def _trend_line() -> str:
        if not trend or trend.get("months", 0) < 2:
            return "시세 트렌드: 표본 부족"
        return (
            f"시세 트렌드: 최근 {trend['months']}개월 {trend['direction']} "
            f"({trend['trend_pct']:+.1f}%, "
            f"{trend.get('first_avg', 0):,} → {trend.get('last_avg', 0):,}만원)"
        )

    def _peer_line() -> str:
        if not peers or peers.get("count", 0) == 0:
            return "동일 지역+유형 비교군: 표본 없음"
        return (
            f"동일 지역+유형 {peers['count']}건 평균 - "
            f"감정가 {peers['avg_appraisal']:,} / 최저가 {peers['avg_min_bid']:,} / "
            f"시세 {peers['avg_market']:,}만원"
        )

    def _grade_line() -> str:
        if not grade:
            return ""
        s = f"추천 등급 {grade}"
        if score is not None:
            s += f" (점수 {score:.1f})"
        if backtest.get("count"):
            s += (
                f" - {backtest['grade']}등급 백테스트 통계: "
                f"{backtest['count']}건 평균 {int(backtest['mean_profit'] or 0):+,}만원, "
                f"승률 {backtest['win_rate']}%"
            )
        return s

    if "왜 추천" in question or "추천된" in question:
        lines = [
            f"({addr}) 분석 근거:",
            f"- 예상 시세차익 {profit:+,}만원 / ROI {roi:.1f}%",
            "- " + _trend_line(),
            "- " + _peer_line(),
        ]
        gl = _grade_line()
        if gl:
            lines.append(f"- {gl}")
        lines.append("\n실거래가 데이터/위험 키워드/신뢰도를 함께 확인해 주세요. (참고용)")
        return "\n".join(lines)

    if "위험" in question:
        risk_lines = [
            f"위험도: severity {risk_score}/10",
            "- " + _trend_line(),
        ]
        if context.get("price_analysis", {}).get("appraisal_inflated"):
            risk_lines.append("- 감정가가 시세 대비 비정상적으로 높음 (거품 의심)")
        flags = context.get("risk_flags_summary", [])
        if flags:
            high = [f for f in flags if f.get("level") == "high"]
            if high:
                risk_lines.append(
                    f"- 고위험 키워드: {', '.join(f['type'] for f in high)}"
                )
        risk_lines.append("\n법률 판단은 전문가 검토 권장 / 매각물건명세서 원문 확인 필수.")
        return "\n".join(risk_lines)

    if "얼마" in question or "입찰가" in question:
        if bid:
            lines = [
                "입찰가 추천 (시세 기준):",
                f"- 보수: {bid['conservative']['price']:>7,}만원 (예상차익 {bid['conservative'].get('profit', 0):+,}만원)",
                f"- 기준: {bid['standard']['price']:>7,}만원 (예상차익 {bid['standard'].get('profit', 0):+,}만원)",
                f"- 공격: {bid['aggressive']['price']:>7,}만원 (예상차익 {bid['aggressive'].get('profit', 0):+,}만원)",
                f"\n실제 입찰가는 본인 판단. 시세 신뢰도와 위험 키워드를 함께 검토하세요.",
            ]
            return "\n".join(lines)
        return "보수/기준/공격 입찰가는 입찰가 시뮬 도구로 확인하세요."

    if "현장" in question:
        base = [
            "현장조사 권장 항목:",
            "- 점유자 현황 (거주 여부, 세입자 인원)",
            "- 외관 하자 (균열, 누수, 도배·장판)",
            "- 관리비 체납 여부 (관리사무소 확인)",
            "- 주변 인프라 (학교, 마트, 교통)",
            "- 등기부등본 최신본 확인 (현장 방문 직전)",
        ]
        if peers and peers.get("count", 0) > 0:
            base.append("- " + _peer_line())
        return "\n".join(base)

    if "보류" in question or "제외" in question:
        if grade in ("D", "X"):
            return (
                f"이 매물은 등급 {grade} 로 분류되어 추천에서 보류/제외 권장됩니다. "
                f"점수 {score:.1f} / "
                f"감정가-시세 비율 등 핵심 지표 재검토 필요."
            )
        return (
            f"등급 {grade or '?'} 으로 검토 가능 후보입니다. "
            f"단정하지 않고 추가 확인 후 결정 권장."
        )

    if bid_days is not None and ("기일" in question or "언제" in question):
        if bid_days < 0:
            return f"입찰기일이 지났습니다 (D+{abs(bid_days)})."
        return f"입찰기일까지 D-{bid_days} 남았습니다 ({context.get('bid_date', '미정')})."

    # 기본 fallback
    parts = [
        "현재 자료 기준 답변:",
        f"- {_grade_line() or '등급 정보 없음'}",
        f"- 예상차익 {profit:+,}만원 / ROI {roi:.1f}%",
        f"- {_trend_line()}",
        f"- {_peer_line()}",
        "\n구체적인 항목(왜 추천 / 위험 / 입찰가 / 현장 / 보류) 키워드로 질문하시면 더 정확한 답변이 가능합니다.",
    ]
    return "\n".join(parts)


def mock_telegram_send(text: str) -> bool:
    log.info(f"[mock-telegram] {text[:80]}...")
    print("\n[mock 알림 미리보기]\n" + "-" * 40)
    print(text)
    print("-" * 40 + "\n")
    return True
