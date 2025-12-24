"""
Unit tests for TrailingManager.
Tests trailing stop logic for both long and short positions.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
from decimal import Decimal

from src.strategies.trailing_manager import TrailingManager
from src.strategies.position_state import PositionState, PositionDirection, TradePhase


def create_mock_bot_config(
    trailing_deviation: float = 0.5,
    target_percent: float = 2.0
):
    """
    Helper to create mock BotConfiguration matching the actual structure.
    
    Args:
        trailing_deviation: Trailing stop deviation percentage
        target_percent: Profit target percentage
    """
    config = Mock()
    config.dca_config = Mock()
    config.dca_config.take_profit = Mock()
    # Return actual float values for arithmetic operations
    # The code divides these by 100.0 so they should be floats
    config.dca_config.take_profit.trailing_deviation = float(trailing_deviation)
    config.dca_config.take_profit.price_change_percent = float(target_percent)
    config.dca_config.take_profit.target_percent = float(target_percent)
    return config


def create_position(
    symbol: str = "AAPL",
    direction: PositionDirection = PositionDirection.LONG,
    phase: TradePhase = TradePhase.ENTRY,
    quantity: float = 100,
    average_price: float = 150.0,
    current_price: float = 155.0
) -> PositionState:
    """Helper to create a PositionState with correct required fields."""
    return PositionState(
        symbol=symbol,
        direction=direction,
        phase=phase,
        quantity=quantity,
        average_price=average_price,
        current_price=current_price,
        entry_time=datetime.now()
    )


class TestShouldStartTrailing:
    """Tests for trailing activation logic."""
    
    @pytest.fixture
    def manager(self):
        """Create TrailingManager with mock config."""
        return TrailingManager(bot_config=create_mock_bot_config())
    
    def test_should_start_when_profit_above_threshold(self, manager):
        """Trailing should start when profit exceeds threshold."""
        position = create_position(
            symbol="AAPL",
            direction=PositionDirection.LONG,
            quantity=100,
            average_price=150.0,
            current_price=154.0
        )
        position.profit_percentage = 0.025  # 2.5% as decimal - Above 0.02 threshold
        
        result = manager.should_start_trailing(position)
        
        assert result is True
    
    def test_should_not_start_when_profit_below_threshold(self, manager):
        """Trailing should NOT start when profit is below threshold."""
        position = create_position(
            symbol="AAPL",
            direction=PositionDirection.LONG,
            quantity=100,
            average_price=150.0,
            current_price=152.0
        )
        position.profit_percentage = 0.015  # 1.5% as decimal - Below 0.02 threshold
        
        result = manager.should_start_trailing(position)
        
        assert result is False
    
    def test_should_start_at_exact_threshold(self, manager):
        """Trailing should start at exactly the threshold."""
        position = create_position(
            symbol="AAPL",
            direction=PositionDirection.LONG,
            quantity=100,
            average_price=150.0,
            current_price=153.0
        )
        position.profit_percentage = 0.02  # 2% as decimal - Exactly at threshold
        
        result = manager.should_start_trailing(position)
        
        assert result is True


class TestInitializeTrailing:
    """Tests for trailing initialization."""
    
    @pytest.fixture
    def manager(self):
        """Create TrailingManager with 0.5% trailing."""
        return TrailingManager(bot_config=create_mock_bot_config(trailing_deviation=0.5))
    
    def test_initialize_long_position_trailing(self, manager):
        """Initialize trailing for LONG position sets correct trail price."""
        position = create_position(
            symbol="AAPL",
            direction=PositionDirection.LONG,
            phase=TradePhase.ENTRY,
            quantity=100,
            average_price=150.0,
            current_price=155.0
        )
        
        manager.initialize_trailing(position)
        
        assert position.phase == TradePhase.PROFIT_TRAILING
        assert position.peak_price == 155.0
        # Trail price = 155.0 * (1 - 0.005) = 154.225
        assert position.trail_price == pytest.approx(154.225, rel=0.001)
    
    def test_initialize_short_position_trailing(self, manager):
        """Initialize trailing for SHORT position sets correct trail price."""
        position = create_position(
            symbol="TSLA",
            direction=PositionDirection.SHORT,
            phase=TradePhase.ENTRY,
            quantity=-50,
            average_price=200.0,
            current_price=194.0
        )
        
        manager.initialize_trailing(position)
        
        assert position.phase == TradePhase.PROFIT_TRAILING
        assert position.peak_price == 194.0
        # Trail price = 194.0 * (1 + 0.005) = 194.97
        assert position.trail_price == pytest.approx(194.97, rel=0.001)


class TestUpdateLongTrailing:
    """Tests for LONG position trailing updates."""
    
    @pytest.fixture
    def manager(self):
        """Create TrailingManager with 0.5% trailing."""
        return TrailingManager(bot_config=create_mock_bot_config(trailing_deviation=0.5))
    
    @pytest.mark.asyncio
    async def test_updates_peak_on_new_high(self, manager):
        """Peak price should update when price makes new high."""
        position = create_position(
            symbol="AAPL",
            direction=PositionDirection.LONG,
            phase=TradePhase.PROFIT_TRAILING,
            quantity=100,
            average_price=150.0,
            current_price=157.0  # New high
        )
        position.peak_price = 155.0
        position.trail_price = 154.225
        
        close_callback = AsyncMock()
        
        result = await manager.update_long_trailing(position, close_callback)
        
        assert result is False  # Position not closed
        assert position.peak_price == 157.0  # Updated peak
        assert position.trail_price == pytest.approx(156.215, rel=0.001)  # New trail
        close_callback.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_triggers_close_when_trailing_stop_hit(self, manager):
        """Should close position when price drops below trail price."""
        position = create_position(
            symbol="AAPL",
            direction=PositionDirection.LONG,
            phase=TradePhase.PROFIT_TRAILING,
            quantity=100,
            average_price=150.0,
            current_price=154.0  # Below trail price
        )
        position.peak_price = 157.0
        position.trail_price = 156.215  # Current is below this
        
        close_callback = AsyncMock()
        
        result = await manager.update_long_trailing(position, close_callback)
        
        assert result is True  # Position closed
        close_callback.assert_called_once_with("AAPL")


class TestUpdateShortTrailing:
    """Tests for SHORT position trailing updates."""
    
    @pytest.fixture
    def manager(self):
        """Create TrailingManager with 0.5% trailing."""
        return TrailingManager(bot_config=create_mock_bot_config(trailing_deviation=0.5))
    
    @pytest.mark.asyncio
    async def test_updates_peak_on_new_low(self, manager):
        """Peak price should update when price makes new low (good for shorts)."""
        position = create_position(
            symbol="TSLA",
            direction=PositionDirection.SHORT,
            phase=TradePhase.PROFIT_TRAILING,
            quantity=-50,
            average_price=200.0,
            current_price=191.0  # New low - more profit
        )
        position.peak_price = 194.0  # Old peak (lower is better for shorts)
        position.trail_price = 194.97
        
        close_callback = AsyncMock()
        
        result = await manager.update_short_trailing(position, close_callback)
        
        assert result is False  # Position not closed
        assert position.peak_price == 191.0  # Updated to lower price
        assert position.trail_price == pytest.approx(191.955, rel=0.001)
        close_callback.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_triggers_close_when_trailing_stop_hit(self, manager):
        """Should close SHORT when price rises above trail price."""
        position = create_position(
            symbol="TSLA",
            direction=PositionDirection.SHORT,
            phase=TradePhase.PROFIT_TRAILING,
            quantity=-50,
            average_price=200.0,
            current_price=196.0  # Above trail price
        )
        position.peak_price = 191.0
        position.trail_price = 191.955  # Current is above this
        
        close_callback = AsyncMock()
        
        result = await manager.update_short_trailing(position, close_callback)
        
        assert result is True  # Position closed
        close_callback.assert_called_once_with("TSLA")


class TestInterfaceCompliance:
    """Tests for ITrailingManager interface compliance."""
    
    @pytest.fixture
    def manager(self):
        """Create TrailingManager."""
        return TrailingManager(bot_config=create_mock_bot_config())
    
    @pytest.mark.asyncio
    async def test_update_trailing_interface_routes_to_long(self, manager):
        """update_trailing interface method should route to long handler."""
        position = create_position(
            symbol="AAPL",
            direction=PositionDirection.LONG,
            phase=TradePhase.PROFIT_TRAILING,
            quantity=100,
            average_price=150.0,
            current_price=155.0
        )
        position.peak_price = 155.0
        position.trail_price = 154.225
        
        close_callback = AsyncMock()
        
        # Interface method
        result = await manager.update_trailing(position, close_callback)
        
        assert isinstance(result, bool)
    
    @pytest.mark.asyncio
    async def test_update_trailing_interface_routes_to_short(self, manager):
        """update_trailing interface method should route to short handler."""
        position = create_position(
            symbol="TSLA",
            direction=PositionDirection.SHORT,
            phase=TradePhase.PROFIT_TRAILING,
            quantity=-50,
            average_price=200.0,
            current_price=194.0
        )
        position.peak_price = 194.0
        position.trail_price = 194.97
        
        close_callback = AsyncMock()
        
        # Interface method
        result = await manager.update_trailing(position, close_callback)
        
        assert isinstance(result, bool)
