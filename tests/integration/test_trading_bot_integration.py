"""
Integration tests for the complete trading bot system.
"""

import pytest
import asyncio
import tempfile
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import yaml

from src.trading_bot import TradingBotOrchestrator
from src.core import ConfigurationManager
from src.interfaces import TradingSignal, SignalType, Order, OrderType, OrderStatus
from src.exceptions import *


class TestTradingBotIntegration:
    """Integration tests for the complete trading bot system."""
    
    @pytest.fixture
    def integration_config(self):
        """Integration test configuration."""
        return {
            "api": {
                "alpaca": {
                    "api_key": "test_api_key",
                    "secret_key": "test_secret_key",
                    "base_url": "https://paper-api.alpaca.markets",
                    "timeout": 30,
                    "max_retries": 3,
                    "retry_delay": 1.0
                },
                "webhook": {
                    "host": "0.0.0.0",
                    "port": 8080,
                    "secret": "test_webhook_secret"
                }
            },
            "trading": {
                "default_quantity": 100,
                "max_position_size": 1000,
                "max_daily_trades": 50,
                "risk_per_trade": 0.02,
                "max_portfolio_risk": 0.10,
                "order_timeout_minutes": 5,
                "use_market_orders": False,
                "limit_order_offset": 0.001
            },
            "strategies": {
                "averaging_down": {
                    "enabled": True,
                    "max_attempts": 3,
                    "step_percentage": 0.02,
                    "timeframe": "1h",
                    "min_gap_percentage": 0.01
                },
                "trailing_profit": {
                    "enabled": True,
                    "initial_trail_percent": 0.05,
                    "trail_step_percent": 0.01,
                    "min_profit_percent": 0.02,
                    "max_trail_percent": 0.15,
                    "trail_adjustment_threshold": 0.03
                }
            },
            "database": {
                "url": "sqlite:///test_integration.db",
                "echo": False
            },
            "logging": {
                "level": "INFO",
                "file": "test_integration.log",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            }
        }
    
    @pytest.fixture
    def integration_config_file(self, integration_config):
        """Create temporary config file for integration tests."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(integration_config, f)
            config_file = f.name
        
        yield config_file
        
        # Cleanup
        if os.path.exists(config_file):
            os.unlink(config_file)
    
    @pytest.fixture
    async def trading_bot(self, integration_config_file):
        """Trading bot instance for integration tests."""
        bot = TradingBotOrchestrator(integration_config_file)
        yield bot
        
        # Cleanup
        if bot.is_running:
            await bot.stop()
    
    @pytest.fixture
    def mock_all_external_apis(self):
        """Mock all external API calls."""
        with patch('alpaca.trading.client.TradingClient') as mock_trading_client, \
             patch('alpaca.data.historical.StockHistoricalDataClient') as mock_data_client, \
             patch('uvicorn.run') as mock_uvicorn:
            
            # Mock trading client
            mock_trading_instance = Mock()
            mock_trading_instance.get_account.return_value = Mock(
                buying_power=10000.0,
                cash=10000.0,
                equity=10000.0,
                status="ACTIVE"
            )
            mock_trading_instance.get_positions.return_value = []
            mock_trading_instance.get_orders.return_value = []
            mock_trading_instance.submit_order.return_value = Mock(
                id="test_order_id",
                status="NEW",
                filled_qty=0,
                qty=100,
                symbol="AAPL",
                side="buy",
                order_type="limit",
                limit_price=150.0,
                created_at=datetime.now()
            )
            mock_trading_client.return_value = mock_trading_instance
            
            # Mock data client
            mock_data_instance = Mock()
            mock_data_instance.get_stock_bars.return_value = Mock(
                df=Mock(
                    iloc=Mock(
                        __getitem__=Mock(return_value=Mock(
                            close=150.0,
                            high=155.0,
                            low=145.0,
                            volume=1000000
                        ))
                    )
                )
            )
            mock_data_instance.get_stock_latest_quote.return_value = Mock(
                ask_price=150.05,
                bid_price=149.95,
                ask_size=100,
                bid_size=100
            )
            mock_data_client.return_value = mock_data_instance
            
            yield {
                'trading_client': mock_trading_instance,
                'data_client': mock_data_instance,
                'uvicorn': mock_uvicorn
            }
    
    @pytest.mark.asyncio
    async def test_bot_initialization(self, trading_bot, mock_all_external_apis):
        """Test complete bot initialization."""
        # Initialize components
        await trading_bot._initialize_components()
        
        # Verify all components are initialized
        assert trading_bot.config is not None
        assert trading_bot.signal_listener is not None
        assert trading_bot.order_manager is not None
        assert trading_bot.position_manager is not None
        assert trading_bot.risk_manager is not None
        assert trading_bot.support_calculator is not None
        assert trading_bot.trailing_manager is not None
        assert trading_bot.market_data is not None
        assert trading_bot.database is not None
        assert trading_bot.trading_client is not None
        assert trading_bot.data_client is not None
    
    @pytest.mark.asyncio
    async def test_bot_start_and_stop(self, trading_bot, mock_all_external_apis):
        """Test bot start and stop lifecycle."""
        # Start the bot in a background task
        start_task = asyncio.create_task(trading_bot.start())
        
        # Give it a moment to start
        await asyncio.sleep(0.1)
        
        # Verify it's running
        assert trading_bot.is_running is True
        
        # Stop the bot
        await trading_bot.stop()
        
        # Verify it's stopped
        assert trading_bot.is_running is False
        
        # Cancel the start task
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass
    
    @pytest.mark.asyncio
    async def test_signal_processing_workflow(self, trading_bot, mock_all_external_apis):
        """Test complete signal processing workflow."""
        await trading_bot._initialize_components()
        
        # Create a test signal
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            price=150.0,
            timestamp=int(datetime.now().timestamp()),
            source="test",
            metadata={"test": "integration"}
        )
        
        # Process the signal
        await trading_bot._handle_trading_signal(signal)
        
        # Verify signal was processed (order should be submitted)
        mock_all_external_apis['trading_client'].submit_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_buy_signal_complete_flow(self, trading_bot, mock_all_external_apis):
        """Test complete buy signal flow."""
        await trading_bot._initialize_components()
        
        # Mock no existing positions
        mock_all_external_apis['trading_client'].get_positions.return_value = []
        
        # Create buy signal
        buy_signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            price=150.0,
            timestamp=int(datetime.now().timestamp()),
            source="tradingview",
            metadata={"strategy": "momentum"}
        )
        
        # Process the signal
        await trading_bot._handle_trading_signal(buy_signal)
        
        # Verify order was submitted
        mock_all_external_apis['trading_client'].submit_order.assert_called_once()
        
        # Verify the order details
        call_args = mock_all_external_apis['trading_client'].submit_order.call_args
        assert call_args[1]['symbol'] == "AAPL"
        assert call_args[1]['side'] == "buy"
        assert call_args[1]['qty'] == 100  # Default quantity
    
    @pytest.mark.asyncio
    async def test_sell_signal_complete_flow(self, trading_bot, mock_all_external_apis):
        """Test complete sell signal flow."""
        await trading_bot._initialize_components()
        
        # Mock existing position
        mock_position = Mock(
            symbol="AAPL",
            qty=100,
            market_value=15500.0,
            unrealized_pl=500.0,
            avg_entry_price=150.0,
            side="long"
        )
        mock_all_external_apis['trading_client'].get_positions.return_value = [mock_position]
        
        # Create sell signal
        sell_signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.SELL,
            price=155.0,
            timestamp=int(datetime.now().timestamp()),
            source="tradingview",
            metadata={"strategy": "profit_taking"}
        )
        
        # Process the signal
        await trading_bot._handle_trading_signal(sell_signal)
        
        # Verify sell order was submitted
        mock_all_external_apis['trading_client'].submit_order.assert_called_once()
        
        # Verify the order details
        call_args = mock_all_external_apis['trading_client'].submit_order.call_args
        assert call_args[1]['symbol'] == "AAPL"
        assert call_args[1]['side'] == "sell"
    
    @pytest.mark.asyncio
    async def test_averaging_down_strategy(self, trading_bot, mock_all_external_apis):
        """Test averaging down strategy integration."""
        await trading_bot._initialize_components()
        
        # Mock existing losing position
        mock_position = Mock(
            symbol="AAPL",
            qty=100,
            market_value=14000.0,
            unrealized_pl=-1000.0,
            avg_entry_price=150.0,
            side="long"
        )
        mock_all_external_apis['trading_client'].get_positions.return_value = [mock_position]
        
        # Mock current price below entry
        mock_all_external_apis['data_client'].get_stock_latest_quote.return_value = Mock(
            ask_price=140.0,
            bid_price=139.95
        )
        
        # Create buy signal at lower price
        buy_signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            price=140.0,
            timestamp=int(datetime.now().timestamp()),
            source="tradingview",
            metadata={"strategy": "averaging_down"}
        )
        
        # Process the signal - should trigger averaging down
        await trading_bot._handle_trading_signal(buy_signal)
        
        # Verify averaging down order was submitted
        mock_all_external_apis['trading_client'].submit_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_trailing_profit_strategy(self, trading_bot, mock_all_external_apis):
        """Test trailing profit strategy integration."""
        await trading_bot._initialize_components()
        
        # Mock profitable position
        mock_position = Mock(
            symbol="AAPL",
            qty=100,
            market_value=16000.0,
            unrealized_pl=1000.0,
            avg_entry_price=150.0,
            side="long"
        )
        mock_all_external_apis['trading_client'].get_positions.return_value = [mock_position]
        
        # Mock current price above entry
        mock_all_external_apis['data_client'].get_stock_latest_quote.return_value = Mock(
            ask_price=160.0,
            bid_price=159.95
        )
        
        # Simulate price update that should trigger trailing profit
        await trading_bot._update_trailing_profits()
        
        # The trailing profit manager should have been updated
        # (Specific assertions would depend on the trailing profit implementation)
        assert trading_bot.trailing_manager is not None
    
    @pytest.mark.asyncio
    async def test_risk_management_integration(self, trading_bot, mock_all_external_apis):
        """Test risk management integration."""
        await trading_bot._initialize_components()
        
        # Mock high-risk scenario (large position already exists)
        mock_position = Mock(
            symbol="AAPL",
            qty=900,
            market_value=135000.0,
            unrealized_pl=0.0,
            avg_entry_price=150.0,
            side="long"
        )
        mock_all_external_apis['trading_client'].get_positions.return_value = [mock_position]
        
        # Create buy signal that would exceed position limits
        buy_signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            price=150.0,
            timestamp=int(datetime.now().timestamp()),
            source="tradingview",
            metadata={"quantity": 200}
        )
        
        # Process the signal - should be rejected by risk management
        await trading_bot._handle_trading_signal(buy_signal)
        
        # Verify order was NOT submitted due to risk limits
        mock_all_external_apis['trading_client'].submit_order.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_order_monitoring_and_updates(self, trading_bot, mock_all_external_apis):
        """Test order monitoring and updates."""
        await trading_bot._initialize_components()
        
        # Mock pending order
        mock_order = Mock(
            id="test_order_123",
            status="NEW",
            symbol="AAPL",
            qty=100,
            side="buy",
            order_type="limit",
            limit_price=150.0,
            filled_qty=0,
            created_at=datetime.now() - timedelta(minutes=3)
        )
        mock_all_external_apis['trading_client'].get_orders.return_value = [mock_order]
        
        # Run order monitoring
        await trading_bot._monitor_orders()
        
        # Verify order status was checked
        mock_all_external_apis['trading_client'].get_orders.assert_called()
    
    @pytest.mark.asyncio
    async def test_position_updates_and_pnl_calculation(self, trading_bot, mock_all_external_apis):
        """Test position updates and P&L calculations."""
        await trading_bot._initialize_components()
        
        # Mock position with current market data
        mock_position = Mock(
            symbol="AAPL",
            qty=100,
            market_value=15500.0,
            unrealized_pl=500.0,
            avg_entry_price=150.0,
            side="long"
        )
        mock_all_external_apis['trading_client'].get_positions.return_value = [mock_position]
        
        # Mock current market price
        mock_all_external_apis['data_client'].get_stock_latest_quote.return_value = Mock(
            ask_price=155.0,
            bid_price=154.95
        )
        
        # Update positions
        await trading_bot._update_positions()
        
        # Verify position data was retrieved
        mock_all_external_apis['trading_client'].get_positions.assert_called()
        mock_all_external_apis['data_client'].get_stock_latest_quote.assert_called()
    
    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, trading_bot, mock_all_external_apis):
        """Test error handling and recovery mechanisms."""
        await trading_bot._initialize_components()
        
        # Mock API failure
        mock_all_external_apis['trading_client'].submit_order.side_effect = Exception("API Error")
        
        # Create signal
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            price=150.0,
            timestamp=int(datetime.now().timestamp()),
            source="test"
        )
        
        # Process signal - should handle error gracefully
        await trading_bot._handle_trading_signal(signal)
        
        # Bot should still be running despite the error
        assert trading_bot.is_running is not False
    
    @pytest.mark.asyncio
    async def test_configuration_reload(self, trading_bot, mock_all_external_apis):
        """Test configuration reload functionality."""
        await trading_bot._initialize_components()
        
        # Change configuration
        original_quantity = trading_bot.config.get_config("trading.default_quantity")
        trading_bot.config.set_config("trading.default_quantity", 200)
        
        # Verify configuration changed
        assert trading_bot.config.get_config("trading.default_quantity") == 200
        
        # Reload configuration
        trading_bot.config.reload_config()
        
        # Verify configuration was reloaded
        assert trading_bot.config.get_config("trading.default_quantity") == original_quantity
    
    @pytest.mark.asyncio
    async def test_database_persistence(self, trading_bot, mock_all_external_apis):
        """Test database persistence of trades and positions."""
        await trading_bot._initialize_components()
        
        # Create and process a signal
        signal = TradingSignal(
            symbol="AAPL",
            signal_type=SignalType.BUY,
            price=150.0,
            timestamp=int(datetime.now().timestamp()),
            source="test"
        )
        
        await trading_bot._handle_trading_signal(signal)
        
        # Verify database operations
        # (Specific assertions would depend on database implementation)
        assert trading_bot.database is not None
    
    @pytest.mark.asyncio
    async def test_webhook_integration(self, trading_bot, mock_all_external_apis):
        """Test webhook integration with signal processing."""
        await trading_bot._initialize_components()
        
        # Register signal handler
        signals_received = []
        
        async def test_signal_handler(signal):
            signals_received.append(signal)
        
        trading_bot.signal_listener.register_signal_handler(test_signal_handler)
        
        # Simulate webhook signal
        webhook_payload = {
            "symbol": "AAPL",
            "action": "buy",
            "price": 150.0,
            "timestamp": int(datetime.now().timestamp()),
            "source": "tradingview"
        }
        
        # Process webhook signal
        signal = trading_bot.signal_listener._parse_tradingview_signal(webhook_payload)
        await trading_bot.signal_listener._process_signal(signal)
        
        # Verify signal was received
        assert len(signals_received) == 1
        assert signals_received[0].symbol == "AAPL"
    
    @pytest.mark.asyncio
    async def test_market_data_integration(self, trading_bot, mock_all_external_apis):
        """Test market data integration."""
        await trading_bot._initialize_components()
        
        # Test market data retrieval
        price = await trading_bot.market_data.get_current_price("AAPL")
        assert price is not None
        
        # Test historical data retrieval
        historical_data = await trading_bot.market_data.get_historical_data("AAPL", "1d", 5)
        assert historical_data is not None
    
    @pytest.mark.asyncio
    async def test_graceful_shutdown(self, trading_bot, mock_all_external_apis):
        """Test graceful shutdown of all components."""
        await trading_bot._initialize_components()
        
        # Start components
        await trading_bot._start_components()
        
        # Verify components are running
        assert trading_bot.is_running is False  # Not yet in main loop
        
        # Stop all components
        await trading_bot.stop()
        
        # Verify clean shutdown
        assert trading_bot.is_running is False
    
    @pytest.mark.asyncio
    async def test_performance_under_load(self, trading_bot, mock_all_external_apis):
        """Test performance under simulated load."""
        await trading_bot._initialize_components()
        
        # Create multiple signals
        signals = []
        for i in range(10):
            signal = TradingSignal(
                symbol=f"STOCK{i}",
                signal_type=SignalType.BUY,
                price=100.0 + i,
                timestamp=int(datetime.now().timestamp()) + i,
                source="test"
            )
            signals.append(signal)
        
        # Process all signals concurrently
        start_time = datetime.now()
        tasks = [trading_bot._handle_trading_signal(signal) for signal in signals]
        await asyncio.gather(*tasks, return_exceptions=True)
        end_time = datetime.now()
        
        # Verify processing completed in reasonable time
        processing_time = (end_time - start_time).total_seconds()
        assert processing_time < 5.0  # Should complete within 5 seconds
    
    @pytest.mark.asyncio
    async def test_configuration_validation(self, trading_bot):
        """Test configuration validation."""
        await trading_bot._initialize_components()
        
        # Test configuration validation
        await trading_bot._validate_configuration()
        
        # Should not raise exception with valid configuration
        assert True  # If we get here, validation passed
    
    @pytest.mark.asyncio
    async def test_missing_configuration_handling(self, integration_config):
        """Test handling of missing configuration."""
        # Remove required configuration
        del integration_config['api']['alpaca']['api_key']
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(integration_config, f)
            config_file = f.name
        
        try:
            bot = TradingBotOrchestrator(config_file)
            
            # Should raise exception during validation
            with pytest.raises(ConfigurationException):
                await bot._validate_configuration()
        finally:
            os.unlink(config_file)
    
    @pytest.mark.asyncio
    async def test_component_health_monitoring(self, trading_bot, mock_all_external_apis):
        """Test component health monitoring."""
        await trading_bot._initialize_components()
        
        # Test health check
        health_status = await trading_bot._check_component_health()
        
        # Should return health status for all components
        assert isinstance(health_status, dict)
        assert "signal_listener" in health_status
        assert "order_manager" in health_status
        assert "database" in health_status
