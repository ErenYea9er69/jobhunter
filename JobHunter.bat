@echo off
setlocal
cd /d "%~dp0"
where pythonw >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    start "" pythonw desktop.py %*
) else (
    start "" python desktop.py %*
)
