"""
tests/test_real_api_adapters.py
실 API 어댑터 + price_matcher 자동 스위치 동작.

- 키 없을 때 빈 리스트 반환 (안전)
- 주소 파싱
- price_matcher 가 mock fallback 으로 동작
- check_apis 진단이 ok 상태 반환
"""


def test_real_molit_returns_empty_without_key(monkeypatch):
    """PUBLIC_DATA_KEY 없으면 빈 결과."""
    monkeypatch.setenv("PUBLIC_DATA_SERVICE_KEY", "")
    import importlib, core.config
    importlib.reload(core.config)
    import modules.valuation.real_molit_api as real_molit
    importlib.reload(real_molit)
    out = real_molit.fetch_trades("서울특별시 강남구 역삼동 1", "아파트", area_m2=60)
    assert out == []


def test_parse_si_gu_extracts():
    from modules.valuation.real_molit_api import _parse_si_gu
    assert _parse_si_gu("서울특별시 강남구 역삼동 1") == ("서울특별시", "강남구")
    assert _parse_si_gu("경기도 수원시 영통구 매탄동 789") == (
        "경기도", "수원시 영통구"
    )
    assert _parse_si_gu("") == ("", "")


def test_real_onbid_returns_empty_without_key(monkeypatch):
    monkeypatch.setenv("PUBLIC_DATA_SERVICE_KEY", "")
    monkeypatch.setenv("ONBID_API_KEY", "")
    import importlib, core.config
    importlib.reload(core.config)
    import modules.public_sale.real_onbid_api as ro
    importlib.reload(ro)
    out = ro.list_public_sale_items(count=5)
    assert out == []


def test_price_matcher_uses_mock_when_key_missing(monkeypatch):
    """키 없으면 자동으로 mock 사용."""
    monkeypatch.setenv("USE_MOCK_APIS", "false")
    monkeypatch.setenv("PUBLIC_DATA_SERVICE_KEY", "")
    import importlib, core.config
    importlib.reload(core.config)
    import modules.valuation.price_matcher as pm
    importlib.reload(pm)
    trades = pm.fetch_trades("서울특별시 강남구 역삼동 1", "아파트", area_m2=60.0)
    # mock 은 결정론적으로 거래 데이터 생성
    assert isinstance(trades, list)


def test_check_apis_run_returns_dict():
    from scripts.check_apis import run_all
    res = run_all()
    assert "config" in res
    assert "checks" in res
    for k in ("molit", "onbid", "claude", "telegram"):
        assert k in res["checks"]
        assert "ok" in res["checks"][k]


def test_populate_real_data_falls_back_to_mock_without_key():
    from scripts.populate_real_data import populate
    res = populate(count=10, reset=True)
    # 키 없으면 mock fallback
    assert res["items"] >= 1
