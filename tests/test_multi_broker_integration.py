"""
Multi-Broker Integration Tests

Tests for broker routing, Tastytrade-specific flows, and multi-broker scenarios.
These tests validate the BrokerRouter, BrokerSubsystem, and broker-specific
order execution paths.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC

from src.broker.router import BrokerRouter
from src.broker.interfaces import BrokerType, IBrokerOrderExecutor, IBrokerAccountProvider, IBrokerMarketDataProvider
from src.interfaces import Order, OrderSide, OrderType, OrderStatus
from src.risk.martingale_validator import (
    MartingaleSafetyManager, 
    MartingaleSafetyPolicy, 
    MartingaleSafetyState
)
from src.exceptions import ConfigurationException


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_config():
    """Create a mock configuration manager."""
    config = MagicMock()
    config.get_config = MagicMock(side_effect=lambda key, default=None: {
        'trading.brokers.default': 'alpaca',
        'trading.brokers.routing': {'SPY': 'tastytrade', 'IWM': 'tastytrade'},
        'trading.account_value': 100000.0,
        'strategies.long_strategy.martingale.max_account_risk_percent': 25.0,
        'strategies.long_strategy.martingale.daily_loss_limit_percent': 10.0,
        'strategies.long_strategy.martingale.weekly_loss_limit_percent': 20.0,
        'strategies.long_strategy.martingale.max_single_loss_percent': 10.0,
        'strategies.long_strategy.martingale.max_consecutive_losses': 3,
    }.get(key, default))
    return config


@pytest.fixture
def mock_alpaca_executor():
    """Create a mock Alpaca order executor."""
    executor = AsyncMock(spec=IBrokerOrderExecutor)
    executor.place_order = AsyncMock(return_value="ALPACA-ORDER-123")
    executor.cancel_order = AsyncMock(return_value=True)
    executor.get_order_status = AsyncMock(return_value=OrderStatus.FILLED)
    executor.get_open_orders = AsyncMock(return_value=[])
    return executor


@pytest.fixture
def mock_tastytrade_executor():
    """Create a mock Tastytrade order executor."""
    executor = AsyncMock(spec=IBrokerOrderExecutor)
    executor.place_order = AsyncMock(return_value="TT-ORDER-456")
    executor.cancel_order = AsyncMock(return_value=True)
    executor.get_order_status = AsyncMock(return_value=OrderStatus.PENDING)
    executor.get_open_orders = AsyncMock(return_value=[])
    return executor


@pytest.fixture
def mock_alpaca_account_provider():
    """Create a mock Alpaca account provider."""
    provider = AsyncMock(spec=IBrokerAccountProvider)
    provider.get_account_info = AsyncMock(return_value={
        'equity': 100000.0,
        'buying_power': 200000.0,
        'cash': 50000.0
    })
    provider.get_positions = AsyncMock(return_value=[])
    return provider


@pytest.fixture
def mock_tastytrade_account_provider():
    """Create a mock Tastytrade account provider."""
    provider = AsyncMock(spec=IBrokerAccountProvider)
    provider.get_account_info = AsyncMock(return_value={
        'equity': 75000.0,
        'buying_power': 150000.0,
        'cash': 40000.0
    })
    provider.get_positions = AsyncMock(return_value=[])
    return provider


@pytest.fixture
def mock_market_data_provider():
    """Create a mock market data provider."""
    provider = AsyncMock(spec=IBrokerMarketDataProvider)
    provider.get_current_price = AsyncMock(return_value=150.0)
    return provider


@pytest.fixture
def broker_router(
    mock_config, 
    mock_alpaca_executor, 
    mock_tastytrade_executor,
    mock_alpaca_account_provider,
    mock_tastytrade_account_provider,
    mock_market_data_provider
):
    """Create a BrokerRouter with mocked dependencies."""
    return BrokerRouter(
        config=mock_config,
        executors={
            BrokerType.ALPACA: mock_alpaca_executor,
            BrokerType.TASTYTRADE: mock_tastytrade_executor
        },
        account_providers={
            BrokerType.ALPACA: mock_alpaca_account_provider,
            BrokerType.TASTYTRADE: mock_tastytrade_account_provider
        },
        market_data_providers={
            BrokerType.ALPACA: mock_market_data_provider,
            BrokerType.TASTYTRADE: mock_market_data_provider
        }
    )


# =============================================================================
# Broker Routing Tests
# =============================================================================

class TestBrokerRouting:
    """Tests for symbol-to-broker routing logic."""
    
    def test_default_broker_routing(self, broker_router):
        """Test that unrouted symbols use the default broker."""
        # AAPL is not in routing config, should use default (Alpaca)
        broker = broker_router.get_broker_for_symbol("AAPL")
        assert broker == BrokerType.ALPACA
    
    def test_explicit_symbol_routing(self, broker_router):
        """Test that explicitly routed symbols go to configured broker."""
        # SPY is routed to Tastytrade
        broker = broker_router.get_broker_for_symbol("SPY")
        assert broker == BrokerType.TASTYTRADE
        
        # IWM is also routed to Tastytrade
        broker = broker_router.get_broker_for_symbol("IWM")
        assert broker == BrokerType.TASTYTRADE
    
    def test_case_insensitive_routing(self, broker_router):
        """Test that symbol routing is case-insensitive."""
        broker_upper = broker_router.get_broker_for_symbol("SPY")
        broker_lower = broker_router.get_broker_for_symbol("spy")
        broker_mixed = broker_router.get_broker_for_symbol("Spy")
        
        assert broker_upper == broker_lower == broker_mixed == BrokerType.TASTYTRADE
    
    def test_empty_symbol_returns_default(self, broker_router):
        """Test that empty symbol returns default broker."""
        broker = broker_router.get_broker_for_symbol("")
        assert broker == BrokerType.ALPACA
    
    def test_get_order_executor(self, broker_router, mock_alpaca_executor, mock_tastytrade_executor):
        """Test getting order executor for specific broker."""
        alpaca_executor = broker_router.get_order_executor(BrokerType.ALPACA)
        assert alpaca_executor == mock_alpaca_executor
        
        tt_executor = broker_router.get_order_executor(BrokerType.TASTYTRADE)
        assert tt_executor == mock_tastytrade_executor
    
    def test_get_account_provider(self, broker_router, mock_alpaca_account_provider):
        """Test getting account provider for specific broker."""
        provider = broker_router.get_account_provider(BrokerType.ALPACA)
        assert provider == mock_alpaca_account_provider
    
    def test_get_registered_brokers(self, broker_router):
        """Test listing all registered brokers."""
        brokers = broker_router.get_registered_brokers()
        assert BrokerType.ALPACA in brokers
        assert BrokerType.TASTYTRADE in brokers
        assert len(brokers) == 2


# =============================================================================
# Multi-Broker Order Execution Tests
# =============================================================================

class TestMultiBrokerOrderExecution:
    """Tests for order execution across multiple brokers."""
    
    @pytest.mark.asyncio
    async def test_alpaca_order_execution(self, broker_router, mock_alpaca_executor):
        """Test placing order through Alpaca."""
        order = Order(
            order_id=None,
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.LIMIT,
            price=150.0
        )
        
        # Get executor for AAPL (should be Alpaca)
        broker = broker_router.get_broker_for_symbol("AAPL")
        executor = broker_router.get_order_executor(broker)
        
        order_id = await executor.place_order(order)
        
        assert order_id == "ALPACA-ORDER-123"
        mock_alpaca_executor.place_order.assert_called_once_with(order)
    
    @pytest.mark.asyncio
    async def test_tastytrade_order_execution(self, broker_router, mock_tastytrade_executor):
        """Test placing order through Tastytrade."""
        order = Order(
            order_id=None,
            symbol="SPY",
            side=OrderSide.BUY,
            quantity=5,
            order_type=OrderType.MARKET,
            price=None
        )
        
        # Get executor for SPY (should be Tastytrade)
        broker = broker_router.get_broker_for_symbol("SPY")
        executor = broker_router.get_order_executor(broker)
        
        order_id = await executor.place_order(order)
        
        assert order_id == "TT-ORDER-456"
        mock_tastytrade_executor.place_order.assert_called_once_with(order)
    
    @pytest.mark.asyncio
    async def test_concurrent_multi_broker_orders(
        self, broker_router, mock_alpaca_executor, mock_tastytrade_executor
    ):
        """Test placing orders on multiple brokers concurrently."""
        import asyncio
        
        alpaca_order = Order(
            order_id=None,
            symbol="AAPL",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.LIMIT,
            price=150.0
        )
        
        tastytrade_order = Order(
            order_id=None,
            symbol="SPY",
            side=OrderSide.SELL,
            quantity=5,
            order_type=OrderType.MARKET,
            price=None
        )
        
        # Place orders concurrently
        alpaca_executor = broker_router.get_order_executor(BrokerType.ALPACA)
        tt_executor = broker_router.get_order_executor(BrokerType.TASTYTRADE)
        
        results = await asyncio.gather(
            alpaca_executor.place_order(alpaca_order),
            tt_executor.place_order(tastytrade_order)
        )
        
        assert results[0] == "ALPACA-ORDER-123"
        assert results[1] == "TT-ORDER-456"
    
    @pytest.mark.asyncio
    async def test_order_cancellation_routing(
        self, broker_router, mock_alpaca_executor, mock_tastytrade_executor
    ):
        """Test order cancellation is routed to correct broker."""
        # Cancel Alpaca order
        alpaca_executor = broker_router.get_order_executor(BrokerType.ALPACA)
        result = await alpaca_executor.cancel_order("ALPACA-ORDER-123")
        assert result is True
        mock_alpaca_executor.cancel_order.assert_called_once()
        
        # Cancel Tastytrade order
        tt_executor = broker_router.get_order_executor(BrokerType.TASTYTRADE)
        result = await tt_executor.cancel_order("TT-ORDER-456")
        assert result is True
        mock_tastytrade_executor.cancel_order.assert_called_once()


# =============================================================================
# Martingale Safety Policy/State Tests
# =============================================================================

class TestMartingaleSafetyPolicy:
    """Tests for MartingaleSafetyPolicy."""
    
    def test_policy_from_config(self, mock_config):
        """Test creating policy from configuration."""
        policy = MartingaleSafetyPolicy.from_config(mock_config)
        
        assert policy.max_account_risk == 0.25
        assert policy.daily_loss_limit == 0.10
        assert policy.weekly_loss_limit == 0.20
        assert policy.default_max_consecutive_losses == 3
    
    def test_consecutive_loss_check(self):
        """Test consecutive loss policy check."""
        policy = MartingaleSafetyPolicy(max_account_risk=0.25)
        
        # Under limit
        safe, reason = policy.check_consecutive_losses(2, 3)
        assert safe is True
        assert reason is None
        
        # At limit
        safe, reason = policy.check_consecutive_losses(3, 3)
        assert safe is True
        
        # Over limit
        safe, reason = policy.check_consecutive_losses(4, 3)
        assert safe is False
        assert "Exceeded max consecutive losses" in reason
    
    def test_symbol_loss_check(self):
        """Test symbol loss policy check."""
        policy = MartingaleSafetyPolicy(max_account_risk=0.25)
        
        # Under limit (20% of 100k = 20k)
        safe, reason = policy.check_symbol_loss(20000, 100000)
        assert safe is True
        
        # Over limit (30% of 100k = 30k)
        safe, reason = policy.check_symbol_loss(30000, 100000)
        assert safe is False
        assert "exceed account risk limit" in reason
    
    def test_daily_loss_check(self):
        """Test daily loss policy check."""
        policy = MartingaleSafetyPolicy(daily_loss_limit=0.10)
        
        # Under limit
        safe, reason = policy.check_daily_loss(8000, 100000)
        assert safe is True
        
        # Over limit
        safe, reason = policy.check_daily_loss(12000, 100000)
        assert safe is False
        assert "Daily loss" in reason


class TestMartingaleSafetyState:
    """Tests for MartingaleSafetyState."""
    
    def test_record_loss(self):
        """Test recording losses updates state correctly."""
        state = MartingaleSafetyState()
        
        state.record_loss("AAPL", 1000.0, 0)
        
        assert state.consecutive_losses["AAPL"] == 1
        assert state.total_martingale_loss["AAPL"] == 1000.0
        assert state.daily_loss == 1000.0
        assert state.weekly_loss == 1000.0
    
    def test_cumulative_losses(self):
        """Test cumulative loss tracking."""
        state = MartingaleSafetyState()
        
        state.record_loss("AAPL", 1000.0, 0)
        state.record_loss("AAPL", 2000.0, 1)
        state.record_loss("SPY", 500.0, 0)
        
        assert state.consecutive_losses["AAPL"] == 2
        assert state.total_martingale_loss["AAPL"] == 3000.0
        assert state.consecutive_losses["SPY"] == 1
        assert state.total_martingale_loss["SPY"] == 500.0
        assert state.daily_loss == 3500.0
    
    def test_reset_symbol(self):
        """Test resetting symbol tracking."""
        state = MartingaleSafetyState()
        
        state.record_loss("AAPL", 1000.0, 0)
        state.record_loss("AAPL", 2000.0, 1)
        
        state.reset_symbol("AAPL")
        
        assert state.consecutive_losses["AAPL"] == 0
        assert state.total_martingale_loss["AAPL"] == 0.0
        # Daily/weekly loss is NOT reset when symbol is reset
        assert state.daily_loss == 3000.0
    
    def test_emergency_stop_activation(self):
        """Test emergency stop activation."""
        state = MartingaleSafetyState()
        
        assert state.emergency_stop is False
        state.activate_emergency_stop()
        assert state.emergency_stop is True
    
    def test_get_status(self):
        """Test getting state status."""
        state = MartingaleSafetyState()
        state.record_loss("AAPL", 1000.0, 2)
        
        status = state.get_status()
        
        assert status["daily_loss"] == 1000.0
        assert status["symbols_tracked"] == 1
        assert status["max_consecutive_losses"] == 3
        assert status["emergency_stop"] is False


class TestMartingaleSafetyManagerIntegration:
    """Integration tests for MartingaleSafetyManager with Policy/State."""
    
    @pytest.mark.asyncio
    async def test_safety_check_passes(self, mock_config):
        """Test safety check passes for normal loss."""
        manager = MartingaleSafetyManager(mock_config)
        
        result = await manager.check_safety(
            symbol="AAPL",
            loss_amount=1000.0,
            consecutive_losses=0,
            account_value=100000.0
        )
        
        assert result['safe'] is True
        assert result['reason'] is None
        assert result['details']['consecutive_losses'] == 1
    
    @pytest.mark.asyncio
    async def test_safety_check_fails_consecutive_losses(self, mock_config):
        """Test safety check fails on excessive consecutive losses."""
        manager = MartingaleSafetyManager(mock_config)
        
        result = await manager.check_safety(
            symbol="AAPL",
            loss_amount=1000.0,
            consecutive_losses=3,  # Will become 4, exceeding limit of 3
            account_value=100000.0,
            max_consecutive_losses=3
        )
        
        assert result['safe'] is False
        assert "consecutive losses" in result['reason'].lower()
    
    @pytest.mark.asyncio
    async def test_safety_check_fails_daily_limit(self, mock_config):
        """Test safety check fails on daily loss limit."""
        manager = MartingaleSafetyManager(mock_config)
        
        # First loss - 5%
        await manager.check_safety("AAPL", 5000.0, 0, 100000.0)
        
        # Second loss - brings to 11% (over 10% limit)
        result = await manager.check_safety("AAPL", 6000.0, 1, 100000.0)
        
        assert result['safe'] is False
        assert "Daily loss" in result['reason']
        assert manager.state.emergency_stop is True
    
    @pytest.mark.asyncio
    async def test_reset_symbol_clears_tracking(self, mock_config):
        """Test that reset_symbol clears symbol-specific tracking."""
        manager = MartingaleSafetyManager(mock_config)
        
        # Record some losses
        await manager.check_safety("AAPL", 1000.0, 0, 100000.0)
        await manager.check_safety("AAPL", 1000.0, 1, 100000.0)
        
        assert manager.state.consecutive_losses["AAPL"] == 2
        
        # Reset
        manager.reset_symbol("AAPL")
        
        assert manager.state.consecutive_losses["AAPL"] == 0
        assert manager.state.total_martingale_loss["AAPL"] == 0.0
    
    def test_get_status_includes_policy(self, mock_config):
        """Test that get_status includes policy information."""
        manager = MartingaleSafetyManager(mock_config)
        
        status = manager.get_status()
        
        assert "policy" in status
        assert status["policy"]["max_account_risk_pct"] == 25.0
        assert status["policy"]["daily_loss_limit_pct"] == 10.0


# =============================================================================
# Tastytrade-Specific Flow Tests
# =============================================================================

class TestTastytradeSpecificFlows:
    """Tests for Tastytrade-specific behaviors."""
    
    @pytest.mark.asyncio
    async def test_tastytrade_order_status_mapping(self, mock_tastytrade_executor):
        """Test Tastytrade order status is correctly mapped."""
        # Mock different status returns
        mock_tastytrade_executor.get_order_status = AsyncMock(
            side_effect=[
                OrderStatus.PENDING,
                OrderStatus.FILLED,
                OrderStatus.CANCELED
            ]
        )
        
        status1 = await mock_tastytrade_executor.get_order_status("TT-1")
        status2 = await mock_tastytrade_executor.get_order_status("TT-2")
        status3 = await mock_tastytrade_executor.get_order_status("TT-3")
        
        assert status1 == OrderStatus.PENDING
        assert status2 == OrderStatus.FILLED
        assert status3 == OrderStatus.CANCELED
    
    @pytest.mark.asyncio
    async def test_tastytrade_open_orders_returns_list(self, mock_tastytrade_executor):
        """Test Tastytrade get_open_orders returns proper list."""
        mock_order = Order(
            order_id="TT-123",
            symbol="SPY",
            side=OrderSide.BUY,
            quantity=10,
            order_type=OrderType.LIMIT,
            price=450.0
        )
        mock_tastytrade_executor.get_open_orders = AsyncMock(return_value=[mock_order])
        
        orders = await mock_tastytrade_executor.get_open_orders("SPY")
        
        assert len(orders) == 1
        assert orders[0].symbol == "SPY"
        assert orders[0].quantity == 10
    
    @pytest.mark.asyncio
    async def test_tastytrade_symbol_filter(self, mock_tastytrade_executor):
        """Test Tastytrade get_open_orders with symbol filter."""
        spy_order = Order(
            order_id="TT-1", symbol="SPY", side=OrderSide.BUY,
            quantity=10, order_type=OrderType.LIMIT, price=450.0
        )
        iwm_order = Order(
            order_id="TT-2", symbol="IWM", side=OrderSide.SELL,
            quantity=5, order_type=OrderType.MARKET, price=None
        )
        
        # Return both when no filter
        mock_tastytrade_executor.get_open_orders = AsyncMock(
            side_effect=lambda symbol=None: [spy_order, iwm_order] if symbol is None 
                else [o for o in [spy_order, iwm_order] if o.symbol == symbol]
        )
        
        # All orders
        all_orders = await mock_tastytrade_executor.get_open_orders()
        assert len(all_orders) == 2
        
        # Filtered to SPY only
        spy_orders = await mock_tastytrade_executor.get_open_orders("SPY")
        assert len(spy_orders) == 1
        assert spy_orders[0].symbol == "SPY"


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestMultiBrokerErrorHandling:
    """Tests for error handling across brokers."""
    
    def test_missing_executor_raises_exception(self, mock_config, mock_alpaca_account_provider, mock_market_data_provider):
        """Test that missing executor raises ConfigurationException."""
        router = BrokerRouter(
            config=mock_config,
            executors={},  # No executors
            account_providers={BrokerType.ALPACA: mock_alpaca_account_provider},
            market_data_providers={BrokerType.ALPACA: mock_market_data_provider}
        )
        
        with pytest.raises(ConfigurationException) as exc_info:
            router.get_order_executor(BrokerType.ALPACA)
        
        assert "No order executor configured" in str(exc_info.value)
    
    def test_missing_account_provider_raises_exception(self, mock_config, mock_alpaca_executor, mock_market_data_provider):
        """Test that missing account provider raises ConfigurationException."""
        router = BrokerRouter(
            config=mock_config,
            executors={BrokerType.ALPACA: mock_alpaca_executor},
            account_providers={},  # No providers
            market_data_providers={BrokerType.ALPACA: mock_market_data_provider}
        )
        
        with pytest.raises(ConfigurationException) as exc_info:
            router.get_account_provider(BrokerType.ALPACA)
        
        assert "No account provider configured" in str(exc_info.value)
