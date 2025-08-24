"""
Integration tests for AdvancedTradingStrategy with Martingale DCA

Tests the integration between AdvancedTradingStrategy and MartingaleDCAManager.
"""

import pytest
import pytest_asyncio
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from src.strategies.advanced_strategy import AdvancedTradingStrategy, PositionState, PositionDirection, TradePhase
from src.strategies.martingale_dca_manager import MartingaleDCAManager
from src.strategies.support_calculator import TechnicalSupportCalculator
from src import TradingSignal, SignalType


@pytest.fixture
def mock_config():
    """Mock configuration manager with martingale settings."""
    config = Mock()
    config.get_config.side_effect = lambda key, default=None: {
        'symbol_settings': {
            'AAPL': {
                'base_order_size_type': 'dollars',
                'base_order_size': 1000.0,
                'dca_order_size_type': 'multiplier',
                'dca_amount_multiplier': 2.0,
                'dca_step_percent': 1.5,
                'step_multiplier': 1.2,
                'max_dca_orders': 5,
                'take_profit_percent': 3.0,
                'trailing_deviation_percent': 0.8,
                'max_position_value': 10000.0,
                'enabled': True
            }
        },
        'strategies.martingale_dca.enabled': True,
        'strategies.long_strategy.enabled': True,
        'strategies.short_strategy.enabled': True,
        'trading.order_type': 'limit',
        'trading.limit_order_offset': 0.001
    }.get(key, default)
    return config


@pytest.fixture
def mock_order_manager():
    """Mock order manager."""
    order_manager = Mock()
    order_manager.place_order = AsyncMock()
    return order_manager


@pytest.fixture
def mock_market_data():
    """Mock market data provider."""
    market_data = Mock()
    market_data.get_current_price = AsyncMock(return_value=150.0)
    return market_data


@pytest.fixture
def mock_support_calculator():
    """Mock support calculator."""
    return Mock(spec=TechnicalSupportCalculator)


@pytest.fixture
def mock_risk_manager():
    """Mock risk manager."""
    risk_manager = Mock()
    risk_manager.get_portfolio_value = AsyncMock(return_value=100000.0)
    risk_manager.get_max_order_value = AsyncMock(return_value=5000.0)
    risk_manager.get_available_cash = AsyncMock(return_value=50000.0)
    return risk_manager


@pytest.fixture
def mock_position_manager():
    """Mock position manager."""
    position_manager = Mock()
    position_manager.get_position = AsyncMock(return_value=None)
    position_manager.get_all_positions = AsyncMock(return_value=[])  # Fix for initialization
    return position_manager


@pytest_asyncio.fixture
async def advanced_strategy(mock_config, mock_order_manager, mock_market_data, 
                           mock_support_calculator, mock_risk_manager, mock_position_manager):
    """Create AdvancedTradingStrategy with MartingaleDCAManager."""
    strategy = AdvancedTradingStrategy(
        mock_config,
        mock_order_manager,
        mock_market_data,
        mock_support_calculator,
        mock_risk_manager,
        mock_position_manager
    )
    
    # Initialize martingale DCA manager
    martingale_dca = MartingaleDCAManager(mock_config, mock_market_data, mock_risk_manager)
    strategy.martingale_dca = martingale_dca
    
    return strategy


