#!/usr/bin/env python3
"""
Test Exchange-Aware Market Hours System
Validates the new exchange-aware market hours configuration and functionality.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.exchange_market_hours import (
    ExchangeAwareMarketHoursManager, Exchange, ExchangeSchedule, MarketStatus
)
from src.core import ConfigurationManager


class MockConfig:
    """Mock configuration for testing."""
    
    def __init__(self):
        self.config_data = {
            "market_hours": {
                "default_exchange": "NYSE",
                "exchanges": {
                    "NYSE": {
                        "timezone": "America/New_York",
                        "regular_session": {
                            "start_time": "09:30",
                            "end_time": "16:00"
                        },
                        "extended_hours": {
                            "premarket": {
                                "enabled": True,
                                "start_time": "04:00",
                                "end_time": "09:30"
                            },
                            "postmarket": {
                                "enabled": True,
                                "start_time": "16:00",
                                "end_time": "20:00"
                            }
                        },
                        "weekend_trading": False,
                        "holidays_closed": True
                    },
                    "NASDAQ": {
                        "timezone": "America/New_York",
                        "regular_session": {
                            "start_time": "09:30",
                            "end_time": "16:00"
                        },
                        "extended_hours": {
                            "premarket": {
                                "enabled": True,
                                "start_time": "04:00",
                                "end_time": "09:30"
                            },
                            "postmarket": {
                                "enabled": True,
                                "start_time": "16:00",
                                "end_time": "20:00"
                            }
                        },
                        "weekend_trading": False,
                        "holidays_closed": True
                    },
                    "CRYPTO": {
                        "timezone": "UTC",
                        "regular_session": {
                            "start_time": "00:00",
                            "end_time": "23:59"
                        },
                        "weekend_trading": True,
                        "holidays_closed": False
                    },
                    "FOREX": {
                        "timezone": "UTC",
                        "regular_session": {
                            "start_time": "21:00",  # Sunday 21:00 UTC
                            "end_time": "21:00"     # Friday 21:00 UTC
                        },
                        "weekend_trading": False,
                        "holidays_closed": True
                    }
                },
                "symbol_exchanges": {
                    "AAPL": "NASDAQ",
                    "MSFT": "NASDAQ",
                    "SPY": "NYSE",
                    "TSLA": "NASDAQ",
                    "BTCUSD": "CRYPTO",
                    "EURUSD": "FOREX"
                },
                "broker_exchanges": {
                    "alpaca": {
                        "default_exchange": "NYSE",
                        "supported_exchanges": ["NYSE", "NASDAQ"]
                    },
                    "mock": {
                        "default_exchange": "NYSE",
                        "supported_exchanges": ["NYSE", "NASDAQ", "CRYPTO", "FOREX"]
                    }
                },
                "buffers": {
                    "start_before_session_minutes": 15,
                    "stop_after_session_minutes": 30
                }
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


async def test_exchange_market_hours():
    """Test the exchange-aware market hours system."""
    print("🧪 Testing Exchange-Aware Market Hours System")
    print("=" * 60)
    
    # Initialize mock config and market hours manager
    config = MockConfig()
    manager = ExchangeAwareMarketHoursManager(config)
    
    # Test 1: Exchange schedules loading
    print("\n📊 Test 1: Exchange Schedules Loading")
    print("-" * 40)
    
    supported_exchanges = manager.get_supported_exchanges()
    print(f"✅ Supported Exchanges: {[ex.value for ex in supported_exchanges]}")
    
    for exchange in supported_exchanges:
        if exchange in manager.exchange_schedules:
            schedule = manager.exchange_schedules[exchange]
            print(f"   {exchange.value}:")
            print(f"     Timezone: {schedule.timezone}")
            print(f"     Regular Hours: {schedule.regular_session.start_time} - {schedule.regular_session.end_time}")
            if schedule.premarket:
                print(f"     Premarket: {schedule.premarket.start_time} - {schedule.premarket.end_time}")
            if schedule.postmarket:
                print(f"     Postmarket: {schedule.postmarket.start_time} - {schedule.postmarket.end_time}")
    
    # Test 2: Symbol-to-exchange mapping
    print("\n🔍 Test 2: Symbol-to-Exchange Mapping")
    print("-" * 40)
    
    test_symbols = ["AAPL", "MSFT", "SPY", "TSLA", "BTCUSD", "EURUSD", "UNKNOWN"]
    
    for symbol in test_symbols:
        try:
            exchange = await manager.get_exchange_for_symbol(symbol)
            print(f"✅ {symbol} -> {exchange.value}")
        except Exception as e:
            print(f"❌ {symbol} -> Error: {e}")
    
    # Test 3: Market status for exchanges
    print("\n⏰ Test 3: Current Market Status")
    print("-" * 40)
    
    for exchange in [Exchange.NYSE, Exchange.NASDAQ, Exchange.CRYPTO, Exchange.FOREX]:
        try:
            status = await manager.get_market_status_for_exchange(exchange)
            print(f"   {exchange.value}:")
            print(f"     Current Session: {status.current_session.value}")
            print(f"     Market Open: {status.is_open}")
            print(f"     Trading Day: {status.is_trading_day}")
            print(f"     Local Time: {status.local_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"     Bot Should Be Active: {status.bot_should_be_active} ({status.activation_reason})")
        except Exception as e:
            print(f"❌ {exchange.value} -> Error: {e}")
    
    # Test 4: Overall bot activation status
    print("\n🤖 Test 4: Bot Activation Status")
    print("-" * 40)
    
    try:
        should_be_active = await manager.should_bot_be_active()
        active_exchanges = await manager.get_active_exchanges()
        
        print(f"✅ Bot Should Be Active: {should_be_active}")
        print(f"✅ Active Exchanges: {[ex.value for ex in active_exchanges]}")
        
        if should_be_active:
            print("🚀 Bot would be started based on current market conditions")
        else:
            print("💤 Bot would wait for favorable market conditions")
            
    except Exception as e:
        print(f"❌ Bot status check failed: {e}")
    
    # Test 5: Symbol-specific market status
    print("\n📈 Test 5: Symbol-Specific Market Status")
    print("-" * 40)
    
    for symbol in ["AAPL", "TSLA", "BTCUSD"]:
        try:
            status = await manager.get_market_status_for_symbol(symbol)
            exchange = await manager.get_exchange_for_symbol(symbol)
            print(f"   {symbol} ({exchange.value}):")
            print(f"     Session: {status.current_session.value}")
            print(f"     Market Open: {status.is_open}")
            print(f"     Bot Should Be Active: {status.bot_should_be_active}")
        except Exception as e:
            print(f"❌ {symbol} -> Error: {e}")
    
    print("\n" + "=" * 60)
    print("🎉 Exchange-Aware Market Hours Test Completed!")
    
    # Final summary
    try:
        total_supported = len(manager.get_supported_exchanges())
        total_active = len(await manager.get_active_exchanges())
        should_trade = await manager.should_bot_be_active()
        
        print(f"\n📊 SUMMARY:")
        print(f"   Total Supported Exchanges: {total_supported}")
        print(f"   Currently Active Exchanges: {total_active}")
        print(f"   Trading Bot Should Be Active: {should_trade}")
        
        if should_trade:
            print(f"✅ System is ready for multi-exchange trading!")
        else:
            print(f"⏳ System is waiting for market hours...")
            
    except Exception as e:
        print(f"❌ Summary generation failed: {e}")


if __name__ == "__main__":
    print("🚀 Starting Exchange-Aware Market Hours Test")
    asyncio.run(test_exchange_market_hours())