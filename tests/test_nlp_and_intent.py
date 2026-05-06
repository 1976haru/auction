"""
tests/test_nlp_and_intent.py
자연어 파서, 의도 이해, 규칙 기반 폴백 검증.
"""


def test_mock_parse_basic():
    from core.mock_api import mock_parse_natural_language
    r = mock_parse_natural_language("서울 아파트 시세차익 큰 것 3개")
    assert r["limit"] == 3
    assert "서울" in r["regions"]
    assert "아파트" in r["item_types"]
    assert r["sort_by"] == "expected_profit"


def test_mock_parse_ambiguous_handled():
    from core.mock_api import mock_parse_natural_language
    r = mock_parse_natural_language("요즘 괜찮은 거 있어?")
    assert r["intent"] == "soft_recommend"
    assert any("애매" in a for a in r["assumptions"])


def test_intent_understanding_fills_defaults():
    from agents.intent_understanding_agent import understand
    r = understand("공매만 보고 수익률 높은 물건 10개")
    assert r["limit"] == 10
    assert r["source_types"] == ["public_sale"]
    assert r["sort_by"] == "expected_roi"


def test_legacy_rule_based_parse_keeps_signature():
    from agents.natural_language_agent import _rule_based_parse
    r = _rule_based_parse("서울 아파트 시세차익 큰 것 3개 찾아줘")
    assert r["limit"] == 3
    assert r["sort_by"] == "profit"
    assert "서울" in r["filters"]["regions"]
