@echo off
REM =============================================================================
REM Trading Bot Local Test Script
REM =============================================================================
REM 
REM This script sets required environment variables and runs the trading bot.
REM 
REM REQUIRED:
REM   - Cosmos DB (emulator pre-configured below)
REM
REM OPTIONAL:
REM   - Broker credentials (can be added via web UI after startup)
REM
REM SETUP INSTRUCTIONS:
REM   1. Start Cosmos DB Emulator: https://aka.ms/cosmosdb-emulator
REM   2. Run this script: run_local.bat
REM   3. Open browser: http://localhost:3000
REM   4. Add your broker from Settings > Brokers
REM
REM =============================================================================

echo.
echo ========================================
echo   Trading Bot - Local Development
echo ========================================
echo.

REM =============================================================================
REM AZURE COSMOS DB - Using Emulator by Default (REQUIRED)
REM =============================================================================
REM Using Cosmos DB Emulator for local testing (no Azure account needed)
REM Download from: https://aka.ms/cosmosdb-emulator
REM
REM To use Azure Cosmos DB instead, replace with your Azure credentials:
REM   set AZURE_COSMOS_ENDPOINT=https://your-account.documents.azure.com:443/
REM   set AZURE_COSMOS_KEY=your_actual_key_here

set AZURE_COSMOS_ENDPOINT=https://localhost:8081
set AZURE_COSMOS_DATABASE=trading_bot
set AZURE_COSMOS_KEY=C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw==
REM Explicit emulator flag - disables SSL verification safely
set AZURE_COSMOS_EMULATOR=true

REM =============================================================================
REM WEBHOOK / SERVER SETTINGS
REM =============================================================================
REM NOTE: Defaulting to localhost (127.0.0.1) for security. This binds only to
REM the local network interface, preventing external access.
REM 
REM If you need to access the server from another device (e.g., mobile testing),
REM change to 0.0.0.0 but be aware this exposes the server on your network.
REM In that case, ensure you're on a trusted network or enable webhook security.
set WEBHOOK_HOST=127.0.0.1
set WEBHOOK_PORT=8080
REM Security is disabled for local development. Enable in production!
set WEBHOOK_SECURITY_ENABLED=false

REM =============================================================================
REM GENERAL SETTINGS
REM =============================================================================
set TRADING_PAPER_MODE=true
set LOG_LEVEL=INFO
set ENVIRONMENT=development

REM =============================================================================
REM ALPACA BROKER (OPTIONAL - can be added via web UI)
REM =============================================================================
REM Uncomment and set these if you want to pre-configure Alpaca:
REM Get your paper trading API keys from: https://app.alpaca.markets/
REM
REM set ALPACA_API_KEY=your_api_key_here
REM set ALPACA_SECRET_KEY=your_secret_key_here
REM set ALPACA_BASE_URL=https://paper-api.alpaca.markets

REM =============================================================================
REM Validate Configuration
REM =============================================================================

echo Checking configuration...
echo.

if "%AZURE_COSMOS_ENDPOINT%"=="https://localhost:8081" (
    echo [OK] Database: Cosmos DB Emulator at localhost:8081
    echo      Make sure the emulator is running!
    echo      Download from: https://aka.ms/cosmosdb-emulator
    echo.
)

if defined ALPACA_API_KEY (
    echo [OK] Broker: Alpaca pre-configured
) else (
    echo [INFO] Broker: None pre-configured
    echo       Add your broker via web UI: http://localhost:3000/brokers
)
echo.

REM =============================================================================
REM Activate Virtual Environment and Run Bot
REM =============================================================================

echo Starting Trading Bot...
echo   API URL: http://localhost:%WEBHOOK_PORT%/api/v1
echo   Mode: Paper Trading
echo.

REM Activate virtual environment
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else if exist ".venv-2\Scripts\activate.bat" (
    call .venv-2\Scripts\activate.bat
) else (
    echo ERROR: Virtual environment not found!
    echo Please run: python -m venv .venv
    echo Then: pip install -r requirements.txt
    pause
    exit /b 1
)

REM Run the bot
python run_bot.py

REM Keep window open if bot exits
echo.
echo Bot exited. Press any key to close...
pause >nul
