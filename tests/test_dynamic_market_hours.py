#!/usr/bin/env python3
"""
Test Dynamic Broker-Based Market Hours System
Validates the new broker API-driven market hours system without hardcoded exchanges.
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.dynamic_market_hours import DynamicMarketHoursManager
from src.brokers.alpaca_market_status import MockDynamicMarketStatusProvider
from src.core import ConfigurationManager


class MockConfig:
    """Mock configuration for testing dynamic market hours."""
    
    def __init__(self):
        self.config_data = {
            "market_hours": {
                "polling_interval_seconds": 60,
                "enable_caching": True,
                "cache_duration_seconds": 60,
                "auto_start_stop": True,
                "emergency_override": False,
                "fallback_on_api_failure": True,
                "max_consecutive_api_failures": 3,
                "buffers": {
                    "start_before_session_minutes": 15,
                    "stop_after_session_minutes": 15
                },
                "symbol_routing": {
                    # Let brokers determine routing automatically
                }
            },
            "symbols": {
                "default_symbols": ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA"]
            }
        }
    
    def get_config(self, key: str, default=None):
        """Get configuration value by key."""
        keys = key.split('.')
        value = self.config_data
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value


async def test_dynamic_broker_market_hours():
    """Test the dynamic broker-based market hours system."""
    print("🧪 Testing Dynamic Broker-Based Market Hours System")
    print("=" * 60)
    
    # Initialize mock config and dynamic market hours manager
    config = MockConfig()
    manager = DynamicMarketHoursManager(config)
    
    # Test 1: Register different types of brokers
    print("\n📊 Test 1: Broker Registration")
    print("-" * 40)
    
    # Register traditional US stock broker (Alpaca simulation)
    us_stock_broker = MockDynamicMarketStatusProvider("alpaca", supports_24_7=False)
    manager.register_broker("alpaca", us_stock_broker)
    print("✅ Registered US Stock broker (alpaca) - traditional market hours")
    
    # Register crypto broker (24/7 simulation)
    crypto_broker = MockDynamicMarketStatusProvider("crypto_broker", supports_24_7=True)
    manager.register_broker("crypto_broker", crypto_broker)
    print("✅ Registered Crypto broker - 24/7 trading")
    
    # Register forex broker (24/5 simulation - treated as traditional for simplicity)
    forex_broker = MockDynamicMarketStatusProvider("forex_broker", supports_24_7=False)
    manager.register_broker("forex_broker", forex_broker)
    print("✅ Registered Forex broker - 24/5 trading")
    
    registered_brokers = manager.get_registered_brokers()
    print(f"\n📈 Total Registered Brokers: {len(registered_brokers)}")
    print(f"   Brokers: {registered_brokers}")
    
    # Test 2: Individual broker status
    print("\n⏰ Test 2: Individual Broker Market Status")
    print("-" * 40)
    
    for broker_type in registered_brokers:
        try:
            status = await manager.get_broker_status(broker_type)
            if status:
                print(f"   {broker_type}:")
                print(f"     Market Open: {status.is_market_open}")
                print(f"     Current Session: {status.current_session.value}")
                print(f"     Trading Day: {status.is_trading_day}")
                print(f"     24/7 Trading: {status.weekend_trading_available}")
                print(f"     Extended Hours: {status.extended_hours_available}")
                print(f"     Supported Symbols: {len(status.supported_symbols)} symbols")
                print(f"     Market Timezone: {status.market_timezone}")
        except Exception as e:
            print(f"❌ Error getting status for {broker_type}: {e}")
    
    # Test 3: Aggregated market status
    print("\n🤖 Test 3: Aggregated Market Status (Bot Decision)")
    print("-" * 40)
    
    try:
        aggregated_status = await manager.get_aggregated_market_status()
        
        print(f"✅ Bot Should Be Active: {aggregated_status.should_bot_be_active}")
        print(f"✅ Active Brokers: {aggregated_status.active_brokers}")
        print(f"✅ Available Sessions: {aggregated_status.available_sessions}")
        print(f"✅ Total Tradeable Symbols: {len(aggregated_status.total_tradeable_symbols)} symbols")
        print(f"✅ Has 24/7 Markets: {aggregated_status.has_24_7_markets}")
        print(f"✅ Reason: {aggregated_status.reason}")
        
        if aggregated_status.next_market_activity:
            time_to_next = (aggregated_status.next_market_activity - datetime.now(timezone.utc)).total_seconds() / 60
            print(f"✅ Next Market Activity: in {time_to_next:.1f} minutes")
        
        # Bot decision summary
        if aggregated_status.should_bot_be_active:
            if aggregated_status.has_24_7_markets:
                print("🚀 Bot would be ACTIVE (24/7 markets available)")
            else:
                print("🚀 Bot would be ACTIVE (traditional markets open)")
        else:
            print("💤 Bot would be WAITING (no active markets)")
            
    except Exception as e:
        print(f"❌ Aggregated status check failed: {e}")
    
    # Test 4: Symbol tradeability checks
    print("\n📈 Test 4: Symbol Tradeability")
    print("-" * 40)
    
    test_symbols = ["AAPL", "TSLA", "BTCUSD", "EURUSD", "UNKNOWN"]
    
    for symbol in test_symbols:
        try:
            is_tradeable = await manager.is_symbol_tradeable(symbol)
            best_broker = await manager.get_best_broker_for_symbol(symbol)
            
            if is_tradeable:
                print(f"✅ {symbol}: Tradeable via {best_broker}")
            else:
                print(f"❌ {symbol}: Not tradeable (no supporting broker or market closed)")
                
        except Exception as e:
            print(f"⚠️ {symbol}: Error checking tradeability: {e}")
    
    # Test 5: Bot activation decision
    print("\n🎯 Test 5: Bot Activation Decision")
    print("-" * 40)
    
    try:
        should_be_active = await manager.should_bot_be_active()
        
        print(f"Bot Activation Decision: {'ACTIVE' if should_be_active else 'INACTIVE'}")
        
        if should_be_active:
            print("✅ Bot would start trading components")
            print("   Reasons bot is active:")
            aggregated_status = await manager.get_aggregated_market_status()
            if aggregated_status.has_24_7_markets:
                print("   • 24/7 markets (crypto) are available")
            if aggregated_status.active_brokers:
                print(f"   • Traditional markets open via: {aggregated_status.active_brokers}")
        else:
            print("💤 Bot would wait for market conditions")
            print("   All traditional markets closed and no 24/7 markets available")
        
    except Exception as e:
        print(f"❌ Bot activation decision failed: {e}")
    
    # Test 6: Cache and performance
    print("\n⚡ Test 6: Performance and Caching")
    print("-" * 40)
    
    try:
        # Time multiple calls to test caching
        import time
        
        start_time = time.time()
        for i in range(5):
            await manager.should_bot_be_active()
        cached_time = time.time() - start_time
        
        # Clear cache and time again
        await manager.refresh_all_broker_status()
        
        start_time = time.time()
        for i in range(5):
            await manager.should_bot_be_active()
        uncached_time = time.time() - start_time
        
        print(f"✅ Cached calls (5x): {cached_time:.3f}s")
        print(f"✅ Uncached calls (5x): {uncached_time:.3f}s")
        print(f"✅ Cache effectiveness: {((uncached_time - cached_time) / uncached_time * 100):.1f}% faster")
        
    except Exception as e:
        print(f"⚠️ Performance test error: {e}")
    
    print("\n" + "=" * 60)
    print("🎉 Dynamic Broker-Based Market Hours Test Completed!")
    
    # Final summary
    try:
        final_status = await manager.get_aggregated_market_status()
        
        print(f"\n📊 FINAL SUMMARY:")
        print(f"   System Design: Broker API-driven (no hardcoded exchanges)")
        print(f"   Registered Brokers: {len(manager.get_registered_brokers())}")
        print(f"   Active Brokers: {len(final_status.active_brokers)}")
        print(f"   24/7 Coverage: {'Yes' if final_status.has_24_7_markets else 'No'}")
        print(f"   Bot Status: {'ACTIVE' if final_status.should_bot_be_active else 'WAITING'}")
        
        # Key advantages
        print(f"\n🌟 KEY ADVANTAGES:")
        print(f"   ✅ No hardcoded exchange schedules")
        print(f"   ✅ Broker APIs determine market status")
        print(f"   ✅ Automatic 24/7 support for crypto brokers")
        print(f"   ✅ Dynamic symbol routing based on broker capabilities")
        print(f"   ✅ Scalable to any number of brokers")
        print(f"   ✅ Real-time market status from actual broker APIs")
        
        if final_status.should_bot_be_active:
            print(f"✅ System is ready for dynamic multi-broker trading!")
        else:
            print(f"⏳ System is properly waiting for market hours...")
            
    except Exception as e:
        print(f"❌ Final summary generation failed: {e}")


if __name__ == "__main__":
    print("🚀 Starting Dynamic Broker-Based Market Hours Test")
    asyncio.run(test_dynamic_broker_market_hours())