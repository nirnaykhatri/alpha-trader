"""
Integration tests for Alpaca API wrapper implementation.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
import pandas as pd

from src.trading import OrderManager
from src.data import AlpacaMarketDataProvider
from src.core import ConfigurationManager
from src.interfaces import Order, OrderType, OrderStatus, Position
from src.exceptions import OrderException, MarketDataException


class TestAlpacaAPIIntegration:
    """Integration tests for Alpaca API wrapper."""
    
    @pytest.fixture
    def config_manager(self, test_config_file):
        """Configuration manager for testing."""
        return ConfigurationManager(test_config_file)
    
    @pytest.fixture
    def mock_alpaca_trading_client(self):
        """Mock Alpaca trading client with comprehensive responses."""
        mock_client = Mock()
        
        # Mock account info
        mock_client.get_account.return_value = Mock(
            id="test_account_id",
            account_number="123456789",
            status="ACTIVE",
            currency="USD",
            buying_power=50000.0,
            regt_buying_power=25000.0,
            daytrading_buying_power=100000.0,
            cash=25000.0,
            portfolio_value=50000.0,
            equity=50000.0,
            last_equity=49500.0,
            multiplier=4,
            initial_margin=0.0,
            maintenance_margin=0.0,
            long_market_value=25000.0,
            short_market_value=0.0,
            pattern_day_trader=False,
            trading_blocked=False,
            transfers_blocked=False,
            account_blocked=False,
            created_at=datetime.now() - timedelta(days=365),
            trade_suspended_by_user=False,
            shorting_enabled=True,
            max_margin_multiplier=4.0,
            acats_elig=True,
            daytrade_count=0
        )
        
        # Mock positions
        mock_client.get_positions.return_value = [
            Mock(
                symbol="AAPL",
                qty=100,
                market_value=15000.0,
                side="long",
                avg_entry_price=150.0,
                unrealized_pl=0.0,
                unrealized_plpc=0.0,
                current_price=150.0,
                lastday_price=149.0,
                change_today=1.0,
                asset_id="test_asset_id",
                asset_class="us_equity",
                asset_marginable=True,
                cost_basis=15000.0,
                qty_available=100
            ),
            Mock(
                symbol="TSLA",
                qty=50,
                market_value=40000.0,
                side="long",
                avg_entry_price=800.0,
                unrealized_pl=2000.0,
                unrealized_plpc=0.05,
                current_price=840.0,
                lastday_price=820.0,
                change_today=20.0,
                asset_id="test_asset_id_2",
                asset_class="us_equity",
                asset_marginable=True,
                cost_basis=40000.0,
                qty_available=50
            )
        ]
        
        # Mock orders
        mock_client.get_orders.return_value = [
            Mock(
                id="order_123",
                client_order_id="client_order_123",
                created_at=datetime.now() - timedelta(minutes=5),
                updated_at=datetime.now() - timedelta(minutes=2),
                submitted_at=datetime.now() - timedelta(minutes=5),
                filled_at=datetime.now() - timedelta(minutes=2),
                expired_at=None,
                canceled_at=None,
                failed_at=None,
                replaced_at=None,
                replaced_by=None,
                replaces=None,
                asset_id="test_asset_id",
                symbol="AAPL",
                asset_class="us_equity",
                notional=None,
                qty=100,
                filled_qty=100,
                filled_avg_price=150.25,
                order_class="simple",
                order_type="limit",
                type="limit",
                side="buy",
                time_in_force="day",
                limit_price=150.50,
                stop_price=None,
                status="filled",
                extended_hours=False,
                legs=None,
                trail_percent=None,
                trail_price=None,
                hwm=None,
                commission=0.0,
                source="web"
            )
        ]
        
        # Mock order submission
        mock_client.submit_order.return_value = Mock(
            id="new_order_456",
            client_order_id="client_new_order_456",
            created_at=datetime.now(),
            updated_at=datetime.now(),
            submitted_at=datetime.now(),
            filled_at=None,
            expired_at=None,
            canceled_at=None,
            failed_at=None,
            replaced_at=None,
            replaced_by=None,
            replaces=None,
            asset_id="test_asset_id",
            symbol="AAPL",
            asset_class="us_equity",
            notional=None,
            qty=100,
            filled_qty=0,
            filled_avg_price=None,
            order_class="simple",
            order_type="limit",
            type="limit",
            side="buy",
            time_in_force="day",
            limit_price=150.00,
            stop_price=None,
            status="new",
            extended_hours=False,
            legs=None,
            trail_percent=None,
            trail_price=None,
            hwm=None,
            commission=0.0,
            source="api"
        )
        
        # Mock order cancellation
        mock_client.cancel_order_by_id.return_value = Mock(
            id="order_123",
            status="canceled",
            canceled_at=datetime.now()
        )
        
        # Mock order retrieval
        mock_client.get_order_by_id.return_value = Mock(
            id="order_123",
            status="filled",
            filled_qty=100,
            filled_avg_price=150.25
        )
        
        return mock_client
    
    @pytest.fixture
    def mock_alpaca_data_client(self):
        """Mock Alpaca data client with comprehensive responses."""
        mock_client = Mock()
        
        # Mock historical bars
        mock_bars_df = pd.DataFrame({
            'timestamp': pd.date_range('2023-01-01', periods=100, freq='1H'),
            'open': [150.0 + i * 0.1 for i in range(100)],
            'high': [151.0 + i * 0.1 for i in range(100)],
            'low': [149.0 + i * 0.1 for i in range(100)],
            'close': [150.5 + i * 0.1 for i in range(100)],
            'volume': [1000000 + i * 1000 for i in range(100)]
        })
        
        mock_client.get_stock_bars.return_value = Mock(
            df=mock_bars_df
        )
        
        # Mock latest quote
        mock_client.get_stock_latest_quote.return_value = Mock(
            ask_price=150.05,
            ask_size=100,
            bid_price=149.95,
            bid_size=200,
            timestamp=datetime.now()
        )
        
        # Mock latest trade
        mock_client.get_stock_latest_trade.return_value = Mock(
            price=150.00,
            size=100,
            timestamp=datetime.now()
        )
        
        # Mock latest bar
        mock_client.get_stock_latest_bar.return_value = Mock(
            open=149.50,
            high=150.75,
            low=149.25,
            close=150.00,
            volume=1500000,
            timestamp=datetime.now()
        )
        
        # Mock multi-symbol data
        mock_client.get_stock_bars.return_value = Mock(
            df=pd.DataFrame({
                'AAPL': mock_bars_df['close'],
                'TSLA': mock_bars_df['close'] * 5,
                'GOOGL': mock_bars_df['close'] * 20
            })
        )
        
        return mock_client
    
    @pytest.fixture
    def order_manager(self, config_manager, mock_alpaca_trading_client):
        """Order manager with mocked Alpaca client."""
        with patch('src.trading.order_manager.TradingClient') as mock_client_class:
            mock_client_class.return_value = mock_alpaca_trading_client
            return OrderManager(config_manager)
    
    @pytest.fixture
    def market_data_provider(self, config_manager, mock_alpaca_data_client):
        """Market data provider with mocked Alpaca client."""
        with patch('src.data.market_data.StockHistoricalDataClient') as mock_client_class:
            mock_client_class.return_value = mock_alpaca_data_client
            return AlpacaMarketDataProvider(config_manager)
    
    @pytest.mark.asyncio
    async def test_account_info_retrieval(self, order_manager, mock_alpaca_trading_client):
        """Test account information retrieval."""
        account = await order_manager.get_account_info()
        
        assert account is not None
        assert account.buying_power == 50000.0
        assert account.cash == 25000.0
        assert account.equity == 50000.0
        assert account.status == "ACTIVE"
        mock_alpaca_trading_client.get_account.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_position_retrieval(self, order_manager, mock_alpaca_trading_client):
        """Test position retrieval."""
        positions = await order_manager.get_positions()
        
        assert len(positions) == 2
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == 100
        assert positions[0].average_price == 150.0
        assert positions[1].symbol == "TSLA"
        assert positions[1].quantity == 50
        assert positions[1].average_price == 800.0
        mock_alpaca_trading_client.get_all_positions.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_order_submission_limit(self, order_manager, mock_alpaca_trading_client):
        """Test limit order submission."""
        order = await order_manager.submit_order(
            symbol="AAPL",
            quantity=100,
            side="buy",
            order_type=OrderType.LIMIT,
            limit_price=150.0
        )
        
        assert order.id == "new_order_456"
        assert order.symbol == "AAPL"
        assert order.quantity == 100
        assert order.side == "buy"
        assert order.order_type == OrderType.LIMIT
        assert order.limit_price == 150.0
        assert order.status == OrderStatus.NEW
        mock_alpaca_trading_client.submit_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_order_submission_market(self, order_manager, mock_alpaca_trading_client):
        """Test market order submission."""
        # Mock market order response
        mock_alpaca_trading_client.submit_order.return_value = Mock(
            id="market_order_789",
            symbol="AAPL",
            qty=100,
            side="buy",
            order_type="market",
            status="new",
            limit_price=None,
            stop_price=None,
            filled_qty=0,
            filled_avg_price=None,
            created_at=datetime.now()
        )
        
        order = await order_manager.submit_order(
            symbol="AAPL",
            quantity=100,
            side="buy",
            order_type=OrderType.MARKET
        )
        
        assert order.id == "market_order_789"
        assert order.order_type == OrderType.MARKET
        assert order.limit_price is None
        mock_alpaca_trading_client.submit_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_order_submission_stop_loss(self, order_manager, mock_alpaca_trading_client):
        """Test stop loss order submission."""
        # Mock stop loss order response
        mock_alpaca_trading_client.submit_order.return_value = Mock(
            id="stop_order_101",
            symbol="AAPL",
            qty=100,
            side="sell",
            order_type="stop",
            status="new",
            limit_price=None,
            stop_price=145.0,
            filled_qty=0,
            filled_avg_price=None,
            created_at=datetime.now()
        )
        
        order = await order_manager.submit_order(
            symbol="AAPL",
            quantity=100,
            side="sell",
            order_type=OrderType.STOP,
            stop_price=145.0
        )
        
        assert order.id == "stop_order_101"
        assert order.order_type == OrderType.STOP
        assert order.stop_price == 145.0
        mock_alpaca_trading_client.submit_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_order_cancellation(self, order_manager, mock_alpaca_trading_client):
        """Test order cancellation."""
        result = await order_manager.cancel_order("order_123")
        
        assert result is True
        mock_alpaca_trading_client.cancel_order_by_id.assert_called_once_with("order_123")
    
    @pytest.mark.asyncio
    async def test_order_status_retrieval(self, order_manager, mock_alpaca_trading_client):
        """Test order status retrieval."""
        status = await order_manager.get_order_status("order_123")
        
        assert status == OrderStatus.FILLED
        mock_alpaca_trading_client.get_order_by_id.assert_called_once_with("order_123")
    
    @pytest.mark.asyncio
    async def test_active_orders_retrieval(self, order_manager, mock_alpaca_trading_client):
        """Test active orders retrieval."""
        orders = await order_manager.get_active_orders()
        
        assert len(orders) == 1
        assert orders[0].id == "order_123"
        assert orders[0].status == OrderStatus.FILLED
        mock_alpaca_trading_client.get_orders.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_current_price_retrieval(self, market_data_provider, mock_alpaca_data_client):
        """Test current price retrieval."""
        price = await market_data_provider.get_current_price("AAPL")
        
        assert price == 150.00
        mock_alpaca_data_client.get_stock_latest_trade.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_latest_quote_retrieval(self, market_data_provider, mock_alpaca_data_client):
        """Test latest quote retrieval."""
        quote = await market_data_provider.get_latest_quote("AAPL")
        
        assert quote.ask_price == 150.05
        assert quote.bid_price == 149.95
        assert quote.ask_size == 100
        assert quote.bid_size == 200
        mock_alpaca_data_client.get_stock_latest_quote.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_historical_data_retrieval(self, market_data_provider, mock_alpaca_data_client):
        """Test historical data retrieval."""
        historical_data = await market_data_provider.get_historical_data(
            symbol="AAPL",
            timeframe="1H",
            limit=100
        )
        
        assert historical_data is not None
        assert len(historical_data) == 100
        mock_alpaca_data_client.get_stock_bars.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_multi_symbol_data_retrieval(self, market_data_provider, mock_alpaca_data_client):
        """Test multi-symbol data retrieval."""
        symbols = ["AAPL", "TSLA", "GOOGL"]
        data = await market_data_provider.get_multi_symbol_data(symbols, "1H", 50)
        
        assert data is not None
        assert len(data.columns) == 3
        mock_alpaca_data_client.get_stock_bars.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_order_with_bracket_strategy(self, order_manager, mock_alpaca_trading_client):
        """Test bracket order submission."""
        # Mock bracket order response
        mock_alpaca_trading_client.submit_order.return_value = Mock(
            id="bracket_order_201",
            symbol="AAPL",
            qty=100,
            side="buy",
            order_type="limit",
            status="new",
            limit_price=150.0,
            stop_price=None,
            filled_qty=0,
            filled_avg_price=None,
            created_at=datetime.now(),
            order_class="bracket",
            legs=[
                Mock(id="take_profit_leg", order_type="limit", limit_price=155.0),
                Mock(id="stop_loss_leg", order_type="stop", stop_price=145.0)
            ]
        )
        
        order = await order_manager.submit_bracket_order(
            symbol="AAPL",
            quantity=100,
            side="buy",
            limit_price=150.0,
            take_profit_price=155.0,
            stop_loss_price=145.0
        )
        
        assert order.id == "bracket_order_201"
        assert order.order_class == "bracket"
        assert len(order.legs) == 2
        mock_alpaca_trading_client.submit_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_trailing_stop_order(self, order_manager, mock_alpaca_trading_client):
        """Test trailing stop order submission."""
        # Mock trailing stop order response
        mock_alpaca_trading_client.submit_order.return_value = Mock(
            id="trailing_stop_301",
            symbol="AAPL",
            qty=100,
            side="sell",
            order_type="trailing_stop",
            status="new",
            limit_price=None,
            stop_price=None,
            trail_percent=0.05,
            trail_price=None,
            filled_qty=0,
            filled_avg_price=None,
            created_at=datetime.now()
        )
        
        order = await order_manager.submit_trailing_stop_order(
            symbol="AAPL",
            quantity=100,
            side="sell",
            trail_percent=0.05
        )
        
        assert order.id == "trailing_stop_301"
        assert order.order_type == OrderType.TRAILING_STOP
        assert order.trail_percent == 0.05
        mock_alpaca_trading_client.submit_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_order_replacement(self, order_manager, mock_alpaca_trading_client):
        """Test order replacement."""
        # Mock order replacement response
        mock_alpaca_trading_client.replace_order_by_id.return_value = Mock(
            id="order_123",
            symbol="AAPL",
            qty=200,
            side="buy",
            order_type="limit",
            status="new",
            limit_price=149.0,
            stop_price=None,
            filled_qty=0,
            filled_avg_price=None,
            created_at=datetime.now(),
            replaced_at=datetime.now()
        )
        
        updated_order = await order_manager.update_order(
            order_id="order_123",
            quantity=200,
            limit_price=149.0
        )
        
        assert updated_order.quantity == 200
        assert updated_order.limit_price == 149.0
        mock_alpaca_trading_client.replace_order_by_id.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_portfolio_history(self, order_manager, mock_alpaca_trading_client):
        """Test portfolio history retrieval."""
        # Mock portfolio history response
        mock_alpaca_trading_client.get_portfolio_history.return_value = Mock(
            timestamp=[datetime.now() - timedelta(days=i) for i in range(30, 0, -1)],
            equity=[50000.0 + i * 100 for i in range(30)],
            profit_loss=[0.0 + i * 10 for i in range(30)],
            profit_loss_pct=[0.0 + i * 0.001 for i in range(30)]
        )
        
        history = await order_manager.get_portfolio_history(period="1M")
        
        assert history is not None
        assert len(history.equity) == 30
        mock_alpaca_trading_client.get_portfolio_history.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_real_time_data_subscription(self, market_data_provider, mock_alpaca_data_client):
        """Test real-time data subscription."""
        # Mock real-time data subscription
        mock_subscription = Mock()
        mock_alpaca_data_client.subscribe_stock_trades.return_value = mock_subscription
        
        await market_data_provider.subscribe_real_time_data(
            symbols=["AAPL", "TSLA"],
            data_types=["trades", "quotes"]
        )
        
        # Verify subscription was set up
        assert market_data_provider.subscription is not None
    
    @pytest.mark.asyncio
    async def test_api_error_handling(self, order_manager, mock_alpaca_trading_client):
        """Test API error handling."""
        # Mock API error
        mock_alpaca_trading_client.submit_order.side_effect = Exception("API Error: Insufficient funds")
        
        with pytest.raises(OrderException) as exc_info:
            await order_manager.submit_order(
                symbol="AAPL",
                quantity=100,
                side="buy",
                order_type=OrderType.LIMIT,
                limit_price=150.0
            )
        
        assert "API Error" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_rate_limiting_handling(self, order_manager, mock_alpaca_trading_client):
        """Test rate limiting handling."""
        # Mock rate limiting error
        mock_alpaca_trading_client.submit_order.side_effect = [
            Exception("Rate limit exceeded"),
            Mock(id="rate_limited_order", status="new")
        ]
        
        # Should retry after rate limit
        order = await order_manager.submit_order(
            symbol="AAPL",
            quantity=100,
            side="buy",
            order_type=OrderType.LIMIT,
            limit_price=150.0
        )
        
        assert order.id == "rate_limited_order"
        assert mock_alpaca_trading_client.submit_order.call_count == 2
    
    @pytest.mark.asyncio
    async def test_market_calendar_integration(self, market_data_provider, mock_alpaca_data_client):
        """Test market calendar integration."""
        # Mock market calendar response
        mock_alpaca_data_client.get_calendar.return_value = [
            Mock(
                date=datetime.now().date(),
                open=datetime.now().replace(hour=9, minute=30),
                close=datetime.now().replace(hour=16, minute=0),
                session_open=datetime.now().replace(hour=4, minute=0),
                session_close=datetime.now().replace(hour=20, minute=0)
            )
        ]
        
        is_market_open = await market_data_provider.is_market_open()
        
        assert isinstance(is_market_open, bool)
        mock_alpaca_data_client.get_calendar.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_asset_search_and_validation(self, market_data_provider, mock_alpaca_data_client):
        """Test asset search and validation."""
        # Mock asset search response
        mock_alpaca_data_client.search_assets.return_value = [
            Mock(
                symbol="AAPL",
                name="Apple Inc.",
                asset_class="us_equity",
                exchange="NASDAQ",
                status="active",
                tradable=True,
                marginable=True,
                shortable=True,
                easy_to_borrow=True,
                fractionable=True
            )
        ]
        
        assets = await market_data_provider.search_assets("AAPL")
        
        assert len(assets) == 1
        assert assets[0].symbol == "AAPL"
        assert assets[0].tradable is True
        mock_alpaca_data_client.search_assets.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_order_validation(self, order_manager):
        """Test comprehensive order validation."""
        # Test invalid symbol
        with pytest.raises(OrderException) as exc_info:
            await order_manager.submit_order(
                symbol="",
                quantity=100,
                side="buy",
                order_type=OrderType.LIMIT,
                limit_price=150.0
            )
        assert "Invalid symbol" in str(exc_info.value)
        
        # Test invalid quantity
        with pytest.raises(OrderException) as exc_info:
            await order_manager.submit_order(
                symbol="AAPL",
                quantity=0,
                side="buy",
                order_type=OrderType.LIMIT,
                limit_price=150.0
            )
        assert "Invalid quantity" in str(exc_info.value)
        
        # Test invalid price
        with pytest.raises(OrderException) as exc_info:
            await order_manager.submit_order(
                symbol="AAPL",
                quantity=100,
                side="buy",
                order_type=OrderType.LIMIT,
                limit_price=0.0
            )
        assert "Invalid price" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_data_validation(self, market_data_provider):
        """Test market data validation."""
        # Test invalid symbol
        with pytest.raises(MarketDataException) as exc_info:
            await market_data_provider.get_current_price("")
        assert "Invalid symbol" in str(exc_info.value)
        
        # Test invalid timeframe
        with pytest.raises(MarketDataException) as exc_info:
            await market_data_provider.get_historical_data("AAPL", "invalid", 100)
        assert "Invalid timeframe" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_connection_health_check(self, order_manager, market_data_provider):
        """Test connection health checks."""
        # Test trading API health
        trading_health = await order_manager.check_api_health()
        assert isinstance(trading_health, bool)
        
        # Test data API health
        data_health = await market_data_provider.check_api_health()
        assert isinstance(data_health, bool)
    
    @pytest.mark.asyncio
    async def test_comprehensive_integration_workflow(self, order_manager, market_data_provider, mock_alpaca_trading_client, mock_alpaca_data_client):
        """Test comprehensive integration workflow."""
        # 1. Get account info
        account = await order_manager.get_account_info()
        assert account.buying_power > 0
        
        # 2. Get current market price
        current_price = await market_data_provider.get_current_price("AAPL")
        assert current_price > 0
        
        # 3. Submit order
        order = await order_manager.submit_order(
            symbol="AAPL",
            quantity=100,
            side="buy",
            order_type=OrderType.LIMIT,
            limit_price=current_price * 0.99  # 1% below current price
        )
        assert order.id is not None
        
        # 4. Check order status
        status = await order_manager.get_order_status(order.id)
        assert status is not None
        
        # 5. Get positions
        positions = await order_manager.get_positions()
        assert isinstance(positions, list)
        
        # 6. Get historical data for analysis
        historical_data = await market_data_provider.get_historical_data("AAPL", "1D", 30)
        assert historical_data is not None
        
        # All API calls should have been made
        assert mock_alpaca_trading_client.get_account.called
        assert mock_alpaca_data_client.get_stock_latest_trade.called
        assert mock_alpaca_trading_client.submit_order.called
        assert mock_alpaca_trading_client.get_order_by_id.called
        assert mock_alpaca_trading_client.get_all_positions.called
        assert mock_alpaca_data_client.get_stock_bars.called
