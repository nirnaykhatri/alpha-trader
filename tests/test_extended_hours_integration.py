#!/usr/bin/env python3
"""
Test script to validate extended hours management functionality.
Tests Alpaca Clock API integration, extended hours coordination, and order configuration.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
from typing import Dict, Any

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.core.configuration import ConfigurationManager
from src.core.market_hours_manager import AlpacaIntegratedMarketHoursManager
from src.core.extended_hours_manager import ExtendedHoursManager
from src.core.market_status_provider import MarketSession
from src.core.logging_config import get_logger

logger = get_logger(__name__)


async def test_extended_hours_integration():
    """Test extended hours manager integration with market hours manager."""
    print("🧪 TESTING EXTENDED HOURS INTEGRATION")
    print("=" * 60)
    
    try:
        # Initialize configuration
        config = ConfigurationManager()
        
        # Initialize market hours manager
        print("\n📅 Initializing Market Hours Manager...")
        market_hours_manager = AlpacaIntegratedMarketHoursManager(config)
        
        # Initialize extended hours manager
        print("🌅 Initializing Extended Hours Manager...")
        extended_hours_manager = ExtendedHoursManager(config, market_hours_manager)
        
        # Connect them
        market_hours_manager.set_extended_hours_manager(extended_hours_manager)
        print("✅ Extended hours manager integrated with market hours manager")
        
        # Get current market status
        print("\n📊 Getting Current Market Status...")
        market_status = await market_hours_manager.get_current_market_status()
        
        print(f"   Current Session: {market_status.current_session.value.upper()}")
        print(f"   Market Open: {market_status.is_open}")
        print(f"   Is Trading Day: {market_status.is_trading_day}")
        print(f"   Bot Should Be Active: {market_status.bot_should_be_active}")
        print(f"   Source: {market_status.source}")
        
        # Test extended hours functionality
        print("\n🌅 Testing Extended Hours Functionality...")
        
        # Test symbols
        test_symbols = ['AAPL', 'GOOGL', 'MSFT', 'SPY', 'QQQ']
        
        for symbol in test_symbols:
            print(f"\n   Testing {symbol}:")
            
            # Check if extended hours trading is allowed
            is_allowed, reason = await extended_hours_manager.is_extended_hours_trading_allowed(symbol)
            print(f"   ├─ Extended hours allowed: {is_allowed} ({reason})")
            
            # Test symbol validation
            symbol_supported = await extended_hours_manager.validate_extended_hours_symbol(symbol)
            print(f"   ├─ Symbol supports extended hours: {symbol_supported}")
            
            # Test volume check
            sufficient_volume, volume = await extended_hours_manager.get_extended_hours_volume_check(symbol)
            print(f"   └─ Sufficient volume: {sufficient_volume} (volume: {volume:,})")
        
        # Test order configuration
        print("\n📋 Testing Extended Hours Order Configuration...")
        
        test_order = {
            'symbol': 'AAPL',
            'side': 'buy',
            'type': 'market',
            'qty': 10,
            'time_in_force': 'day'
        }
        
        print(f"   Original order: {test_order}")
        configured_order = await extended_hours_manager.configure_extended_hours_order(test_order, 'AAPL')
        print(f"   Configured order: {configured_order}")
        
        # Test market hours manager extended hours integration
        print("\n🔗 Testing Market Hours Manager Integration...")
        
        # Test extended hours trading enabled check
        is_enabled = await market_hours_manager.is_extended_hours_trading_enabled('AAPL')
        print(f"   Extended hours trading enabled for AAPL: {is_enabled}")
        
        # Test order configuration through market hours manager
        configured_via_manager = await market_hours_manager.configure_order_for_current_session(test_order, 'AAPL')
        print(f"   Order configured via market hours manager: {configured_via_manager}")
        
        # Log extended hours status
        print("\n📊 Extended Hours Status Summary:")
        await extended_hours_manager.log_extended_hours_status()
        
        # Display configuration summary
        summary = extended_hours_manager.get_extended_hours_trading_summary()
        print(f"\n📋 Extended Hours Configuration Summary:")
        for key, value in summary.items():
            print(f"   {key}: {value}")
        
        print("\n✅ Extended hours integration test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Extended hours integration test failed: {e}")
        logger.error(f"Extended hours integration test error: {e}", exc_info=True)
        raise


async def test_session_transitions():
    """Test how extended hours manager handles different trading sessions."""
    print("\n🔄 TESTING SESSION TRANSITIONS")
    print("=" * 60)
    
    try:
        # Initialize components
        config = ConfigurationManager()
        market_hours_manager = AlpacaIntegratedMarketHoursManager(config)
        extended_hours_manager = ExtendedHoursManager(config, market_hours_manager)
        market_hours_manager.set_extended_hours_manager(extended_hours_manager)
        
        # Test different symbols during current session
        test_symbols = ['AAPL', 'GOOGL', 'TSLA', 'SPY', 'QQQ', 'UNKNOWN_SYMBOL']
        
        print(f"Testing {len(test_symbols)} symbols for extended hours eligibility...")
        
        for symbol in test_symbols:
            is_allowed, reason = await extended_hours_manager.is_extended_hours_trading_allowed(symbol)
            print(f"   {symbol:15s} | Allowed: {str(is_allowed):5s} | Reason: {reason}")
        
        # Test order configurations for different order types
        print(f"\n📋 Testing Order Configuration for Different Order Types:")
        
        order_types = [
            {'type': 'market', 'side': 'buy'},
            {'type': 'limit', 'side': 'buy', 'limit_price': 150.00},
            {'type': 'market', 'side': 'sell'},
            {'type': 'limit', 'side': 'sell', 'limit_price': 155.00},
        ]
        
        for order_type in order_types:
            base_order = {
                'symbol': 'AAPL',
                'qty': 10,
                'time_in_force': 'day',
                **order_type
            }
            
            configured = await extended_hours_manager.configure_extended_hours_order(base_order, 'AAPL')
            
            print(f"   {order_type['type']:6s} {order_type['side']:4s} order:")
            print(f"      Original:   {base_order}")
            print(f"      Configured: {configured}")
            print()
        
        print("✅ Session transitions test completed successfully!")
        
    except Exception as e:
        print(f"❌ Session transitions test failed: {e}")
        logger.error(f"Session transitions test error: {e}", exc_info=True)
        raise


async def test_extended_hours_account_check():
    """Test extended hours account capability checking."""
    print("\n🏦 TESTING EXTENDED HOURS ACCOUNT CHECK")
    print("=" * 60)
    
    try:
        config = ConfigurationManager()
        market_hours_manager = AlpacaIntegratedMarketHoursManager(config)
        
        # Initialize without Alpaca client to test fallback
        extended_hours_manager = ExtendedHoursManager(config, market_hours_manager, alpaca_client=None)
        
        # Test account availability
        is_available = await extended_hours_manager.is_extended_hours_available()
        print(f"   Extended hours available (no client): {is_available}")
        
        # Test multiple symbols
        symbols_to_test = ['AAPL', 'GOOGL', 'MSFT', 'AMD', 'NVDA', 'META', 'NFLX']
        print(f"\n   Testing {len(symbols_to_test)} symbols for extended hours support:")
        
        for symbol in symbols_to_test:
            is_supported = await extended_hours_manager.validate_extended_hours_symbol(symbol)
            print(f"      {symbol:6s}: {'✅ Supported' if is_supported else '❌ Not supported'}")
        
        print("\n✅ Extended hours account check test completed!")
        
    except Exception as e:
        print(f"❌ Extended hours account check test failed: {e}")
        logger.error(f"Extended hours account check error: {e}", exc_info=True)
        raise


async def main():
    """Run all extended hours integration tests."""
    print("🚀 STARTING EXTENDED HOURS INTEGRATION TESTS")
    print("=" * 80)
    print(f"Start time: {datetime.now(timezone.utc).isoformat()}")
    print()
    
    try:
        # Run tests
        await test_extended_hours_integration()
        await test_session_transitions()
        await test_extended_hours_account_check()
        
        print("\n" + "=" * 80)
        print("🎉 ALL EXTENDED HOURS INTEGRATION TESTS PASSED!")
        print("=" * 80)
        
    except Exception as e:
        print("\n" + "=" * 80)
        print(f"❌ EXTENDED HOURS INTEGRATION TESTS FAILED: {e}")
        print("=" * 80)
        raise


if __name__ == "__main__":
    asyncio.run(main())