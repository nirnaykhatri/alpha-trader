#!/usr/bin/env python3
"""
Test script to verify missing price field handling in signal listener.
This script tests the new functionality that allows signals without price fields.
"""

import asyncio
import json
from datetime import datetime
from unittest.mock import Mock, AsyncMock

# Mock the required modules for testing
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))  # Go up one level from tests/

from src.signals.signal_listener import TradingViewSignalListener
from src import TradingSignal, SignalType
from src.exceptions import ValidationException, SignalProcessingException


class MockConfig:
    """Mock configuration manager for testing."""
    
    def __init__(self, config_dict):
        self.config = config_dict
    
    def get_config(self, key, default=None):
        keys = key.split('.')
        value = self.config
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default


class MockMarketData:
    """Mock market data provider for testing."""
    
    async def get_current_price(self, symbol):
        """Return mock current price for testing."""
        mock_prices = {
            'AAPL': 150.25,
            'TSLA': 800.50,
            'MSFT': 300.75
        }
        if symbol in mock_prices:
            return mock_prices[symbol]
        raise Exception(f"No price data available for {symbol}")


async def test_missing_price_handling():
    """Test the new missing price field handling functionality."""
    
    print("🧪 Testing Missing Price Field Handling\n")
    
    # Configuration with missing price handling enabled
    config_dict = {
        'api': {
            'webhook': {
                'host': '0.0.0.0',
                'port': 8080,
                'security_enabled': False,
                'secret': '',
                'allow_missing_price': True,
                'price_fallback_enabled': True
            }
        }
    }
    
    config = MockConfig(config_dict)
    market_data = MockMarketData()
    
    # Mock signal callback
    processed_signals = []
    
    def signal_callback(signal):
        processed_signals.append(signal)
    
    # Create signal listener
    listener = TradingViewSignalListener(config, signal_callback, market_data)
    
    # Test cases
    test_cases = [
        {
            'name': 'Signal with valid price',
            'data': {'ticker': 'AAPL', 'signal': 'buy', 'price': 149.99},
            'expected_price': 149.99,
            'should_succeed': True
        },
        {
            'name': 'Signal missing price field (should fetch current)',
            'data': {'ticker': 'AAPL', 'signal': 'buy'},
            'expected_price': 150.25,  # From mock market data
            'should_succeed': True
        },
        {
            'name': 'Signal with zero price (should fetch current)',
            'data': {'ticker': 'TSLA', 'signal': 'sell', 'price': 0},
            'expected_price': 800.50,  # From mock market data
            'should_succeed': True
        },
        {
            'name': 'Signal with null price (should fetch current)',
            'data': {'ticker': 'MSFT', 'signal': 'buy', 'price': None},
            'expected_price': 300.75,  # From mock market data
            'should_succeed': True
        },
        {
            'name': 'Signal for unknown symbol (should use placeholder)',
            'data': {'ticker': 'UNKNOWN', 'signal': 'buy'},
            'expected_price': 1.0,  # Placeholder price
            'should_succeed': True
        }
    ]
    
    # Run test cases
    for i, test_case in enumerate(test_cases, 1):
        print(f"Test {i}: {test_case['name']}")
        processed_signals.clear()
        
        try:
            # Process the signal
            signal = await listener.process_signal(test_case['data'])
            
            if test_case['should_succeed']:
                print(f"  ✅ Signal processed successfully")
                print(f"  📊 Symbol: {signal.symbol}")
                print(f"  📈 Signal Type: {signal.signal_type.value}")
                print(f"  💰 Price: {signal.price} (expected: {test_case['expected_price']})")
                
                # Verify price matches expectation
                if abs(signal.price - test_case['expected_price']) < 0.01:
                    print(f"  ✅ Price matches expected value")
                else:
                    print(f"  ❌ Price mismatch: got {signal.price}, expected {test_case['expected_price']}")
            else:
                print(f"  ❌ Signal should have failed but didn't")
                
        except Exception as e:
            if test_case['should_succeed']:
                print(f"  ❌ Signal processing failed unexpectedly: {e}")
            else:
                print(f"  ✅ Signal correctly rejected: {e}")
        
        print()
    
    # Test with fallback disabled
    print("🧪 Testing with price fallback disabled\n")
    
    config_dict['api']['webhook']['price_fallback_enabled'] = False
    config_no_fallback = MockConfig(config_dict)
    listener_no_fallback = TradingViewSignalListener(config_no_fallback, signal_callback, market_data)
    
    test_data = {'ticker': 'AAPL', 'signal': 'buy'}  # No price field
    
    try:
        signal = await listener_no_fallback.process_signal(test_data)
        print("✅ Signal processed with placeholder price:")
        print(f"  💰 Price: {signal.price} (should be 1.0)")
        
        if signal.price == 1.0:
            print("  ✅ Placeholder price used correctly")
        else:
            print(f"  ❌ Expected placeholder price 1.0, got {signal.price}")
            
    except Exception as e:
        print(f"❌ Signal processing failed: {e}")
    
    print("\n🎉 Testing completed!")


if __name__ == "__main__":
    try:
        asyncio.run(test_missing_price_handling())
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
