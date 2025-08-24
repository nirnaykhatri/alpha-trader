"""
Unit tests for OrderManager.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
import asyncio

from src.trading import OrderManager
from src.core import ConfigurationManager
from src.exceptions import OrderException, TradingException
from src.interfaces import Order, OrderType, OrderStatus


class TestOrderManager:
    """Test cases for OrderManager class."""
    
    @pytest.fixture
    def config_manager(self, test_config_file):
        """Configuration manager for testing."""
        return ConfigurationManager(test_config_file)
    
    @pytest.fixture
    def order_manager(self, config_manager, mock_alpaca_trading_client):
        """Order manager instance for testing."""
        return OrderManager(config_manager, mock_alpaca_trading_client)
    
    @pytest.mark.asyncio
    async def test_submit_order_success(self, order_manager, mock_alpaca_trading_client):
        """Test successful order submission."""
        mock_alpaca_trading_client.submit_order.return_value = Mock(
            id="test_order_123",
            status="NEW",
            symbol="AAPL",
            qty=100,
            side="buy",
            order_type="limit",
            limit_price=150.0,
            filled_qty=0,
            filled_avg_price=None,
            created_at=datetime.now()
        )
        
        # Create an Order object as expected by the interface
        order = Order(
            order_id="test_order_123",
            symbol="AAPL",
            quantity=100,
            side="buy",
            order_type=OrderType.LIMIT,
            price=150.0
        )
        
        order_id = await order_manager.place_order(order)
        
        assert order.order_id == "test_order_123"
        assert order.symbol == "AAPL"
        assert order.quantity == 100
        assert order.side == "buy"
        assert order.order_type == OrderType.LIMIT
        assert order.price == 150.0
        assert order.status == OrderStatus.PENDING  # Initial status before processing
        
        mock_alpaca_trading_client.submit_order.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_submit_order_with_retry(self, order_manager, mock_alpaca_trading_client):
        """Test order submission with retry logic."""
        # First call fails, second succeeds
        mock_alpaca_trading_client.submit_order.side_effect = [
            Exception("Network error"),
            Mock(
                id="test_order_123",
                status="NEW",
                symbol="AAPL",
                qty=100,
                side="buy",
                order_type="limit",
                limit_price=150.0,
                filled_qty=0,
                filled_avg_price=None,
                created_at=datetime.now()
            )
        ]
        
        order = await order_manager.submit_order(
            symbol="AAPL",
            quantity=100,
            side="buy",
            order_type=OrderType.LIMIT,
            limit_price=150.0
        )
        
        assert order.id == "test_order_123"
        assert mock_alpaca_trading_client.submit_order.call_count == 2
    
    @pytest.mark.asyncio
    async def test_submit_order_max_retries_exceeded(self, order_manager, mock_alpaca_trading_client):
        """Test order submission failure after max retries."""
        mock_alpaca_trading_client.submit_order.side_effect = Exception("Persistent error")
        
        with pytest.raises(OrderException) as exc_info:
            await order_manager.submit_order(
                symbol="AAPL",
                quantity=100,
                side="buy",
                order_type=OrderType.LIMIT,
                limit_price=150.0
            )
        
        assert "Failed to submit order after retries" in str(exc_info.value)
        assert mock_alpaca_trading_client.submit_order.call_count == 4  # 1 initial + 3 retries
    
    @pytest.mark.asyncio
    async def test_cancel_order_success(self, order_manager, mock_alpaca_trading_client):
        """Test successful order cancellation."""
        mock_alpaca_trading_client.cancel_order_by_id.return_value = Mock(
            id="test_order_123",
            status="CANCELED"
        )
        
        result = await order_manager.cancel_order("test_order_123")
        
        assert result is True
        mock_alpaca_trading_client.cancel_order_by_id.assert_called_once_with("test_order_123")
    
    @pytest.mark.asyncio
    async def test_cancel_order_failure(self, order_manager, mock_alpaca_trading_client):
        """Test order cancellation failure."""
        mock_alpaca_trading_client.cancel_order_by_id.side_effect = Exception("Order not found")
        
        result = await order_manager.cancel_order("nonexistent_order")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_get_order_status_success(self, order_manager, mock_alpaca_trading_client):
        """Test getting order status."""
        mock_alpaca_trading_client.get_order_by_id.return_value = Mock(
            id="test_order_123",
            status="FILLED",
            filled_qty=100,
            filled_avg_price=150.5
        )
        
        status = await order_manager.get_order_status("test_order_123")
        
        assert status == OrderStatus.FILLED
        mock_alpaca_trading_client.get_order_by_id.assert_called_once_with("test_order_123")
    
    @pytest.mark.asyncio
    async def test_get_order_status_not_found(self, order_manager, mock_alpaca_trading_client):
        """Test getting status for non-existent order."""
        mock_alpaca_trading_client.get_order_by_id.side_effect = Exception("Order not found")
        
        status = await order_manager.get_order_status("nonexistent_order")
        
        assert status is None
    
    @pytest.mark.asyncio
    async def test_get_active_orders(self, order_manager, mock_alpaca_trading_client):
        """Test getting active orders."""
        mock_orders = [
            Mock(
                id="order_1",
                status="NEW",
                symbol="AAPL",
                qty=100,
                side="buy",
                order_type="limit",
                limit_price=150.0,
                filled_qty=0,
                filled_avg_price=None,
                created_at=datetime.now()
            ),
            Mock(
                id="order_2",
                status="PARTIALLY_FILLED",
                symbol="TSLA",
                qty=50,
                side="sell",
                order_type="market",
                limit_price=None,
                filled_qty=25,
                filled_avg_price=800.0,
                created_at=datetime.now()
            )
        ]
        
        mock_alpaca_trading_client.get_orders.return_value = mock_orders
        
        orders = await order_manager.get_active_orders()
        
        assert len(orders) == 2
        assert orders[0].id == "order_1"
        assert orders[0].status == OrderStatus.NEW
        assert orders[1].id == "order_2"
        assert orders[1].status == OrderStatus.PARTIALLY_FILLED
    
    @pytest.mark.asyncio
    async def test_get_orders_by_symbol(self, order_manager, mock_alpaca_trading_client):
        """Test getting orders by symbol."""
        mock_orders = [
            Mock(
                id="order_1",
                status="NEW",
                symbol="AAPL",
                qty=100,
                side="buy",
                order_type="limit",
                limit_price=150.0,
                filled_qty=0,
                filled_avg_price=None,
                created_at=datetime.now()
            )
        ]
        
        mock_alpaca_trading_client.get_orders.return_value = mock_orders
        
        orders = await order_manager.get_orders_by_symbol("AAPL")
        
        assert len(orders) == 1
        assert orders[0].symbol == "AAPL"
        mock_alpaca_trading_client.get_orders.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_order_success(self, order_manager, mock_alpaca_trading_client):
        """Test successful order update."""
        mock_alpaca_trading_client.replace_order_by_id.return_value = Mock(
            id="test_order_123",
            status="NEW",
            symbol="AAPL",
            qty=200,
            side="buy",
            order_type="limit",
            limit_price=149.0,
            filled_qty=0,
            filled_avg_price=None,
            created_at=datetime.now()
        )
        
        updated_order = await order_manager.update_order(
            order_id="test_order_123",
            quantity=200,
            limit_price=149.0
        )
        
        assert updated_order.quantity == 200
        assert updated_order.limit_price == 149.0
        mock_alpaca_trading_client.replace_order_by_id.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_update_order_failure(self, order_manager, mock_alpaca_trading_client):
        """Test order update failure."""
        mock_alpaca_trading_client.replace_order_by_id.side_effect = Exception("Cannot update filled order")
        
        with pytest.raises(OrderException) as exc_info:
            await order_manager.update_order(
                order_id="test_order_123",
                quantity=200,
                limit_price=149.0
            )
        
        assert "Failed to update order" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_market_order_submission(self, order_manager, mock_alpaca_trading_client):
        """Test market order submission."""
        mock_alpaca_trading_client.submit_order.return_value = Mock(
            id="test_order_123",
            status="NEW",
            symbol="AAPL",
            qty=100,
            side="buy",
            order_type="market",
            limit_price=None,
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
        
        assert order.order_type == OrderType.MARKET
        assert order.limit_price is None
    
    @pytest.mark.asyncio
    async def test_stop_loss_order_submission(self, order_manager, mock_alpaca_trading_client):
        """Test stop loss order submission."""
        mock_alpaca_trading_client.submit_order.return_value = Mock(
            id="test_order_123",
            status="NEW",
            symbol="AAPL",
            qty=100,
            side="sell",
            order_type="stop",
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
        
        assert order.order_type == OrderType.STOP
        assert order.stop_price == 145.0
    
    @pytest.mark.asyncio
    async def test_order_timeout_handling(self, order_manager, mock_alpaca_trading_client):
        """Test order timeout handling."""
        # Mock an order that's been pending for too long
        old_time = datetime.now() - timedelta(minutes=10)
        mock_order = Mock(
            id="old_order_123",
            status="NEW",
            symbol="AAPL",
            qty=100,
            side="buy",
            order_type="limit",
            limit_price=150.0,
            filled_qty=0,
            filled_avg_price=None,
            created_at=old_time
        )
        
        mock_alpaca_trading_client.get_orders.return_value = [mock_order]
        mock_alpaca_trading_client.cancel_order_by_id.return_value = Mock(status="CANCELED")
        
        # This would typically be called by a background task
        await order_manager.cleanup_expired_orders()
        
        mock_alpaca_trading_client.cancel_order_by_id.assert_called_once_with("old_order_123")
    
    @pytest.mark.asyncio
    async def test_order_validation(self, order_manager):
        """Test order validation."""
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
        
        # Test invalid side
        with pytest.raises(OrderException) as exc_info:
            await order_manager.submit_order(
                symbol="AAPL",
                quantity=100,
                side="invalid",
                order_type=OrderType.LIMIT,
                limit_price=150.0
            )
        assert "Invalid side" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_order_conversion_from_alpaca(self, order_manager):
        """Test conversion from Alpaca order format to internal Order format."""
        alpaca_order = Mock(
            id="test_order_123",
            status="FILLED",
            symbol="AAPL",
            qty=100,
            side="buy",
            order_type="limit",
            limit_price=150.0,
            filled_qty=100,
            filled_avg_price=150.25,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        internal_order = order_manager._convert_alpaca_order(alpaca_order)
        
        assert internal_order.id == "test_order_123"
        assert internal_order.status == OrderStatus.FILLED
        assert internal_order.symbol == "AAPL"
        assert internal_order.quantity == 100
        assert internal_order.side == "buy"
        assert internal_order.order_type == OrderType.LIMIT
        assert internal_order.limit_price == 150.0
        assert internal_order.filled_quantity == 100
        assert internal_order.filled_average_price == 150.25
