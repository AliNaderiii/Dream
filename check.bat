@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Dream doctor
chcp 65001 >nul 2>nul
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

REM Secondary script: offline diagnostics. Primary launcher is run.bat.

if not exist ".venv\Scripts\python.exe" (
    echo [Dream] Virtual environment not found.
    echo [Dream] Double-click run.bat first, or run this one command:
    echo     python -m venv .venv
    echo.
    pause
    exit /b 1
)

set "VENVPY=.venv\Scripts\python.exe"
"%VENVPY%" doctor.py
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo [Dream] All checks passed.
) else (
    echo [Dream] One or more checks failed; see the messages above.
)
pause
exit /b %EXIT_CODE%
