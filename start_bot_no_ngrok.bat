@echo off
REM Trading Bot - Start Without ngrok
REM This script starts the trading bot without ngrok integration

echo ========================================
echo   Trading Bot - No ngrok Mode
echo ========================================
echo.

REM Check if Python is available
python --version >nul 2>nul
if %errorlevel% neq 0 (
    echo ❌ Python not found
    echo Please install Python 3.9+ and try again
    pause
    exit /b 1
)

REM Check if config.yaml exists
if not exist "config.yaml" (
    echo ❌ config.yaml not found
    echo.
    echo Please copy and edit config.yaml with your Alpaca credentials
    pause
    exit /b 1
)

REM Quick dependency check
echo 🔍 Checking dependencies...
python -c "import tenacity, fastapi, alpaca" >nul 2>nul
if %errorlevel% neq 0 (
    echo ❌ Missing dependencies detected
    echo.
    echo Please run: fix_dependencies.bat
    echo Or manually: pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo ✅ Starting Trading Bot (ngrok disabled)...
echo.
echo 🚀 The bot will:
echo    • Start FastAPI server on localhost:8080
echo    • Process trading signals directly (no webhook tunnel)
echo    • Use manual webhook URLs if configured
echo.
echo 📋 Bot running in local-only mode
echo 🛑 Shutdown options:
echo    • Method 1: python shutdown_bot.py
echo    • Method 2: run stop_bot.bat
echo    • Method 3: Ctrl+Break or close terminal
echo.

REM Temporarily disable ngrok in environment
set TRADING_BOT_NO_NGROK=1

REM Start the bot
python run_bot.py

echo.
echo 👋 Trading Bot stopped
pause
