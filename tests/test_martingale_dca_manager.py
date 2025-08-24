"""
Test suite for MartingaleDCAManager

Tests cover:
- Configuration validation and loading
- Position sizing calculations
- DCA trigger logic
- Safety limit enforcement
- Take profit and trailing stop logic
- Edge cases and error handling
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from decimal import Decimal

from src.strategies.martingale_dca_manager import (
    MartingaleDCAManager, MartingaleConfig, MartingalePositionState,
    OrderSizeType, DCAAmountType
)
from src.exceptions import TradingBotException, ConfigurationException


@pytest.fixture
def mock_config():
    """Mock configuration manager."""
    config = Mock()
    # Set up side_effect to handle different config keys
    def get_config_side_effect(key, default=None):
        configs = {
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
            'trading.max_portfolio_risk': 20.0,  # Return float, not dict
            'risk.max_position_value': 10000.0
        }
        return configs.get(key, default)
    
    config.get_config.side_effect = get_config_side_effect
    return config


@pytest.fixture
def mock_market_data():
    """Mock market data provider."""
    market_data = Mock()
    market_data.get_current_price = AsyncMock(return_value=150.0)
    return market_data


@pytest.fixture
def mock_risk_manager():
    """Mock risk manager."""
    risk_manager = Mock()
    risk_manager.get_portfolio_value = AsyncMock(return_value=100000.0)
    risk_manager.get_max_order_value = AsyncMock(return_value=5000.0)
    risk_manager.get_available_cash = AsyncMock(return_value=50000.0)
    return risk_manager


@pytest.fixture
def martingale_manager(mock_config, mock_market_data, mock_risk_manager):
    """Create MartingaleDCAManager instance for testing."""
    return MartingaleDCAManager(mock_config, mock_market_data, mock_risk_manager)


class TestMartingaleConfig:
    """Test MartingaleConfig validation."""
    
    def test_valid_config_creation(self):
        """Test creating a valid MartingaleConfig."""
        config = MartingaleConfig(
            symbol="AAPL",
            base_order_size_type=OrderSizeType.DOLLARS,
            base_order_size=1000.0,
            dca_order_size_type=DCAAmountType.MULTIPLIER,
            dca_amount_multiplier=2.0,
            dca_step_percent=1.5,
            step_multiplier=1.2,
            max_dca_orders=5,
            take_profit_percent=3.0,
            trailing_deviation_percent=0.8,
            max_position_value=10000.0
        )
        assert config.symbol == "AAPL"
        assert config.base_order_size == 1000.0
    
    def test_invalid_base_order_size(self):
        """Test validation fails for negative base order size."""
        with pytest.raises(ConfigurationException):
            MartingaleConfig(
                symbol="AAPL",
                base_order_size_type=OrderSizeType.DOLLARS,
                base_order_size=-1000.0,  # Invalid
                dca_order_size_type=DCAAmountType.MULTIPLIER,
                dca_amount_multiplier=2.0,
                dca_step_percent=1.5,
                step_multiplier=1.2,
                max_dca_orders=5,
                take_profit_percent=3.0,
                trailing_deviation_percent=0.8,
                max_position_value=10000.0
            )
    
    def test_invalid_dca_multiplier(self):
        """Test validation fails for DCA multiplier < 1."""
        with pytest.raises(ConfigurationException):
            MartingaleConfig(
                symbol="AAPL",
                base_order_size_type=OrderSizeType.DOLLARS,
                base_order_size=1000.0,
                dca_order_size_type=DCAAmountType.MULTIPLIER,
                dca_amount_multiplier=0.5,  # Invalid
                dca_step_percent=1.5,
                step_multiplier=1.2,
                max_dca_orders=5,
                take_profit_percent=3.0,
                trailing_deviation_percent=0.8,
                max_position_value=10000.0
            )
    
    def test_invalid_portfolio_percentage(self):
        """Test validation fails for excessive portfolio percentage."""
        with pytest.raises(ConfigurationException):
            MartingaleConfig(
                symbol="AAPL",
                base_order_size_type=OrderSizeType.PORTFOLIO_PERCENT,
                base_order_size=60.0,  # Invalid - too high
                dca_order_size_type=DCAAmountType.MULTIPLIER,
                dca_amount_multiplier=2.0,
                dca_step_percent=1.5,
                step_multiplier=1.2,
                max_dca_orders=5,
                take_profit_percent=3.0,
                trailing_deviation_percent=0.8,
                max_position_value=10000.0
            )


class TestPositionSizing:
    """Test position sizing calculations."""
    
    @pytest.mark.asyncio
    async def test_calculate_base_order_size_dollars(self, martingale_manager):
        """Test base order size calculation in dollars."""
        size = await martingale_manager.calculate_base_order_size("AAPL", 150.0)
        assert size == 1000.0
    
    @pytest.mark.asyncio
    async def test_calculate_base_order_size_portfolio_percent(self, mock_market_data, mock_risk_manager):
        """Test base order size calculation as portfolio percentage."""
        # Create a separate config mock for this test
        mock_config = Mock()
        def get_config_side_effect(key, default=None):
            configs = {
                'symbol_settings': {
                    'AAPL': {
                        'base_order_size_type': 'portfolio_percent',
                        'base_order_size': 2.0,  # 2% of portfolio
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
                'trading.max_portfolio_risk': 20.0,
                'risk.max_position_value': 10000.0
            }
            return configs.get(key, default)
        
        mock_config.get_config.side_effect = get_config_side_effect
        
        manager = MartingaleDCAManager(mock_config, mock_market_data, mock_risk_manager)
        
        size = await manager.calculate_base_order_size("AAPL", 150.0)
        assert size == 2000.0  # 2% of 100,000 portfolio
    
    @pytest.mark.asyncio
    async def test_calculate_dca_order_size_multiplier(self, martingale_manager):
        """Test DCA order size calculation using multiplier."""
        base_order_value = 1000.0
        
        # DCA 1: 1000 * 2^1 = 2000
        dca1_size = await martingale_manager.calculate_dca_order_size("AAPL", 1, base_order_value)
        assert dca1_size == 2000.0
        
        # DCA 2: 1000 * 2^2 = 4000
        dca2_size = await martingale_manager.calculate_dca_order_size("AAPL", 2, base_order_value)
        assert dca2_size == 4000.0
        
        # DCA 3: 1000 * 2^3 = 8000
        dca3_size = await martingale_manager.calculate_dca_order_size("AAPL", 3, base_order_value)
        assert dca3_size == 8000.0
    
    def test_calculate_next_dca_step_percent(self, martingale_manager):
        """Test progressive DCA step percentage calculation."""
        # Initial: 1.5%
        step0 = martingale_manager.calculate_next_dca_step_percent("AAPL", 0)
        assert step0 == 1.5
        
        # DCA 1: 1.5% * 1.2^1 = 1.8%
        step1 = martingale_manager.calculate_next_dca_step_percent("AAPL", 1)
        assert step1 == pytest.approx(1.8)
        
        # DCA 2: 1.5% * 1.2^2 = 2.16%
        step2 = martingale_manager.calculate_next_dca_step_percent("AAPL", 2)
        assert step2 == pytest.approx(2.16)


class TestDCATriggerLogic:
    """Test DCA trigger conditions."""
    
    def test_initialize_position(self, martingale_manager):
        """Test position initialization."""
        position_state = martingale_manager.initialize_position(
            "AAPL", 150.0, 10.0, 1500.0
        )
        
        assert position_state.symbol == "AAPL"
        assert position_state.entry_price == 150.0
        assert position_state.total_quantity == 10.0
        assert position_state.total_value_invested == 1500.0
        assert position_state.dca_count == 0
        assert len(position_state.dca_order_history) == 1  # Initial entry
    
    def test_should_trigger_dca_long_position(self, martingale_manager):
        """Test DCA trigger for long position on price drop."""
        # Initialize position
        position_state = martingale_manager.initialize_position(
            "AAPL", 150.0, 10.0, 1500.0
        )
        
        # Price drops by 2% (more than 1.5% threshold)
        current_price = 147.0  # -2% from 150
        should_trigger, info = martingale_manager.should_trigger_dca(
            "AAPL", current_price, is_long_position=True
        )
        
        assert should_trigger is True
        assert info['price_change_percent'] == pytest.approx(2.0)
        assert info['required_step_percent'] == 1.5
    
    def test_should_not_trigger_dca_insufficient_drop(self, martingale_manager):
        """Test DCA doesn't trigger for insufficient price drop."""
        # Initialize position
        position_state = martingale_manager.initialize_position(
            "AAPL", 150.0, 10.0, 1500.0
        )
        
        # Price drops by only 1% (less than 1.5% threshold)
        current_price = 148.5  # -1% from 150
        should_trigger, info = martingale_manager.should_trigger_dca(
            "AAPL", current_price, is_long_position=True
        )
        
        assert should_trigger is False
        assert info['price_change_percent'] == pytest.approx(1.0)
        assert info['required_step_percent'] == 1.5
    
    def test_should_trigger_dca_short_position(self, martingale_manager):
        """Test DCA trigger for short position on price rise."""
        # Initialize position
        position_state = martingale_manager.initialize_position(
            "AAPL", 150.0, 10.0, 1500.0
        )
        
        # Price rises by 2% (more than 1.5% threshold)
        current_price = 153.0  # +2% from 150
        should_trigger, info = martingale_manager.should_trigger_dca(
            "AAPL", current_price, is_long_position=False  # Short position
        )
        
        assert should_trigger is True
        assert info['price_change_percent'] == pytest.approx(2.0)
    
    def test_max_dca_orders_reached(self, martingale_manager):
        """Test DCA doesn't trigger when max orders reached."""
        # Initialize position with max DCA orders already reached
        position_state = martingale_manager.initialize_position(
            "AAPL", 150.0, 10.0, 1500.0
        )
        position_state.dca_count = 5  # Max DCA orders reached
        
        # Large price drop should not trigger DCA
        current_price = 135.0  # -10% drop
        should_trigger, info = martingale_manager.should_trigger_dca(
            "AAPL", current_price, is_long_position=True
        )
        
        assert should_trigger is False
        assert info['reason'] == 'Maximum DCA orders reached'


