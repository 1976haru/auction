"""
modules/alerts/telegram.py
텔레그램 알림 추상화. mock 모드에서는 콘솔/로그로 출력한다.
"""
from __future__ import annotations

import requests

from core.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, USE_MOCK_APIS
from core.logger import log
from core.mock_api import mock_telegram_send


def send_message(text: str, parse_mode: str = "HTML") -> bool:
    if USE_MOCK_APIS or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return mock_telegram_send(text)

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            log.info("[telegram] 전송 성공")
            return True
        log.error(f"[telegram] 오류 {r.status_code}: {r.text}")
        return False
    except Exception as e:
        log.error(f"[telegram] 예외: {e}")
        return False


def format_briefing(briefing: dict) -> str:
    summary = briefing.get("summary", "")
    return f"<b>오늘의 경매·공매 브리핑</b>\n{summary}"


def format_top_picks(top_picks: list[dict]) -> str:
    if not top_picks:
        return "오늘 조건에 맞는 추천 물건이 없습니다."
    lines = ["<b>오늘의 추천 TOP 5</b>"]
    for i, r in enumerate(top_picks[:5], 1):
        item = r.get("item", {})
        lines.append(
            f"{i}. {item.get('address_full', '미상')[:40]} | "
            f"최저 {item.get('min_bid_price', 0):,}만원 | "
            f"예상차익 {r.get('profit_estimate', 0):,}만원"
        )
    lines.append("")
    lines.append("참고용 결과이며 권리·시세는 직접 확인이 필요합니다.")
    return "\n".join(lines)
