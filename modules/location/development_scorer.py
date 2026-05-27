"""
modules/location/development_scorer.py
개발 호재 점수 (최대 15점). 네이버 뉴스 검색(최근 6개월) 기사 수 기준.
USE_AI=true 시 기사 요약(여기선 구조만, 호출은 호재 요약에 한정).
"""
from __future__ import annotations

from core import config
from core.logger import log
from modules.location._mockutil import seeded_rng, use_real_naver

MAX_SCORE = 15
_NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"


def _score_by_count(count: int) -> int:
    if count >= 10:
        return 15
    if count >= 5:
        return 10
    if count >= 1:
        return 5
    return 0


def _mock_count(address: str, sigungu: str | None) -> int:
    rng = seeded_rng("development", address, sigungu or "")
    # 인기 지역은 호재 기사 많게
    base = rng.randint(0, 12)
    if sigungu and any(k in sigungu for k in ("강남", "송파", "성동", "마포", "분당")):
        base = min(15, base + rng.randint(2, 5))
    return base


def _real_news_count(query: str) -> int | None:
    try:
        import requests
        resp = requests.get(
            _NAVER_NEWS_URL,
            headers={
                "X-Naver-Client-Id": config.NAVER_CLIENT_ID,
                "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET,
            },
            params={"query": query, "display": 30, "sort": "date"},
            timeout=5,
        )
        resp.raise_for_status()
        return int(resp.json().get("total") or 0)
    except Exception as e:
        log.warning(f"[location] 네이버 뉴스 실패 -> mock: {e}")
        return None


def score_development(address: str, sigungu: str | None = None) -> dict:
    region = sigungu or address or ""
    query = f"{region} 재개발 재건축 신규노선 개발호재"

    count = None
    if use_real_naver():
        count = _real_news_count(query)
    if count is None:
        count = _mock_count(address, sigungu)

    score = _score_by_count(count)
    if count >= 10:
        desc = f"개발 호재 다수({count}건)"
    elif count >= 5:
        desc = f"개발 호재 일부({count}건)"
    elif count >= 1:
        desc = f"개발 호재 소수({count}건)"
    else:
        desc = "최근 개발 호재 미발견"

    return {
        "score": score,
        "max": MAX_SCORE,
        "news_count": count,
        "development_news": desc,
        "query": query,
    }
