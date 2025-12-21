@echo off
REM Trading Bot Quick Start with Automated ngrok
REM This script starts the trading bot with automatic ngrok setup

REM Set UTF-8 encoding for emoji support
chcp 65001 >nul 2>nul

echo ========================================
echo   Trading Bot - Automated Setup
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo [X] Python not found
    echo Please install Python 3.9+ and try again
    pause
    exit /b 1
)

REM Check if config directory exists (TOML-based configuration)
if not exist "config\settings.toml" (
    echo [X] config\settings.toml not found
    echo.
    echo Please run: python configure_bot.py
    echo Or copy config\settings.toml.example to config\settings.toml
    echo.
    pause
    exit /b 1
)

REM Quick dependency check
echo [>] Checking dependencies...
python -c "import tenacity, fastapi, alpaca" >nul 2>nul
if %errorlevel% neq 0 (
    echo [X] Missing dependencies detected
    echo.
    echo Please run: fix_dependencies.bat
    echo Or manually: pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo [OK] Starting Trading Bot with Automated ngrok...
echo.
echo [INFO] The bot will:
echo    * Automatically download ngrok if needed
echo    * Start ngrok tunnel for webhooks  
echo    * Display webhook URL for TradingView
echo    * Process trading signals from TradingView
echo.
echo [NOTE] Watch for the webhook URL to copy to TradingView
echo [WARN] Press Ctrl+C to stop the bot
echo.

REM Start the bot
python run_bot.py

echo.
echo [DONE] Trading Bot stopped
pause
