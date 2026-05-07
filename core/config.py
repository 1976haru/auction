"""
core/config.py
환경변수 로드 및 검증 — 누락 시 친절한 안내 출력
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _get(key: str, default=None, required: bool = False):
    val = os.getenv(key, default)
    if required and not val:
        print(f"\n[!] 환경변수 [{key}] 가 설정되지 않았습니다.")
        print(f"   .env 파일에 {key}=값 을 입력해 주세요.")
        print(f"   .env.example 파일을 참고하세요.\n")
    return val


def _to_bool(val, default=False):
    if val is None:
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


# Mock vs Real -------------------------------------------------------
USE_MOCK_APIS      = _to_bool(_get("USE_MOCK_APIS", "true"), default=True)

# Claude API ---------------------------------------------------------
ANTHROPIC_API_KEY  = _get("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL    = _get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
USE_AI             = _to_bool(_get("USE_AI", "false"), default=False)

# 공공 API -----------------------------------------------------------
PUBLIC_DATA_KEY    = _get("PUBLIC_DATA_SERVICE_KEY")
ONBID_API_KEY      = _get("ONBID_API_KEY")

# 텔레그램 ----------------------------------------------------------
TELEGRAM_BOT_TOKEN = _get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = _get("TELEGRAM_CHAT_ID")

# Slack -------------------------------------------------------------
SLACK_WEBHOOK_URL  = _get("SLACK_WEBHOOK_URL")

# Discord -----------------------------------------------------------
DISCORD_WEBHOOK_URL = _get("DISCORD_WEBHOOK_URL")

# Email (SMTP) ------------------------------------------------------
SMTP_HOST          = _get("SMTP_HOST")
SMTP_PORT          = int(_get("SMTP_PORT", "587"))
SMTP_USER          = _get("SMTP_USER")
SMTP_PASSWORD      = _get("SMTP_PASSWORD")
SMTP_FROM          = _get("SMTP_FROM")
SMTP_TO            = _get("SMTP_TO")
SMTP_USE_TLS       = _to_bool(_get("SMTP_USE_TLS", "true"), default=True)

# DB / 경로 ----------------------------------------------------------
DB_PATH            = _get("DB_PATH", "data/auction_agent.db")
EXPORT_DIR         = _get("EXPORT_DIR", "data/exports")
FIXTURE_DIR        = _get("FIXTURE_DIR", "data/fixtures")

# 관심 대상 기본값 ---------------------------------------------------
TARGET_REGIONS     = [r.strip() for r in _get("TARGET_REGIONS", "서울특별시,경기도,인천광역시").split(",") if r.strip()]
TARGET_TYPES       = [t.strip() for t in _get("TARGET_TYPES", "아파트,오피스텔,빌라").split(",") if t.strip()]

# 수익 계산 기본값 ---------------------------------------------------
ACQUISITION_TAX_RATE = float(_get("ACQUISITION_TAX_RATE", "0.035"))
DEFAULT_REPAIR_COST  = int(_get("DEFAULT_REPAIR_COST", "500"))
DEFAULT_EVICTION_COST = int(_get("DEFAULT_EVICTION_COST", "300"))
FINANCE_RATE         = float(_get("FINANCE_RATE", "0.04"))

# 사용자 선호 기본값 -------------------------------------------------
DEFAULT_MIN_PROFIT_MAN  = int(_get("DEFAULT_MIN_PROFIT_MAN", "3000"))   # 만원
DEFAULT_MIN_ROI         = float(_get("DEFAULT_MIN_ROI", "0.05"))


def check_required_keys():
    """필수 키 존재 여부 체크 — Mock 모드에서는 그냥 안내만 출력하고 통과"""
    missing = []
    if not USE_MOCK_APIS:
        if not PUBLIC_DATA_KEY:
            missing.append("PUBLIC_DATA_SERVICE_KEY (국토부·온비드 API)")
        if USE_AI and not ANTHROPIC_API_KEY:
            missing.append("ANTHROPIC_API_KEY (Claude AI 분석)")
    if missing:
        print("\n[i] 아직 설정되지 않은 API 키:")
        for m in missing:
            print(f"   - {m}")
        print("   -> .env 파일에 입력하면 해당 기능이 활성화됩니다.\n")
    return len(missing) == 0


def runtime_summary() -> dict:
    return {
        "use_mock_apis": USE_MOCK_APIS,
        "use_ai":        USE_AI,
        "model":         ANTHROPIC_MODEL,
        "db_path":       DB_PATH,
        "regions":       TARGET_REGIONS,
        "types":         TARGET_TYPES,
    }
