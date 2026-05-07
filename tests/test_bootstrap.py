"""
tests/test_bootstrap.py
대시보드 부트스트랩: env 복사 / 자동 시드 가드.
"""


def test_hydrate_env_from_secrets_returns_int():
    """st.secrets 가 없는 환경에서도 안전하게 0 반환."""
    from dashboard.bootstrap import _hydrate_env_from_secrets
    n = _hydrate_env_from_secrets()
    assert isinstance(n, int)
    assert n >= 0


def test_maybe_seed_when_db_empty():
    """비어있는 DB 에 자동 시드 동작."""
    from core.database import get_connection
    from dashboard.bootstrap import _maybe_seed_mock_data
    # conftest 가 임시 DB 사용. 비어있는 상태에서 시작
    seeded = _maybe_seed_mock_data()
    assert seeded is True
    conn = get_connection()
    n = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    conn.close()
    assert n >= 1


def test_maybe_seed_skipped_when_data_exists():
    """이미 데이터가 있으면 시드 안 함."""
    from scripts.generate_mock_data import generate
    from dashboard.bootstrap import _maybe_seed_mock_data
    generate(count=10, seed=42, reset=True)
    seeded = _maybe_seed_mock_data()
    assert seeded is False


def test_bootstrap_returns_dict():
    """bootstrap 함수가 streamlit 없이도 dict 반환."""
    from dashboard.bootstrap import bootstrap
    res = bootstrap()
    assert isinstance(res, dict)
    assert "hydrated" in res
    assert "seeded" in res
