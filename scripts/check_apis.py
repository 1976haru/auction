"""
scripts/check_apis.py
설정된 외부 API 키와 연결 상태를 진단한다.

체크 항목
- USE_MOCK_APIS / USE_AI 플래그
- 국토부 실거래가 (PUBLIC_DATA_SERVICE_KEY)
- 온비드 공매 (PUBLIC_DATA_SERVICE_KEY 공용 또는 ONBID_API_KEY)
- Anthropic Claude (ANTHROPIC_API_KEY)
- 텔레그램 봇 (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)

사용
    python scripts/check_apis.py
    python scripts/check_apis.py --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import config  # noqa: E402
from core.logger import log  # noqa: E402


def _mask(value: str | None) -> str:
    if not value:
        return "(미설정)"
    if len(value) <= 6:
        return "***"
    return f"{value[:3]}...{value[-3:]}"


def check_molit() -> dict:
    if not config.PUBLIC_DATA_KEY:
        return {"status": "missing_key", "ok": False,
                 "note": "PUBLIC_DATA_SERVICE_KEY 미설정"}
    try:
        from modules.price.molit_api import fetch_apt_trades
        # 서울 강남구 11680, 최근 1개월 1건이라도 오면 OK
        from datetime import datetime, timedelta
        ym = (datetime.now() - timedelta(days=30)).strftime("%Y%m")
        trades = fetch_apt_trades("11680", ym)
        return {"status": "ok" if isinstance(trades, list) else "unknown", "ok": True,
                 "sample_count": len(trades),
                 "note": f"강남구 {ym} 거래 {len(trades)}건 응답"}
    except Exception as e:
        return {"status": "error", "ok": False, "note": str(e)[:100]}


def check_onbid() -> dict:
    if not config.PUBLIC_DATA_KEY and not config.ONBID_API_KEY:
        return {"status": "missing_key", "ok": False,
                 "note": "PUBLIC_DATA_SERVICE_KEY 또는 ONBID_API_KEY 미설정"}
    try:
        from modules.public_sale.onbid_client import fetch_public_sale_list
        items = fetch_public_sale_list(region="서울특별시", page_size=5)
        return {"status": "ok", "ok": True, "sample_count": len(items),
                 "note": f"서울 공매 5건 요청 -> {len(items)}건 응답"}
    except Exception as e:
        return {"status": "error", "ok": False, "note": str(e)[:100]}


def check_claude() -> dict:
    if not config.USE_AI:
        return {"status": "disabled", "ok": True,
                 "note": "USE_AI=false (의도적 비활성)"}
    if not config.ANTHROPIC_API_KEY:
        return {"status": "missing_key", "ok": False,
                 "note": "ANTHROPIC_API_KEY 미설정"}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        # 가장 작은 호출 - 모델 list 를 돌리거나 1토큰 메시지
        resp = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=8,
            messages=[{"role": "user", "content": "ping"}],
        )
        return {"status": "ok", "ok": True,
                 "model": config.ANTHROPIC_MODEL,
                 "note": f"응답 OK ({len(resp.content[0].text)}자)"}
    except ImportError:
        return {"status": "no_lib", "ok": False,
                 "note": "anthropic 패키지 미설치 (pip install anthropic)"}
    except Exception as e:
        return {"status": "error", "ok": False, "note": str(e)[:100]}


def check_slack() -> dict:
    if not config.SLACK_WEBHOOK_URL:
        return {"status": "missing_key", "ok": False,
                 "note": "SLACK_WEBHOOK_URL 미설정"}
    # 실 호출은 alert 발송이라 안 함. URL 형식만 검증.
    if not config.SLACK_WEBHOOK_URL.startswith("https://hooks.slack.com/"):
        return {"status": "invalid_url", "ok": False,
                 "note": "SLACK_WEBHOOK_URL 가 hooks.slack.com 으로 시작하지 않음"}
    return {"status": "configured", "ok": True,
             "note": "URL 형식 OK (실 발송은 alert 시점)"}


def check_discord() -> dict:
    if not config.DISCORD_WEBHOOK_URL:
        return {"status": "missing_key", "ok": False,
                 "note": "DISCORD_WEBHOOK_URL 미설정"}
    if "discord.com/api/webhooks" not in config.DISCORD_WEBHOOK_URL:
        return {"status": "invalid_url", "ok": False,
                 "note": "Discord webhook URL 형식 불일치"}
    return {"status": "configured", "ok": True,
             "note": "URL 형식 OK (실 발송은 alert 시점)"}


def check_email() -> dict:
    if not all([config.SMTP_HOST, config.SMTP_USER, config.SMTP_PASSWORD,
                config.SMTP_FROM, config.SMTP_TO]):
        return {"status": "missing_config", "ok": False,
                 "note": "SMTP_HOST/USER/PASSWORD/FROM/TO 중 일부 미설정"}
    try:
        import smtplib
        if config.SMTP_USE_TLS:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as s:
                s.ehlo()
                s.starttls()
                s.login(config.SMTP_USER, config.SMTP_PASSWORD)
        else:
            with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as s:
                s.login(config.SMTP_USER, config.SMTP_PASSWORD)
        return {"status": "ok", "ok": True,
                 "note": f"{config.SMTP_HOST}:{config.SMTP_PORT} 로그인 성공"}
    except Exception as e:
        return {"status": "error", "ok": False, "note": str(e)[:120]}


def check_telegram() -> dict:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return {"status": "missing_key", "ok": False,
                 "note": "TELEGRAM_BOT_TOKEN / CHAT_ID 미설정"}
    try:
        import requests
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getMe"
        r = requests.get(url, timeout=10)
        data = r.json() if r.status_code == 200 else {}
        if data.get("ok"):
            uname = data.get("result", {}).get("username", "?")
            return {"status": "ok", "ok": True,
                     "bot": uname, "note": f"@{uname} 인증 OK"}
        return {"status": "error", "ok": False,
                 "note": f"HTTP {r.status_code}: {data}"}
    except Exception as e:
        return {"status": "error", "ok": False, "note": str(e)[:100]}


def run_all() -> dict:
    return {
        "config": {
            "use_mock_apis": config.USE_MOCK_APIS,
            "use_ai": config.USE_AI,
            "anthropic_model": config.ANTHROPIC_MODEL,
            "regions": config.TARGET_REGIONS,
            "types": config.TARGET_TYPES,
            "db_path": config.DB_PATH,
            "key_summary": {
                "PUBLIC_DATA_SERVICE_KEY": _mask(config.PUBLIC_DATA_KEY),
                "ONBID_API_KEY": _mask(config.ONBID_API_KEY),
                "ANTHROPIC_API_KEY": _mask(config.ANTHROPIC_API_KEY),
                "TELEGRAM_BOT_TOKEN": _mask(config.TELEGRAM_BOT_TOKEN),
                "TELEGRAM_CHAT_ID": _mask(config.TELEGRAM_CHAT_ID),
                "SLACK_WEBHOOK_URL": _mask(config.SLACK_WEBHOOK_URL),
                "DISCORD_WEBHOOK_URL": _mask(config.DISCORD_WEBHOOK_URL),
                "SMTP_HOST": config.SMTP_HOST or "(미설정)",
                "SMTP_USER": _mask(config.SMTP_USER),
            },
        },
        "checks": {
            "molit": check_molit(),
            "onbid": check_onbid(),
            "claude": check_claude(),
            "telegram": check_telegram(),
            "slack": check_slack(),
            "discord": check_discord(),
            "email": check_email(),
        },
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true", help="JSON 형식 출력")
    args = p.parse_args()
    result = run_all()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return

    cfg = result["config"]
    print("=" * 60)
    print("외부 API 헬스체크")
    print("=" * 60)
    print(f"\n[설정]")
    print(f"  USE_MOCK_APIS = {cfg['use_mock_apis']}")
    print(f"  USE_AI        = {cfg['use_ai']}")
    print(f"  Model         = {cfg['anthropic_model']}")
    print(f"  지역           = {', '.join(cfg['regions'])}")
    print(f"  유형           = {', '.join(cfg['types'])}")
    print(f"  DB            = {cfg['db_path']}")
    print(f"\n[키 요약]")
    for k, v in cfg["key_summary"].items():
        print(f"  {k:<30} = {v}")

    print(f"\n[연결 상태]")
    for name, c in result["checks"].items():
        mark = "OK  " if c.get("ok") else "FAIL"
        print(f"  [{mark}] {name:<10} {c['status']:<14} {c.get('note', '')}")
    print()

    if cfg["use_mock_apis"]:
        print("주의: USE_MOCK_APIS=true 상태이므로 실제 API 키가 있어도 mock으로 동작합니다.")
        print("      운영 모드 전환은 USE_MOCK_APIS=false 로 변경하세요.\n")


if __name__ == "__main__":
    main()
