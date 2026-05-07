"""
dashboard/responsive.py
모바일/좁은 화면 호환 헬퍼.

Streamlit 은 viewport 를 직접 노출하지 않아서 자동 감지가 어렵다.
대신 사이드바에 "컴팩트 모드" 토글을 두고 사용자가 명시적으로 켜면
- 다중 column 을 1열 또는 2열로 축소
- 메트릭/표 폰트 크기 축소
- 일부 보조 차트 숨김
방식으로 모바일 / 작은 창에서 가독성을 끌어올린다.

사용
    import streamlit as st
    from dashboard.responsive import (
        compact_mode_toggle, is_compact, responsive_columns, inject_mobile_css
    )

    inject_mobile_css()
    with st.sidebar:
        compact_mode_toggle()

    cols = responsive_columns(4)  # 데스크톱 4col / 컴팩트 2col
"""
from __future__ import annotations


COMPACT_KEY = "compact_mode"


def inject_mobile_css() -> None:
    """공용 모바일 친화 CSS. 한 번만 주입."""
    try:
        import streamlit as st
    except Exception:
        return
    st.markdown(
        """
        <style>
        /* 좁은 화면에서 메인 컨테이너 패딩 축소 */
        @media (max-width: 768px) {
            .block-container {
                padding-left: 0.75rem !important;
                padding-right: 0.75rem !important;
                padding-top: 1rem !important;
            }
            /* 사이드바 자동 collapse 시에도 토글 버튼 잘 보이게 */
            section[data-testid="stSidebar"] {
                min-width: 0 !important;
            }
            /* 표 폰트 살짝 축소 */
            div[data-testid="stDataFrame"] {
                font-size: 0.85rem;
            }
            /* 메트릭 라벨/값 살짝 축소 */
            div[data-testid="stMetric"] label {
                font-size: 0.8rem !important;
            }
            div[data-testid="stMetric"] [data-testid="stMetricValue"] {
                font-size: 1.2rem !important;
            }
        }
        /* 컴팩트 모드 - viewport 와 무관하게 강제 좁게 표시 */
        .compact-mode div[data-testid="stMetric"] label {
            font-size: 0.8rem !important;
        }
        .compact-mode div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-size: 1.1rem !important;
        }
        .compact-mode div[data-testid="stHorizontalBlock"] {
            gap: 0.4rem !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def is_compact() -> bool:
    """현재 컴팩트 모드인지."""
    try:
        import streamlit as st
        return bool(st.session_state.get(COMPACT_KEY, False))
    except Exception:
        return False


def compact_mode_toggle(label: str = "컴팩트 모드 (모바일)") -> bool:
    """사이드바에 토글을 그리고 현재 상태 반환."""
    try:
        import streamlit as st
        v = st.toggle(label, value=is_compact(), key=COMPACT_KEY,
                       help="좁은 화면 / 모바일에서 다중 컬럼을 줄여 가독성 향상")
        return bool(v)
    except Exception:
        return False


def compact_columns_for(n_desktop: int) -> int:
    """컴팩트 모드일 때 권장 col 수."""
    if not is_compact():
        return n_desktop
    if n_desktop >= 4:
        return 2
    if n_desktop == 3:
        return 1
    return n_desktop  # 2 이하는 그대로


def responsive_columns(n_desktop: int):
    """st.columns 의 반응형 wrapper. 컴팩트 모드면 col 수 축소."""
    try:
        import streamlit as st
        n = compact_columns_for(n_desktop)
        return st.columns(n)
    except Exception:
        return None


def begin_compact_block() -> None:
    """compact-mode CSS 클래스 컨테이너 열기."""
    try:
        import streamlit as st
        if is_compact():
            st.markdown('<div class="compact-mode">', unsafe_allow_html=True)
    except Exception:
        pass


def end_compact_block() -> None:
    try:
        import streamlit as st
        if is_compact():
            st.markdown("</div>", unsafe_allow_html=True)
    except Exception:
        pass
