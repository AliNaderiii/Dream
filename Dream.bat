@echo off
setlocal
REM Dream desktop launcher — double-click to open the window.
REM Finds the virtual-environment interpreter without manual typing.
REM If the environment is missing, prints a readable Persian message.
REM Secondary launcher (desktop window). For first-time setup, double-click run.bat.

chcp 65001 >nul 2>nul

REM Prefer .venv, fall back to venv, then system python as last resort.
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    "%~dp0.venv\Scripts\pythonw.exe" "%~dp0desktop.py"
    exit /b %ERRORLEVEL%
)
if exist "%~dp0.venv\Scripts\python.exe" (
    "%~dp0.venv\Scripts\python.exe" "%~dp0desktop.py"
    exit /b %ERRORLEVEL%
)
if exist "%~dp0venv\Scripts\pythonw.exe" (
    "%~dp0venv\Scripts\pythonw.exe" "%~dp0desktop.py"
    exit /b %ERRORLEVEL%
)
if exist "%~dp0venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" "%~dp0desktop.py"
    exit /b %ERRORLEVEL%
)

REM Try python on PATH (covers python launcher case)
where python >nul 2>nul
if %ERRORLEVEL%==0 (
    python "%~dp0desktop.py"
    exit /b %ERRORLEVEL%
)

REM No environment found — readable Persian message.
echo.
echo ========================================
echo  محيط مجازي پيدا نشد.
echo  لطفاً ابتدا محيط مجازي را بسازيد:
echo    python -m venv .venv
echo  سپس وابستگي‌ها را نصب کنيد اگر لازم است و دوباره Dream.bat را اجرا کنيد.
echo ========================================
echo.
pause
exit /b 1
