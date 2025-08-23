@echo off
echo ========================================
echo   Trading Bot - Quick Shutdown
echo ========================================
echo.
echo 🛑 Attempting graceful shutdown...

REM Try graceful shutdown first
python shutdown_bot.py

echo.
echo 💡 If the bot didn't stop, you can:
echo    1. Wait a few more seconds
echo    2. Run 'stop_bot.bat' to force stop
echo    3. Use Ctrl+Break in the bot terminal
echo.
pause
