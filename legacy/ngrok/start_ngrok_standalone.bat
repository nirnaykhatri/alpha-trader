@echo off
echo ================================================================
echo                STANDALONE NGROK TUNNEL SERVICE
echo ================================================================
echo.
echo This starts ngrok as a separate process, independent of the bot.
echo This approach may help with shutdown issues on Windows.
echo.
echo Press Ctrl+C to stop the tunnel service.
echo ================================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Please install Python or add it to your PATH
    pause
    exit /b 1
)

REM Default port is 8080, but you can pass a different port as argument
set PORT=8080
if not "%1"=="" set PORT=%1

echo Starting standalone ngrok service on port %PORT%...
echo.

REM Run the standalone ngrok service
python start_ngrok_standalone.py --port %PORT% --verbose

echo.
echo Ngrok tunnel service has stopped.
pause
