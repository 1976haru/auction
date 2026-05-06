"""
core/ai_client.py
Claude API 공통 래퍼.
- USE_MOCK_APIS=true 또는 USE_AI=false 또는 키 없음 -> Mock 응답
- 그 외에는 Anthropic 호출
"""
from __future__ import annotations

import json

from core.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, USE_AI, USE_MOCK_APIS
from core.logger import log
from core.mock_api import (
    mock_analyze_risk,
    mock_item_qa,
    mock_parse_natural_language,
    mock_summarize_document,
)


SYSTEM_RISK_ANALYST = """당신은 부동산 경매·공매 권리분석 보조 도구입니다.
반드시 지켜야 할 규칙:
1. "안전합니다", "무조건 입찰하세요" 같은 단정 표현을 절대 사용하지 않습니다.
2. 모든 판단에 "확인 필요", "가능성이 있습니다", "주의가 필요합니다" 표현을 씁니다.
3. 법률 해석은 참고용이며 최종 판단은 전문가·본인이 해야 함을 명시합니다.
4. 반드시 JSON 형식으로만 응답합니다."""

SYSTEM_NL_PARSER = """당신은 부동산 경매·공매 검색 조건 파서입니다.
사용자의 자연어 문장을 분석해 반드시 JSON 형식으로만 응답합니다.
다른 텍스트나 설명 없이 JSON만 출력하세요."""


def _is_mock_mode() -> bool:
    if USE_MOCK_APIS:
        return True
    if not USE_AI:
        return True
    if not ANTHROPIC_API_KEY:
        return True
    return False


def call_claude(
    prompt: str,
    system: str = "",
    max_tokens: int = 1500,
    as_json: bool = False,
):
    """직접 호출이 필요한 경우 사용. Mock 모드에선 안내문 반환."""
    if _is_mock_mode():
        log.info("[AI] mock 모드 -> 안내 응답 반환")
        msg = "(mock) AI 응답입니다. 실제 호출은 USE_AI=true + ANTHROPIC_API_KEY 설정 후 가능합니다."
        return {"result": msg} if as_json else msg

    try:
        import anthropic  # 선택 의존성
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        kwargs = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        response = client.messages.create(**kwargs)
        text = response.content[0].text.strip()
        if as_json:
            cleaned = text.replace("```json", "").replace("```", "").strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return {"error": "JSON 파싱 실패", "raw": text}
        return text
    except Exception as e:
        log.warning(f"[AI] Claude 호출 실패 -> mock으로 대체: {e}")
        return {"error": str(e)} if as_json else f"AI 오류: {e}"


def parse_natural_language(user_input: str) -> dict:
    if _is_mock_mode():
        log.info("[AI] (mock) NL 파서 사용")
        return mock_parse_natural_language(user_input)
    prompt = f"다음 문장을 검색조건 JSON으로 변환:\n{user_input}\nJSON만 출력."
    result = call_claude(prompt, system=SYSTEM_NL_PARSER, as_json=True)
    if isinstance(result, dict) and "error" not in result:
        return result
    return mock_parse_natural_language(user_input)


def analyze_risk(text: str, item_info: dict) -> dict:
    if _is_mock_mode():
        return mock_analyze_risk(text, item_info)
    prompt = f"""다음 문서/물건 정보를 분석해 위험도를 평가하라.
물건: {json.dumps(item_info, ensure_ascii=False)[:1500]}
문서: {(text or '')[:2000]}
JSON만 출력. 키: risk_score(1-10), risk_items[], summary, check_required[]
"""
    result = call_claude(prompt, system=SYSTEM_RISK_ANALYST, as_json=True)
    if isinstance(result, dict) and "risk_score" in result:
        return result
    return mock_analyze_risk(text, item_info)


def summarize_document(text: str, doc_type: str) -> str:
    if _is_mock_mode():
        return mock_summarize_document(text, doc_type)
    prompt = f"""{doc_type} 내용을 핵심 위주로 3~5줄로 요약. 단정 표현 금지.
{(text or '')[:3000]}"""
    return call_claude(prompt, system=SYSTEM_RISK_ANALYST)


def item_qa(question: str, context: dict) -> str:
    if _is_mock_mode():
        return mock_item_qa(question, context)
    prompt = f"""다음 물건 컨텍스트를 바탕으로 질문에 답하라.
컨텍스트: {json.dumps(context, ensure_ascii=False)[:1800]}
질문: {question}
법률 단정 금지. 모르는 것은 모른다고 답하라."""
    return call_claude(prompt, system=SYSTEM_RISK_ANALYST)