class TestMartingaleDCAIntegration:
    """Test integration between AdvancedTradingStrategy and MartingaleDCAManager."""
    
    @pytest.mark.asyncio
    async def test_position_initialization_with_martingale(self, advanced_strategy):
        """Test that positions are initialized with martingale settings."""
        # Create a mock database position
        db_position = Mock()
        db_position.symbol = "AAPL"
        db_position.quantity = 10.0
        db_position.avg_price = 150.0
        
        # Mock position manager to return the position
        advanced_strategy.position_manager.get_position = AsyncMock(return_value=db_position)
        
        # Call update_position_monitoring to initialize position
        await advanced_strategy.update_position_monitoring("AAPL", 150.0)
        
        # Verify position was created with martingale settings
        assert "AAPL" in advanced_strategy.positions
        position = advanced_strategy.positions["AAPL"]
        
        assert position.symbol == "AAPL"
        assert position.is_martingale_enabled is True
        assert position.dca_count == 0
        assert position.total_position_value == 1500.0  # 10 * 150
        assert position.next_dca_step_percent == 1.5  # Initial step
    
    @pytest.mark.asyncio
    async def test_martingale_dca_trigger_and_execution(self, advanced_strategy):
        """Test that martingale DCA triggers and executes orders correctly."""
        # Initialize position
        position_state = PositionState(
            symbol="AAPL",
            direction=PositionDirection.LONG,
            phase=TradePhase.ENTRY,
            quantity=10.0,
            average_price=150.0,
            current_price=150.0,
            entry_time=datetime.utcnow(),
            is_martingale_enabled=True,
            dca_count=0,
            total_position_value=1500.0,
            next_dca_step_percent=1.5
        )
        advanced_strategy.positions["AAPL"] = position_state
        
        # Initialize martingale position state
        advanced_strategy.martingale_dca.initialize_position("AAPL", 150.0, 10.0, 1500.0)
        
        # Mock successful order placement
        mock_order = Mock()
        mock_order.order_id = "order123"
        advanced_strategy.order_manager.place_order = AsyncMock(return_value=mock_order)
        
        # Price drops by 2% (should trigger DCA)
        current_price = 147.0
        await advanced_strategy.update_position_monitoring("AAPL", current_price)
        
        # Verify order was placed
        advanced_strategy.order_manager.place_order.assert_called_once()
        call_args = advanced_strategy.order_manager.place_order.call_args
        
        assert call_args[1]['symbol'] == "AAPL"
        assert call_args[1]['quantity'] == pytest.approx(2000.0 / 147.0)  # DCA order size / price
        assert "order123" in position_state.active_orders
    
    @pytest.mark.asyncio
    async def test_martingale_dca_safety_limits_prevent_order(self, advanced_strategy, mock_risk_manager):
        """Test that safety limits prevent DCA orders when limits are exceeded."""
        # Set low available cash
        mock_risk_manager.get_available_cash = AsyncMock(return_value=500.0)  # Too low for DCA
        
        # Initialize position near max value
        position_state = PositionState(
            symbol="AAPL",
            direction=PositionDirection.LONG,
            phase=TradePhase.ENTRY,
            quantity=60.0,  # High quantity
            average_price=150.0,
            current_price=150.0,
            entry_time=datetime.utcnow(),
            is_martingale_enabled=True,
            dca_count=0,
            total_position_value=9000.0,  # Close to 10,000 limit
            next_dca_step_percent=1.5
        )
        advanced_strategy.positions["AAPL"] = position_state
        
        # Initialize martingale position state
        advanced_strategy.martingale_dca.initialize_position("AAPL", 150.0, 60.0, 9000.0)
        
        # Price drops significantly (would normally trigger DCA)
        current_price = 140.0
        await advanced_strategy.update_position_monitoring("AAPL", current_price)
        
        # Verify no order was placed due to safety limits
        advanced_strategy.order_manager.place_order.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_position_update_after_martingale_fill(self, advanced_strategy):
        """Test position update after martingale DCA order fills."""
        # Initialize position
        position_state = PositionState(
            symbol="AAPL",
            direction=PositionDirection.LONG,
            phase=TradePhase.ENTRY,
            quantity=10.0,
            average_price=150.0,
            current_price=150.0,
            entry_time=datetime.utcnow(),
            is_martingale_enabled=True,
            dca_count=0,
            total_position_value=1500.0,
            next_dca_step_percent=1.5
        )
        advanced_strategy.positions["AAPL"] = position_state
        
        # Initialize martingale position state
        advanced_strategy.martingale_dca.initialize_position("AAPL", 150.0, 10.0, 1500.0)
        
        # Simulate DCA order fill
        fill_price = 147.0
        fill_quantity = 13.61  # Approximately 2000 / 147
        fill_value = 2000.0
        
        await advanced_strategy._update_position_after_martingale_fill(
            "AAPL", fill_price, fill_quantity, fill_value
        )
        
        # Verify position was updated
        assert position_state.quantity == pytest.approx(23.61)  # 10 + 13.61
        assert position_state.dca_count == 1
        assert position_state.total_position_value == 3500.0  # 1500 + 2000
        assert position_state.average_price < 150.0  # Should be averaged down
    
    @pytest.mark.asyncio
    async def test_martingale_disabled_position(self, advanced_strategy):
        """Test that positions with martingale disabled don't trigger DCA."""
        # Initialize position with martingale disabled
        position_state = PositionState(
            symbol="AAPL",
            direction=PositionDirection.LONG,
            phase=TradePhase.ENTRY,
            quantity=10.0,
            average_price=150.0,
            current_price=150.0,
            entry_time=datetime.utcnow(),
            is_martingale_enabled=False,  # Disabled
            dca_count=0,
            total_position_value=1500.0,
            next_dca_step_percent=0.0
        )
        advanced_strategy.positions["AAPL"] = position_state
        
        # Large price drop that would trigger DCA if enabled
        current_price = 135.0  # -10% drop
        await advanced_strategy.update_position_monitoring("AAPL", current_price)
        
        # Verify no order was placed
        advanced_strategy.order_manager.place_order.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_max_dca_orders_reached(self, advanced_strategy):
        """Test that DCA doesn't trigger when max orders reached."""
        # Initialize position at max DCA count
        position_state = PositionState(
            symbol="AAPL",
            direction=PositionDirection.LONG,
            phase=TradePhase.ENTRY,
            quantity=10.0,
            average_price=150.0,
            current_price=150.0,
            entry_time=datetime.utcnow(),
            is_martingale_enabled=True,
            dca_count=5,  # Max DCA orders reached
            total_position_value=1500.0,
            next_dca_step_percent=1.5
        )
        advanced_strategy.positions["AAPL"] = position_state
        
        # Initialize martingale position state with max DCA count
        martingale_state = advanced_strategy.martingale_dca.initialize_position("AAPL", 150.0, 10.0, 1500.0)
        martingale_state.dca_count = 5  # Max reached
        
        # Large price drop
        current_price = 135.0  # -10% drop
        await advanced_strategy.update_position_monitoring("AAPL", current_price)
        
        # Verify no order was placed
        advanced_strategy.order_manager.place_order.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_short_position_martingale_dca(self, advanced_strategy):
        """Test martingale DCA for short positions."""
        # Initialize short position
        position_state = PositionState(
            symbol="AAPL",
            direction=PositionDirection.SHORT,
            phase=TradePhase.ENTRY,
            quantity=10.0,
            average_price=150.0,
            current_price=150.0,
            entry_time=datetime.utcnow(),
            is_martingale_enabled=True,
            dca_count=0,
            total_position_value=1500.0,
            next_dca_step_percent=1.5
        )
        advanced_strategy.positions["AAPL"] = position_state
        
        # Initialize martingale position state
        advanced_strategy.martingale_dca.initialize_position("AAPL", 150.0, 10.0, 1500.0)
        
        # Mock successful order placement
        mock_order = Mock()
        mock_order.order_id = "order123"
        advanced_strategy.order_manager.place_order = AsyncMock(return_value=mock_order)
        
        # Price rises by 2% (should trigger DCA for short position)
        current_price = 153.0
        await advanced_strategy.update_position_monitoring("AAPL", current_price)
        
        # Verify sell order was placed (covering more of the short)
        advanced_strategy.order_manager.place_order.assert_called_once()
        call_args = advanced_strategy.order_manager.place_order.call_args
        
        assert call_args[1]['symbol'] == "AAPL"
        assert call_args[1]['side'].value == "sell"  # Short position uses sell orders


