@echo off
echo.
echo ========================================
echo   Trading Bot - Environment Setup
echo ========================================
echo.

echo 🔧 Setting up isolated Python environment...
echo.

REM Check if virtual environment already exists
if exist "trading-bot-env" (
    echo ✅ Virtual environment already exists
    echo.
    goto activate_env
)

echo 📦 Creating virtual environment...
python -m venv trading-bot-env
if errorlevel 1 (
    echo ❌ Failed to create virtual environment
    echo Make sure Python is installed and accessible
    pause
    exit /b 1
)

echo ✅ Virtual environment created successfully
echo.

:activate_env
echo 🚀 Activating virtual environment...
call trading-bot-env\Scripts\activate

echo ⬆️  Upgrading pip...
python -m pip install --upgrade pip

echo 🔍 Checking compatibility...
python check_compatibility.py
if errorlevel 1 (
    echo ⚠️  Compatibility issues detected, but continuing...
)

echo.
echo 📦 Installing trading bot dependencies...
pip install -r requirements.txt
if errorlevel 1 (
    echo ❌ Failed to install dependencies
    echo.
    echo 🔄 Trying alternative installation...
    pip uninstall -y pandas alpaca-py pydantic fastapi
    pip install "pandas>=1.5.0,<2.0.0"
    pip install "pydantic>=1.9.0,<2.0.0"
    pip install "alpaca-py==0.7.0"
    pip install "fastapi==0.100.1"
    pip install -r requirements.txt --force-reinstall
)

echo.
echo ✅ Verifying installation...
python verify_installation.py
if errorlevel 1 (
    echo ❌ Verification failed
    pause
    exit /b 1
)

echo.
echo 🎉 Environment setup complete!
echo.
echo ✅ Virtual environment: trading-bot-env
echo ✅ All dependencies installed
echo.
echo 📝 To activate this environment in the future:
echo    trading-bot-env\Scripts\activate
echo.
echo 🚀 To start the trading bot:
echo    python run_bot.py
echo.
pause
