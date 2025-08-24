#!/usr/bin/env python3
"""
Check for package compatibility issues before installation.
"""

import subprocess
import sys
import pkg_resources
from packaging import specifiers, version

def check_pandas_alpaca_compatibility():
    """Check if pandas and alpaca-py versions are compatible."""
    print("🔍 Checking pandas and alpaca-py compatibility...")
    
    # Check if packages are installed
    try:
        import pandas
        pandas_version = pandas.__version__
        print(f"✅ pandas {pandas_version} is installed")
    except ImportError:
        print("ℹ️  pandas is not installed")
        pandas_version = None
    
    try:
        import alpaca
        # Get alpaca-py version
        alpaca_version = pkg_resources.get_distribution("alpaca-py").version
        print(f"✅ alpaca-py {alpaca_version} is installed")
    except ImportError:
        print("ℹ️  alpaca-py is not installed")
        alpaca_version = None
    except pkg_resources.DistributionNotFound:
        print("ℹ️  alpaca-py is not installed")
        alpaca_version = None
    
    # Check compatibility
    if pandas_version and alpaca_version:
        pandas_ver = version.parse(pandas_version)
        
        # alpaca-py 0.7.0 requires pandas<2.0.0 and >=1.3.5
        if pandas_ver >= version.parse("2.0.0"):
            print("❌ COMPATIBILITY ISSUE DETECTED!")
            print(f"   pandas {pandas_version} is incompatible with alpaca-py {alpaca_version}")
            print("   alpaca-py requires pandas<2.0.0")
            print("")
            print("🔧 SOLUTION:")
            print("   1. Uninstall current pandas: pip uninstall pandas")
            print("   2. Install compatible version: pip install 'pandas>=1.5.0,<2.0.0'")
            print("   3. Or run: fix_dependencies.bat (Windows)")
            return False
        else:
            print("✅ pandas and alpaca-py versions are compatible")
            return True
    
    return True

def check_pydantic_fastapi_alpaca_compatibility():
    """Check if pydantic, fastapi, and alpaca-py versions are compatible."""
    print("🔍 Checking pydantic, fastapi, and alpaca-py compatibility...")
    
    # Check if packages are installed
    try:
        import pydantic
        pydantic_version = pydantic.__version__
        print(f"✅ pydantic {pydantic_version} is installed")
    except ImportError:
        print("ℹ️  pydantic is not installed")
        pydantic_version = None
    
    try:
        import fastapi
        fastapi_version = fastapi.__version__
        print(f"✅ fastapi {fastapi_version} is installed")
    except ImportError:
        print("ℹ️  fastapi is not installed")
        fastapi_version = None
    
    try:
        import alpaca
        # Get alpaca-py version
        alpaca_version = pkg_resources.get_distribution("alpaca-py").version
        print(f"✅ alpaca-py {alpaca_version} is installed")
    except ImportError:
        print("ℹ️  alpaca-py is not installed")
        alpaca_version = None
    except pkg_resources.DistributionNotFound:
        print("ℹ️  alpaca-py is not installed")
        alpaca_version = None
    
    # Check compatibility
    if pydantic_version and alpaca_version:
        pydantic_ver = version.parse(pydantic_version)
        
        # alpaca-py 0.7.0 requires pydantic<2.0.0 and >=1.9.0
        if pydantic_ver >= version.parse("2.0.0"):
            print("❌ COMPATIBILITY ISSUE DETECTED!")
            print(f"   pydantic {pydantic_version} is incompatible with alpaca-py {alpaca_version}")
            print("   alpaca-py requires pydantic<2.0.0")
            print("")
            print("🔧 SOLUTION:")
            print("   1. Uninstall current pydantic: pip uninstall pydantic")
            print("   2. Install compatible version: pip install 'pydantic>=1.9.0,<2.0.0'")
            print("   3. Or run: fix_dependencies.bat (Windows)")
            return False
        else:
            print("✅ pydantic and alpaca-py versions are compatible")
            return True
    
    return True

def main():
    """Main compatibility check."""
    print("📦 Trading Bot - Compatibility Check")
    print("=" * 40)
    print("")
    
    # Check Python version
    python_version = sys.version_info
    print(f"🐍 Python {python_version.major}.{python_version.minor}.{python_version.micro}")
    if python_version < (3, 9):
        print("⚠️  Python 3.9+ is recommended")
    else:
        print("✅ Python version is compatible")
    
    print("")
    
    # Check pandas/alpaca compatibility
    is_compatible = check_pandas_alpaca_compatibility()
    
    print("")
    # Check pydantic/fastapi/alpaca compatibility
    is_compatible &= check_pydantic_fastapi_alpaca_compatibility()
    
    print("")
    if is_compatible:
        print("🎉 All compatibility checks passed!")
        print("✅ You can proceed with: pip install -r requirements.txt")
    else:
        print("❌ Compatibility issues detected!")
        print("🔧 Please fix the issues above before proceeding")
        sys.exit(1)

if __name__ == "__main__":
    main()
