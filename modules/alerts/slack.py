"""
modules/alerts/slack.py
Slack Incoming Webhook 알림.

설정: SLACK_WEBHOOK_URL (https://hooks.slack.com/services/...)
미설정이거나 USE_MOCK_APIS=true 면 콘솔 fallback.
"""
from __future__ import annotations

import re

import requests

from core.config import SLACK_WEBHOOK_URL, USE_MOCK_APIS
from core.logger import log


def _strip_html(text: str) -> str:
    """텔레그램용 HTML 태그를 Slack mrkdwn 으로 변환."""
    text = re.sub(r"<b>(.*?)</b>", r"*\1*", text)
    text = re.sub(r"<i>(.*?)</i>", r"_\1_", text)
    text = re.sub(r"<code>(.*?)</code>", r"`\1`", text)
    text = re.sub(r"<[^>]+>", "", text)
    return text


def send_message(text: str) -> bool:
    if USE_MOCK_APIS or not SLACK_WEBHOOK_URL:
        log.info(f"[mock-slack] {text[:80]}...")
        print("\n[mock Slack 알림]\n" + "-" * 40)
        print(_strip_html(text))
        print("-" * 40 + "\n")
        return True

    payload = {"text": _strip_html(text), "mrkdwn": True}
    try:
        r = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        if r.status_code == 200:
            log.info("[slack] 전송 성공")
            return True
        log.error(f"[slack] HTTP {r.status_code}: {r.text[:200]}")
        return False
    except Exception as e:
        log.error(f"[slack] 예외: {e}")
        return False
