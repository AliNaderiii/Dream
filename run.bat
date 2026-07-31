@echo off
setlocal

where python >nul 2>nul
if errorlevel 1 (
    echo [Dream] Python was not found on PATH. Install Python 3.10 or newer.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\activate.bat" (
    echo [Dream] Virtual environment not found.
    echo [Dream] Create it first with:  python -m venv .venv
    echo [Dream] Then install the package:  .venv\Scripts\python -m pip install -e ".[dev]"
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

set "OPENAI_BASE_URL="
set "OPENAI_API_KEY="

echo.
echo [Dream] Select an Ollama model:
echo   1) qwen2.5:7b  (default)
echo   2) qwen2.5:3b
set "DREAM_MODEL_CHOICE="
set /p "DREAM_MODEL_CHOICE=Choice [1]: "

if "%DREAM_MODEL_CHOICE%"=="2" (
    set "DREAM_MODEL=qwen2.5:3b"
) else (
    set "DREAM_MODEL=qwen2.5:7b"
)

echo [Dream] Starting Dream with model %DREAM_MODEL%
python cli.py --backend ollama
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo [Dream] Dream exited cleanly.
) else (
    echo [Dream] Dream exited with code %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%
