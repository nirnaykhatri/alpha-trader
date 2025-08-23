# Trading Bot Quick Start with Automated ngrok (PowerShell version with emoji support)
# This script starts the trading bot with automatic ngrok setup

# Set console encoding to UTF-8 for emoji support
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  🤖 Trading Bot - Automated Setup" -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is available
try {
    $pythonVersion = python --version 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Python not found"
    }
    Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
}
catch {
    Write-Host "❌ Python not found" -ForegroundColor Red
    Write-Host "Please install Python 3.9+ and try again" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if config.yaml exists
if (-not (Test-Path "config.yaml")) {
    Write-Host "❌ config.yaml not found" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please:" -ForegroundColor Yellow
    Write-Host "1. Copy and edit config.yaml with your Alpaca credentials" -ForegroundColor White
    Write-Host "2. Set ngrok.enabled: true for automatic webhook setup" -ForegroundColor White
    Write-Host "3. Run this script again" -ForegroundColor White
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

# Quick dependency check
Write-Host "🔍 Checking dependencies..." -ForegroundColor Blue
try {
    python -c "import tenacity, fastapi, alpaca" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "Dependencies missing"
    }
    Write-Host "✅ Dependencies OK" -ForegroundColor Green
}
catch {
    Write-Host "❌ Missing dependencies detected" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please run: fix_dependencies.bat" -ForegroundColor Yellow
    Write-Host "Or manually: pip install -r requirements.txt" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "🚀 Starting Trading Bot with Automated ngrok..." -ForegroundColor Green
Write-Host ""
Write-Host "🤖 The bot will:" -ForegroundColor Cyan
Write-Host "   • Automatically download ngrok if needed" -ForegroundColor White
Write-Host "   • Start ngrok tunnel for webhooks" -ForegroundColor White
Write-Host "   • Display webhook URL for TradingView" -ForegroundColor White
Write-Host "   • Process trading signals from TradingView" -ForegroundColor White
Write-Host ""
Write-Host "👀 Watch for the webhook URL to copy to TradingView" -ForegroundColor Yellow
Write-Host "⚠️  Press Ctrl+C to stop the bot" -ForegroundColor Red
Write-Host ""

# Start the bot
python run_bot.py

Write-Host ""
Write-Host "👋 Trading Bot stopped" -ForegroundColor Magenta
Read-Host "Press Enter to exit"
