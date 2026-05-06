"""
modules/keyword_analyzer.py
하위 호환 shim - 실제 구현은 modules.risk.keyword_analyzer 로 이동.
"""
from modules.risk.keyword_analyzer import (  # noqa: F401
    RISK_KEYWORDS,
    analyze_keywords,
    save_risk_flags,
    get_risk_score,
    get_risk_level,
    get_risk_flags,
)
