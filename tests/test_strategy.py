#!/usr/bin/env python3
"""
Strategy Test Runner
Simple script to run comprehensive strategy simulation tests.
"""

import sys
import os
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def print_banner():
    """Print test banner."""
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                ADVANCED STRATEGY SIMULATION TESTS            ║
    ║                                                              ║
    ║  This will test the complete trading strategy workflow:      ║
    ║  • Long entry, profit trailing, and exit                     ║
    ║  • Long support averaging and recovery                       ║
    ║  • Short entry, profit trailing, and cover                   ║
    ║  • Short resistance averaging and recovery                   ║
    ║  • Multiple position management                              ║
    ║  • Complete position lifecycle                               ║
    ╚══════════════════════════════════════════════════════════════╝
    """)

def run_tests():
    """Run the strategy simulation tests."""
    print_banner()
    
    print("🔧 Checking test dependencies...")
    
    # Check if pytest is available
    try:
        import pytest
        print("✅ pytest found")
    except ImportError:
        print("❌ pytest not found. Installing...")
        os.system("pip install pytest pytest-asyncio")
    
    print("\n🧪 Running strategy simulation tests...")
    print("=" * 60)
    
    # Run the tests
    test_file = "tests/test_advanced_strategy_simulation.py"
    if os.path.exists(test_file):
        import subprocess
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            test_file, 
            "-v", "--tb=short", "-s"
        ])
        
        if result.returncode == 0:
            print("\n" + "=" * 60)
            print("🎉 ALL TESTS PASSED!")
            print("✅ Advanced strategy is working correctly")
            print("\nTest Summary:")
            print("• ✅ Long position profit trailing")
            print("• ✅ Long position support averaging")
            print("• ✅ Short position profit trailing")
            print("• ✅ Short position resistance averaging")
            print("• ✅ Multiple position management")
            print("• ✅ Complete position lifecycle")
            print("\n🚀 Your trading bot is ready for live testing!")
            
        else:
            print("\n" + "=" * 60)
            print("❌ SOME TESTS FAILED")
            print("🔧 Please check the output above for details")
            print("💡 Common issues:")
            print("   • Check your Python environment")
            print("   • Ensure all dependencies are installed")
            print("   • Review the error messages for specific issues")
            
    else:
        print(f"❌ Test file not found: {test_file}")
        print("Make sure you're running this from the bot root directory")

def run_quick_validation():
    """Run a quick validation of the strategy components."""
    print("\n🔍 Quick Strategy Validation...")
    
    try:
        from src.strategies.advanced_strategy import AdvancedTradingStrategy
        print("✅ Advanced strategy module loads correctly")
        
        from src.interfaces import TradingSignal, SignalType, OrderType, OrderSide
        print("✅ Trading interfaces load correctly")
        
        from src.core import ConfigurationManager
        print("✅ Configuration manager loads correctly")
        
        print("✅ All core components are accessible")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("🔧 Please check your Python path and dependencies")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Strategy Test Runner Starting...")
    
    # Quick validation first
    print("\n📋 Step 1: Basic Validation")
    if run_quick_validation():
        print("\n📋 Step 2: Full Simulation Tests")
        # Run full tests
        run_tests()
    else:
        print("\n❌ Quick validation failed")
        print("Please fix the issues above before running full tests")
        print("\n💡 Try running: python validate_strategy.py")
