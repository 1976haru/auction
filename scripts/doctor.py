"""
scripts/doctor.py
실행 환경 진단 - "왜 안 돌아가는지" 한 화면에 보여준다.

체크 항목
- Python 버전
- 필수 패키지 import 가능 여부
- 선택 패키지 (anthropic / playwright / libsql)
- .env / .env.example 존재 여부
- USE_MOCK_APIS / USE_AI 상태
- DB 초기화 가능 여부 (테이블 생성 후 row count)
- data/exports / data/fixtures / logs 폴더 존재
- ci.yml YAML 파싱 + 핵심 step 존재
- 핵심 명령 가이드 출력

사용
    python scripts/doctor.py
    python scripts/doctor.py --json
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


REQUIRED_PACKAGES = [
    "requests", "dotenv", "streamlit", "pandas", "plotly", "reportlab", "pytest",
]
OPTIONAL_PACKAGES = ["anthropic", "playwright", "pdfplumber", "libsql_experimental"]


def check_python() -> dict:
    v = sys.version_info
    ok = v.major == 3 and v.minor >= 9
    return {
        "name": "Python",
        "ok": ok,
        "value": f"{v.major}.{v.minor}.{v.micro}",
        "note": "OK" if ok else "Python 3.9+ 권장",
    }


def check_package(pkg: str, required: bool) -> dict:
    try:
        m = importlib.import_module(pkg)
        version = getattr(m, "__version__", "?")
        return {"name": pkg, "ok": True, "value": version,
                 "note": "(필수)" if required else "(선택)"}
    except ImportError:
        return {"name": pkg, "ok": not required,
                 "value": "(미설치)",
                 "note": "필수 - pip install -r requirements.txt" if required else "선택 - 필요할 때만 설치"}


def check_env_files() -> list[dict]:
    out = []
    for fn in [".env.example", ".env"]:
        p = Path(ROOT) / fn
        ok = p.exists()
        out.append({
            "name": fn, "ok": ok or fn == ".env",  # .env 는 없어도 OK
            "value": "있음" if ok else "없음",
            "note": "" if fn == ".env.example" else "(선택, 실 키 보관용)",
        })
    return out


def check_runtime_flags() -> list[dict]:
    try:
        from core.config import USE_AI, USE_MOCK_APIS
    except Exception as e:
        return [{"name": "config 로드", "ok": False, "value": "FAIL", "note": str(e)[:80]}]
    return [
        {"name": "USE_MOCK_APIS", "ok": True, "value": str(USE_MOCK_APIS),
         "note": "mock-first 데모면 true 권장"},
        {"name": "USE_AI", "ok": True, "value": str(USE_AI),
         "note": "Claude 호출하려면 true + ANTHROPIC_API_KEY 필요"},
    ]


def check_db_init() -> dict:
    try:
        from core.database import get_connection, init_db
        init_db()
        conn = get_connection()
        n_tables = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        n_items = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
        conn.close()
        return {"name": "DB 초기화", "ok": True,
                 "value": f"테이블 {n_tables}개 / items {n_items}건",
                 "note": "OK"}
    except Exception as e:
        return {"name": "DB 초기화", "ok": False,
                 "value": "FAIL", "note": str(e)[:120]}


def check_dirs() -> list[dict]:
    out = []
    for sub in ["data", "data/exports", "data/fixtures", "logs"]:
        p = Path(ROOT) / sub
        out.append({
            "name": f"폴더 {sub}", "ok": p.exists(),
            "value": "있음" if p.exists() else "없음",
            "note": "자동 생성됨" if not p.exists() else "",
        })
    return out


def check_ci_yaml() -> dict:
    p = Path(ROOT) / ".github" / "workflows" / "ci.yml"
    if not p.exists():
        return {"name": "ci.yml", "ok": False, "value": "없음",
                 "note": "GitHub Actions 워크플로 누락"}
    try:
        try:
            import yaml
        except ImportError:
            return {"name": "ci.yml", "ok": True,
                     "value": "발견 (yaml 미설치 - 구조 검증 스킵)",
                     "note": "pip install pyyaml 로 검증 활성화"}
        with open(p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        steps = data.get("jobs", {}).get("test", {}).get("steps", [])
        names = [s.get("name", "") for s in steps]
        required = ["Init DB", "Generate small mock data",
                     "Run daily pipeline (mock, count=50)", "Run pytest"]
        missing = [r for r in required if not any(r in n for n in names)]
        if missing:
            return {"name": "ci.yml", "ok": False,
                     "value": f"step 누락: {missing}", "note": ""}
        return {"name": "ci.yml", "ok": True,
                 "value": f"{len(steps)} steps", "note": "OK"}
    except Exception as e:
        return {"name": "ci.yml", "ok": False,
                 "value": "FAIL", "note": str(e)[:120]}


def run_diagnostics() -> dict:
    checks = []
    checks.append(check_python())
    for pkg in REQUIRED_PACKAGES:
        checks.append(check_package(pkg, required=True))
    for pkg in OPTIONAL_PACKAGES:
        checks.append(check_package(pkg, required=False))
    checks.extend(check_env_files())
    checks.extend(check_runtime_flags())
    checks.append(check_db_init())
    checks.extend(check_dirs())
    checks.append(check_ci_yaml())
    return {"checks": checks}


GUIDE = """
[핵심 명령]
  python main.py --init-only
  python scripts/generate_mock_data.py --count 100 --seed 42 --reset
  python scripts/run_daily_pipeline.py --mock --count 100 --top 5
  python main.py recommend "시세차익 큰 물건 5개 찾아줘"
  python -m pytest tests/ -v
  streamlit run dashboard/app.py

[헬스체크]
  python scripts/check_apis.py        # 8개 외부 API 인증/연결
  python scripts/check_court_auction.py # 법원경매 selector 검증

[운영 도구]
  python scripts/run_backtest.py --mode all
  python scripts/run_auto_tune.py --max 50 --apply
  python scripts/clear_qa_cache.py --clear
  python scripts/backup_db.py
  python scripts/export_results.py --target all
  python scripts/export_report.py --item-id 63
"""


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    res = run_diagnostics()
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
        return

    print("=" * 70)
    print("[doctor] 실행 환경 진단")
    print("=" * 70)
    fails = []
    for c in res["checks"]:
        mark = "OK  " if c.get("ok") else "FAIL"
        line = f"  [{mark}] {c['name']:<28} = {c.get('value', '-')}"
        if c.get("note"):
            line += f"   ({c['note']})"
        print(line)
        if not c.get("ok"):
            fails.append(c["name"])

    print()
    if fails:
        print(f"[!] FAIL 항목 {len(fails)}개: {', '.join(fails)}")
        print("    -> requirements 설치 / 폴더 생성 / config 확인 후 재실행")
    else:
        print("[OK] 환경 모두 정상.")
    print(GUIDE)


if __name__ == "__main__":
    main()
