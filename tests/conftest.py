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


@pytest.fixture
def mock_profile():
    """테스트용 사용자 프로필 (자기자본 1.5억)."""
    return {
        "capital_max": 150_000_000, "capital_min": 50_000_000,
        "annual_income": 60_000_000, "other_debt_monthly": 300_000,
        "loan_rate": 0.04, "ltv": 0.70, "dsr": 0.40, "loan_years": 30,
        "scenario_weights": {"short_sale": 0.30, "rental": 0.40, "residence": 0.30},
        "annual_appreciation": 0.03, "is_one_house": True, "min_roi": 0.08,
        "interest_regions": ["마포구", "성동구"],
    }


@pytest.fixture
def sample_items():
    """샘플 물건 5건 생성 후 item_id 리스트 반환."""
    from core.database import upsert_item
    specs = [
        ("마포구", "아파트", 28000, 40000, 84.0),
        ("성동구", "아파트", 32000, 45000, 76.0),
        ("강남구", "오피스텔", 18000, 25000, 33.0),
        ("노원구", "빌라", 15000, 22000, 59.0),
        ("송파구", "아파트", 60000, 80000, 110.0),
    ]
    ids = []
    for i, (gu, it, mb, ap, area) in enumerate(specs):
        ids.append(upsert_item({
            "source": "test", "case_no": f"2024타경E{i}", "item_type": it,
            "address_full": f"서울특별시 {gu} 테스트동", "address_si": "서울특별시",
            "address_gu": gu, "area_m2": area, "min_bid_price": mb,
            "appraisal_price": ap, "fail_count": i % 3, "status": "active",
        }))
    return ids
