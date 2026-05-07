"""
tests/test_responsive.py
반응형 헬퍼 단위 테스트.
"""


def test_compact_columns_for_returns_full_when_not_compact():
    from dashboard.responsive import compact_columns_for, is_compact
    # streamlit session_state 가 없으면 is_compact() = False -> 원래 col 수
    assert is_compact() is False
    assert compact_columns_for(4) == 4
    assert compact_columns_for(3) == 3
    assert compact_columns_for(2) == 2
    assert compact_columns_for(1) == 1


def test_is_compact_returns_bool_in_safe_default():
    from dashboard.responsive import is_compact
    assert isinstance(is_compact(), bool)
    assert is_compact() is False  # streamlit 미초기화 환경


def test_inject_mobile_css_safe_without_streamlit():
    """streamlit 컨텍스트 없이도 inject_mobile_css 가 예외 없이 종료."""
    from dashboard.responsive import inject_mobile_css
    # 호출 자체로 예외 안 나야 함 (스트림릿 미초기화 환경에서)
    inject_mobile_css()


def test_compact_mode_toggle_safe_without_streamlit():
    from dashboard.responsive import compact_mode_toggle
    # streamlit 미초기화 -> False 반환
    res = compact_mode_toggle()
    assert res is False


def test_responsive_columns_safe_without_streamlit():
    from dashboard.responsive import responsive_columns
    # streamlit 미초기화 -> None 반환 (호출자가 가드해야)
    out = responsive_columns(4)
    # 환경에 따라 None 또는 실제 columns 객체 반환 가능
    assert out is None or len(out) >= 1


def test_begin_end_compact_block_safe():
    from dashboard.responsive import begin_compact_block, end_compact_block
    begin_compact_block()
    end_compact_block()
