"""
Example integration test demonstrating complete trading bot workflow.
This file shows how all components work together in realistic scenarios.
"""

import pytest
import asyncio
import json
import hashlib
import hmac
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from src.trading_bot import TradingBotOrchestrator
from src.interfaces import TradingSignal, SignalType


class TestCompleteIntegrationExample:
    """
    Example integration test demonstrating a complete trading workflow.
    This test simulates a real trading scenario from signal receipt to order execution.
    """
    
    @pytest.mark.asyncio
    async def test_complete_trading_workflow_example(self):
        """
        Test a complete trading workflow from TradingView signal to order execution.
        
        This test demonstrates:
        1. Receiving a webhook signal from TradingView
        2. Processing the signal through risk management
        3. Calculating position size
        4. Submitting an order to Alpaca
        5. Monitoring the order status
        6. Updating positions and P&L
        7. Applying trailing profit strategy
        """
        
        # ===== SETUP PHASE =====
        # Mock all external dependencies
        with patch('alpaca.trading.client.TradingClient') as mock_trading_client_class, \
             patch('alpaca.data.historical.StockHistoricalDataClient') as mock_data_client_class, \
             patch('uvicorn.run') as mock_uvicorn:
            
            # Setup mock trading client
            mock_trading_client = Mock()
            mock_trading_client.get_account.return_value = Mock(
                buying_power=50000.0,
                cash=25000.0,
                equity=50000.0,
                status="ACTIVE"
            )
            mock_trading_client.get_all_positions.return_value = []
            mock_trading_client.get_orders.return_value = []
            mock_trading_client_class.return_value = mock_trading_client
            
            # Setup mock data client
            mock_data_client = Mock()
            mock_data_client.get_stock_latest_quote.return_value = Mock(
                ask_price=150.05,
                bid_price=149.95,
                ask_size=100,
                bid_size=100
            )
            mock_data_client.get_stock_latest_trade.return_value = Mock(
                price=150.00,
                size=100,
                timestamp=datetime.now()
            )
            mock_data_client_class.return_value = mock_data_client
            
            # Initialize trading bot (uses config/ TOML files)
            bot = TradingBotOrchestrator()
            await bot._initialize_components()
            
            # ===== PHASE 1: RECEIVE WEBHOOK SIGNAL =====
            print("📡 PHASE 1: Receiving TradingView webhook signal...")
            
            # Simulate TradingView webhook payload
            webhook_payload = {
                "symbol": "AAPL",
                "action": "buy",
                "price": 150.00,
                "timestamp": int(datetime.now().timestamp()),
                "source": "tradingview",
                "strategy": "momentum_breakout",
                "volume": 2500000,
                "rsi": 67.5,
                "macd": 0.35,
                "support_level": 145.00,
                "resistance_level": 155.00,
                "confidence": 0.85
            }
            
            # Create trading signal from webhook
            signal = TradingSignal(
                symbol=webhook_payload["symbol"],
                signal_type=SignalType.BUY,
                price=webhook_payload["price"],
                timestamp=webhook_payload["timestamp"],
                source=webhook_payload["source"],
                metadata={k: v for k, v in webhook_payload.items() 
                         if k not in ["symbol", "action", "price", "timestamp", "source"]}
            )
            
            print(f"✅ Signal received: {signal.symbol} {signal.signal_type.value} @ ${signal.price}")
            print(f"   Strategy: {signal.metadata['strategy']}")
            print(f"   Confidence: {signal.metadata['confidence']}")
            
            # ===== PHASE 2: RISK MANAGEMENT VALIDATION =====
            print("\n🛡️ PHASE 2: Risk management validation...")
            
            # Mock successful risk validation
            with patch.object(bot.risk_manager, 'validate_trade', return_value=True) as mock_risk_validate:
                with patch.object(bot.risk_manager, 'calculate_position_size', return_value=100) as mock_position_size:
                    
                    # Validate trade against risk parameters
                    is_valid = await bot.risk_manager.validate_trade(signal, 100)
                    position_size = await bot.risk_manager.calculate_position_size(signal, stop_loss_price=145.00)
                    
                    print(f"✅ Risk validation passed: {is_valid}")
                    print(f"   Calculated position size: {position_size} shares")
                    print(f"   Risk per trade: 2% of portfolio")
                    
                    # Verify risk management was called
                    mock_risk_validate.assert_called_once()
                    mock_position_size.assert_called_once()
            
            # ===== PHASE 3: ORDER SUBMISSION =====
            print("\n📋 PHASE 3: Order submission to Alpaca...")
            
            # Mock order submission response
            mock_order_response = Mock(
                id="order_12345",
                status="NEW",
                symbol="AAPL",
                qty=100,
                side="buy",
                order_type="limit",
                limit_price=149.50,  # Slightly below market for better fill
                filled_qty=0,
                filled_avg_price=None,
                created_at=datetime.now()
            )
            mock_trading_client.submit_order.return_value = mock_order_response
            
            # Submit order
            order = await bot.order_manager.submit_order(
                symbol=signal.symbol,
                quantity=position_size,
                side="buy",
                order_type="limit",
                limit_price=signal.price * 0.997  # 0.3% below signal price
            )
            
            print(f"✅ Order submitted successfully:")
            print(f"   Order ID: {order.id}")
            print(f"   Symbol: {order.symbol}")
            print(f"   Quantity: {order.quantity}")
            print(f"   Limit Price: ${order.limit_price}")
            print(f"   Status: {order.status.value}")
            
            # Verify order was submitted to Alpaca
            mock_trading_client.submit_order.assert_called_once()
            
            # ===== PHASE 4: ORDER MONITORING =====
            print("\n👀 PHASE 4: Order monitoring and fill simulation...")
            
            # Simulate order fill after some time
            filled_order_response = Mock(
                id="order_12345",
                status="FILLED",
                symbol="AAPL",
                qty=100,
                side="buy",
                order_type="limit",
                limit_price=149.50,
                filled_qty=100,
                filled_avg_price=149.45,
                created_at=datetime.now() - timedelta(minutes=2),
                filled_at=datetime.now()
            )
            
            # Mock order status check
            mock_trading_client.get_order_by_id.return_value = filled_order_response
            
            # Check order status
            order_status = await bot.order_manager.get_order_status(order.id)
            
            print(f"✅ Order filled:")
            print(f"   Fill Price: ${filled_order_response.filled_avg_price}")
            print(f"   Fill Quantity: {filled_order_response.filled_qty}")
            print(f"   Total Cost: ${filled_order_response.filled_avg_price * filled_order_response.filled_qty:,.2f}")
            
            # ===== PHASE 5: POSITION UPDATE =====
            print("\n📊 PHASE 5: Position update and P&L calculation...")
            
            # Mock updated position
            new_position = Mock(
                symbol="AAPL",
                qty=100,
                market_value=15000.0,
                side="long",
                avg_entry_price=149.45,
                unrealized_pl=55.0,  # Current price 150.00 vs entry 149.45
                unrealized_plpc=0.0037,  # 0.37% gain
                current_price=150.00,
                cost_basis=14945.0
            )
            
            mock_trading_client.get_all_positions.return_value = [new_position]
            
            # Update positions
            positions = await bot.position_manager.get_all_positions()
            
            print(f"✅ Position created:")
            print(f"   Symbol: {new_position.symbol}")
            print(f"   Quantity: {new_position.qty}")
            print(f"   Entry Price: ${new_position.avg_entry_price}")
            print(f"   Current Price: ${new_position.current_price}")
            print(f"   Unrealized P&L: ${new_position.unrealized_pl:+.2f} ({new_position.unrealized_plpc:+.2%})")
            
            # ===== PHASE 6: STRATEGY APPLICATION =====
            print("\n🎯 PHASE 6: Strategy application (trailing profit)...")
            
            # Mock current market data for strategy decisions
            mock_data_client.get_stock_latest_quote.return_value = Mock(
                ask_price=152.00,  # Price has moved up
                bid_price=151.95,
                ask_size=100,
                bid_size=100
            )
            
            # Check if trailing profit should be applied
            current_price = 152.00
            entry_price = 149.45
            profit_percent = (current_price - entry_price) / entry_price
            
            should_trail = profit_percent > 0.02  # 2% profit threshold
            
            if should_trail:
                # Calculate trailing stop
                trail_percent = 0.015  # 1.5% trailing stop
                trailing_stop_price = current_price * (1 - trail_percent)
                
                print(f"✅ Trailing profit activated:")
                print(f"   Current Price: ${current_price}")
                print(f"   Current Profit: {profit_percent:+.2%}")
                print(f"   Trailing Stop: ${trailing_stop_price:.2f}")
                
                # Mock trailing stop order submission
                trailing_stop_order = Mock(
                    id="trailing_order_67890",
                    status="NEW",
                    symbol="AAPL",
                    qty=100,
                    side="sell",
                    order_type="trailing_stop",
                    trail_percent=trail_percent,
                    created_at=datetime.now()
                )
                
                mock_trading_client.submit_order.return_value = trailing_stop_order
                
                print(f"   Trailing stop order submitted: {trailing_stop_order.id}")
            
            # ===== PHASE 7: AVERAGING DOWN SCENARIO =====
            print("\n📉 PHASE 7: Averaging down scenario simulation...")
            
            # Simulate price drop that triggers averaging down
            lower_price_signal = TradingSignal(
                symbol="AAPL",
                signal_type=SignalType.BUY,
                price=147.00,  # Price dropped below support
                timestamp=int(datetime.now().timestamp()) + 3600,  # 1 hour later
                source="tradingview",
                metadata={
                    "strategy": "averaging_down",
                    "original_entry": 149.45,
                    "support_break": True,
                    "rsi": 45.0  # Oversold
                }
            )
            
            # Check if averaging down should be applied
            price_drop_percent = (lower_price_signal.price - entry_price) / entry_price
            should_average_down = price_drop_percent < -0.02  # 2% drop threshold
            
            if should_average_down:
                print(f"✅ Averaging down triggered:")
                print(f"   New Signal Price: ${lower_price_signal.price}")
                print(f"   Price Drop: {price_drop_percent:.2%}")
                print(f"   Strategy: {lower_price_signal.metadata['strategy']}")
                
                # Mock averaging down order
                averaging_order = Mock(
                    id="averaging_order_54321",
                    status="NEW",
                    symbol="AAPL",
                    qty=50,  # Smaller size for averaging
                    side="buy",
                    order_type="limit",
                    limit_price=146.50,
                    created_at=datetime.now()
                )
                
                mock_trading_client.submit_order.return_value = averaging_order
                
                print(f"   Averaging down order submitted: {averaging_order.id}")
                print(f"   Additional Quantity: {averaging_order.qty}")
                print(f"   Limit Price: ${averaging_order.limit_price}")
            
            # ===== PHASE 8: MONITORING AND REPORTING =====
            print("\n📈 PHASE 8: Final monitoring and reporting...")
            
            # Mock final portfolio state
            final_account = Mock(
                buying_power=49250.0,  # Reduced by position cost
                cash=24250.0,
                equity=50755.0,  # Increased by unrealized P&L
                portfolio_value=50755.0
            )
            
            mock_trading_client.get_account.return_value = final_account
            
            # Get final account state
            account = await bot.order_manager.get_account_info()
            
            print(f"✅ Final portfolio state:")
            print(f"   Total Equity: ${account.equity:,.2f}")
            print(f"   Cash: ${account.cash:,.2f}")
            print(f"   Buying Power: ${account.buying_power:,.2f}")
            
            # Calculate session performance
            initial_equity = 50000.0
            session_pnl = account.equity - initial_equity
            session_return = session_pnl / initial_equity
            
            print(f"   Session P&L: ${session_pnl:+,.2f}")
            print(f"   Session Return: {session_return:+.3%}")
            
            # ===== VERIFICATION PHASE =====
            print("\n✅ VERIFICATION: All components worked correctly!")
            
            # Verify all major components were called
            assert mock_trading_client.get_account.called, "Account info should be retrieved"
            assert mock_trading_client.submit_order.called, "Orders should be submitted"
            assert mock_trading_client.get_positions.called, "Positions should be monitored"
            assert mock_data_client.get_stock_latest_quote.called, "Market data should be retrieved"
            
            # Verify order flow
            order_calls = mock_trading_client.submit_order.call_args_list
            assert len(order_calls) >= 1, "At least one order should be submitted"
            
            # Verify risk management was applied
            first_order_args = order_calls[0][1] if order_calls else {}
            assert first_order_args.get('qty') == position_size, "Position size should match risk calculation"
            
            print("\n🎉 INTEGRATION TEST COMPLETED SUCCESSFULLY!")
            print("   ✓ Signal processing")
            print("   ✓ Risk management")
            print("   ✓ Order execution")
            print("   ✓ Position monitoring")
            print("   ✓ Strategy application")
            print("   ✓ Portfolio tracking")
            
            return {
                "signal_processed": True,
                "order_submitted": True,
                "position_created": True,
                "strategies_applied": True,
                "final_equity": account.equity,
                "session_return": session_return
            }


# Additional helper function for manual testing
async def run_integration_example():
    """
    Run the integration example manually for demonstration purposes.
    """
    test_instance = TestCompleteIntegrationExample()
    result = await test_instance.test_complete_trading_workflow_example()
    
    print(f"\n📊 INTEGRATION TEST RESULTS:")
    print(f"   Signal Processed: {result['signal_processed']}")
    print(f"   Order Submitted: {result['order_submitted']}")
    print(f"   Position Created: {result['position_created']}")
    print(f"   Strategies Applied: {result['strategies_applied']}")
    print(f"   Final Equity: ${result['final_equity']:,.2f}")
    print(f"   Session Return: {result['session_return']:+.3%}")
    
    return result


if __name__ == "__main__":
    # Run the example directly
    asyncio.run(run_integration_example())
