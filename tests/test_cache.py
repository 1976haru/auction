"""
tests/test_cache.py — API 캐시 (블록 15)
"""


def test_cache_set_get_roundtrip():
    from core.cache import cache_set, cache_get, make_key
    key = make_key("kakao_geocode", address="서울 마포구 망원동")
    assert cache_get("kakao_geocode", key) is None  # 최초 미스
    cache_set("kakao_geocode", key, {"lat": 37.55, "lng": 126.9}, ttl_hours=24)
    got = cache_get("kakao_geocode", key)
    assert got == {"lat": 37.55, "lng": 126.9}


def test_cache_hit_count_increments():
    from core.cache import cache_set, cache_get, make_key, cache_stats
    key = make_key("molit", si="서울", gu="마포구")
    cache_set("molit", key, [{"price": 1}], ttl_hours=24)
    cache_get("molit", key)
    cache_get("molit", key)
    stats = cache_stats()
    assert stats["by_api"]["molit"]["hits"] >= 2


def test_cache_ttl_expiry():
    """TTL 0(즉시 만료) -> 미스로 처리, cleanup으로 제거."""
    from core.cache import cache_set, cache_get, make_key, cleanup_expired
    key = make_key("naver_news", q="강남 재개발")
    cache_set("naver_news", key, {"total": 10}, ttl_hours=0)
    # ttl 0 -> expires_at = now, '> now' 조건에서 제외 -> 미스
    assert cache_get("naver_news", key) is None
    removed = cleanup_expired()
    assert removed >= 1


def test_cache_invalidate():
    from core.cache import cache_set, cache_get, make_key, cache_invalidate
    k1 = make_key("kakao_geocode", address="A")
    k2 = make_key("kakao_geocode", address="B")
    cache_set("kakao_geocode", k1, {"v": 1})
    cache_set("kakao_geocode", k2, {"v": 2})
    n = cache_invalidate("kakao_geocode")
    assert n >= 2
    assert cache_get("kakao_geocode", k1) is None


def test_geocoder_uses_cache_module(monkeypatch):
    """실 모드에서 geocoder가 core.cache를 통해 결과를 캐싱한다."""
    import importlib, core.config
    monkeypatch.setenv("USE_MOCK_APIS", "false")
    monkeypatch.setenv("KAKAO_REST_API_KEY", "dummy-key")
    importlib.reload(core.config)
    import modules.location._mockutil as mu
    importlib.reload(mu)
    import modules.location.geocoder as geo
    importlib.reload(geo)

    # requests 호출을 가짜로 대체 (네트워크 없이 좌표 반환)
    class _Resp:
        def raise_for_status(self): pass
        def json(self): return {"documents": [{"x": "127.05", "y": "37.5"}]}

    import sys, types
    fake = types.ModuleType("requests")
    fake.get = lambda *a, **k: _Resp()
    monkeypatch.setitem(sys.modules, "requests", fake)

    addr = "서울특별시 강남구 대치동"
    a = geo.geocode(addr)
    assert a == (37.5, 127.05)
    # 캐시에 저장됐는지 확인
    from core.cache import cache_get
    cached = cache_get("kakao_geocode", f"kakao_geocode:{addr}")
    assert cached and cached["lat"] == 37.5
