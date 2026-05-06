"""
tests/conftest.py
모든 테스트가 임시 DB를 사용하도록 강제한다.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@pytest.fixture(autouse=True)
def _temp_db(monkeypatch, tmp_path):
    db_file = tmp_path / "test_auction.db"
    monkeypatch.setenv("DB_PATH", str(db_file))
    monkeypatch.setenv("USE_MOCK_APIS", "true")
    monkeypatch.setenv("USE_AI", "false")
    monkeypatch.setenv("EXPORT_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("FIXTURE_DIR", str(tmp_path / "fixtures"))

    import importlib
    import core.config
    importlib.reload(core.config)

    # core.database 와 core.utils 는 core.config 모듈을 동적으로 참조한다.
    import core.database
    import core.utils

    # agents/modules/scripts 모듈을 invalidate해서 다시 로드되게 한다.
    drop = [
        m for m in list(sys.modules)
        if m.startswith(("agents.", "modules.", "scripts."))
    ]
    for m in drop:
        sys.modules.pop(m, None)

    core.database.reset_db()
    yield
