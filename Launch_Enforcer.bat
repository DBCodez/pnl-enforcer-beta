@echo off
title PnL Enforcer Beta — Launcher
cd /d "%~dp0"

echo ========================================================
echo          PnL ENFORCER BETA — STARTUP CHECK
echo ========================================================

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to PATH!
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo IMPORTANT: Check the box "Add python.exe to PATH" during installation!
    pause
    exit /b
)

echo Checking required broker libraries (Schwab ^& Webull)...
python -c "import schwab" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing schwab-py...
    python -m pip install --upgrade schwab-py
)

python -c "from webull.core.client import ApiClient; from webull.trade.trade_client import TradeClient" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing Webull OpenAPI SDK and dependencies...
    python -m pip install --upgrade requests urllib3 certifi cryptography cachetools
    python -m pip install --upgrade --no-deps --ignore-requires-python webull-openapi-core webull-openapi-trade webull-openapi-data webull-openapi-python-sdk
)

echo Launching PnL Enforcer...
python enforcer.py
if %errorlevel% neq 0 (
    echo.
    echo Application exited with an error. See messages above.
    pause
)