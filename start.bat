@echo off
title Analyst Desk - Verifiable Equity Research
cd /d "%~dp0"

echo ======================================================================
echo    Analyst Desk: Verifiable Equity Research Platform (IIT Bombay)    
echo    14 Companies ^| 3 Years Verified XBRL ^| Python Sandbox ^| Evals   
echo ======================================================================
echo.

REM 1. Check for working virtualenv
set "PY_EXE="
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0.venv\Scripts\python.exe"
    goto :RUN_APP
)

REM Check existing venvs in workspace
if exist "%~dp0..\analyst_desk_fixed\analyst_desk_py_extracted\analyst_desk_py\.venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0..\analyst_desk_fixed\analyst_desk_py_extracted\analyst_desk_py\.venv\Scripts\python.exe"
    goto :RUN_APP
)

REM Check system Python
where python >nul 2>&1
if not errorlevel 1 (
    set "PY_EXE=python"
    goto :CHECK_DEPS
)

if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    set "PY_EXE=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
    goto :CHECK_DEPS
)

echo [ERROR] Python not found in system PATH.
echo Please install Python 3.11+ from python.org
pause
exit /b 1

:CHECK_DEPS
echo [*] Using Python: %PY_EXE%
if not exist "%~dp0.venv\Scripts\activate.bat" (
    echo [*] Creating virtual environment...
    "%PY_EXE%" -m venv "%~dp0.venv"
    if errorlevel 1 (
        echo [WARN] Could not create local venv, continuing with system python...
    ) else (
        set "PY_EXE=%~dp0.venv\Scripts\python.exe"
        echo [*] Installing dependencies from requirements.txt...
        "%PY_EXE%" -m pip install -r requirements.txt
    )
)

:RUN_APP
echo [*] Python Runtime: %PY_EXE%
"%PY_EXE%" -c "import prometheus_client" >nul 2>&1
if errorlevel 1 (
    echo [*] Installing prometheus-client for live metrics...
    "%PY_EXE%" -m pip install prometheus-client
)
echo.
echo ======================================================================
echo    Application URL:       http://localhost:8000
echo    Prometheus Metrics:    http://localhost:8000/metrics
echo    Grafana Dashboard:     http://localhost:3000  (run: docker compose up -d)
echo ======================================================================
echo.
echo [*] Starting Uvicorn server on port 8000...
echo (Keep this window open! Press Ctrl+C to stop)
echo.
start "" /min cmd /c "timeout /t 2 /nobreak >nul && start http://localhost:8000"

"%PY_EXE%" -m uvicorn main:app --host 127.0.0.1 --port 8000
if errorlevel 1 (
    echo.
    echo [ERROR] Server terminated with error code %errorlevel%
    pause
)
pause
