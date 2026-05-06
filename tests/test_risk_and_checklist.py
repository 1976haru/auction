"""
tests/test_risk_and_checklist.py
위험 키워드 + 체크리스트 검증.
"""


def test_keyword_analyzer_finds_high_risk():
    from modules.risk.keyword_analyzer import analyze_keywords
    text = "유치권자 신고가 있으며 선순위임차인이 존재합니다."
    flags = analyze_keywords(text)
    types = {f["type"] for f in flags}
    assert "유치권" in types
    assert "선순위임차인" in types
    assert any(f["risk_level"] == "high" for f in flags)


def test_keyword_analyzer_low_risk():
    from modules.risk.keyword_analyzer import analyze_keywords
    text = "특이사항 없음 - 소유자 점유."
    flags = analyze_keywords(text)
    assert all(f["risk_level"] in ("low", "medium") for f in flags)


def test_save_and_load_risk_flags():
    from core.database import upsert_item
    from modules.risk.keyword_analyzer import (
        analyze_keywords, save_risk_flags, get_risk_flags, get_risk_score, get_risk_level,
    )
    iid = upsert_item({
        "source": "auction", "case_no": "2025타경9001", "item_type": "아파트",
        "address_full": "서울 강남구 역삼동 1", "appraisal_price": 50000,
        "min_bid_price": 35000, "bid_date": "2025-12-01",
    })
    flags = analyze_keywords("유치권 신고가 있습니다.")
    save_risk_flags(iid, flags)
    saved = get_risk_flags(iid)
    assert len(saved) >= 1
    assert get_risk_score(iid) >= 7
    assert get_risk_level(iid) == "high"


def test_checklist_builds_for_risk_flags():
    from agents.risk_checklist_agent import build_checklist, save_checklist
    from core.database import upsert_item
    from modules.risk.keyword_analyzer import analyze_keywords, save_risk_flags
    iid = upsert_item({
        "source": "public_sale", "mgmt_no": "PS-9999",
        "item_type": "빌라", "address_full": "서울 마포구 망원동 1",
        "appraisal_price": 30000, "min_bid_price": 21000, "bid_date": "2025-12-01",
    })
    flags = analyze_keywords("유치권 신고와 임차인 거주 중")
    save_risk_flags(iid, flags)
    cl = build_checklist(iid)
    assert any("유치권" in c["flag_type"] for c in cl)
    assert any(c["flag_type"] == "공매" for c in cl), "공매 추가 체크리스트 포함"
    n = save_checklist(iid, cl)
    assert n == len(cl)
