@echo off
setlocal EnableDelayedExpansion
title PnL Enforcer Beta — Launcher
cd /d "%~dp0"

echo ========================================================
echo          PnL ENFORCER BETA — STARTUP CHECK
echo ========================================================

set "PY_CMD="

:: 1. Check if real Python is on PATH (ignoring the blank Windows Store stub)
for /f "delims=" %%i in ('where python 2^>nul') do (
    echo "%%i" | find /i "WindowsApps\python.exe" >nul
    if !errorlevel! neq 0 (
        "%%i" --version >nul 2>&1
        if !errorlevel! equ 0 (
            if not defined PY_CMD set "PY_CMD=%%i"
        )
    )
)

:: 2. If not on PATH, auto-search standard Windows Python install folders
if not defined PY_CMD (
    for /d %%D in ("%LocalAppData%\Programs\Python\Python3*" "%LocalAppData%\Python\pythoncore-3*" "C:\Python3*" "C:\Program Files\Python3*") do (
        if exist "%%~fD\python.exe" (
            set "PY_CMD=%%~fD\python.exe"
        )
    )
)

:: 3. If still not found, auto-install Python 3.12 + PATH via Windows winget
if not defined PY_CMD (
    echo [NOTICE] Python was not found on your system.
    echo Automatically installing Python 3.12 and adding it to PATH...
    echo ^(If a Windows permission prompt appears, click Yes^)
    echo.
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --override "/passive PrependPath=1 Include_test=0"
    
    for /d %%D in ("%LocalAppData%\Programs\Python\Python3*" "C:\Program Files\Python3*") do (
        if exist "%%~fD\python.exe" (
            set "PY_CMD=%%~fD\python.exe"
        )
    )
)

if not defined PY_CMD (
    echo [ERROR] Could not locate or auto-install Python!
    echo Please install Python 3.12 from https://www.python.org/downloads/
    echo and check the box "Add python.exe to PATH".
    pause
    exit /b
)

echo Using Python: "!PY_CMD!"
echo Checking required broker libraries (Schwab ^& Webull)...

"!PY_CMD!" -c "import schwab" >nul 2>&1
if !errorlevel! neq 0 (
    echo Installing schwab-py...
    "!PY_CMD!" -m pip install --upgrade schwab-py
)

"!PY_CMD!" -c "from webull.core.client import ApiClient; from webull.trade.trade_client import TradeClient" >nul 2>&1
if !errorlevel! neq 0 (
    echo Installing Webull OpenAPI SDK and dependencies...
    "!PY_CMD!" -m pip install --upgrade requests urllib3 certifi cryptography cachetools
    "!PY_CMD!" -m pip install --upgrade --no-deps --ignore-requires-python webull-openapi-core webull-openapi-trade webull-openapi-data webull-openapi-python-sdk
)

echo Launching PnL Enforcer...
"!PY_CMD!" enforcer.py
if !errorlevel! neq 0 (
    echo.
    echo Application exited with an error. See messages above.
    pause
)