class TestSafetyLimits:
    """Test safety limit enforcement."""
    
    @pytest.mark.asyncio
    async def test_calculate_dca_order_details(self, martingale_manager):
        """Test DCA order details calculation."""
        # Initialize position
        position_state = martingale_manager.initialize_position(
            "AAPL", 150.0, 10.0, 1500.0
        )
        
        current_price = 147.0
        details = await martingale_manager.calculate_dca_order_details("AAPL", current_price)
        
        assert details['dca_number'] == 1
        assert details['order_value'] == 2000.0  # 1000 * 2^1
        assert details['quantity'] == pytest.approx(2000.0 / 147.0)
        assert details['new_average_price'] < 150.0  # Should be lower due to averaging down
        assert details['is_safe_to_execute'] is True
    
    @pytest.mark.asyncio
    async def test_validate_dca_safety_limits_valid(self, martingale_manager):
        """Test safety limit validation passes for valid order."""
        # Initialize position
        position_state = martingale_manager.initialize_position(
            "AAPL", 150.0, 10.0, 1500.0
        )
        
        validation = await martingale_manager.validate_dca_safety_limits("AAPL", 2000.0)
        
        assert validation['is_valid'] is True
        assert len(validation['violations']) == 0
    
    @pytest.mark.asyncio
    async def test_validate_dca_safety_limits_insufficient_funds(self, martingale_manager, mock_risk_manager):
        """Test safety limit validation fails for insufficient funds."""
        # Set low available cash
        mock_risk_manager.get_available_cash = AsyncMock(return_value=1000.0)
        
        # Initialize position
        position_state = martingale_manager.initialize_position(
            "AAPL", 150.0, 10.0, 1500.0
        )
        
        validation = await martingale_manager.validate_dca_safety_limits("AAPL", 2000.0)
        
        assert validation['is_valid'] is False
        assert 'insufficient_funds' in validation['violations']


