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
RSS_PATH = ROOT / "docs" / "feed.xml"
RSS_BASE_URL = "https://1976haru.github.io/auction/"
RSS_LIMIT = 50
SAMPLE_LIMIT = 200
TOP_LIMIT = 5


# ── 유틸 ──────────────────────────────────────────────────────────
_REGION_RE = re.compile(r"^(?P<si>\S+?(?:특별시|광역시|특별자치시|도|특별자치도|시|군|구))")


def _extract_region(address: str | None) -> str:
    if not address:
        return "기타"
    s = address.split()
    return s[0] if s else "기타"


# ── 초보자 모드 용어 설명 ───────────────────────────────────────
GLOSSARY_DICT = {
    "유치권": "건설업자나 자재 공급자가 미결제 대금을 담보하기 위해 물건에 설정한 권리. 경매 후 새 소유자가 미결제 금액을 인수해야 할 수 있음.",
    "법정지상권": "토지와 건물이 따로 소유자를 가질 때 건물 소유자가 토지를 계속 사용할 수 있는 권리. 건물 경매 시에도 토지 임차료를 계속 내야 함.",
    "대항력": "임차인이 등기부에 기록되지 않아도 새 소유자에게 주장할 수 있는 권리. 임차인이 계속 거주하고 있으면 임차보증금을 인수해야 함.",
    "선순위임차인": "현재 소유자보다 먼저 임차 계약한 임차인. 경매 후 새 소유자도 그들의 보증금을 우선 변제해야 함.",
    "지분매각": "물건 전체가 아닌 일부만 매각되는 경우. 복잡한 권리관계와 추후 분쟁 가능성이 높음.",
    "농지취득자격증명": "농지를 구매하려면 농지소유자 자격이 필요하며 이를 증명하는 서류. 없으면 경매 후에도 농지로 사용할 수 없음.",
    "분묘기지권": "묘지 소유자가 다른 사람의 토지에 무덤을 쓸 수 있는 권리. 토지 소유자가 바뀌어도 그 권리는 계속 유지됨.",
    "명도": "임차인이나 불법 점유자가 물건을 비우도록 강제하는 절차. 비용과 시간이 소요되며 법원 집행이 필요할 수 있음.",
    "말소기준권리": "이미 해결되었거나 소멸했어야 할 권리가 등기부에 남아있는 경우. 새 소유자가 소송으로 말소해야 함.",
    "매각물건명세서": "경매 물건의 상태, 권리, 기타 정보를 정리한 법원 공식 문서. 가장 신뢰할 수 있는 정보 출처.",
    "현황조사서": "법원이 직접 현장 조사해서 작성한 보고서. 실제 점유 상태, 위반건축물, 하자 등을 기록.",
    "감정평가서": "부동산 감정사가 시장 가치를 평가한 문서. 경매 최저가 결정의 근거가 되는 가격.",
}


def _get_easy_explanation(keyword: str) -> str:
    """위험 키워드에 대한 초보자용 쉬운 설명."""
    return GLOSSARY_DICT.get(keyword, f"{keyword}에 대해 전문가 상담이 필요합니다.")


def _is_beginner_friendly(it: dict) -> bool:
    """초보자 모드에서 표시할 물건인지 판단.
    - 고위험 물건 제외
    - 특정 위험 키워드 보유 물건 제외  
    - 신뢰도 낮은 물건 제외
    - A/B등급 주거용 위주
    """
    # 고위험 물건 제외
    if it.get("risk_level") == "high":
        return False
    
    # 신뢰도 낮은 물건 제외 (0.6 이상만)
    if (it.get("confidence_score") or 0) < 0.6:
        return False
    
    # 주거용이 아니면 제외
    item_type = it.get("item_type", "")
    if item_type not in ("아파트", "오피스텔", "주택", "빌라"):
        return False
    
    # A/B 등급 우선
    grade = it.get("recommendation_grade", "C")
    if grade not in ("A", "B"):
        return False
    
    # 복잡한 권리문제 키워드 제외
    forbidden_keywords = {
        "유치권", "법정지상권", "지분매각", 
        "농지취득자격증명", "분묘기지권",
        "선순위임차인"
    }
    for flag in it.get("risk_flags", []):
        if flag.get("keyword") in forbidden_keywords:
            return False
    
    return True


def _beginner_reason(it: dict) -> str:
    """초보자용 추천 이유."""
    grade = it.get("recommendation_grade", "C")
    profit = it.get("expected_profit", 0)
    risk = it.get("risk_level", "medium")
    
    reasons = []
    if grade == "A":
        reasons.append("데이터 기준 검토 가치 높음")
    elif grade == "B":
        reasons.append("조건 충족 양호")
    
    if profit > 50000:
        reasons.append(f"차익 {profit:,}만원 이상")
    elif profit > 0:
        reasons.append(f"차익 {profit:,}만원 기대")
    
    if risk == "low":
        reasons.append("위험 낮음")
    
    return " · ".join(reasons) if reasons else "추가 검토 필요"


def _simple_risk_summary(it: dict) -> str:
    """초보자용 간단한 위험 요약."""
    risk = it.get("risk_level", "medium")
    flags = it.get("risk_flags", [])
    
    if risk == "low":
        if flags:
            kw = flags[0].get("keyword", "")
            return f"낮음 · 단, {kw} 확인 필요"
        return "낮음 · 상대적으로 안전"
    elif risk == "medium":
        if flags:
            kw = flags[0].get("keyword", "")
            return f"보통 · 주의할 점: {kw}"
        return "보통 · 기본 확인 필수"
    else:
        if flags:
            kw = flags[0].get("keyword", "")
            return f"높음 · {kw} 때문에 신중히 검토"
        return "높음 · 전문가 상담 권장"


def _simple_profit_summary(it: dict) -> str:
    """초보자용 간단한 수익 요약."""
    profit = it.get("expected_profit", 0)
    roi = it.get("expected_profit_rate", 0)
    bid = it.get("min_bid_price", 0)
    
    if not bid:
        return "수익 추정 불가"
    
    if profit >= 50000:
        return f"{profit:,}만원 차익 기대 (ROI {roi:.0f}%)"
    elif profit > 0:
        return f"{profit:,}만원 소폭 수익 (ROI {roi:.0f}%)"
    else:
        return f"수익 예상 어려움 (손실 위험)"


def _simple_next_action(it: dict, days_left: int | None) -> str:
    """초보자용 '오늘 할 일'."""
    risk = it.get("risk_level", "medium")
    
    actions = []
    
    # 입찰 임박
    if days_left is not None and 0 <= days_left <= 3:
        actions.append(f"입찰 D-{days_left} · 빠른 결정 필요")
    elif days_left is not None and 0 <= days_left <= 7:
        actions.append(f"D-{days_left} 이내 결정")
    else:
        actions.append("시간 있으니 천천히 검토")
    
    # 현장조사
    if it.get("item_type") in ("아파트", "주택"):
        actions.append("현장 방문 필수")
    
    # 위험도별 조치
    if risk == "high":
        actions.append("전문가 상담 받기")
    elif risk == "medium":
        actions.append("등기부등본 확인")
    
    return " → ".join(actions)


# ── 통합검색 대상 필드 보강 ──────────────────────────────────────
# 시·도 → 관할 법원(데모용 매핑). 실제 관할과 다를 수 있는 mock 값.
COURT_BY_SIDO = {
    "서울특별시": "서울중앙지방법원",
    "경기도": "수원지방법원",
    "인천광역시": "인천지방법원",
    "부산광역시": "부산지방법원",
    "대구광역시": "대구지방법원",
    "대전광역시": "대전지방법원",
    "광주광역시": "광주지방법원",
    "울산광역시": "울산지방법원",
    "세종특별자치시": "대전지방법원",
    "강원특별자치도": "춘천지방법원",
    "충청북도": "청주지방법원",
    "충청남도": "대전지방법원",
    "전북특별자치도": "전주지방법원",
    "전라남도": "광주지방법원",
    "경상북도": "대구지방법원",
    "경상남도": "창원지방법원",
    "제주특별자치도": "제주지방법원",
}

