@echo off
REM Secondary launcher (desktop window + .env). Primary launcher is run.bat.
chcp 65001 >nul 2>nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Dream

echo.
echo  ==========================================
echo   Dream - starting
echo  ==========================================
echo.

REM ---- 1. find the interpreter -------------------------------------------
set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

if not defined PY (
    echo  [!] virtual environment not found.
    echo.
    echo      Run these two commands once, in this folder:
    echo.
    echo        python -m venv .venv
    echo        .venv\Scripts\python -m pip install -e .
    echo.
    pause
    exit /b 1
)
echo  [ok] interpreter: %PY%

REM ---- 2. check the package is installed ---------------------------------
"%PY%" -c "import dream" >nul 2>nul
if errorlevel 1 (
    echo  [!] the dream package is not installed in this environment.
    echo.
    echo      Run this once, in this folder:
    echo.
    echo        %PY% -m pip install -e .
    echo.
    pause
    exit /b 1
)
echo  [ok] package installed

REM ---- 3. load .env into this session ------------------------------------
REM Dream reads settings from environment variables and does NOT read the
REM .env file by itself, so the launcher loads it here.
if not exist ".env" (
    echo.
    echo  [!] no .env file found - Dream will only ECHO your words back.
    echo      It will NOT use real AI until you create .env
    echo.
    echo      Copy env-template.txt to .env and put your key in it.
    echo.
    choice /c YN /m "  Continue in echo mode anyway"
    if errorlevel 2 exit /b 1
) else (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
        set "K=%%A"
        set "V=%%B"
        if not "!K!"=="" if not "!V!"=="" set "!K!=!V!"
    )
    echo  [ok] .env loaded - backend: !DREAM_BACKEND!
)

REM ---- 4. run -------------------------------------------------------------
echo.
echo  Opening the window. Keep THIS black box open - errors appear here.
echo.
"%PY%" desktop.py
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" (
    echo  ==========================================
    echo   Dream exited with an error ^(code %RC%^)
    echo   Read the lines above and send them to me.
    echo  ==========================================
) else (
    echo  Dream closed normally.
)
echo.
pause
exit /b %RC%
