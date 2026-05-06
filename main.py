"""
main.py
진입점 - DB 초기화, 환경 확인, 간단한 CLI.
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


def main() -> None:
    print("\n[경매·공매 AI 에이전트 시작]")
    print("=" * 50)

    rt = runtime_summary()
    print(f"Mode: {'MOCK' if rt['use_mock_apis'] else 'REAL'} | "
          f"AI: {'on' if rt['use_ai'] else 'off'} | "
          f"Model: {rt['model']}")

    check_required_keys()
    init_db()
    print("[OK] DB 초기화 완료")

    if "--init-only" in sys.argv:
        print("초기화 완료 (--init-only 모드)")
        return

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args and args[0] == "recommend":
        from agents.recommendation_agent import recommend
        query = " ".join(args[1:]) or "시세차익 가장 큰 물건 5개 찾아줘"
        result = recommend(query)
        print(f"\n=== 추천 결과 (총 {result['total_found']}건 중 상위) ===")
        for i, r in enumerate(result["results"], 1):
            it = r["item"]
            print(
                f"{i}. [{r['grade']}] {it.get('address_full', '미상')[:40]} | "
                f"차익 {r['profit_estimate']:,}만원 | ROI {r['roi_estimate']:.1f}% | "
                f"위험 {r['risk_level']}"
            )
        return

    if args and args[0] == "pipeline":
        from scripts.run_daily_pipeline import run_pipeline
        run_pipeline(use_mock=True, count=100, top=5, reset=False)
        return

    print("\n사용법:")
    print("  python main.py --init-only")
    print("  python main.py recommend [문장]")
    print("  python main.py pipeline")
    print("  python scripts/generate_mock_data.py --count 100 --seed 42")
    print("  python scripts/run_daily_pipeline.py --mock --count 100 --top 5")
    print("  python scripts/run_stress_test.py --count 1000 --queries 20")
    print("  streamlit run dashboard/app.py")


if __name__ == "__main__":
    main()
