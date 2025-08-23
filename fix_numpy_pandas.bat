@echo off
echo.
echo ========================================
echo   Fixing NumPy/Pandas Binary Compatibility
echo ========================================
echo.

echo 🔧 Activating virtual environment...
call trading-bot-env\Scripts\activate

echo 🧹 Uninstalling numpy and pandas...
pip uninstall numpy pandas -y

echo 📦 Installing numpy (fresh build)...
pip install numpy --force-reinstall --no-cache-dir

echo 📊 Installing pandas (compatible version)...
pip install "pandas>=1.5.0,<2.0.0" --force-reinstall --no-cache-dir

echo ✅ Verifying fix...
python verify_installation.py

echo.
echo 🎉 Fix complete! If verification passed, you're ready to go.
pause
