"""
dashboard/bootstrap.py
Streamlit 앱이 시작될 때 한 번 실행되는 초기화 로직.

- Streamlit Cloud 의 st.secrets 를 os.environ 으로 복사 (config.py 가
  os.getenv 로 읽기 때문)
- DB 가 비어 있으면 mock 데이터 자동 시드 (Streamlit Cloud ephemeral fs 대비)
- 첫 실행 시 1회만 동작 (st.session_state 로 가드)
"""
from __future__ import annotations

import os


def _hydrate_env_from_secrets() -> int:
    """st.secrets 의 string 값을 os.environ 에 복사.

    Streamlit Cloud / secrets.toml 가 없는 환경에서도 안전하게 0 반환.
    Returns: 복사된 키 수
    """
    try:
        import streamlit as st
        if not hasattr(st, "secrets"):
            return 0
        # st.secrets 접근 자체가 secrets.toml 없으면 예외 던질 수 있음
        try:
            keys = list(st.secrets.keys())
        except Exception:
            return 0
        secrets = st.secrets
    except Exception:
        return 0
    n = 0
    for key in keys:
        try:
            val = secrets[key]
            if isinstance(val, (str, int, float, bool)):
                if os.environ.get(key):
                    continue
                os.environ[key] = str(val)
                n += 1
        except Exception:
            continue
    return n


def _maybe_seed_mock_data() -> bool:
    """DB 가 비어 있으면 mock 데이터를 자동 시드한다."""
    # config 모듈은 hydrate 후에 import 해야 환경변수 반영됨
    import importlib
    import core.config
    importlib.reload(core.config)

    from core.database import get_connection, init_db

    init_db()
    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    conn.close()
    if n > 0:
        return False

    # 비어있다 -> 자동 시드 + 파이프라인 한 번 실행
    from scripts.run_daily_pipeline import run_pipeline
    run_pipeline(use_mock=True, count=80, top=5, reset=False,
                  query="시세차익 큰 물건 5개")
    return True


def bootstrap() -> dict:
    """앱 부트스트랩. session_state 에 'bootstrapped' 가드.

    Returns:
        {"hydrated": int, "seeded": bool}
    """
    try:
        import streamlit as st
        try:
            if st.session_state.get("bootstrapped"):
                return st.session_state["bootstrap_result"]
        except Exception:
            pass
    except Exception:
        pass

    hydrated = _hydrate_env_from_secrets()
    seeded = False
    try:
        seeded = _maybe_seed_mock_data()
    except Exception as e:
        # 시드 실패해도 앱은 뜨도록
        try:
            import streamlit as st
            st.warning(f"부트스트랩 경고: 자동 시드 실패 ({e}). 수동으로 mock 데이터를 생성하세요.")
        except Exception:
            pass

    result = {"hydrated": hydrated, "seeded": seeded}
    try:
        import streamlit as st
        try:
            st.session_state["bootstrapped"] = True
            st.session_state["bootstrap_result"] = result
        except Exception:
            pass
    except Exception:
        pass
    return result
