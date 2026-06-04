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
    # 2026-06-04: CustomTkinter UI 실행 진입점입니다.
    run_app()
