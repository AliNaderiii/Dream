@echo off
setlocal

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

python doctor.py --backend ollama
set "EXIT_CODE=%ERRORLEVEL%"

echo.
if "%EXIT_CODE%"=="0" (
    echo [Dream] All checks passed.
) else (
    echo [Dream] One or more checks failed; see the messages above.
)
pause
exit /b %EXIT_CODE%
