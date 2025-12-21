@echo off
echo ========================================
echo   Trading Bot - Stop Bot Only
echo   (Keeps ngrok running)
echo ========================================
echo.

REM First try graceful shutdown via API
echo 🔄 Attempting graceful shutdown via API...
python -c "import requests; r = requests.post('http://localhost:8080/admin/shutdown', json={'action': 'shutdown'}, timeout=5); print('✅ Shutdown command sent' if r.status_code == 200 else '⚠️ API shutdown failed')" 2>nul

if %errorlevel% == 0 (
    echo ⏳ Waiting for graceful shutdown...
    timeout /t 5 /nobreak >nul
)

REM Find and kill only the trading bot Python process (not all Python)
echo.
echo 🔍 Looking for trading bot process on port 8080...

REM Get the PID of the process using port 8080
set "BOT_PID="
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr "LISTENING" ^| findstr ":8080"') do (
    set "BOT_PID=%%a"
)

if defined BOT_PID (
    echo 🔴 Found bot process PID: %BOT_PID%
    taskkill /pid %BOT_PID% /f >nul 2>&1
    if not errorlevel 1 (
        echo ✅ Trading bot process terminated
    ) else (
        echo ⚠️  Could not terminate process %BOT_PID%
    )
) else (
    echo ℹ️  No process found on port 8080 (bot may already be stopped)
)

REM Verify ngrok is still running
echo.
echo 🔍 Checking ngrok status...
tasklist /fi "imagename eq ngrok.exe" 2>nul | find /i "ngrok.exe" >nul
if not errorlevel 1 (
    echo ✅ ngrok is still running
    
    REM Show the tunnel URL
    echo.
    echo 🌐 Your ngrok tunnel should still be active:
    for /f "tokens=*" %%i in ('curl -s http://localhost:4040/api/tunnels 2^>nul ^| python -c "import sys,json; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'] if d.get('tunnels') else 'Could not get URL')" 2^>nul') do (
        echo    %%i/webhook
    )
) else (
    echo ℹ️  ngrok is not running
    echo 💡 Start ngrok separately with: start_ngrok_standalone.bat
)

echo.
echo ========================================
echo ✅ Bot stopped, ngrok preserved!
echo ========================================
echo.
echo 💡 To restart just the bot (using existing ngrok):
echo    start_bot_no_ngrok.bat
echo.
echo 💡 To stop ngrok too:
echo    stop_bot.bat
echo.
pause