class TestTakeProfitAndTrailing:
    """Test take profit and trailing stop logic."""
    
    def test_should_take_profit_long_position(self, martingale_manager):
        """Test take profit trigger for long position."""
        # Initialize position
        position_state = martingale_manager.initialize_position(
            "AAPL", 150.0, 10.0, 1500.0
        )
        
        # Price rises by 4% (above 3% threshold)
        current_price = 156.0
        should_take, info = martingale_manager.should_take_profit(
            "AAPL", current_price, is_long_position=True
        )
        
        assert should_take is True
        assert info['profit_percent'] == pytest.approx(4.0)
        assert info['take_profit_threshold'] == 3.0
    
    def test_should_not_take_profit_insufficient_gain(self, martingale_manager):
        """Test take profit doesn't trigger for insufficient gain."""
        # Initialize position
        position_state = martingale_manager.initialize_position(
            "AAPL", 150.0, 10.0, 1500.0
        )
        
        # Price rises by only 2% (below 3% threshold)
        current_price = 153.0
        should_take, info = martingale_manager.should_take_profit(
            "AAPL", current_price, is_long_position=True
        )
        
        assert should_take is False
        assert info['profit_percent'] == pytest.approx(2.0)
    
    def test_update_trailing_stop_activation(self, martingale_manager):
        """Test trailing stop activation when profitable."""
        # Initialize position
        position_state = martingale_manager.initialize_position(
            "AAPL", 150.0, 10.0, 1500.0
        )
        
        # Price rises to profitable level
        current_price = 155.0  # +3.33% profit
        should_stop, info = martingale_manager.update_trailing_stop(
            "AAPL", current_price, is_long_position=True
        )
        
        assert info['is_trailing_active'] is True
        assert info['peak_profit_price'] == 155.0
        assert info['trailing_stop_price'] == pytest.approx(155.0 * 0.992)  # 0.8% below peak
    
    def test_trailing_stop_trigger(self, martingale_manager):
        """Test trailing stop trigger when price falls below stop."""
        # Initialize position
        position_state = martingale_manager.initialize_position(
            "AAPL", 150.0, 10.0, 1500.0
        )
        
        # First, activate trailing stop
        martingale_manager.update_trailing_stop("AAPL", 155.0, is_long_position=True)
        
        # Then price falls below trailing stop
        current_price = 152.0  # Below stop price
        should_stop, info = martingale_manager.update_trailing_stop(
            "AAPL", current_price, is_long_position=True
        )
        
        assert should_stop is True
        assert info['should_stop'] is True


