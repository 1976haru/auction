"""
main.py
진입점 - DB 초기화, 환경 확인, CLI.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.config import check_required_keys, runtime_summary
from core.database import init_db
from core.logger import log


USAGE = """\
사용법:
  python main.py --init-only
  python main.py seed [--count 100] [--seed 42] [--reset]
  python main.py pipeline [--mock] [--count 100] [--top 5]
  python main.py recommend "<자연어 질문>"
  python main.py briefing
  python main.py actions
  python main.py stress [--count 500] [--queries 5]
  streamlit run dashboard/app.py
"""


def _arg(args: list[str], name: str, default=None, cast=str):
    """간단한 인자 파서: --name value."""
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            try:
                return cast(args[i + 1])
            except Exception:
                return default
    return default


def _flag(args: list[str], name: str) -> bool:
    return name in args


def _print_recommend(result: dict) -> None:
    print(f"\n=== 추천 결과 (총 {result['total_found']}건 중 상위) ===")
    for i, r in enumerate(result["results"], 1):
        it = r["item"]
        print(
            f"{i}. [{r['grade']}] {it.get('address_full', '미상')[:40]} | "
            f"차익 {r['profit_estimate']:,}만원 | ROI {r['roi_estimate']:.1f}% | "
            f"위험 {r['risk_level']} | 점수 {r['score']:.1f}"
        )


def main() -> None:
    print("\n[경매·공매 AI 에이전트 시작]")
    print("=" * 50)

    rt = runtime_summary()
    print(
        f"Mode: {'MOCK' if rt['use_mock_apis'] else 'REAL'} | "
        f"AI: {'on' if rt['use_ai'] else 'off'} | "
        f"Model: {rt['model']}"
    )

    check_required_keys()
    init_db()
    print("[OK] DB 초기화 완료")

    if "--init-only" in sys.argv:
        print("초기화 완료 (--init-only 모드)")
        return

    raw = sys.argv[1:]
    sub_args = [a for a in raw if not a.startswith("-")]
    cmd = sub_args[0] if sub_args else None

    if cmd == "recommend":
        from agents.recommendation_agent import recommend
        query = " ".join(sub_args[1:]) or "시세차익 가장 큰 물건 5개 찾아줘"
        result = recommend(query)
        _print_recommend(result)
        return

    if cmd == "pipeline":
        from scripts.run_daily_pipeline import run_pipeline
        count = _arg(raw, "--count", 100, int)
        top = _arg(raw, "--top", 5, int)
        reset = _flag(raw, "--reset")
        run_pipeline(use_mock=True, count=count, top=top, reset=reset)
        return

    if cmd == "seed":
        from scripts.generate_mock_data import generate as gen_mock
        count = _arg(raw, "--count", 100, int)
        seed = _arg(raw, "--seed", 42, int)
        reset = _flag(raw, "--reset")
        result = gen_mock(count=count, seed=seed, reset=reset)
        print(f"\n[OK] mock 데이터 생성: 물건 {result['items']}건 / 문서 {result['documents']}건")
        return

    if cmd == "briefing":
        from agents.daily_briefing_agent import generate_briefing
        b = generate_briefing()
        print("\n=== 오늘의 브리핑 ===")
        print(f"기준일: {b['run_date']}")
        print(f"전체 {b['total_items']}건 / 분석 {b['analyzed_items']}건 / 매칭 {b['matched_items']}건")
        print(f"고위험: {b['high_risk_items']}건 / 검토 후보(A·B·C) {len(b['top_picks'])}건 / 주의(D·X) {len(b['warning_picks'])}건")
        print("---")
        print(b["summary"])
        if b.get("top_picks"):
            print("\n[추천 TOP]")
            for i, r in enumerate(b["top_picks"], 1):
                it = r.get("item", {})
                print(
                    f"  {i}. [{r.get('grade')}] {it.get('address_full', '미상')[:40]} | "
                    f"차익 {r.get('profit_estimate', 0):,}만원 | ROI {r.get('roi_estimate', 0):.1f}%"
                )
        return

    if cmd == "actions":
        from agents.action_planner_agent import list_today_actions, plan_actions
        n = plan_actions()
        rows = list_today_actions(limit=20)
        print(f"\n=== 오늘 할 일 ({n}건 생성, 상위 {len(rows)} 표시) ===")
        for a in rows:
            print(
                f"- [{a.get('priority', 'medium').upper()}] {a.get('title', '')} | "
                f"{a.get('address_full') or 'item#' + str(a.get('item_id'))} | "
                f"{a.get('detail', '')[:60]}"
            )
        return

    if cmd == "stress":
        from scripts.run_stress_test import run as run_stress
        count = _arg(raw, "--count", 500, int)
        queries = _arg(raw, "--queries", 5, int)
        run_stress(count=count, queries=queries, reset=True, scenario="cli")
        return

    print(USAGE)


if __name__ == "__main__":
    main()
