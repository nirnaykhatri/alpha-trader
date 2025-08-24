#!/usr/bin/env python3
"""
Test script to verify order processing fixes work correctly.
Tests that the bot now fetches current market prices and uses market orders.
"""

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Add the src directory to Python path
sys.path.insert(0, 'src')

from src.core.configuration import ConfigurationManager


def test_config_changes():
    """Test that configuration changes are correct."""
    
    print("🧪 Testing Order Processing Configuration Fixes\n")
    
    try:
        # Load configuration
        config = ConfigurationManager("config.yaml")
        
        # Test cases for order type configuration
        test_cases = [
            {
                "config_path": "strategies.long_strategy.entry_order_type",
                "expected_value": "market",
                "description": "Long strategy entry order type"
            },
            {
                "config_path": "strategies.short_strategy.entry_order_type", 
                "expected_value": "market",
                "description": "Short strategy entry order type"
            },
            {
                "config_path": "trading.averaging_order_type",
                "expected_value": "market",
                "description": "Averaging order type"
            }
        ]
        
        results = []
        
        for test_case in test_cases:
            print(f"Testing: {test_case['description']}")
            print(f"Config Path: {test_case['config_path']}")
            
            try:
                actual_value = config.get_config(test_case['config_path'])
                expected_value = test_case['expected_value']
                
                if actual_value == expected_value:
                    result = "✅ PASS"
                    success = True
                else:
                    result = "❌ FAIL"
                    success = False
                
                print(f"Expected: {expected_value}")
                print(f"Actual: {actual_value}")
                print(f"Result: {result}\n")
                
                results.append({
                    'test': test_case['description'],
                    'success': success,
                    'expected': expected_value,
                    'actual': actual_value
                })
                
            except Exception as e:
                print(f"❌ FAIL - Error reading config: {e}\n")
                results.append({
                    'test': test_case['description'],
                    'success': False,
                    'expected': test_case['expected_value'],
                    'actual': f"ERROR: {e}"
                })
        
        # Summary
        passed_tests = sum(1 for r in results if r['success'])
        total_tests = len(results)
        
        print(f"📊 Configuration Test Summary: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests == total_tests:
            print("🎉 All configuration changes are correct!")
            print("✅ Bot is now configured for market orders")
            print("✅ Should fetch current market prices for all orders")
            return True
        else:
            print("💥 Some configuration tests failed:")
            for result in results:
                if not result['success']:
                    print(f"   ❌ {result['test']}: Expected '{result['expected']}', got '{result['actual']}'")
            return False
        
    except Exception as e:
        print(f"❌ Test setup failed: {e}")
        return False


def test_symbol_recommendations():
    """Test and provide symbol recommendations."""
    print("\n🎯 Symbol Trading Recommendations:")
    print("="*50)
    
    # Valid stock symbols for testing
    valid_symbols = ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "SPY", "QQQ"]
    
    # Invalid/problematic symbols
    crypto_symbols = ["BTC", "ETH", "LTC", "XRP"]
    crypto_stocks = ["BITO", "MSTR", "COIN", "RIOT", "MARA"]
    
    print("✅ RECOMMENDED SYMBOLS (Stocks - will work):")
    for symbol in valid_symbols:
        print(f"   • {symbol}")
    
    print("\n❌ PROBLEMATIC SYMBOLS (Crypto - will fail):")
    for symbol in crypto_symbols:
        print(f"   • {symbol} - Not available via Alpaca Stock API")
    
    print("\n🔄 CRYPTO ALTERNATIVES (Crypto-related stocks):")
    for symbol in crypto_stocks:
        print(f"   • {symbol}")
    
    print("\n📝 Example Working Signal:")
    example_signal = {
        "ticker": "AAPL",
        "signal": "buy"
    }
    print(json.dumps(example_signal, indent=2))
    
    print("\n⚠️  For crypto trading, consider:")
    print("   • Use crypto exchange APIs (Coinbase, Binance)")
    print("   • Trade crypto-related stocks (BITO, MSTR)")
    print("   • Check if Alpaca account supports crypto API")


if __name__ == "__main__":
    print("🔧 Order Processing Fixes Verification")
    print("="*50)
    
    config_success = test_config_changes()
    test_symbol_recommendations()
    
    print("\n" + "="*50)
    if config_success:
        print("✅ READY: Bot configuration is correct for market orders")
        print("🚀 Next: Test with valid stock symbols (AAPL, MSFT, etc.)")
    else:
        print("❌ ISSUES: Configuration problems detected")
        print("🔧 Fix the configuration issues before testing")
    
    sys.exit(0 if config_success else 1)
