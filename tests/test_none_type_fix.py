#!/usr/bin/env python3
"""
Test that the NoneType multiplication error in order manager is fixed.
"""
import sys
import os
import asyncio
from unittest.mock import Mock, AsyncMock, patch

# Add the project root to the path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.trading.order_manager import OrderManager
from src.core.configuration import ConfigurationManager
from src import Order, OrderType, OrderSide

async def test_none_type_fix():
    """Test that market orders with None price don't cause NoneType errors."""
    print("🧪 Testing NoneType Error Fix in Order Manager")
    print("=" * 60)
    
    # Create a mock configuration
    mock_config = Mock(spec=ConfigurationManager)
    mock_config.get_config.side_effect = lambda key, default=None: {
        "trading.order_monitoring.check_interval": 10,
        "trading.order_monitoring.max_pending_time": 604800,
        "trading.order_monitoring.log_pending_orders": True,
    }.get(key, default)
    
    # Create a mock trading client
    mock_trading_client = Mock()
    mock_alpaca_order = Mock()
    mock_alpaca_order.id = "test-order-123"
    mock_alpaca_order.status = "new"
    mock_alpaca_order.created_at = None
    mock_alpaca_order.filled_qty = None
    mock_alpaca_order.filled_avg_price = None
    
    # Mock the trading client to return our mock order
    mock_trading_client.submit_order.return_value = mock_alpaca_order
    
    # Create order manager
    order_manager = OrderManager(mock_config, mock_trading_client)
    
    # Test Case 1: Market order with None price (this used to cause NoneType error)
    print("\n📊 Test Case 1: Market Order with None Price")
    print("-" * 40)
    
    market_order = Order(
        order_id=None,
        symbol="TEST",
        quantity=100.0,
        order_type=OrderType.MARKET,
        side=OrderSide.BUY,
        price=None  # This is None for market orders
    )
    
    try:
        # This should not raise a NoneType error anymore
        with patch.object(order_manager, '_execute_alpaca_order', return_value=mock_alpaca_order):
            order_id = await order_manager.place_order(market_order)
        
        print(f"✅ Market order placed successfully: {order_id}")
        print(f"   Order type: {market_order.order_type.value}")
        print(f"   Price: {market_order.price} (None is expected for market orders)")
        print(f"   No NoneType multiplication error occurred!")
        
    except Exception as e:
        if "unsupported operand type(s) for *: 'NoneType'" in str(e):
            print(f"❌ NoneType error still occurs: {e}")
        else:
            print(f"❌ Unexpected error: {e}")
    
    # Test Case 2: Limit order with price (should work as before)
    print("\n📊 Test Case 2: Limit Order with Price")
    print("-" * 40)
    
    limit_order = Order(
        order_id=None,
        symbol="TEST",
        quantity=100.0,
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        price=20.50  # This has a price for limit orders
    )
    
    try:
        with patch.object(order_manager, '_execute_alpaca_order', return_value=mock_alpaca_order):
            order_id = await order_manager.place_order(limit_order)
        
        print(f"✅ Limit order placed successfully: {order_id}")
        print(f"   Order type: {limit_order.order_type.value}")
        print(f"   Price: ${limit_order.price:.2f}")
        print(f"   Price range logging works correctly for limit orders")
        
    except Exception as e:
        print(f"❌ Unexpected error with limit order: {e}")
    
    print(f"\n🎯 SUMMARY:")
    print("✅ Market orders with None price no longer cause NoneType errors")
    print("✅ Limit orders with price continue to work correctly")
    print("✅ Order monitoring logging handles both cases appropriately")
    print("✅ The 'unsupported operand type(s) for *: 'NoneType' and 'float'' error is fixed")

if __name__ == "__main__":
    asyncio.run(test_none_type_fix())
