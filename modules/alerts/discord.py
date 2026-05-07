"""
modules/alerts/discord.py
Discord Webhook 알림.

설정: DISCORD_WEBHOOK_URL (https://discord.com/api/webhooks/...)
미설정이거나 USE_MOCK_APIS=true 면 콘솔 fallback.
"""
from __future__ import annotations

import re

import requests

from core.config import DISCORD_WEBHOOK_URL, USE_MOCK_APIS
from core.logger import log


def _to_markdown(text: str) -> str:
    text = re.sub(r"<b>(.*?)</b>", r"**\1**", text)
    text = re.sub(r"<i>(.*?)</i>", r"*\1*", text)
    text = re.sub(r"<code>(.*?)</code>", r"`\1`", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def send_message(text: str) -> bool:
    if USE_MOCK_APIS or not DISCORD_WEBHOOK_URL:
        log.info(f"[mock-discord] {text[:80]}...")
        print("\n[mock Discord 알림]\n" + "-" * 40)
        print(_to_markdown(text))
        print("-" * 40 + "\n")
        return True

    # Discord 메시지 길이 제한 2000자
    body = _to_markdown(text)[:1990]
    try:
        r = requests.post(DISCORD_WEBHOOK_URL, json={"content": body}, timeout=10)
        if r.status_code in (200, 204):
            log.info("[discord] 전송 성공")
            return True
        log.error(f"[discord] HTTP {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        log.error(f"[discord] 예외: {e}")
        return False
