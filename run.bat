@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Dream
chcp 65001 >nul 2>nul
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

REM Primary Windows launcher. Double-click this file.
REM Other scripts: check.bat (diagnostics), Dream.bat / Dream-Start.bat (desktop window).

REM ---- find a system Python (only used to create .venv) -------------------
set "SYSPY="
where python >nul 2>nul
if not errorlevel 1 set "SYSPY=python"
if not defined SYSPY (
    where py >nul 2>nul
    if not errorlevel 1 set "SYSPY=py -3"
)

REM ---- create .venv if missing -------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo [Dream] Virtual environment not found. Creating .venv ...
    if defined SYSPY %SYSPY% -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        where py >nul 2>nul
        if not errorlevel 1 py -3 -m venv .venv
    )
    if not exist ".venv\Scripts\python.exe" (
        echo [Dream] Could not create .venv.
        echo [Dream] Run this one command, then double-click run.bat again:
        echo     python -m venv .venv
        echo.
        pause
        exit /b 1
    )
)

set "VENVPY=.venv\Scripts\python.exe"

REM ---- install the package if needed -------------------------------------
"%VENVPY%" -c "import dream" >nul 2>nul
if errorlevel 1 (
    echo [Dream] Installing Dream into .venv ...
    "%VENVPY%" -m pip install -e .
    if errorlevel 1 (
        echo [Dream] Install failed.
        echo [Dream] Run this one command, then double-click run.bat again:
        echo     .venv\Scripts\python -m pip install -e .
        echo.
        pause
        exit /b 1
    )
)

REM ---- Ollama must be present for the no-VPN path ------------------------
set "OLLAMA_OK="
where ollama >nul 2>nul
if not errorlevel 1 set "OLLAMA_OK=1"
if not defined OLLAMA_OK if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_OK=1"
if not defined OLLAMA_OK if exist "%ProgramFiles%\Ollama\ollama.exe" set "OLLAMA_OK=1"

if not defined OLLAMA_OK (
    "%VENVPY%" doctor.py --message ollama-missing
    echo.
    pause
    exit /b 1
)

REM Stay on the local Ollama path: do not send cloud credentials.
set "OPENAI_BASE_URL="
set "OPENAI_API_KEY="
if not defined DREAM_MODEL set "DREAM_MODEL=qwen2.5:7b"

echo [Dream] Starting Dream with local Ollama model %DREAM_MODEL%
"%VENVPY%" cli.py --backend ollama
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo [Dream] Dream exited cleanly.
) else (
    echo [Dream] Dream exited with code %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%
