@echo off
REM 2026-06-04: PyInstaller EXE build script for Windows

echo [build] Cleaning up previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist NaverPlaceSalesDBCollector.spec del /q NaverPlaceSalesDBCollector.spec

echo [build] Activating virtual environment and running PyInstaller...
call .venv\Scripts\activate

pyinstaller --noconfirm --onefile --windowed --name "NaverPlaceSalesDBCollector" --collect-all customtkinter "app.py"

echo [build] Copying Playwright browsers next to EXE...
if exist "%LOCALAPPDATA%\ms-playwright" (
    xcopy "%LOCALAPPDATA%\ms-playwright" "dist\ms-playwright" /E /I /Y
) else (
    echo [build] ERROR: Playwright browser folder not found: %LOCALAPPDATA%\ms-playwright
    echo [build] Run: .venv\Scripts\python.exe -m playwright install chromium
)

echo [build] Build process completed! Please check the dist/ folder.
pause
