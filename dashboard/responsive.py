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
        /* PC: wide layout 의 좌우 여백을 적당히 유지 (너무 좁지도 넓지도 않게) */
        @media (min-width: 1200px) {
            .block-container {
                max-width: 1400px;
                padding-left: 2rem !important;
                padding-right: 2rem !important;
            }
        }
        /* 태블릿/노트북 */
        @media (min-width: 769px) and (max-width: 1199px) {
            .block-container {
                padding-left: 1.25rem !important;
                padding-right: 1.25rem !important;
            }
        }
        /* 모바일: 패딩 최소화 + 가독성 보강 */
        @media (max-width: 768px) {
            .block-container {
                padding-left: 0.6rem !important;
                padding-right: 0.6rem !important;
                padding-top: 0.75rem !important;
            }
            section[data-testid="stSidebar"] {
                min-width: 0 !important;
            }
            /* 표는 좌우 스크롤 허용해서 안 깨지게 */
            div[data-testid="stDataFrame"],
            div[data-testid="stTable"] {
                font-size: 0.82rem;
                overflow-x: auto !important;
            }
            /* 메트릭 라벨/값 모바일 가독성 */
            div[data-testid="stMetric"] label {
                font-size: 0.78rem !important;
                white-space: normal !important;
            }
            div[data-testid="stMetric"] [data-testid="stMetricValue"] {
                font-size: 1.15rem !important;
            }
            /* 다중 컬럼 모바일에서 줄간격 축소 */
            div[data-testid="stHorizontalBlock"] {
                gap: 0.35rem !important;
            }
            /* 탭이 좁으면 줄바꿈 + 스크롤 */
            div[data-testid="stTabs"] button[role="tab"] {
                font-size: 0.85rem !important;
                padding: 0.4rem 0.6rem !important;
            }
            div[data-testid="stTabs"] [role="tablist"] {
                overflow-x: auto;
                flex-wrap: nowrap;
            }
            /* 버튼 터치 타겟 최소 44px */
            .stButton > button,
            .stDownloadButton > button {
                min-height: 42px;
                font-size: 0.9rem;
            }
            /* expander 헤더 가독성 */
            div[data-testid="stExpander"] summary {
                font-size: 0.92rem;
            }
            /* 헤딩 사이즈 모바일 */
            h1 { font-size: 1.4rem !important; }
            h2 { font-size: 1.2rem !important; }
            h3 { font-size: 1.05rem !important; }
        }
        /* 컴팩트 모드 - viewport 와 무관하게 강제 좁게 표시 */
        .compact-mode div[data-testid="stMetric"] label {
            font-size: 0.78rem !important;
        }
        .compact-mode div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            font-size: 1.05rem !important;
        }
        .compact-mode div[data-testid="stHorizontalBlock"] {
            gap: 0.35rem !important;
        }
        .compact-mode div[data-testid="stDataFrame"] {
            font-size: 0.82rem;
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
