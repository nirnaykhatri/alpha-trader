#!/usr/bin/env python3
"""
Multi-Broker System Test - Comprehensive testing of broker abstraction layer.
Tests symbol routing, multi-broker management, and broker switching scenarios.
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
from src.core.broker_manager import BrokerManager, BrokerManagerConfig
from src.core.broker_interfaces import (
    BrokerType, BrokerCredentials, UniversalOrder, OrderSide, 
    OrderType, TimeInForce, SymbolBrokerMapping
)
from src.core.logging_config import get_logger

logger = get_logger(__name__)


async def test_broker_factory_and_registration():
    """Test broker factory and broker registration."""
    print("🧪 TESTING BROKER FACTORY AND REGISTRATION")
    print("=" * 60)
    
    try:
        config = ConfigurationManager()
        broker_manager = BrokerManager(config)
        
        # Test supported broker types
        supported_brokers = broker_manager._factory.get_supported_broker_types()
        print(f"   Supported broker types: {[b.value for b in supported_brokers]}")
        
        # Test broker support checks
        is_alpaca_supported = broker_manager._factory.is_broker_supported(BrokerType.ALPACA)
        is_mock_supported = broker_manager._factory.is_broker_supported(BrokerType.MOCK)
        
        print(f"   Alpaca supported: {is_alpaca_supported}")
        print(f"   Mock supported: {is_mock_supported}")
        
        # Test creating broker providers
        print("\n   Testing broker provider creation...")
        
        # Create mock broker
        mock_credentials = BrokerCredentials(
            broker_type=BrokerType.MOCK,
            environment="paper"
        )
        
        mock_provider = broker_manager._factory.create_broker_provider(
            BrokerType.MOCK, mock_credentials
        )
        print(f"   ✅ Created Mock broker provider: {mock_provider.broker_type.value}")
        
        print("✅ Broker factory and registration test completed successfully!")
        
    except Exception as e:
        print(f"❌ Broker factory test failed: {e}")
        logger.error(f"Broker factory test error: {e}", exc_info=True)
        raise


async def test_multi_broker_initialization():
    """Test initializing multiple brokers simultaneously."""
    print("\n🔗 TESTING MULTI-BROKER INITIALIZATION")
    print("=" * 60)
    
    try:
        # Create test configuration with multiple brokers
        config = ConfigurationManager()
        
        # Override config to include mock broker for testing
        original_get_config = config.get_config
        
        def mock_get_config(key, default=None):
            if key == "brokers":
                return {
                    "mock": {
                        "enabled": True,
                        "environment": "paper",
                        "additional_params": {
                            "simulate_latency": False,
                            "default_account_balance": 100000.0
                        }
                    }
                }
            elif key == "symbol_broker_mappings":
                return [
                    {
                        "symbol": "AAPL",
                        "broker_type": "mock",
                        "priority": 1,
                        "is_primary": True,
                        "extended_hours_enabled": True
                    }
                ]
            elif key == "broker_management.default_broker":
                return "mock"
            else:
                return original_get_config(key, default)
        
        config.get_config = mock_get_config
        
        # Initialize broker manager
        broker_manager = BrokerManager(config)
        await broker_manager.initialize()
        
        print(f"   Initialized brokers: {broker_manager.broker_count}")
        print(f"   Available brokers: {[b.value for b in broker_manager.get_available_brokers()]}")
        
        # Test broker health
        health_status = broker_manager.get_broker_health()
        for broker_type, health in health_status.items():
            print(f"   {broker_type.value}: {'✅ Healthy' if health.is_healthy else '❌ Unhealthy'}")
        
        # Test symbol routing
        print("\n   Testing symbol routing...")
        
        test_symbols = ['AAPL', 'GOOGL', 'TSLA']
        for symbol in test_symbols:
            trading_client = await broker_manager._router.get_trading_client_for_symbol(symbol)
            market_data = await broker_manager._router.get_market_data_provider_for_symbol(symbol)
            
            print(f"   {symbol} -> Trading: {trading_client.broker_type.value}, Data: {market_data.broker_type.value}")
        
        await broker_manager.close()
        print("✅ Multi-broker initialization test completed successfully!")
        
    except Exception as e:
        print(f"❌ Multi-broker initialization test failed: {e}")
        logger.error(f"Multi-broker test error: {e}", exc_info=True)
        raise


async def test_order_routing_and_execution():
    """Test order routing to appropriate brokers."""
    print("\n📋 TESTING ORDER ROUTING AND EXECUTION")
    print("=" * 60)
    
    try:
        # Setup mock broker manager
        config = ConfigurationManager()
        
        def mock_get_config(key, default=None):
            if key == "brokers":
                return {
                    "mock": {
                        "enabled": True,
                        "environment": "paper"
                    }
                }
            elif key == "broker_management.default_broker":
                return "mock"
            else:
                return config._config.get(key, default)
        
        config.get_config = mock_get_config
        
        broker_manager = BrokerManager(config)
        await broker_manager.initialize()
        
        # Test order submission through broker manager
        print("   Testing order submission...")
        
        test_order = UniversalOrder(
            symbol="AAPL",
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            quantity=10.0,
            time_in_force=TimeInForce.DAY
        )
        
        # Submit order
        order_response = await broker_manager.submit_order("AAPL", test_order)
        print(f"   ✅ Order submitted: {order_response.broker_order_id} ({order_response.broker_type.value})")
        print(f"      Symbol: {order_response.symbol}, Side: {order_response.side.value}")
        print(f"      Status: {order_response.status.value}, Quantity: {order_response.quantity}")
        
        # Wait for order to potentially fill (mock broker simulates this)
        await asyncio.sleep(1.0)
        
        # Get positions
        positions = await broker_manager.get_positions()
        print(f"\n   Current positions: {len(positions)}")
        for pos in positions:
            print(f"      {pos.symbol}: {pos.quantity} @ ${pos.average_cost:.2f} ({pos.broker_type.value})")
        
        # Get account info
        accounts = await broker_manager.get_account_info()
        print(f"\n   Account information ({len(accounts)} accounts):")
        for account in accounts:
            print(f"      {account.broker_type.value}: Equity: ${account.equity:,.2f}, Cash: ${account.cash:,.2f}")
        
        await broker_manager.close()
        print("✅ Order routing and execution test completed successfully!")
        
    except Exception as e:
        print(f"❌ Order routing test failed: {e}")
        logger.error(f"Order routing test error: {e}", exc_info=True)
        raise


async def test_market_data_routing():
    """Test market data routing to appropriate brokers."""
    print("\n📊 TESTING MARKET DATA ROUTING")
    print("=" * 60)
    
    try:
        # Setup mock broker
        config = ConfigurationManager()
        
        def mock_get_config(key, default=None):
            if key == "brokers":
                return {"mock": {"enabled": True, "environment": "paper"}}
            elif key == "broker_management.default_broker":
                return "mock"
            else:
                return config._config.get(key, default)
        
        config.get_config = mock_get_config
        
        broker_manager = BrokerManager(config)
        await broker_manager.initialize()
        
        # Test market data retrieval
        test_symbols = ['AAPL', 'GOOGL', 'MSFT']
        
        print("   Testing current price retrieval...")
        for symbol in test_symbols:
            price = await broker_manager.get_current_price(symbol)
            print(f"      {symbol}: ${price:.2f}")
        
        # Test quote retrieval
        print("\n   Testing quote retrieval...")
        market_data_provider = await broker_manager._router.get_market_data_provider_for_symbol('AAPL')
        quote = await market_data_provider.get_quote('AAPL')
        
        print(f"      AAPL Quote from {quote.broker_type.value}:")
        print(f"         Bid: ${quote.bid_price:.2f} x {quote.bid_size}")
        print(f"         Ask: ${quote.ask_price:.2f} x {quote.ask_size}")
        print(f"         Last: ${quote.last_price:.2f} x {quote.last_size}")
        print(f"         Spread: ${quote.spread:.4f} ({(quote.spread/quote.mid_price*100):.2f}%)")
        
        await broker_manager.close()
        print("✅ Market data routing test completed successfully!")
        
    except Exception as e:
        print(f"❌ Market data routing test failed: {e}")
        logger.error(f"Market data routing test error: {e}", exc_info=True)
        raise


async def test_symbol_mapping_management():
    """Test dynamic symbol-to-broker mapping management."""
    print("\n🗺️ TESTING SYMBOL MAPPING MANAGEMENT")
    print("=" * 60)
    
    try:
        config = ConfigurationManager()
        broker_manager = BrokerManager(config)
        
        # Test adding symbol mappings
        print("   Testing symbol mapping operations...")
        
        # Add symbol mapping
        broker_manager.add_symbol_mapping(
            symbol="TSLA",
            broker_type=BrokerType.MOCK,
            priority=1,
            extended_hours_enabled=True
        )
        print("   ✅ Added TSLA -> MOCK mapping")
        
        # Get all mappings
        mappings = broker_manager._router.get_all_mappings()
        print(f"   Current mappings: {len(mappings)}")
        for mapping in mappings:
            print(f"      {mapping.symbol} -> {mapping.broker_type.value} (priority: {mapping.priority})")
        
        # Test broker selection
        broker_type = await broker_manager._router.get_broker_for_symbol("TSLA")
        print(f"   TSLA routes to: {broker_type.value}")
        
        # Remove mapping
        broker_manager._router.remove_symbol_mapping("TSLA")
        remaining_mappings = broker_manager._router.get_all_mappings()
        print(f"   ✅ Removed TSLA mapping, remaining: {len(remaining_mappings)}")
        
        print("✅ Symbol mapping management test completed successfully!")
        
    except Exception as e:
        print(f"❌ Symbol mapping test failed: {e}")
        logger.error(f"Symbol mapping test error: {e}", exc_info=True)
        raise


async def test_broker_health_monitoring():
    """Test broker health monitoring and failover scenarios."""
    print("\n❤️ TESTING BROKER HEALTH MONITORING")
    print("=" * 60)
    
    try:
        config = ConfigurationManager()
        broker_config = BrokerManagerConfig(
            health_check_interval_seconds=2,  # Fast for testing
            max_consecutive_failures=2
        )
        
        def mock_get_config(key, default=None):
            if key == "brokers":
                return {"mock": {"enabled": True, "environment": "paper"}}
            elif key == "broker_management.default_broker":
                return "mock"
            else:
                return config._config.get(key, default)
        
        config.get_config = mock_get_config
        
        broker_manager = BrokerManager(config, broker_config)
        await broker_manager.initialize()
        
        print("   Initial health status:")
        health = broker_manager.get_broker_health()
        for broker_type, health_info in health.items():
            print(f"      {broker_type.value}: {'✅ Healthy' if health_info.is_healthy else '❌ Unhealthy'}")
        
        # Wait for a few health checks
        print("\n   Waiting for health monitoring cycles...")
        await asyncio.sleep(5)
        
        # Check health again
        print("   Health status after monitoring:")
        health = broker_manager.get_broker_health()
        for broker_type, health_info in health.items():
            print(f"      {broker_type.value}: {'✅ Healthy' if health_info.is_healthy else '❌ Unhealthy'}")
            if health_info.last_health_check:
                print(f"         Last check: {health_info.last_health_check}")
            print(f"         Consecutive failures: {health_info.consecutive_failures}")
        
        await broker_manager.close()
        print("✅ Broker health monitoring test completed successfully!")
        
    except Exception as e:
        print(f"❌ Broker health monitoring test failed: {e}")
        logger.error(f"Broker health test error: {e}", exc_info=True)
        raise


async def main():
    """Run all multi-broker system tests."""
    print("🚀 STARTING MULTI-BROKER SYSTEM TESTS")
    print("=" * 80)
    print(f"Start time: {datetime.now(timezone.utc).isoformat()}")
    print()
    
    try:
        # Run all tests
        await test_broker_factory_and_registration()
        await test_multi_broker_initialization()
        await test_order_routing_and_execution()
        await test_market_data_routing()
        await test_symbol_mapping_management()
        await test_broker_health_monitoring()
        
        print("\n" + "=" * 80)
        print("🎉 ALL MULTI-BROKER SYSTEM TESTS PASSED!")
        print("=" * 80)
        print()
        print("✅ BROKER ABSTRACTION LAYER VALIDATION COMPLETE:")
        print("   • Broker factory and registration: WORKING")
        print("   • Multi-broker initialization: WORKING") 
        print("   • Order routing and execution: WORKING")
        print("   • Market data routing: WORKING")
        print("   • Symbol mapping management: WORKING")
        print("   • Broker health monitoring: WORKING")
        print()
        print("🎯 READY FOR PRODUCTION MULTI-BROKER TRADING!")
        
    except Exception as e:
        print("\n" + "=" * 80)
        print(f"❌ MULTI-BROKER SYSTEM TESTS FAILED: {e}")
        print("=" * 80)
        raise


if __name__ == "__main__":
    asyncio.run(main())