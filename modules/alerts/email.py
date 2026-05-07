"""
modules/alerts/email.py
SMTP 이메일 알림.

설정: SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD / SMTP_FROM / SMTP_TO
미설정이거나 USE_MOCK_APIS=true 면 콘솔 fallback.

Gmail 사용 시: 2단계 인증 + 앱 비밀번호 발급 권장 (SMTP_PASSWORD 에 입력).
"""
from __future__ import annotations

import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.config import (
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_TO,
    SMTP_USE_TLS,
    SMTP_USER,
    USE_MOCK_APIS,
)
from core.logger import log


def _is_configured() -> bool:
    return all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_TO])


def _to_html(text: str) -> str:
    """HTML 본문 변환 - <b>/<i>/<code> 유지, 줄바꿈은 <br>."""
    return text.replace("\n", "<br>")


def send_message(text: str, subject: str = "[경매·공매 AI] 알림") -> bool:
    if USE_MOCK_APIS or not _is_configured():
        log.info(f"[mock-email] {subject} - {text[:60]}...")
        print(f"\n[mock 이메일] {subject}\n" + "-" * 40)
        print(re.sub(r"<[^>]+>", "", text))
        print("-" * 40 + "\n")
        return True

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = SMTP_TO

    plain = re.sub(r"<[^>]+>", "", text)
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(_to_html(text), "html", "utf-8"))

    try:
        if SMTP_USE_TLS:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        log.info("[email] 전송 성공")
        return True
    except Exception as e:
        log.error(f"[email] 예외: {e}")
        return False