# ── 연번 15: 법원별 데이터 ────────────────────────────────────────
# 법원 → 권역(court_region 짧은 표기) · 권역그룹(court_group)
COURT_META = {
    "서울중앙지방법원": {"region": "서울", "group": "서울권"},
    "서울동부지방법원": {"region": "서울", "group": "서울권"},
    "서울남부지방법원": {"region": "서울", "group": "서울권"},
    "서울북부지방법원": {"region": "서울", "group": "서울권"},
    "서울서부지방법원": {"region": "서울", "group": "서울권"},
    "의정부지방법원": {"region": "경기", "group": "수도권"},
    "인천지방법원": {"region": "인천", "group": "수도권"},
    "수원지방법원": {"region": "경기", "group": "수도권"},
    "춘천지방법원": {"region": "강원", "group": "강원권"},
    "대전지방법원": {"region": "대전", "group": "충청권"},
    "청주지방법원": {"region": "충북", "group": "충청권"},
    "대구지방법원": {"region": "대구", "group": "영남권"},
    "부산지방법원": {"region": "부산", "group": "영남권"},
    "울산지방법원": {"region": "울산", "group": "영남권"},
    "창원지방법원": {"region": "경남", "group": "영남권"},
    "광주지방법원": {"region": "광주", "group": "호남권"},
    "전주지방법원": {"region": "전북", "group": "호남권"},
    "제주지방법원": {"region": "제주", "group": "제주권"},
}
# 본원 → 지원(데모용) — 일부 물건을 지원으로 표시
COURT_BRANCHES = {
    "수원지방법원": ["성남지원", "안산지원", "안양지원", "평택지원", "여주지원"],
    "의정부지방법원": ["고양지원"],
    "대전지방법원": ["천안지원", "서산지원"],
    "광주지방법원": ["순천지원", "목포지원"],
    "대구지방법원": ["포항지원"],
    "창원지방법원": ["마산지원", "진주지원"],
}
# 시·도 → 관할 가능한 본원 후보(수도권은 여러 법원으로 분산)
SIDO_TO_COURTS = {
    "서울특별시": ["서울중앙지방법원", "서울동부지방법원", "서울남부지방법원",
                "서울북부지방법원", "서울서부지방법원"],
    "경기도": ["수원지방법원", "의정부지방법원"],
    "인천광역시": ["인천지방법원"],
    "부산광역시": ["부산지방법원"],
    "대구광역시": ["대구지방법원"],
    "대전광역시": ["대전지방법원"],
    "광주광역시": ["광주지방법원"],
    "울산광역시": ["울산지방법원"],
    "세종특별자치시": ["대전지방법원"],
    "강원특별자치도": ["춘천지방법원"],
    "충청북도": ["청주지방법원"],
    "충청남도": ["대전지방법원"],
    "전북특별자치도": ["전주지방법원"],
    "전라남도": ["광주지방법원"],
    "경상북도": ["대구지방법원"],
    "경상남도": ["창원지방법원"],
    "제주특별자치도": ["제주지방법원"],
}
# ── 연번 16: 공매 기관 데이터 ─────────────────────────────────────
# 기관 카탈로그: name·type(대분류)·region·group(공공/지자체/금융/기타)·sale_type(공매유형)
# 캠코 비중을 높이고(가중치 반영용 중복) 지자체·공공·금융·기타를 고루 포함한다.
PUBLIC_AGENCIES = [
    {"name": "한국자산관리공사", "type": "한국자산관리공사", "region": "전국",
     "group": "공공", "sale_type": "압류재산"},
    {"name": "한국자산관리공사", "type": "한국자산관리공사", "region": "전국",
     "group": "공공", "sale_type": "압류재산"},
    {"name": "한국자산관리공사", "type": "한국자산관리공사", "region": "전국",
     "group": "공공", "sale_type": "국유재산"},
    {"name": "한국자산관리공사", "type": "한국자산관리공사", "region": "전국",
     "group": "공공", "sale_type": "수탁재산"},
    {"name": "서울특별시", "type": "지자체", "region": "서울",
     "group": "지자체", "sale_type": "공유재산"},
    {"name": "경기도", "type": "지자체", "region": "경기",
     "group": "지자체", "sale_type": "공유재산"},
    {"name": "인천광역시", "type": "지자체", "region": "인천",
     "group": "지자체", "sale_type": "공유재산"},
    {"name": "부산광역시", "type": "지자체", "region": "부산",
     "group": "지자체", "sale_type": "공유재산"},
    {"name": "대전광역시", "type": "지자체", "region": "대전",
     "group": "지자체", "sale_type": "공유재산"},
    {"name": "한국토지주택공사", "type": "공공기관", "region": "전국",
     "group": "공공", "sale_type": "국유재산"},
    {"name": "한국도로공사", "type": "공공기관", "region": "전국",
     "group": "공공", "sale_type": "국유재산"},
    {"name": "한국전력공사", "type": "공공기관", "region": "전국",
     "group": "공공", "sale_type": "국유재산"},
    {"name": "국민건강보험공단", "type": "공공기관", "region": "전국",
     "group": "공공", "sale_type": "압류재산"},
    {"name": "예금보험공사", "type": "금융기관", "region": "전국",
     "group": "금융", "sale_type": "금융기관 매각"},
    {"name": "금융기관", "type": "금융기관", "region": "전국",
     "group": "금융", "sale_type": "금융기관 매각"},
    {"name": "기타기관", "type": "기타기관", "region": "전국",
     "group": "기타", "sale_type": "기타 공매"},
]
# 온비드 카테고리(물건종류 → 카테고리)
ONBID_CATEGORY_BY_TYPE = {
    "차량": "차량",
    "선박": "차량",
    "기계": "기계/동산",
    "회원권": "회원권",
}
COURT_REGION_GROUP = {
    "서울": "서울권", "경기": "수도권", "인천": "수도권", "강원": "강원권",
    "대전": "충청권", "충북": "충청권", "충남": "충청권", "세종": "충청권",
    "대구": "영남권", "부산": "영남권", "울산": "영남권", "경남": "영남권", "경북": "영남권",
    "광주": "호남권", "전북": "호남권", "전남": "호남권", "제주": "제주권",
}


