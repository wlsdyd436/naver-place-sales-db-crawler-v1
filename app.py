"""데스크톱 앱 실행 진입점.

`src.ui.run_app`을 호출하기 전에 Playwright 브라우저 실행에 필요한
PLAYWRIGHT_BROWSERS_PATH 환경 변수만 준비한다. 목록 수집·홈페이지 보강·
Excel 저장 등 실제 동작은 전부 `src` 하위 모듈에 위임하며, 이 파일은
어떤 수집·파싱 로직도 직접 구현하지 않는다.
"""
import os
import sys

# 2026-06-04: 판매형 EXE는 exe 옆 dist/ms-playwright 브라우저 폴더를 우선 사용합니다.
if getattr(sys, "frozen", False):
    bundled_browser_path = os.path.join(
        os.path.dirname(sys.executable),
        "ms-playwright",
    )
else:
    bundled_browser_path = os.path.join(os.getcwd(), "dist", "ms-playwright")

if os.path.exists(bundled_browser_path):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = bundled_browser_path
else:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "ms-playwright",
    )

from src.ui import run_app


if __name__ == "__main__":
    run_app()
