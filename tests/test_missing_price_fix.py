#!/usr/bin/env python3
"""
Test script to verify that missing price field handling works correctly.
This script tests the signal listener's ability to process signals with and without price fields.
"""

import json
import sys
import traceback
from unittest.mock import AsyncMock, MagicMock

# Add the src directory to Python path
sys.path.insert(0, '../src')  # Go up one level from tests/

from src.core.configuration import ConfigurationManager
from src.signals.signal_listener import TradingViewSignalListener


def test_signal_processing():
    """Test signal processing with and without price fields."""
    
    print("🧪 Testing Missing Price Field Handling\n")
    
    try:
        # Initialize configuration
        config = ConfigurationManager("config.yaml")
        
        # Mock signal callback
        signal_callback = MagicMock()
        
        # Initialize signal listener (without market data since we simplified it)
        listener = TradingViewSignalListener(config, signal_callback)
        
        # Test cases
        test_cases = [
            {
                "name": "Signal with price",
                "data": {
                    "ticker": "AAPL",
                    "signal": "buy",
                    "price": 150.25,
                    "quantity": 100
                },
                "should_work": True
            },
            {
                "name": "Signal without price",
                "data": {
                    "ticker": "AAPL", 
                    "signal": "buy",
                    "quantity": 100
                },
                "should_work": True
            },
            {
                "name": "Signal with price = 0",
                "data": {
                    "ticker": "AAPL",
                    "signal": "buy", 
                    "price": 0,
                    "quantity": 100
                },
                "should_work": False  # Price = 0 should still fail validation
            },
            {
                "name": "Signal with null price",
                "data": {
                    "ticker": "AAPL",
                    "signal": "buy",
                    "price": None,
                    "quantity": 100
                },
                "should_work": False  # None price should fail validation
            },
            {
                "name": "Signal missing ticker",
                "data": {
                    "signal": "buy",
                    "price": 150.25
                },
                "should_work": False  # Missing ticker should fail
            }
        ]
        
        results = []
        
        for test_case in test_cases:
            print(f"Testing: {test_case['name']}")
            print(f"Data: {json.dumps(test_case['data'], indent=2)}")
            
            try:
                # Test validation
                listener._validate_signal_data(test_case['data'])
                validation_passed = True
                validation_error = None
            except Exception as e:
                validation_passed = False
                validation_error = str(e)
            
            # Check if result matches expectation
            if validation_passed == test_case['should_work']:
                result = "✅ PASS"
                success = True
            else:
                result = "❌ FAIL"
                success = False
            
            print(f"Expected: {'✅ Pass' if test_case['should_work'] else '❌ Fail'}")
            print(f"Actual: {'✅ Pass' if validation_passed else f'❌ Fail ({validation_error})'}")
            print(f"Result: {result}\n")
            
            results.append({
                'test': test_case['name'],
                'success': success,
                'expected': test_case['should_work'],
                'actual': validation_passed,
                'error': validation_error
            })
        
        # Summary
        passed_tests = sum(1 for r in results if r['success'])
        total_tests = len(results)
        
        print(f"📊 Test Summary: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests == total_tests:
            print("🎉 All tests passed! Missing price field handling is working correctly.")
            return True
        else:
            print("💥 Some tests failed. Please check the implementation.")
            for result in results:
                if not result['success']:
                    print(f"   ❌ {result['test']}: Expected {result['expected']}, got {result['actual']}")
            return False
        
    except Exception as e:
        print(f"❌ Test setup failed: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return False


if __name__ == "__main__":
    success = test_signal_processing()
    sys.exit(0 if success else 1)
