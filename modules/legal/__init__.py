"""
modules/legal — 권리분석 엔진 (등기부 시계열 기반)

핵심: 단순 키워드 검출이 아닌, 말소기준권리 식별 + 인수금액 자동 추정.
모든 출력은 단정 표현을 피하고 "~로 보입니다 / ~가능성이 있습니다 / 확인 필요"
형태로 안내한다. 법률 자문이 아니며 참고용 추정치이다.
"""
from __future__ import annotations

from modules.legal.rights_parser import (
    parse_rights,
    save_rights_timeline,
    get_rights_timeline,
    parse_korean_amount,
)
from modules.legal.senior_right import (
    identify_senior_right,
    get_senior_right,
    SENIOR_RIGHT_TYPES,
)
from modules.legal.tenant_protection import analyze_tenant
from modules.legal.inheritance_cost import calculate_inheritance

__all__ = [
    "parse_rights",
    "save_rights_timeline",
    "get_rights_timeline",
    "parse_korean_amount",
    "identify_senior_right",
    "get_senior_right",
    "SENIOR_RIGHT_TYPES",
    "analyze_tenant",
    "calculate_inheritance",
]
