@echo off
REM 2026-06-04: PyInstaller EXE build script for Windows
REM 2026-07-30: removed the path that deleted the spec and rebuilt app.py
REM directly with inline CLI options (--onefile etc). NaverPlaceSalesDBCollector.spec
REM (includes the data/legal_dong_snapshot.json bundle contract) is now the
REM single build contract - bypassing it drops the legal dong Snapshot from
REM the EXE. Comments in this file must stay ASCII: cmd.exe parses .bat files
REM using the system ANSI codepage, and non-ASCII REM text in a UTF-8 file
REM can be misread as a command token.
setlocal
cd /d "%~dp0"

echo [build] Cleaning up previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Project virtual environment was not found: .venv\Scripts\python.exe
    exit /b 1
)

echo [build] Running PyInstaller with NaverPlaceSalesDBCollector.spec...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean NaverPlaceSalesDBCollector.spec

if errorlevel 1 (
    echo [ERROR] EXE build failed.
    exit /b 1
)

echo [build] Copying Playwright browsers next to EXE...
if exist "%LOCALAPPDATA%\ms-playwright" (
    xcopy "%LOCALAPPDATA%\ms-playwright" "dist\ms-playwright" /E /I /Y
) else (
    echo [build] ERROR: Playwright browser folder not found: %LOCALAPPDATA%\ms-playwright
    echo [build] Run: .venv\Scripts\python.exe -m playwright install chromium
)

echo [OK] EXE build completed. Please check the dist/ folder.
exit /b 0
