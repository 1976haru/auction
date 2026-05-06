"""
tests/test_pipeline_and_stress.py
전체 파이프라인과 빠른 스트레스 테스트(소규모) 검증.
"""


def test_daily_pipeline_smoke():
    from scripts.run_daily_pipeline import run_pipeline
    summary = run_pipeline(use_mock=True, count=20, top=3, reset=True,
                            query="시세차익 큰 물건 3개")
    assert summary["price_analyzed"] >= 1
    assert "exports" in summary and "json" in summary["exports"]


def test_quick_stress_small():
    """빠른 스트레스 테스트만 실행 (CI 시간 절약)."""
    from scripts.run_stress_test import run
    details = run(count=50, queries=3, reset=True, scenario="quick")
    assert details["count"] == 50
    assert details["queries"] == 3
    # elapsed 키 존재
    assert "elapsed" in details and "total" in details["elapsed"]
