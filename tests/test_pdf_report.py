"""
tests/test_pdf_report.py
PDF 리포트 생성기 검증 - 단일/묶음 / 한글 폰트 / 누락 매물 처리.
"""


def _seed():
    from scripts.generate_mock_data import generate
    from scripts.run_daily_pipeline import run_pipeline
    generate(count=15, seed=42, reset=True)
    run_pipeline(use_mock=True, count=15, top=3, reset=False,
                  query="시세차익 큰 물건 3개")


def test_generate_item_report_pdf_returns_bytes():
    from agents.pdf_report_agent import generate_item_report_pdf
    from core.database import get_connection
    _seed()
    conn = get_connection()
    iid = conn.execute("SELECT id FROM items LIMIT 1").fetchone()["id"]
    conn.close()
    pdf = generate_item_report_pdf(iid)
    assert isinstance(pdf, bytes)
    assert len(pdf) > 1000  # 최소 1KB
    assert pdf[:4] == b"%PDF"  # PDF magic number


def test_generate_top_picks_pdf_multiple_pages():
    from agents.pdf_report_agent import generate_top_picks_pdf
    from core.database import get_connection
    _seed()
    conn = get_connection()
    ids = [r["id"] for r in conn.execute("SELECT id FROM items LIMIT 3").fetchall()]
    conn.close()
    pdf = generate_top_picks_pdf(ids)
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"
    # 매물 3건이면 단일보다 PDF 가 커야 함
    from agents.pdf_report_agent import generate_item_report_pdf
    single = generate_item_report_pdf(ids[0])
    assert len(pdf) > len(single)


def test_generate_item_pdf_raises_on_missing_id():
    from agents.pdf_report_agent import generate_item_report_pdf
    import pytest
    _seed()
    with pytest.raises(ValueError):
        generate_item_report_pdf(999_999)


def test_korean_font_registered_after_call():
    from agents.pdf_report_agent import _register_korean_font
    font = _register_korean_font()
    assert font in ("HYSMyeongJo-Medium", "Helvetica")
    # 두 번 호출해도 안전
    assert _register_korean_font() == font


def test_export_report_cli_imports():
    import scripts.export_report as mod
    assert hasattr(mod, "main")
