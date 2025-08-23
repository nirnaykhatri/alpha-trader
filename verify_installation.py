#!/usr/bin/env python3
"""
Installation verification script for the trading bot.
Run this to check if all dependencies are properly installed.
"""

import sys
import importlib
from pathlib import Path

def check_dependency(module_name, package_name=None):
    """Check if a module can be imported."""
    try:
        importlib.import_module(module_name)
        print(f"✅ {package_name or module_name}")
        return True
    except ImportError as e:
        print(f"❌ {package_name or module_name} - Error: {e}")
        return False
    except ValueError as e:
        if "numpy.dtype size changed" in str(e):
            print(f"⚠️  {package_name or module_name} - Binary incompatibility detected")
            print(f"    Error: {e}")
            print(f"    💡 Solution: Reinstall numpy and pandas with --force-reinstall")
            return False
        else:
            print(f"❌ {package_name or module_name} - Error: {e}")
            return False
    except Exception as e:
        print(f"❌ {package_name or module_name} - Unexpected error: {e}")
        return False

def check_numpy_pandas_compatibility():
    """Check for numpy/pandas binary compatibility issues."""
    print("\n🔍 Checking numpy/pandas binary compatibility...")
    
    try:
        import numpy
        numpy_version = numpy.__version__
        print(f"✅ numpy {numpy_version} is installed")
    except ImportError:
        print("❌ numpy is not installed")
        return False
    except Exception as e:
        print(f"❌ numpy - Error: {e}")
        return False
    
    try:
        import pandas
        pandas_version = pandas.__version__
        print(f"✅ pandas {pandas_version} is installed")
        return True
    except ValueError as e:
        if "numpy.dtype size changed" in str(e):
            print("❌ BINARY INCOMPATIBILITY DETECTED!")
            print(f"   Error: {e}")
            print("")
            print("🔧 SOLUTION:")
            print("   1. Reinstall numpy and pandas with compatible versions")
            print("   2. Use --force-reinstall to rebuild binary dependencies")
            print("")
            print("💻 Commands to fix:")
            print("   pip uninstall numpy pandas -y")
            print("   pip install numpy pandas --force-reinstall --no-cache-dir")
            print("   pip install -r requirements.txt --force-reinstall")
            return False
        else:
            print(f"❌ pandas - Error: {e}")
            return False
    except ImportError as e:
        print(f"❌ pandas - Error: {e}")
        return False
    except Exception as e:
        print(f"❌ pandas - Unexpected error: {e}")
        return False

def main():
    """Main verification function."""
    print("🔍 Trading Bot Installation Verification")
    print("=" * 50)
    
    # Check Python version
    python_version = sys.version_info
    print(f"Python Version: {python_version.major}.{python_version.minor}.{python_version.micro}")
    
    if python_version < (3, 9):
        print("⚠️  Warning: Python 3.9+ is recommended")
    else:
        print("✅ Python version OK")
    
    # Check numpy/pandas binary compatibility first
    numpy_pandas_compatible = check_numpy_pandas_compatibility()
    
    if not numpy_pandas_compatible:
        print("")
        print("❌ Binary compatibility issues detected!")
        print("🔧 Please fix numpy/pandas compatibility before continuing")
        return False

    print("\n📦 Checking Dependencies:")
    print("-" * 30)
    
    # Core dependencies
    dependencies = [
        ("fastapi", "FastAPI"),
        ("uvicorn", "Uvicorn"),
        ("alpaca", "Alpaca API"),
        ("pandas", "Pandas"),
        ("numpy", "NumPy"),
        ("yaml", "PyYAML"),
        ("dotenv", "Python-dotenv"),
        ("httpx", "HTTPX"),
        ("aiohttp", "AioHTTP"),
        ("sqlalchemy", "SQLAlchemy"),
        ("aiosqlite", "AioSQLite"),
        ("pytest", "Pytest"),
        ("structlog", "StructLog"),
        ("apscheduler", "APScheduler"),
        ("pydantic", "Pydantic"),
        ("tenacity", "Tenacity"),
    ]
    
    failed_dependencies = []
    
    for module, package in dependencies:
        if not check_dependency(module, package):
            failed_dependencies.append(package)
    
    print("\n" + "=" * 50)
    
    if not failed_dependencies:
        print("🎉 All dependencies installed successfully!")
        print("✅ Ready to run the trading bot!")
    else:
        print(f"❌ {len(failed_dependencies)} dependencies missing:")
        for dep in failed_dependencies:
            print(f"   - {dep}")
        
        print("\n🔧 To fix missing dependencies:")
        print("   pip install -r requirements.txt")
        print("   # or install specific packages:")
        print("   pip install " + " ".join(failed_dependencies).lower())
    
    # Check if src directory exists
    print("\n📁 Checking Project Structure:")
    print("-" * 30)
    
    src_path = Path("src")
    if src_path.exists():
        print("✅ src/ directory found")
        
        # Check key modules
        key_modules = [
            "src/trading_bot.py",
            "src/core/configuration.py",
            "src/signals/signal_listener.py",
            "src/trading/order_manager.py",
        ]
        
        for module_path in key_modules:
            if Path(module_path).exists():
                print(f"✅ {module_path}")
            else:
                print(f"❌ {module_path} - Missing")
    else:
        print("❌ src/ directory not found")
        print("   Make sure you're in the trading bot root directory")
    
    # Check config file
    if Path("config.yaml").exists():
        print("✅ config.yaml found")
    else:
        print("❌ config.yaml not found")
        print("   Copy config.yaml.example to config.yaml and configure it")
    
    print("\n" + "=" * 50)
    if not failed_dependencies and src_path.exists():
        print("🚀 Installation verification complete!")
        print("   You can now run: python run_bot.py")
    else:
        print("🔧 Please fix the issues above before running the bot")

if __name__ == "__main__":
    main()
