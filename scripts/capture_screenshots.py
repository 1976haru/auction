"""
scripts/capture_screenshots.py

Playwright (Chromium) 으로 정적 대시보드의 주요 화면을 자동 캡처한다.
GitHub Actions 의 screenshot.yml 워크플로에서 호출되며, 결과물은
docs/screenshots/ 에 저장돼 README 와 GitHub Pages 모두에서 참조된다.

생성 파일:
- desktop-light.png   (1280x800, 라이트 모드, 전체 페이지)
- desktop-dark.png    (1280x800, 다크 모드, 뷰포트만)
- mobile-light.png    (390x844, 라이트 모드, 전체 페이지)
- detail-modal.png    (1280x800, 매물 상세 모달 열린 상태)

로컬에서도 직접 실행 가능:
    pip install playwright
    playwright install chromium
    python scripts/capture_screenshots.py
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
OUT = DOCS / "screenshots"
PORT = 8765
URL = f"http://localhost:{PORT}/"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # 정적 서버 시작 (백그라운드)
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "-d", str(DOCS)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(1)

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()

            def shoot(label: str, *, viewport, color_scheme="light",
                      mobile=False, full_page=True, open_first_card=False):
                ctx_kwargs = {"viewport": viewport, "color_scheme": color_scheme}
                if mobile:
                    ctx_kwargs.update({
                        "device_scale_factor": 2,
                        "is_mobile": True,
                        "has_touch": True,
                    })
                ctx = browser.new_context(**ctx_kwargs)
                page = ctx.new_page()
                page.goto(URL, wait_until="networkidle")
                # 카드가 렌더링될 때까지 대기
                page.wait_for_selector("#items-card-view article.item-card",
                                       timeout=10000)
                # 차트/시뮬레이터 등 그릴 시간을 충분히
                page.wait_for_timeout(700)
                if open_first_card:
                    page.click("#items-card-view article.item-card:first-child")
                    page.wait_for_selector("#detail-modal:not([hidden])",
                                            timeout=3000)
                    # 상세 모달 안의 시세 트렌드/시뮬레이터/점수 분해 그릴 시간
                    page.wait_for_timeout(800)
                target = OUT / f"{label}.png"
                page.screenshot(path=str(target), full_page=full_page)
                size = target.stat().st_size
                print(f"[OK] {target.relative_to(ROOT)} ({size:,} bytes)")
                ctx.close()

            shoot("desktop-light",
                  viewport={"width": 1280, "height": 800},
                  color_scheme="light", full_page=True)
            shoot("desktop-dark",
                  viewport={"width": 1280, "height": 800},
                  color_scheme="dark", full_page=False)
            shoot("mobile-light",
                  viewport={"width": 390, "height": 844},
                  color_scheme="light", mobile=True, full_page=True)
            shoot("detail-modal",
                  viewport={"width": 1280, "height": 800},
                  color_scheme="light", full_page=False, open_first_card=True)

            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=2)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