class TestErrorHandling:
    """Test error handling in martingale DCA integration."""
    
    @pytest.mark.asyncio
    async def test_order_placement_failure(self, advanced_strategy):
        """Test handling of order placement failures."""
        # Initialize position
        position_state = PositionState(
            symbol="AAPL",
            direction=PositionDirection.LONG,
            phase=TradePhase.ENTRY,
            quantity=10.0,
            average_price=150.0,
            current_price=150.0,
            entry_time=datetime.utcnow(),
            is_martingale_enabled=True,
            dca_count=0,
            total_position_value=1500.0,
            next_dca_step_percent=1.5
        )
        advanced_strategy.positions["AAPL"] = position_state
        
        # Initialize martingale position state
        advanced_strategy.martingale_dca.initialize_position("AAPL", 150.0, 10.0, 1500.0)
        
        # Mock order placement failure
        advanced_strategy.order_manager.place_order = AsyncMock(return_value=None)
        
        # Price drop should trigger DCA attempt
        current_price = 147.0
        await advanced_strategy.update_position_monitoring("AAPL", current_price)
        
        # Verify order placement was attempted but no order was added to active orders
        advanced_strategy.order_manager.place_order.assert_called_once()
        assert len(position_state.active_orders) == 0
    
    @pytest.mark.asyncio
    async def test_missing_martingale_position_state(self, advanced_strategy):
        """Test handling when martingale position state is missing."""
        # Initialize strategy position without martingale state
        position_state = PositionState(
            symbol="AAPL",
            direction=PositionDirection.LONG,
            phase=TradePhase.ENTRY,
            quantity=10.0,
            average_price=150.0,
            current_price=150.0,
            entry_time=datetime.utcnow(),
            is_martingale_enabled=True,
            dca_count=0,
            total_position_value=1500.0,
            next_dca_step_percent=1.5
        )
        advanced_strategy.positions["AAPL"] = position_state
        
        # Don't initialize martingale position state
        
        # Price drop should not cause errors
        current_price = 147.0
        await advanced_strategy.update_position_monitoring("AAPL", current_price)
        
        # Should handle gracefully without placing orders
        advanced_strategy.order_manager.place_order.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])