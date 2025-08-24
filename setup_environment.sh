#!/bin/bash

echo ""
echo "========================================"
echo "   Trading Bot - Environment Setup"
echo "========================================"
echo ""

echo "🔧 Setting up isolated Python environment..."
echo ""

# Check if virtual environment already exists
if [ -d "trading-bot-env" ]; then
    echo "✅ Virtual environment already exists"
    echo ""
else
    echo "📦 Creating virtual environment..."
    python3 -m venv trading-bot-env
    if [ $? -ne 0 ]; then
        echo "❌ Failed to create virtual environment"
        echo "Make sure Python 3 is installed and accessible"
        exit 1
    fi
    echo "✅ Virtual environment created successfully"
    echo ""
fi

echo "🚀 Activating virtual environment..."
source trading-bot-env/bin/activate

echo "⬆️  Upgrading pip..."
python -m pip install --upgrade pip

echo "🔍 Checking compatibility..."
python check_compatibility.py
if [ $? -ne 0 ]; then
    echo "⚠️  Compatibility issues detected, but continuing..."
fi

echo ""
echo "📦 Installing trading bot dependencies..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies"
    echo ""
    echo "🔄 Trying alternative installation..."
    pip uninstall -y pandas alpaca-py pydantic fastapi
    pip install "pandas>=1.5.0,<2.0.0"
    pip install "pydantic>=1.9.0,<2.0.0"
    pip install "alpaca-py==0.7.0"
    pip install "fastapi==0.100.1"
    pip install -r requirements.txt --force-reinstall
fi

echo ""
echo "✅ Verifying installation..."
python verify_installation.py
if [ $? -ne 0 ]; then
    echo "❌ Verification failed"
    exit 1
fi

echo ""
echo "🎉 Environment setup complete!"
echo ""
echo "✅ Virtual environment: trading-bot-env"
echo "✅ All dependencies installed"
echo ""
echo "📝 To activate this environment in the future:"
echo "   source trading-bot-env/bin/activate"
echo ""
echo "🚀 To start the trading bot:"
echo "   python run_bot.py"
echo ""
