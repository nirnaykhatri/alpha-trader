@echo off
echo ========================================
echo  Trading Bot + ngrok Quick Setup
echo ========================================
echo.

REM Check if ngrok is available
where ngrok >nul 2>nul
if %errorlevel% neq 0 (
    echo ❌ ngrok not found in PATH
    echo.
    echo Please:
    echo 1. Download ngrok from https://ngrok.com/
    echo 2. Add ngrok.exe to your PATH or copy it to this folder
    echo 3. Run: ngrok config add-authtoken YOUR_TOKEN
    echo.
    pause
    exit /b 1
)

REM Check if config directory exists (TOML-based configuration)
if not exist "config\settings.toml" (
    echo ❌ config\settings.toml not found
    echo Please run: python configure_bot.py
    echo.
    pause
    exit /b 1
)

echo ✅ Starting Trading Bot...
echo.

REM Start the bot in a new window
start "Trading Bot" cmd /k "python run_bot.py"

REM Wait a moment for the bot to start
timeout /t 3 /nobreak >nul

echo ✅ Starting ngrok tunnel...
echo.
echo 🌐 Your webhook URL will be displayed below
echo 📋 Copy the HTTPS URL and use it in TradingView
echo 📊 Visit http://localhost:4040 to monitor webhook calls
echo.

REM Start ngrok and keep this window open
ngrok http 8080
