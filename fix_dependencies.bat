@echo off
echo.
echo ========================================
echo   Trading Bot - Dependency Fix
echo ========================================
echo.

echo 🔧 Fixing dependency conflicts...
echo.

REM Upgrade pip first
echo ⬆️  Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo ❌ Failed to upgrade pip. Continuing anyway...
)

echo.
echo 🧹 Uninstalling conflicting packages...

REM Uninstall potentially conflicting packages including numpy for binary compatibility
pip uninstall -y pandas alpaca-py pydantic fastapi numpy
if errorlevel 1 (
    echo ⚠️  Some packages might not have been installed. Continuing...
)

echo.
echo 📦 Installing compatible dependencies...

REM Install requirements with compatible versions
pip install -r requirements.txt --force-reinstall
if errorlevel 1 (
    echo ❌ Failed to install dependencies. Trying alternative approach...
    echo.
    echo 🔄 Installing packages individually...
    
    REM Install core packages individually with binary compatibility
    pip install numpy --force-reinstall --no-cache-dir
    pip install "pandas>=1.5.0,<2.0.0" --force-reinstall --no-cache-dir
    pip install "pydantic>=1.9.0,<2.0.0"
    pip install "alpaca-py==0.7.0"
    pip install "fastapi==0.100.1"
    pip install fastapi uvicorn
    pip install tenacity
    pip install -r requirements.txt --force-reinstall
)

echo.
echo ✅ Verifying installation...
python verify_installation.py
if errorlevel 1 (
    echo ❌ Verification failed. Please check the output above.
    echo.
    echo 🛠️  Manual fix steps:
    echo    1. pip uninstall pandas alpaca-py pydantic fastapi numpy
    echo    2. pip install numpy --force-reinstall --no-cache-dir
    echo    3. pip install "pandas>=1.5.0,<2.0.0" --force-reinstall --no-cache-dir
    echo    4. pip install "pydantic>=1.9.0,<2.0.0"  
    echo    5. pip install "alpaca-py==0.7.0"
    echo    6. pip install "fastapi==0.100.1"
    echo    7. pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo.
echo 🎉 Dependencies fixed successfully!
echo ✅ You can now run: start_trading_bot.bat
echo.
pause
