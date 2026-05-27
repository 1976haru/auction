"""
modules/location/geocoder.py
주소 -> (위도, 경도). 카카오 Geocoding API + api_cache(TTL 30일).
키 없음/mock 모드면 주소 해시 기반 결정적 좌표 반환(대한민국 범위).
"""
from __future__ import annotations

from core import config
from core.logger import log
from modules.location._mockutil import seeded_rng, use_real_kakao

_KAKAO_GEOCODE_URL = "https://dapi.kakao.com/v2/local/search/address.json"

# 대한민국 대략 범위
_LAT_RANGE = (33.2, 38.5)
_LNG_RANGE = (126.0, 129.5)


def _mock_geocode(address: str) -> tuple[float, float]:
    rng = seeded_rng("geocode", address)
    lat = round(rng.uniform(*_LAT_RANGE), 6)
    lng = round(rng.uniform(*_LNG_RANGE), 6)
    return (lat, lng)


def geocode(address: str) -> tuple[float, float] | None:
    if not address:
        return None

    if not use_real_kakao():
        return _mock_geocode(address)

    # ── 실 API 경로 (캐시는 블록 15 core.cache 가 있으면 사용) ──
    cache_key = f"kakao_geocode:{address}"
    try:
        from core.cache import cache_get, cache_set
    except Exception:
        cache_get = cache_set = None

    if cache_get:
        cached = cache_get("kakao_geocode", cache_key)
        if cached and cached.get("lat") is not None:
            return (cached["lat"], cached["lng"])

    try:
        import requests
        resp = requests.get(
            _KAKAO_GEOCODE_URL,
            headers={"Authorization": f"KakaoAK {config.KAKAO_REST_API_KEY}"},
            params={"query": address},
            timeout=5,
        )
        resp.raise_for_status()
        docs = resp.json().get("documents") or []
        if not docs:
            log.info(f"[location] geocode 결과 없음 -> mock: {address}")
            return _mock_geocode(address)
        lat = float(docs[0]["y"])
        lng = float(docs[0]["x"])
        if cache_set:
            cache_set("kakao_geocode", cache_key, {"lat": lat, "lng": lng}, ttl_hours=24 * 30)
        return (lat, lng)
    except Exception as e:
        log.warning(f"[location] geocode 실패 -> mock 대체: {e}")
        return _mock_geocode(address)
