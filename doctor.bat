@echo off
setlocal
echo === 1. Checking Python and Virtual Environment ===
.venv\Scripts\python.exe --version
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found in .venv
    exit /b %ERRORLEVEL%
)

echo.
echo === 2. Checking Public Test Suite ===
.venv\Scripts\pytest.exe tests_public -q
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Public tests failed!
    exit /b %ERRORLEVEL%
)

echo.
echo === 3. Running Baseline Check ===
.venv\Scripts\python.exe scripts\run_baseline.py
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Baseline run failed!
    exit /b %ERRORLEVEL%
)

echo.
echo [READY] Day 27 setup is complete and all starter checks pass!
