@echo off
setlocal
cd /d "%~dp0"

echo =========================================================
echo   Starting JobHunter Turnkey Copilot
echo =========================================================

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python was not found in your PATH.
    echo Please install Python 3.11+ from https://www.python.org/
    pause
    exit /b 1
)

python run.py %*
if %ERRORLEVEL% neq 0 (
    pause
)