class TestPositionManagement:
    """Test position state management."""
    
    def test_update_position_after_dca(self, martingale_manager):
        """Test position update after DCA order execution."""
        # Initialize position
        position_state = martingale_manager.initialize_position(
            "AAPL", 150.0, 10.0, 1500.0
        )
        
        # Execute DCA order
        updated_state = martingale_manager.update_position_after_dca(
            "AAPL", 147.0, 13.61, 2000.0  # ~13.61 shares at $147
        )
        
        assert updated_state.dca_count == 1
        assert updated_state.total_quantity == pytest.approx(23.61)  # 10 + 13.61
        assert updated_state.total_value_invested == 3500.0  # 1500 + 2000
        assert updated_state.current_average_price == pytest.approx(3500.0 / 23.61)
        assert len(updated_state.dca_order_history) == 2  # Entry + DCA
    
    def test_get_position_summary(self, martingale_manager):
        """Test position summary generation."""
        # Initialize position
        position_state = martingale_manager.initialize_position(
            "AAPL", 150.0, 10.0, 1500.0
        )
        
        summary = martingale_manager.get_position_summary("AAPL")
        
        assert summary['symbol'] == "AAPL"
        assert summary['entry_price'] == 150.0
        assert summary['total_quantity'] == 10.0
        assert summary['total_value_invested'] == 1500.0
        assert summary['dca_count'] == 0
        assert summary['max_dca_orders'] == 5
    
    def test_remove_position(self, martingale_manager):
        """Test position removal."""
        # Initialize position
        position_state = martingale_manager.initialize_position(
            "AAPL", 150.0, 10.0, 1500.0
        )
        
        # Verify position exists
        assert martingale_manager.get_position_state("AAPL") is not None
        
        # Remove position
        removed = martingale_manager.remove_position("AAPL")
        assert removed is True
        
        # Verify position is gone
        assert martingale_manager.get_position_state("AAPL") is None


class TestEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_no_position_state_dca_check(self, martingale_manager):
        """Test DCA check with no position state returns False."""
        should_trigger, info = martingale_manager.should_trigger_dca(
            "NONEXISTENT", 100.0, is_long_position=True
        )
        
        assert should_trigger is False
        assert info['reason'] == 'No position state found'
    
    def test_position_value_limit_exceeded(self, martingale_manager):
        """Test DCA doesn't trigger when position value limit would be exceeded."""
        # Initialize position near the limit
        position_state = martingale_manager.initialize_position(
            "AAPL", 150.0, 60.0, 9000.0  # Close to 10,000 limit
        )
        
        # Large price drop that would normally trigger DCA
        current_price = 140.0  # -6.67% drop
        should_trigger, info = martingale_manager.should_trigger_dca(
            "AAPL", current_price, is_long_position=True
        )
        
        assert should_trigger is False
        assert 'exceed maximum position value' in info['reason']
    
    @pytest.mark.asyncio
    async def test_calculate_dca_order_details_no_position(self, martingale_manager):
        """Test DCA order details calculation fails with no position."""
        with pytest.raises(TradingBotException):
            await martingale_manager.calculate_dca_order_details("NONEXISTENT", 100.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])