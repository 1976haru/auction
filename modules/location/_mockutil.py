"""
modules/location/_mockutil.py
입지 mock 값 생성을 위한 결정적 RNG 헬퍼.
같은 좌표/주소에는 항상 같은 결과를 반환한다.
"""
from __future__ import annotations

import hashlib
import random

from core import config


def use_real_kakao() -> bool:
    return (not config.USE_MOCK_APIS) and bool(config.KAKAO_REST_API_KEY)


def use_real_naver() -> bool:
    return (not config.USE_MOCK_APIS) and bool(config.NAVER_CLIENT_ID and config.NAVER_CLIENT_SECRET)


def seeded_rng(*parts) -> random.Random:
    """좌표/주소 등으로 결정적 시드 생성."""
    raw = "|".join(str(p) for p in parts)
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return random.Random(int(h[:12], 16))