def _assign_courts(items: list[dict]) -> None:
    """연번 15: 경매 item 에 법원 필드를, 공매 item 에 기관 필드를 결정적으로 부여.

    시·도(관할) 기준으로 법원을 고르되 수도권(서울 5개 법원·경기 2개 법원)은
    골고루 분산하고, 일부는 지원(court_type='지원')으로 표시한다.
    """
    for idx, it in enumerate(items):
        seed = int(it.get("id") or idx)
        if it.get("source") == "auction":
            sido = it.get("sido") or _extract_region(it.get("address"))
            cands = SIDO_TO_COURTS.get(sido) or ["지방법원"]
            court = cands[seed % len(cands)]
            meta = COURT_META.get(court, {"region": "기타", "group": "기타"})
            court_type, branch = "본원", ""
            branches = COURT_BRANCHES.get(court)
            if branches and seed % 4 == 0:
                branch = branches[(seed // 4) % len(branches)]
                court_type = "지원"
            it["court_name"] = court
            it["court_region"] = meta["region"]
            it["court_group"] = meta["group"]
            it["court_type"] = court_type
            it["court_branch"] = branch
            it["sale_type"] = "법원경매"
            it["source_site"] = "court"
            it["agency_name"] = ""
            it["agency_type"] = ""
            it["agency_region"] = ""
            it["agency_group"] = ""
            it["public_sale_type"] = ""
            it["onbid_category"] = ""
        else:
            ag = PUBLIC_AGENCIES[seed % len(PUBLIC_AGENCIES)]
            it["agency_name"] = ag["name"]
            it["agency_type"] = ag["type"]
            it["agency_region"] = ag["region"]
            it["agency_group"] = ag["group"]
            it["court_name"] = ""
            it["court_region"] = ""
            it["court_group"] = ""
            it["court_type"] = ""
            it["court_branch"] = ""
            it["sale_type"] = "공매"
            it["source_site"] = "onbid"
            it["public_sale_type"] = ag["sale_type"]
            it["onbid_category"] = ONBID_CATEGORY_BY_TYPE.get(it.get("item_type"), "부동산")

ITEM_GROUP_BY_TYPE = {
    "아파트": "주거용 건물",
    "오피스텔": "주거용 건물",
    "빌라": "주거용 건물",
    "주택": "주거용 건물",
    "다세대": "주거용 건물",
    "연립": "주거용 건물",
    "단독주택": "주거용 건물",
    "다가구주택": "주거용 건물",
    "상가": "상업용 건물",
    "사무실": "상업용 건물",
    "공장": "산업용 건물",
    "창고": "산업용 건물",
    "토지": "토지",
    "임야": "토지",
    "전답": "토지",
    "차량": "차량",
    "기계": "기계·중기",
}

# 데모 데이터 다양성 확보: enumerate 인덱스 기준으로 일부 물건의 종류를
# 빠른 메뉴(연립/다세대·단독/다가구·공장/창고·차량)가 동작하도록 주입.
DEMO_TYPE_INJECT = {
    0: "다세대", 1: "다세대", 2: "단독주택", 3: "다가구주택",
    4: "공장", 5: "창고", 6: "차량", 7: "차량",
    8: "단독주택", 9: "연립",
}


def _addr_parts(address: str | None, sido: str | None, sigungu: str | None) -> tuple[str, str, str]:
    """주소를 시/도·시군구·동(읍·면)으로 분해. DB 값이 없으면 주소 문자열에서 추출."""
    s = (address or "").strip()
    toks = s.split()
    _sido = sido or (toks[0] if toks else "")
    _sigungu = sigungu or (toks[1] if len(toks) > 1 else "")
    _dong = ""
    for t in toks[2:]:
        if t.endswith(("동", "읍", "면", "가", "리")):
            _dong = t
            break
    if not _dong and len(toks) > 2:
        _dong = toks[2]
    return _sido, _sigungu, _dong


def _search_fields(
    item_id: int,
    source: str,
    region: str,
    item_type: str,
    address: str | None,
    sido: str | None,
    sigungu: str | None,
    case_no: str | None,
    flags: list[dict],
    rec_reason: str | None,
    risk_level: str,
) -> dict:
    """통합검색에서 매칭될 메타 필드 묶음. DB 값이 없으면 결정적(mock) 기본값 생성."""
    seed = int(item_id or 0)
    _sido, _sigungu, _dong = _addr_parts(address, sido, sigungu)
    is_auction = source == "auction"
    court_name = COURT_BY_SIDO.get(_sido, "지방법원") if is_auction else ""
    agency_name = "" if is_auction else "한국자산관리공사(캠코)"
    if is_auction:
        cno = case_no or f"2025타경{10000 + (seed * 7) % 89999}"
        mgmt_no = ""
        source_site = "법원경매(대법원 법원경매정보)"
        sale_type = "기일입찰"
    else:
        cno = case_no or ""
        mgmt_no = f"2025-{(seed * 13) % 10000:04d}-{(seed % 9) + 1:03d}"
        source_site = "온비드(한국자산관리공사)"
        sale_type = "공매(매각)"
    item_no = str((seed % 5) + 1)
    risk_keywords = [f.get("keyword") for f in flags if f.get("keyword")]
    descs = [f.get("description") for f in flags if f.get("description")]
    caution_reason = ("; ".join(descs))[:240] if descs else f"{risk_level} 위험 — 기본 권리분석 확인 권장"
    # 일부 물건은 문서 미공개 / 현장조사 필요로 표시 (결정적 mock)
    documents_missing = (seed % 7 == 0)
    document_status = (
        "문서 미공개 — 매각물건명세서·현황조사서 미열람 (mock)"
        if documents_missing
        else "매각물건명세서·현황조사서·감정평가서 열람 가능 (mock)"
    )
    # 현장조사가 특히 필요한 물건: 문서 미공개거나 점유·위반건축물·전입세대 이슈가 있는 경우
    # (임차인 일반은 별도 '임차인 주의' 칩에서 다루므로 여기서는 제외)
    field_survey_needed = (
        documents_missing
        or any(kw_part in (f.get("keyword") or "")
               for f in flags
               for kw_part in ("점유", "위반건축물", "전입세대"))
    )
    return {
        "case_no": cno,
        "item_no": item_no,
        "mgmt_no": mgmt_no,
        "court_name": court_name,
        "court_region": _sido if is_auction else "",
        "agency_name": agency_name,
        "source_site": source_site,
        "sale_type": sale_type,
        "sido": _sido,
        "sigungu": _sigungu,
        "dong": _dong,
        "item_group": ITEM_GROUP_BY_TYPE.get(item_type, "기타"),
        "risk_keywords": risk_keywords,
        "caution_reason": caution_reason,
        "document_status": document_status,
        "documents_missing": documents_missing,
        "field_survey_needed": field_survey_needed,
        "agent_opinion": rec_reason or f"{risk_level} 위험 기준 검토 필요",
    }


def _conf_breakdown(overall: float | None, seed: int) -> dict:
    """전체 신뢰도 주변으로 항목별(가격/권리/문서/주소) 신뢰도를 결정적 생성."""
    o = float(overall if overall is not None else 0.7)

    def jit(base: float, span: int) -> float:
        return round(max(0.3, min(0.98, base + ((seed % (2 * span + 1)) - span) / 100.0)), 3)

    return {
        "price_confidence": jit(o, 6),
        "legal_confidence": jit(o - 0.02, 8),
        "document_confidence": jit(o + 0.01, 5),
        "address_confidence": jit(o + 0.03, 4),
    }


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
        gen_mock(count=200, seed=42, reset=False)
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


def _price_trend_for(conn: sqlite3.Connection, item_id: int,
                     market_price: int, months: int = 12) -> list[dict]:
    """매물 단위 월별 시세 sparkline 데이터.
    실거래 기록이 있으면 그것을 월별 집계, 없으면 market_price 중심으로 합성한다."""
    out: list[dict] = []
    try:
        rows = conn.execute(
            """
            SELECT trade_date, trade_price FROM price_records
            WHERE item_id=? AND trade_price > 0
            ORDER BY trade_date ASC
            """,
            (item_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    if rows:
        by_ym: dict[str, list[int]] = {}
        for r in rows:
            d = (r["trade_date"] or "")[:7]
            if len(d) < 7:
                continue
            by_ym.setdefault(d, []).append(int(r["trade_price"] or 0))
        keys = sorted(by_ym.keys())[-months:]
        for ym in keys:
            arr = by_ym[ym]
            out.append({"ym": ym, "avg_price": int(sum(arr) / len(arr)),
                        "count": len(arr)})
    if not out:
        # 합성: market_price 중심으로 12개월 시드 기반 흐름 생성
        base = market_price or 0
        if base <= 0:
            return []
        rnd = random.Random(item_id * 0x9E3779B9 & 0xFFFFFFFF)
        # 약한 추세(±15%) + 작은 노이즈
        trend = rnd.uniform(-0.15, 0.15)
        today = datetime.now().date().replace(day=1)
        series = []
        for k in range(months - 1, -1, -1):
            ym = (today - timedelta(days=30 * k))
            ratio = 1.0 + trend * (1 - k / (months - 1)) + rnd.uniform(-0.04, 0.04)
            avg = max(1, int(base * ratio))
            series.append({"ym": f"{ym.year:04d}-{ym.month:02d}",
                           "avg_price": avg, "count": rnd.randrange(1, 6)})
        out = series
    return out


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


def _score_breakdown(profit: int, roi: float, risk_level: str,
                     confidence: float, days_left: int | None) -> list[dict]:
    """매물 추천 점수의 기여 항목별 분해. 합산은 약 0~100 범위.
    실제 recommendation_agent 의 가중치와 정확히 같지 않더라도, 사용자가
    '왜 이 점수인지' 한눈에 볼 수 있게 한다."""
    pf = max(0, min(35, round((profit or 0) / 50000 * 35)))
    rs = max(0, min(25, round((roi or 0) / 50 * 25)))
    rk_map = {"low": 20, "medium": 10, "high": 0}
    rk = rk_map.get(risk_level, 10)
    cf = max(0, min(10, round((confidence or 0) * 10)))
    if days_left is None or days_left < 0:
        ur = 1
    elif days_left <= 3:
        ur = 10
    elif days_left <= 7:
        ur = 7
    elif days_left <= 14:
        ur = 4
    else:
        ur = 1
    risk_label = {"low": "낮음", "medium": "보통", "high": "높음"}.get(risk_level, "-")
    days_note = (f"D-{days_left}" if days_left is not None and days_left >= 0
                 else "기일 미정")
    return [
        {"key": "profit", "label": "예상 차익", "contribution": pf, "max": 35,
         "note": f"{(profit or 0):,}만원 추정"},
        {"key": "roi", "label": "수익률", "contribution": rs, "max": 25,
         "note": f"{(roi or 0):.1f}%"},
        {"key": "risk", "label": "위험도", "contribution": rk, "max": 20,
         "note": risk_label},
        {"key": "confidence", "label": "신뢰도", "contribution": cf, "max": 10,
         "note": f"{(confidence or 0):.2f}"},
        {"key": "urgency", "label": "기일 임박", "contribution": ur, "max": 10,
         "note": days_note},
    ]


def _decision_summary(grade: str, risk_level: str, profit: int) -> str:
    """단정하지 않는 한줄 판단 (검토 후보 / 확인 필요 / 추가 검토 필요 톤)."""
    if grade == "A":
        return "현재 자료 기준 검토 후보로 볼 만합니다 — 등기부·현장조사로 확인 필요합니다."
    if grade == "B":
        return "조건은 양호한 편이나, 위험 항목 보완 후 추가 검토가 필요합니다."
    if grade == "C":
        return "수익·위험 중 한쪽이 애매해 추가 검토가 필요한 물건입니다."
    if grade == "D":
        return "현재 자료 기준 신중한 접근이 필요하며 보류도 선택지입니다."
    return "수익 대비 위험이 커 보여 확인이 필요합니다 — 보수적으로 접근하세요."


def _detail_fields(
    *,
    appraisal: int,
    minb: int,
    market: int,
    expected_profit: int,
    expected_profit_rate: float,
    risk_level: str,
    price_trend: list[dict],
    confidence: float,
    conf_parts: dict,
    repair: int,
    eviction: int,
    flags: list[dict],
    documents_missing: bool,
    source: str,
    grade: str,
    caution_reason: str,
) -> dict:
    """연번 11 상세 패널이 요구하는 추가 필드를 결정적으로 산출한다.

    시세(6/12개월 평균·거래량·비율), 수익(비용 분해·안전마진),
    예상입찰가(보수/기준/공격/최대·경고), 위험 원문 근거, 문서 상태,
    신뢰도 사유, 비단정 한줄 판단을 모두 한 번에 만든다.
    """
    # ── 시세 분석 ──
    prices = [p.get("avg_price") for p in (price_trend or []) if p.get("avg_price")]
    counts = [p.get("count") or 0 for p in (price_trend or [])]
    avg6 = int(sum(prices[-6:]) / len(prices[-6:])) if prices else (market or 0)
    avg12 = int(sum(prices[-12:]) / len(prices[-12:])) if prices else (market or 0)
    txn = int(sum(counts)) if counts else 0
    appr_ratio = round(appraisal / market * 100, 1) if market else None
    min_ratio = round(minb / market * 100, 1) if market else None
    price_conf = conf_parts.get("price_confidence", confidence)

    # ── 수익 분석 (비용 분해) ──
    acquisition = int(minb * 0.045)       # 취득세·등기 등 부대비용(주거 기준 가정)
    finance = int(minb * 0.6 * 0.05)      # 낙찰가 60% 대출·연 5% 1년 가정
    estimated_total = minb + acquisition + repair + eviction + finance
    safety_margin = int((market or 0) - estimated_total) if market else 0

    # ── 예상 입찰가 ──
    conservative = round(minb * 1.02)
    normal = round(minb * 1.10)
    aggressive = round(minb * 1.18)
    if market:
        max_bid = max(int(market - repair - eviction - int(market * 0.05)), normal)
    else:
        max_bid = aggressive
    bid_warnings: list[str] = []
    if risk_level == "high":
        bid_warnings.append("고위험 물건 — 공격적 입찰가는 고위험으로 참고 제한, 참고용으로만 보세요.")
    if not market:
        bid_warnings.append("시세 표본이 부족해 예상 입찰가 신뢰도가 낮을 수 있습니다.")
    if min_ratio is not None and min_ratio < 60:
        bid_warnings.append("최저가가 시세 대비 크게 낮아 권리상 부담 여부를 함께 확인하세요.")
    bid_warnings.append("예상 입찰가는 mock 데이터 기반 단순 추정치이며 실제 입찰 판단을 단정하지 않습니다.")

    # ── 위험 분석 원문 근거 ──
    src_parts = [f.get("description") for f in (flags or []) if f.get("description")]
    source_text = " / ".join(src_parts) if src_parts else (caution_reason or "검출된 위험 키워드 없음")

    # ── 문서 상태 ──
    is_auction = source == "auction"
    has_sale = not documents_missing
    has_survey = not documents_missing
    has_appraisal = not documents_missing
    has_public_notice = (not documents_missing) if not is_auction else False
    documents = [
        {"name": "매각물건명세서", "available": has_sale},
        {"name": "현황조사서", "available": has_survey},
        {"name": "감정평가서", "available": has_appraisal},
    ]
    if not is_auction:
        documents.append({"name": "공매 공고문", "available": has_public_notice})

    # ── 신뢰도 사유 ──
    conf_reasons: list[str] = []
    if price_conf < 0.6:
        conf_reasons.append("실거래 표본이 적어 시세 추정 신뢰도가 낮습니다.")
    if conf_parts.get("legal_confidence", 1) < 0.6:
        conf_reasons.append("권리관계 분석에 추가 확인이 필요합니다.")
    if conf_parts.get("document_confidence", 1) < 0.6 or documents_missing:
        conf_reasons.append("핵심 문서가 일부 미공개라 문서 완성도가 낮습니다.")
    if conf_parts.get("address_confidence", 1) < 0.6:
        conf_reasons.append("주소 매칭 정확도가 낮아 동일 물건 여부 확인이 필요합니다.")
    if not conf_reasons:
        conf_reasons.append("현재 자료 기준 주요 항목 신뢰도가 양호한 편입니다.")
    confidence_reason = " ".join(conf_reasons)

    return {
        # 시세
        "avg_price_6m": avg6,
        "avg_price_12m": avg12,
        "transaction_count": txn,
        "appraisal_to_market_ratio": appr_ratio,
        "confidence_reason": confidence_reason,
        "confidence_reasons": conf_reasons,
        # 수익
        "acquisition_cost": acquisition,
        "repair_cost": repair,
        "eviction_cost": eviction,
        "finance_cost": finance,
        "estimated_total_cost": estimated_total,
        "safety_margin": safety_margin,
        # 예상 입찰가
        "conservative_bid": conservative,
        "normal_bid": normal,
        "aggressive_bid": aggressive,
        "max_bid_price": max_bid,
        "bid_warnings": bid_warnings,
        "warning_messages": bid_warnings,
        # 위험 원문 근거
        "source_text": source_text,
        # 문서 상태
        "documents": documents,
        "has_sale_statement": has_sale,
        "has_survey_report": has_survey,
        "has_appraisal_report": has_appraisal,
        "has_public_notice": has_public_notice,
        # AI 한줄 판단(비단정)
        "decision_summary": _decision_summary(grade, risk_level, expected_profit),
    }


def _recompute_for_minbid(it: dict) -> None:
    """min_bid_price 를 바꾼 뒤 이에 의존하는 경제성·상세 필드를 다시 계산한다."""
    m = it.get("market_price") or 0
    minb = it.get("min_bid_price") or 0
    appr = it.get("appraisal_price") or 0
    repair = it.get("repair_cost") if it.get("repair_cost") is not None else int(appr * 0.01)
    eviction = it.get("eviction_cost") or 0
    profit = int(m - minb - repair - eviction) if m else 0
    it["minimum_price"] = minb
    it["expected_profit"] = profit
    it["expected_profit_rate"] = round(profit / minb * 100, 1) if minb else 0.0
    it["minimum_to_market_ratio"] = round(minb / m * 100, 1) if m else None
    it["detail_summary"] = (
        f"감정가 {appr:,}만원 / 최저가 {minb:,}만원"
        + (f" / 추정시세 {int(m):,}만원" if m else "")
        + (f" / 차익 {profit:,}만원" if profit else "")
        + f" / 위험 {it.get('risk_level', 'medium')} / 신뢰도 {(it.get('confidence_score') or 0):.2f}"
    )
    it.update(_detail_fields(
        appraisal=appr, minb=minb, market=int(m) if m else 0, expected_profit=profit,
        expected_profit_rate=it["expected_profit_rate"], risk_level=it.get("risk_level", "medium"),
        price_trend=it.get("price_trend") or [], confidence=float(it.get("confidence_score") or 0.7),
        conf_parts={
            "price_confidence": it.get("price_confidence"),
            "legal_confidence": it.get("legal_confidence"),
            "document_confidence": it.get("document_confidence"),
            "address_confidence": it.get("address_confidence"),
        },
        repair=repair, eviction=eviction, flags=it.get("risk_flags") or [],
        documents_missing=bool(it.get("documents_missing")), source=it.get("source", "auction"),
        grade=it.get("recommendation_grade", "C"), caution_reason=it.get("caution_reason", ""),
    ))


def _set_court(it: dict, court: str) -> None:
    """item 의 법원 필드를 일관되게 세팅(테스트 케이스 보정용)."""
    meta = COURT_META.get(court, {"region": "기타", "group": "기타"})
    it["source"] = "auction"
    it["court_name"] = court
    it["court_region"] = meta["region"]
    it["court_group"] = meta["group"]
    it["court_type"] = "본원"
    it["court_branch"] = ""
    it["sale_type"] = "법원경매"
    it["source_site"] = "court"
    it["agency_name"] = ""
    it["agency_type"] = ""
    it["agency_region"] = ""
    it["agency_group"] = ""
    it["public_sale_type"] = ""
    it["onbid_category"] = ""


def _ensure_agent_test_cases(items: list[dict]) -> None:
    """연번 12·15 자연어/법원 검색 데모가 항상 결과를 내도록 핵심 케이스를 보장한다.

    수원지방법원 아파트 / 부산지방법원 토지(저평가) / 인천지방법원 오피스텔 /
    서울중앙지방법원 상가 조합을 결정적으로 1건씩 확보한다.
    """
    if not items:
        return
    used: set = set()

    def pick(court: str, item_type: str, item_group: str | None = None):
        # 우선 해당 법원·종류가 이미 있으면 재사용, 없으면 미사용 item 하나를 보정
        for it in items:
            if id(it) in used:
                continue
            if (it.get("court_name") or "") == court and (it.get("item_type") or "") == item_type:
                used.add(id(it))
                return it
        for it in items:
            if id(it) in used or it.get("source") != "auction":
                continue
            _set_court(it, court)
            it["item_type"] = item_type
            if item_group:
                it["item_group"] = item_group
            used.add(id(it))
            return it
        return None

    # 1) 수원지방법원 아파트
    pick("수원지방법원", "아파트")
    # 2) 인천지방법원 오피스텔
    pick("인천지방법원", "오피스텔")
    # 3) 서울중앙지방법원 상가
    pick("서울중앙지방법원", "상가")
    # 4) 부산지방법원 토지(저평가)
    busan = pick("부산지방법원", "토지", "토지")
    if busan:
        m = busan.get("market_price") or 0
        if m > 0:
            busan["min_bid_price"] = int(m * 0.55)
            _recompute_for_minbid(busan)

    # 5) 공매 차량 (온비드 카테고리=차량) 최소 1건
    if not any(it.get("source") == "public_sale" and it.get("item_type") == "차량"
               for it in items):
        for it in items:
            if it.get("source") == "public_sale" and id(it) not in used:
                it["item_type"] = "차량"
                it["item_group"] = "차량"
                it["onbid_category"] = "차량"
                used.add(id(it))
                break


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


def _additional_checklist(flags: list[dict]) -> list[str]:
    """위험 키워드에 따른 추가 확인사항(심화)."""
    kws = " ".join((f.get("keyword") or "") for f in flags)
    out: list[str] = []
    if any(k in kws for k in ("임차", "전입", "대항")):
        out.append("전입세대 열람내역서·확정일자 부여현황 발급 확인")
    if "유치권" in kws:
        out.append("유치권 신고서·점유 개시 시점·피담보채권 확인")
    if "지분" in kws or "공유" in kws:
        out.append("공유자 우선매수 신고 가능성·공유물분할 청구 검토")
    if "농지" in kws:
        out.append("농지취득자격증명 발급 가능 여부 사전 확인")
    if "위반건축물" in kws:
        out.append("위반건축물 이행강제금·양성화 가능성 확인")
    if "분묘" in kws:
        out.append("분묘기지권 성립 여부·개장 협의 비용 확인")
    if "재매각" in kws:
        out.append("재매각 사유 확인·입찰보증금 비율(통상 20~30%) 준비")
    if not out:
        out.append("등기부등본 최신본·전입세대 열람으로 권리 재확인")
    return out[:5]


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
    for idx, r in enumerate(rows):
        item_id = r["id"]
        item_type = DEMO_TYPE_INJECT.get(idx, r["item_type"])
        flags = _flags_for(conn, item_id)
        # 데모: 일부 물건에 '대금미납 재매각' 위험 키워드 주입 (해당 케이스 확보)
        if idx % 11 == 0:
            flags = flags + [{
                "keyword": "대금미납 재매각", "flag_type": "resale",
                "risk_level": "medium", "severity": "medium",
                "description": "전 낙찰자 대금 미납으로 재매각 — 입찰보증금 비율 확인 필요",
            }]
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
        price_trend = _price_trend_for(conn, item_id, int(market) if market else 0)
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

        sf = _search_fields(
            item_id, r["source"], region, item_type, r["address_full"],
            r["address_si"], r["address_gu"], r["case_no"], flags, rec_reason, risk_level,
        )
        mtm_ratio = round(minb / market * 100, 1) if market else None
        conf_parts = _conf_breakdown(confidence, item_id)
        detail_fields = _detail_fields(
            appraisal=appr, minb=minb, market=int(market) if market else 0,
            expected_profit=expected_profit, expected_profit_rate=expected_profit_rate,
            risk_level=risk_level, price_trend=price_trend, confidence=float(confidence),
            conf_parts=conf_parts, repair=repair, eviction=eviction, flags=flags,
            documents_missing=sf["documents_missing"], source=r["source"], grade=grade,
            caution_reason=sf["caution_reason"],
        )
        out.append({
            "id": item_id,
            "source": r["source"],
            "case_no": sf["case_no"],
            "title": title,
            "address": r["address_full"],
            "region": region,
            "item_type": item_type,
            "minimum_to_market_ratio": mtm_ratio,
            "additional_checklist": _additional_checklist(flags),
            **conf_parts,
            **sf,
            **detail_fields,
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
            "price_trend": price_trend,
            "score_breakdown": _score_breakdown(
                expected_profit, expected_profit_rate, risk_level,
                float(confidence), days_left,
            ),
            # ─── 초보자 모드 필드 ───
            "beginner_friendly": _is_beginner_friendly({
                "risk_level": risk_level,
                "confidence_score": confidence,
                "item_type": item_type,
                "recommendation_grade": grade,
                "risk_flags": [{
                    "keyword": fl.get("keyword"),
                    "flag_type": fl.get("flag_type"),
                    "risk_level": fl.get("risk_level"),
                    "severity": fl.get("severity"),
                    "description": fl.get("description"),
                } for fl in flags],
            }),
            "beginner_reason": _beginner_reason({
                "recommendation_grade": grade,
                "expected_profit": expected_profit,
                "risk_level": risk_level,
            }),
            "simple_risk_summary": _simple_risk_summary({
                "risk_level": risk_level,
                "risk_flags": [{
                    "keyword": fl.get("keyword"),
                    "flag_type": fl.get("flag_type"),
                } for fl in flags],
            }),
            "simple_profit_summary": _simple_profit_summary({
                "expected_profit": expected_profit,
                "expected_profit_rate": expected_profit_rate,
                "min_bid_price": minb,
            }),
            "simple_next_action": _simple_next_action({
                "risk_level": risk_level,
                "item_type": item_type,
            }, days_left),
            "why_recommended": rec_reason,
            "what_to_check": checklist[0] if checklist else "등기부등본 확인",
            "easy_explanation": _get_easy_explanation(
                warnings_list[0] if warnings_list else ""
            ),
            "glossary_terms": [
                {"term": kw, "explanation": _get_easy_explanation(kw)}
                for kw in warnings_list
            ],
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


# ── 연번 13: 브리핑 강화 ──────────────────────────────────────────
def _item_kw_text(it: dict) -> str:
    """물건의 위험 관련 텍스트를 한 문자열로(키워드 매칭용)."""
    parts = [str(it.get("caution_reason") or "")]
    parts += [str(k) for k in (it.get("risk_keywords") or [])]
    for fl in it.get("risk_flags") or []:
        parts.append(str(fl.get("keyword") or ""))
        parts.append(str(fl.get("description") or ""))
    for w in it.get("warnings") or []:
        parts.append(str(w))
    return " ".join(parts)


def _is_recommended(it: dict) -> bool:
    """검토 후보(추천 후보) 판정: A·B 등급 또는 추천점수 60 이상."""
    if it.get("recommendation_grade") in ("A", "B"):
        return True
    return (it.get("recommendation_score") or 0) >= 60


def _is_urgent(it: dict) -> bool:
    d = it.get("days_left")
    return d is not None and 0 <= d <= 7


def _priority_reason(it: dict) -> str:
    """오늘 우선 확인 한줄 이유(비단정)."""
    bits = []
    if it.get("recommendation_grade") == "A":
        bits.append("A등급 검토 후보")
    if _is_urgent(it):
        bits.append(f"입찰 D-{it.get('days_left')}")
    if (it.get("expected_profit") or 0) > 0:
        bits.append(f"예상차익 {it.get('expected_profit'):,}만원")
    if not bits:
        bits.append(it.get("decision_summary") or it.get("recommendation_reason") or "현재 자료 기준 검토 후보")
    return " · ".join(bits)


def _avg_roi(items: list[dict]) -> float:
    vals = []
    for it in items:
        r = it.get("expected_profit_rate")
        if r is None:
            continue
        r = float(r)
        # 분수(0.12)·퍼센트(12) 혼용 → 퍼센트 통일
        vals.append(r * 100 if 0 < abs(r) < 1 else r)
    return round(sum(vals) / len(vals), 1) if vals else 0.0


def _group_summary(items: list[dict], key_fn, *, top: int = 5,
                   label_key: str) -> list[dict]:
    """법원/종류 등 그룹별 요약. 그룹 내 대표 추천 물건 1건 포함."""
    groups: dict[str, list[dict]] = {}
    for it in items:
        k = key_fn(it)
        if not k:
            continue
        groups.setdefault(k, []).append(it)
    out: list[dict] = []
    for name, arr in groups.items():
        rep = max(arr, key=lambda x: (x.get("recommendation_score") or 0,
                                      x.get("expected_profit") or 0))
        out.append({
            label_key: name,
            "count": len(arr),
            "recommended": sum(1 for x in arr if _is_recommended(x)),
            "grade_a": sum(1 for x in arr if x.get("recommendation_grade") == "A"),
            "high_risk": sum(1 for x in arr if x.get("risk_level") == "high"),
            "avg_roi": _avg_roi(arr),
            "top_item": {
                "id": rep.get("id"),
                "title": rep.get("title") or rep.get("address") or "주소 미상",
                "item_type": rep.get("item_type"),
                "recommendation_grade": rep.get("recommendation_grade"),
                "expected_profit": rep.get("expected_profit"),
                "risk_level": rep.get("risk_level"),
            },
        })
    out.sort(key=lambda g: (-g["count"], -g["recommended"]))
    return out[:top]


def _priority_items(items: list[dict], *, limit: int = 6) -> list[dict]:
    """오늘 우선 확인 물건: A등급 우선 → 추천점수 → 예상차익 → 기일 가까운,
    고위험은 제외(별도 주의), 시세 신뢰도 high/medium 우선."""
    def conf_band(it):
        c = it.get("price_confidence")
        c = it.get("confidence_score") if c is None else c
        return (c or 0) >= 0.6  # high/medium 우선
    cand = [it for it in items if it.get("risk_level") != "high"]
    cand.sort(key=lambda it: (
        0 if it.get("recommendation_grade") == "A" else 1,
        0 if conf_band(it) else 1,
        -(it.get("recommendation_score") or 0),
        -(it.get("expected_profit") or 0),
        it.get("days_left") if (it.get("days_left") is not None and it.get("days_left") >= 0) else 9999,
    ))
    out = []
    for it in cand[:limit]:
        out.append({
            "id": it.get("id"),
            "title": it.get("title") or it.get("address") or "주소 미상",
            "court": it.get("court_name") or it.get("agency_name") or "-",
            "item_type": it.get("item_type"),
            "expected_profit": it.get("expected_profit"),
            "expected_profit_rate": it.get("expected_profit_rate"),
            "risk_level": it.get("risk_level"),
            "recommendation_grade": it.get("recommendation_grade"),
            "bid_date": it.get("bid_date"),
            "days_left": it.get("days_left"),
            "reason": _priority_reason(it),
        })
    return out


def _risk_points(items: list[dict]) -> dict[str, int]:
    """오늘 주의할 위험 포인트 집계."""
    def cnt(*kws):
        return sum(1 for it in items if any(k in _item_kw_text(it) for k in kws))
    return {
        "lien": cnt("유치권"),
        "superficies": cnt("법정지상권"),
        "share": cnt("지분", "공유지분"),
        "farmland": cnt("농지취득자격증명", "농지"),
        "tenant": cnt("임차인", "전입세대", "대항력", "선순위임차인"),
        "document_missing": sum(1 for it in items if it.get("documents_missing")
                                or "미공개" in (it.get("document_status") or "")),
    }


def _build_briefing(items: list[dict], run_date: str | None = None) -> dict[str, Any]:
    """연번 13 브리핑 강화: 요약 지표·문장·우선물건·법원/종류별·위험포인트 일괄 생성."""
    total = len(items)
    analyzed = sum(1 for it in items if it.get("market_price") or it.get("recommendation_score"))
    recommended = sum(1 for it in items if _is_recommended(it))
    grade_a = sum(1 for it in items if it.get("recommendation_grade") == "A")
    urgent = sum(1 for it in items if _is_urgent(it))
    high_risk = sum(1 for it in items if it.get("risk_level") == "high")
    auction = sum(1 for it in items if it.get("source") == "auction")
    public_sale = sum(1 for it in items if it.get("source") == "public_sale")
    market_matched = sum(1 for it in items if (it.get("market_price") or 0) > 0)
    doc_missing = sum(1 for it in items if it.get("documents_missing")
                      or "미공개" in (it.get("document_status") or ""))
    field_needed = sum(1 for it in items if it.get("field_survey_needed"))

    top_courts = _group_summary(items, lambda it: it.get("court_name"), label_key="court")
    top_agencies = _group_summary(items, lambda it: it.get("agency_name"), label_key="agency")
    top_types = _group_summary(items, lambda it: it.get("item_type"), label_key="item_type")
    priority = _priority_items(items)
    risk_points = _risk_points(items)

    # 우선 확인 권장 라벨(법원·종류 조합 상위)
    focus_labels = []
    if top_courts:
        c0 = top_courts[0]
        if c0.get("top_item"):
            focus_labels.append(f"{c0['court']} {c0['top_item'].get('item_type') or ''}".strip())
    pub_shops = [it for it in items if it.get("source") == "public_sale" and "상가" in (it.get("item_type") or "")]
    if pub_shops:
        focus_labels.append("공매 상가")
    if not focus_labels:
        focus_labels.append("추천점수 상위 후보")

    text = (
        "오늘의 경매·공매 브리핑입니다.\n"
        f"총 {total}건 중 분석 완료 물건은 {analyzed}건입니다.\n"
        f"추천 후보는 {recommended}건이며, 그중 A등급은 {grade_a}건입니다.\n"
        f"입찰기일 7일 이내 후보는 {urgent}건입니다.\n"
        f"고위험 키워드가 있는 물건은 {high_risk}건입니다.\n"
        f"오늘은 {', '.join(focus_labels)} 후보를 우선 확인하는 것이 좋습니다.\n"
        "※ mock 데이터 기반 참고용이며, 입찰 전 등기부·현장조사 확인이 필요합니다."
    )

    return {
        "run_date": run_date or datetime.now().date().isoformat(),
        "summary": text,
        "briefing_text": text,
        "total_items": total,
        "analyzed_items": analyzed,
        "recommended_items": recommended,
        "high_risk_items": high_risk,
        "grade_a_items": grade_a,
        "urgent_items": urgent,
        "auction_count": auction,
        "public_sale_count": public_sale,
        "market_matched_items": market_matched,
        "document_missing_items": doc_missing,
        "field_visit_needed_items": field_needed,
        "top_courts": top_courts,
        "top_agencies": top_agencies,
        "top_types": top_types,
        "priority_items": priority,
        "risk_points": risk_points,
        "matched_items": market_matched,
        "candidate_items": recommended,
        "data_timestamp": datetime.now().isoformat(timespec="seconds"),
    }


def _briefing_action_items(items: list[dict]) -> list[dict]:
    """연번 13 작업10: 브리핑 우선물건/위험포인트를 '오늘 할 일'로 연결."""
    actions: list[dict] = []
    seen_ids: set = set()

    def add(priority, title, detail, it):
        iid = it.get("id")
        actions.append({
            "priority": priority, "title": title, "detail": detail,
            "due_date": it.get("bid_date"), "address": it.get("address") or it.get("title"),
            "item_id": iid, "item_type": it.get("item_type"),
        })

    # 입찰임박 A등급 → 상세 검토
    for it in items:
        if it.get("recommendation_grade") == "A" and _is_urgent(it) and it.get("id") not in seen_ids:
            add("high", "입찰임박 A등급 — 상세 검토",
                f"입찰 D-{it.get('days_left')} · 등기부·현장조사로 의사결정 근거 확인", it)
            seen_ids.add(it.get("id"))
    # 고위험 고수익 → 전문가 검토
    for it in sorted(items, key=lambda x: -(x.get("expected_profit") or 0)):
        if it.get("risk_level") == "high" and (it.get("expected_profit") or 0) > 10000 and it.get("id") not in seen_ids:
            add("high", "고위험 고수익 — 전문가 검토 필요",
                "수익은 크지만 권리위험이 높아 전문가 자문·현장조사가 필요합니다.", it)
            seen_ids.add(it.get("id"))
            if sum(1 for a in actions if "고위험 고수익" in a["title"]) >= 2:
                break
    # 임차인 관련 → 전입세대열람
    for it in items:
        if it.get("id") in seen_ids:
            continue
        if any(k in _item_kw_text(it) for k in ("임차인", "전입세대", "대항력", "선순위임차인")):
            add("medium", "임차인 관련 — 전입세대열람 확인",
                "전입세대 열람내역서·확정일자로 대항력 임차인 여부를 확인하세요.", it)
            seen_ids.add(it.get("id"))
            break
    # 문서 미공개 → 문서 공개 추적
    for it in items:
        if it.get("id") in seen_ids:
            continue
        if it.get("documents_missing") or "미공개" in (it.get("document_status") or ""):
            add("medium", "문서 미공개 — 공개 여부 추적",
                "매각물건명세서·현황조사서 공개 시점을 확인하고 재검토하세요.", it)
            seen_ids.add(it.get("id"))
            break
    return actions


def _build_distributions(items: list[dict]) -> dict[str, Any]:
    """연번 14 통계 섹션용 분포 데이터(summary 보강용). 정적 JSON 직접 소비자를 위한 사본."""
    def count_by(key_fn):
        m: dict[str, int] = {}
        for it in items:
            k = key_fn(it)
            if not k:
                continue
            m[k] = m.get(k, 0) + 1
        return dict(sorted(m.items(), key=lambda x: -x[1]))

    # 입찰기일 버킷
    def bid_bucket(it):
        d = it.get("days_left")
        if d is None or d == "":
            return "기일 미정"
        if d < 0:
            return "기일 미정"
        if d == 0:
            return "오늘"
        if d <= 3:
            return "3일 이내"
        if d <= 7:
            return "7일 이내"
        if d <= 14:
            return "14일 이내"
        if d <= 30:
            return "30일 이내"
        return "30일 초과"

    def fail_bucket(it):
        n = it.get("fail_count") or 0
        return "3회 이상" if n >= 3 else f"{n}회"

    # 위험 키워드 분포
    kw_counts: dict[str, int] = {}
    for it in items:
        seen = set()
        for kw in (it.get("risk_keywords") or
                   [f.get("keyword") for f in (it.get("risk_flags") or [])]):
            if not kw or kw in seen:
                continue
            seen.add(kw)
            kw_counts[kw] = kw_counts.get(kw, 0) + 1
    risk_kw = dict(sorted(kw_counts.items(), key=lambda x: -x[1])[:12])

    doc_missing = sum(1 for it in items if it.get("documents_missing")
                      or "미공개" in (it.get("document_status") or ""))
    return {
        "court_distribution": count_by(lambda it: it.get("court_name")),
        "court_region_distribution": count_by(lambda it: it.get("court_region")),
        "court_group_distribution": count_by(lambda it: it.get("court_group")),
        "agency_distribution": count_by(lambda it: it.get("agency_name")),
        "agency_type_distribution": count_by(lambda it: it.get("agency_type")),
        "agency_region_distribution": count_by(lambda it: it.get("agency_region")),
        "public_sale_type_distribution": count_by(lambda it: it.get("public_sale_type")),
        "onbid_category_distribution": count_by(lambda it: it.get("onbid_category")),
        "region_distribution": count_by(lambda it: it.get("sido") or it.get("region")),
        "type_distribution": count_by(lambda it: it.get("item_type")),
        "item_group_distribution": count_by(lambda it: it.get("item_group")),
        "bid_date_distribution": count_by(bid_bucket),
        "fail_count_distribution": count_by(fail_bucket),
        "risk_keyword_distribution": risk_kw,
        "document_status_distribution": {
            "present": len(items) - doc_missing,
            "missing": doc_missing,
        },
        "top_courts": _group_summary(
            [it for it in items if it.get("court_name")],
            lambda it: it.get("court_name"), top=8, label_key="court"),
        "top_agencies": _group_summary(
            [it for it in items if it.get("agency_name")],
            lambda it: it.get("agency_name"), top=8, label_key="agency"),
    }


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
    "공유지분", "농지취득자격증명", "분묘기지권", "대금미납 재매각",
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
        item_type = DEMO_TYPE_INJECT.get(i - 1, rnd.choice(FALLBACK_TYPES))
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

        sf = _search_fields(
            i, source, region, item_type, addr,
            None, None, case_no, flags, rec_reason, risk,
        )
        price_trend = [
            {"ym": (today.replace(day=1) - timedelta(days=30 * k)).strftime("%Y-%m"),
             "avg_price": max(1, int(market * (1 + rnd.uniform(-0.12, 0.12) +
                                               rnd.uniform(-0.04, 0.04)))),
             "count": rnd.randrange(1, 6)}
            for k in range(11, -1, -1)
        ]
        conf_parts = _conf_breakdown(confidence, i)
        detail_fields = _detail_fields(
            appraisal=appr, minb=minb, market=market, expected_profit=profit,
            expected_profit_rate=roi, risk_level=risk, price_trend=price_trend,
            confidence=float(confidence), conf_parts=conf_parts, repair=repair,
            eviction=evict, flags=flags, documents_missing=sf["documents_missing"],
            source=source, grade=grade, caution_reason=sf["caution_reason"],
        )
        items.append({
            "id": i,
            "source": source,
            "case_no": sf["case_no"],
            "title": addr,
            "address": addr,
            "region": region,
            "item_type": item_type,
            "minimum_to_market_ratio": round(minb / market * 100, 1) if market else None,
            "additional_checklist": _additional_checklist(flags),
            **conf_parts,
            **sf,
            **detail_fields,
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
            "price_trend": price_trend,
            "score_breakdown": _score_breakdown(profit, roi, risk, confidence, days_offset),
            # ─── 초보자 모드 필드 ───
            "beginner_friendly": _is_beginner_friendly({
                "risk_level": risk,
                "confidence_score": confidence,
                "item_type": item_type,
                "recommendation_grade": grade,
                "risk_flags": flags,
            }),
            "beginner_reason": _beginner_reason({
                "recommendation_grade": grade,
                "expected_profit": profit,
                "risk_level": risk,
            }),
            "simple_risk_summary": _simple_risk_summary({
                "risk_level": risk,
                "risk_flags": flags,
            }),
            "simple_profit_summary": _simple_profit_summary({
                "expected_profit": profit,
                "expected_profit_rate": roi,
                "min_bid_price": minb,
            }),
            "simple_next_action": _simple_next_action({
                "risk_level": risk,
                "item_type": item_type,
            }, days_offset),
            "why_recommended": rec_reason,
            "what_to_check": checklist[0] if checklist else "등기부등본 확인",
            "easy_explanation": _get_easy_explanation(
                warnings_list[0] if warnings_list else ""
            ),
            "glossary_terms": [
                {"term": kw, "explanation": _get_easy_explanation(kw)}
                for kw in warnings_list
            ],
        })
    return items


def _fallback_payload() -> dict[str, Any]:
    rnd = random.Random(42)
    items = _fallback_items(rnd, n=200)
    _assign_courts(items)
    _ensure_agent_test_cases(items)
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
    # 브리핑 우선물건/위험포인트 기반 '오늘 할 일' 연결 (작업10)
    actions = _briefing_action_items(items) + actions

    briefing = _build_briefing(items)
    summary = {
        "total_items": len(items),
        "analyzed_items": briefing["analyzed_items"],
        "recommended_items": briefing["recommended_items"],
        "high_risk_items": rs["high"],
        "grade_a_items": briefing["grade_a_items"],
        "avg_confidence": round(sum(it["confidence_score"] for it in items) / len(items), 3),
        "auction_count": sum(1 for it in items if it["source"] == "auction"),
        "public_sale_count": sum(1 for it in items if it["source"] == "public_sale"),
        "urgent_items": briefing["urgent_items"],
        "market_matched_items": briefing["market_matched_items"],
        "document_missing_items": briefing["document_missing_items"],
        "field_visit_needed_items": briefing["field_visit_needed_items"],
        "beginner_candidate_items": sum(1 for it in items if it.get("beginner_friendly")),
        "beginner_mode_default": False,
        "grade_distribution": {
            g: sum(1 for it in items if it.get("recommendation_grade") == g)
            for g in ("A", "B", "C", "D", "X")
        },
        "risk_distribution": {
            r: sum(1 for it in items if it.get("risk_level") == r)
            for r in ("low", "medium", "high")
        },
        **_build_distributions(items),
        "data_timestamp": datetime.now().isoformat(timespec="seconds"),
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
    _assign_courts(items)
    _ensure_agent_test_cases(items)

    recs = _recommendations_from_items(items, TOP_LIMIT)
    briefing = _build_briefing(items)
    db_actions = _action_items_from_db(conn) or _fallback_payload()["action_items"]
    actions = _briefing_action_items(items) + db_actions
    rs = _risk_summary_from_items(items)
    conf = _confidence_summary_from_db(conn)

    summary["recommended_items"] = briefing["recommended_items"]
    summary["urgent_items"] = briefing["urgent_items"]
    summary["grade_a_items"] = briefing["grade_a_items"]
    summary["market_matched_items"] = briefing["market_matched_items"]
    summary["document_missing_items"] = briefing["document_missing_items"]
    summary["field_visit_needed_items"] = briefing["field_visit_needed_items"]
    summary["beginner_candidate_items"] = sum(1 for it in items if it.get("beginner_friendly"))
    summary["beginner_mode_default"] = False
    summary["grade_distribution"] = {
        g: sum(1 for it in items if it.get("recommendation_grade") == g)
        for g in ("A", "B", "C", "D", "X")
    }
    summary["risk_distribution"] = {
        r: sum(1 for it in items if it.get("risk_level") == r)
        for r in ("low", "medium", "high")
    }
    summary.update(_build_distributions(items))
    summary["data_timestamp"] = datetime.now().isoformat(timespec="seconds")
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "db",
        "summary": summary,
        "briefing": briefing,
        "recommendations": recs,
        "action_items": actions,
        "risk_summary": rs,
        "confidence_summary": conf,
        "items": items,
        "agent_status": _agent_status(),
    }


def _xml_escape(s: Any) -> str:
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))


def _rfc822(dt: datetime) -> str:
    # 간단 RFC 822 (RSS pubDate 표준)
    return dt.strftime("%a, %d %b %Y %H:%M:%S +0900")


def _build_rss(items: list[dict], base_url: str = RSS_BASE_URL,
               limit: int = RSS_LIMIT) -> str:
    """추천 점수순 상위 N개 매물을 RSS 2.0 피드로 직렬화."""
    sorted_items = sorted(
        items, key=lambda it: (it.get("recommendation_score") or 0), reverse=True
    )[:limit]
    now = datetime.now()
    last_build = _rfc822(now)
    feed_url = base_url.rstrip("/") + "/feed.xml"
    site_url = base_url.rstrip("/") + "/"

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8" ?>')
    lines.append('<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">')
    lines.append("<channel>")
    lines.append("<title>경매·공매 지능형 에이전트 — 추천 후보</title>")
    lines.append(f'<link>{_xml_escape(site_url)}</link>')
    lines.append(
        f'<atom:link href="{_xml_escape(feed_url)}" rel="self" type="application/rss+xml" />'
    )
    lines.append("<description>법원경매·공매 mock 데이터 기반 추천 매물 (점수순). "
                 "실제 거래 대상이 아닌 데모 피드입니다.</description>")
    lines.append("<language>ko-KR</language>")
    lines.append(f"<lastBuildDate>{last_build}</lastBuildDate>")
    lines.append(f"<generator>export_static_dashboard.py</generator>")

    # 안정적인 pubDate: rank 순으로 1분씩 뒤로 — 피드 리더가 새 항목 정렬을 유지
    for i, it in enumerate(sorted_items):
        pub = now - timedelta(minutes=i)
        item_url = site_url + f"#item-{it.get('id')}"
        grade = it.get("recommendation_grade") or "C"
        score = it.get("recommendation_score") or 0
        title = (
            f"[{grade}] {it.get('title') or it.get('address') or '주소 미상'} "
            f"(점수 {round(float(score), 1)})"
        )
        risk = {"low": "낮음", "medium": "보통", "high": "높음"}.get(
            it.get("risk_level"), "-"
        )
        source = {"auction": "경매", "public_sale": "공매"}.get(it.get("source"), it.get("source") or "-")
        profit = it.get("expected_profit")
        profit_rate = it.get("expected_profit_rate")
        market = it.get("market_price")
        minb = it.get("min_bid_price")
        confidence = it.get("confidence_score")
        reason = it.get("recommendation_reason") or ""
        # description: 한 줄 요약 + 이유
        desc_parts = [
            f"{source} · {it.get('item_type') or '-'}",
            f"감정가 {(it.get('appraisal_price') or 0):,}만원",
            f"최저가 {(minb or 0):,}만원",
        ]
        if market:
            desc_parts.append(f"시세 {market:,}만원")
        if profit is not None:
            desc_parts.append(f"차익 {profit:,}만원")
        if profit_rate is not None:
            desc_parts.append(f"ROI {round(profit_rate, 1)}%")
        desc_parts.append(f"위험 {risk}")
        if confidence is not None:
            desc_parts.append(f"신뢰도 {round(float(confidence), 2)}")
        if it.get("bid_date"):
            desc_parts.append(f"입찰 {it.get('bid_date')}")
        desc_text = " / ".join(desc_parts)
        if reason:
            desc_text += "\n" + reason

        lines.append("<item>")
        lines.append(f"<title>{_xml_escape(title)}</title>")
        lines.append(f"<link>{_xml_escape(item_url)}</link>")
        lines.append(f'<guid isPermaLink="true">{_xml_escape(item_url)}</guid>')
        lines.append(f"<pubDate>{_rfc822(pub)}</pubDate>")
        lines.append(f"<category>{_xml_escape(it.get('item_type') or '기타')}</category>")
        lines.append(f"<category>{_xml_escape(grade)}</category>")
        lines.append(f"<description>{_xml_escape(desc_text)}</description>")
        lines.append("</item>")

    lines.append("</channel>")
    lines.append("</rss>")
    return "\n".join(lines) + "\n"


def _write_rss(payload: dict[str, Any]) -> None:
    items = payload.get("items") or []
    if not items:
        return
    try:
        xml = _build_rss(items)
    except Exception as e:
        print(f"[warn] RSS 직렬화 실패: {e}", file=sys.stderr)
        return
    RSS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RSS_PATH.open("w", encoding="utf-8") as f:
        f.write(xml)


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

    _write_rss(payload)

    return OUT_PATH


def main() -> None:
    out = export()
    size = out.stat().st_size
    print(f"[OK] {out.relative_to(ROOT)} ({size:,} bytes)")
    if RSS_PATH.exists():
        rsize = RSS_PATH.stat().st_size
        print(f"[OK] {RSS_PATH.relative_to(ROOT)} ({rsize:,} bytes)")


if __name__ == "__main__":
    main()
