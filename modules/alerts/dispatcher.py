"""
modules/alerts/dispatcher.py
다중 채널 알림 fanout.

각 채널의 send_message(text) 를 호출해서 결과를 dict 로 반환.
호출자는 채널 리스트를 명시할 수도, 기본값(설정된 모든 채널)을 사용할 수도 있다.
"""
from __future__ import annotations

from typing import Callable

from core.logger import log

CHANNELS = ("telegram", "slack", "discord", "email")


def _channel_sender(name: str) -> Callable[[str], bool] | None:
    if name == "telegram":
        from modules.alerts.telegram import send_message
        return send_message
    if name == "slack":
        from modules.alerts.slack import send_message
        return send_message
    if name == "discord":
        from modules.alerts.discord import send_message
        return send_message
    if name == "email":
        from modules.alerts.email import send_message
        return send_message
    return None


def configured_channels() -> list[str]:
    """현재 환경에 키가 설정된 채널 목록 (mock 모드여도 설정 안됐으면 제외)."""
    from core.config import (
        DISCORD_WEBHOOK_URL,
        SLACK_WEBHOOK_URL,
        SMTP_HOST,
        SMTP_PASSWORD,
        SMTP_USER,
        TELEGRAM_BOT_TOKEN,
        TELEGRAM_CHAT_ID,
    )
    out = []
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        out.append("telegram")
    if SLACK_WEBHOOK_URL:
        out.append("slack")
    if DISCORD_WEBHOOK_URL:
        out.append("discord")
    if all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD]):
        out.append("email")
    return out


def send_to_channels(text: str, channels: list[str] | None = None) -> dict[str, bool]:
    """선택된 채널들에 메시지 발송 후 채널별 성공 여부 반환.

    channels=None 이면 모든 알려진 채널 시도 (mock 모드면 콘솔 출력으로 모두 OK).
    """
    targets = channels or list(CHANNELS)
    results: dict[str, bool] = {}
    for ch in targets:
        sender = _channel_sender(ch)
        if not sender:
            log.warning(f"[dispatcher] 알 수 없는 채널: {ch}")
            results[ch] = False
            continue
        try:
            results[ch] = bool(sender(text))
        except Exception as e:
            log.error(f"[dispatcher] {ch} 발송 예외: {e}")
            results[ch] = False
    return results
