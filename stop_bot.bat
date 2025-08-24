@echo off
echo ========================================
echo   Trading Bot - Force Stop Tool
echo ========================================
echo.
echo 🛑 Force stopping all trading bot processes...
echo.

REM Kill Python processes that might be running the bot
echo 🔍 Looking for Python processes...
tasklist /fi "imagename eq python.exe" >nul 2>&1
if not errorlevel 1 (
    echo 🔴 Killing Python processes (may include the bot)
    taskkill /f /im python.exe /t >nul 2>&1
    if not errorlevel 1 (
        echo ✅ Python processes terminated
    ) else (
        echo ⚠️  No Python processes found or already stopped
    )
) else (
    echo ℹ️  No Python processes running
)

REM Kill ngrok if running
echo.
echo 🔍 Looking for ngrok processes...
tasklist /fi "imagename eq ngrok.exe" >nul 2>&1
if not errorlevel 1 (
    echo 🔴 Killing ngrok processes
    taskkill /f /im ngrok.exe /t >nul 2>&1
    if not errorlevel 1 (
        echo ✅ ngrok processes terminated
    ) else (
        echo ⚠️  Failed to kill ngrok processes
    )
) else (
    echo ℹ️  No ngrok processes running
)

REM Also try to kill any processes using port 8080
echo.
echo 🔍 Checking for processes using port 8080...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080') do (
    echo 🔴 Killing process using port 8080: %%a
    taskkill /pid %%a /f >nul 2>&1
)

echo.
echo ========================================
echo ✅ Force stop complete!
echo ========================================
echo 💡 All trading bot related processes have been terminated
echo � You can now start the bot again safely
echo 📋 Next time, try 'python shutdown_bot.py' for graceful shutdown
echo.
pause
