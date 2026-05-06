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
    """item_qa_agent용 mock 답변 (USE_AI=false 일 때)."""
    addr = context.get("address_full", "이 물건")
    risk_score = context.get("risk_score", 0)
    profit = context.get("profit_estimate", 0)
    if "왜 추천" in question or "추천된" in question:
        return (
            f"({addr}) 시세 대비 최저가가 낮고 예상 시세차익 약 {profit:,}만원으로 검토 후보로 분류되었습니다.\n"
            f"실거래가 데이터와 위험 키워드 분석 결과를 함께 확인해 주세요. (참고용)"
        )
    if "위험" in question:
        return (
            f"위험도는 현재 {risk_score}/10 으로 추정되며, 권리관계 원문 확인이 필요합니다.\n"
            f"법률 판단은 전문가 검토를 권장합니다."
        )
    if "얼마" in question or "입찰가" in question:
        return "보수/기준/공격 입찰가 계산 결과를 확인하세요. 실제 입찰가는 본인 판단입니다."
    if "현장" in question:
        return "점유자 현황, 외관 하자, 관리비 체납, 주변 시세를 현장에서 확인하세요."
    return (
        "현재 자료 기준으로는 단정해서 답하기 어렵습니다. 추가 확인이 필요합니다.\n"
        "- 매각물건명세서 원문 확인\n- 등기부등본 확인\n- 전문가 상담 권장"
    )


def mock_telegram_send(text: str) -> bool:
    log.info(f"[mock-telegram] {text[:80]}...")
    print("\n[mock 알림 미리보기]\n" + "-" * 40)
    print(text)
    print("-" * 40 + "\n")
    return True
