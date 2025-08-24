"""
Unit tests for RiskManager.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from decimal import Decimal

from src.risk import RiskManager
from src.core import ConfigurationManager
from src.exceptions import RiskException
from src.interfaces import Position, TradingSignal, SignalType


class TestRiskManager:
    """Test cases for RiskManager class."""
    
    @pytest.fixture
    def config_manager(self, test_config_file):
        """Configuration manager for testing."""
        return ConfigurationManager(test_config_file)
    
    @pytest.fixture
    def risk_manager(self, config_manager, mock_position_manager):
        """Risk manager instance for testing."""
        return RiskManager(config_manager, mock_position_manager)
    
    @pytest.fixture
    def mock_account_info(self):
        """Mock account information."""
        return {
            "equity": 10000.0,
            "cash": 8000.0,
            "buying_power": 12000.0,
            "day_trade_count": 2,
            "portfolio_value": 10000.0
        }
    
    @pytest.mark.asyncio
    async def test_validate_trade_success(self, risk_manager, sample_trading_signal, mock_account_info):
        """Test successful trade validation."""
        with patch.object(risk_manager, '_get_account_info', return_value=mock_account_info):
            with patch.object(risk_manager, '_get_current_positions', return_value=[]):
                is_valid = await risk_manager.validate_trade(sample_trading_signal, 100)
                assert is_valid is True
    
    @pytest.mark.asyncio
    async def test_validate_trade_insufficient_buying_power(self, risk_manager, sample_trading_signal):
        """Test trade validation with insufficient buying power."""
        mock_account_info = {
            "equity": 1000.0,
            "cash": 100.0,
            "buying_power": 200.0,
            "day_trade_count": 2,
            "portfolio_value": 1000.0
        }
        
        with patch.object(risk_manager, '_get_account_info', return_value=mock_account_info):
            with patch.object(risk_manager, '_get_current_positions', return_value=[]):
                is_valid = await risk_manager.validate_trade(sample_trading_signal, 100)
                assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_validate_trade_exceeds_max_position_size(self, risk_manager, sample_trading_signal, mock_account_info):
        """Test trade validation that exceeds max position size."""
        existing_position = Position(
            symbol="AAPL",
            quantity=900,
            avg_price=150.0,
            current_price=155.0,
            market_value=139500.0,
            unrealized_pnl=4500.0,
            unrealized_pnl_percent=0.033,
            side="long",
            created_at=1234567890,
            updated_at=1234567890
        )
        
        with patch.object(risk_manager, '_get_account_info', return_value=mock_account_info):
            with patch.object(risk_manager, '_get_current_positions', return_value=[existing_position]):
                is_valid = await risk_manager.validate_trade(sample_trading_signal, 200)
                assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_validate_trade_exceeds_daily_trade_limit(self, risk_manager, sample_trading_signal, mock_account_info):
        """Test trade validation that exceeds daily trade limit."""
        with patch.object(risk_manager, '_get_account_info', return_value=mock_account_info):
            with patch.object(risk_manager, '_get_current_positions', return_value=[]):
                with patch.object(risk_manager, '_get_daily_trade_count', return_value=55):
                    is_valid = await risk_manager.validate_trade(sample_trading_signal, 100)
                    assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_calculate_position_size_risk_based(self, risk_manager, sample_trading_signal, mock_account_info):
        """Test position size calculation based on risk percentage."""
        with patch.object(risk_manager, '_get_account_info', return_value=mock_account_info):
            position_size = await risk_manager.calculate_position_size(sample_trading_signal, stop_loss_price=140.0)
            
            # Risk per trade is 2% of portfolio (10000 * 0.02 = 200)
            # Price difference is 150 - 140 = 10
            # Position size should be 200 / 10 = 20 shares
            assert position_size == 20
    
    @pytest.mark.asyncio
    async def test_calculate_position_size_default_quantity(self, risk_manager, sample_trading_signal, mock_account_info):
        """Test position size calculation with default quantity."""
        with patch.object(risk_manager, '_get_account_info', return_value=mock_account_info):
            position_size = await risk_manager.calculate_position_size(sample_trading_signal)
            
            # Should return default quantity from config
            assert position_size == 100
    
    @pytest.mark.asyncio
    async def test_calculate_position_size_max_limit(self, risk_manager, sample_trading_signal, mock_account_info):
        """Test position size calculation with max limit."""
        with patch.object(risk_manager, '_get_account_info', return_value=mock_account_info):
            position_size = await risk_manager.calculate_position_size(sample_trading_signal, stop_loss_price=149.0)
            
            # Risk per trade is 2% of portfolio (10000 * 0.02 = 200)
            # Price difference is 150 - 149 = 1
            # Position size would be 200 / 1 = 200 shares
            # But max position size is 1000, so it should be capped
            assert position_size <= 1000
    
    @pytest.mark.asyncio
    async def test_check_portfolio_risk_within_limits(self, risk_manager, mock_account_info):
        """Test portfolio risk check within limits."""
        positions = [
            Position(
                symbol="AAPL",
                quantity=100,
                avg_price=150.0,
                current_price=155.0,
                market_value=15500.0,
                unrealized_pnl=500.0,
                unrealized_pnl_percent=0.033,
                side="long",
                created_at=1234567890,
                updated_at=1234567890
            )
        ]
        
        with patch.object(risk_manager, '_get_account_info', return_value=mock_account_info):
            with patch.object(risk_manager, '_get_current_positions', return_value=positions):
                is_within_limits = await risk_manager.check_portfolio_risk()
                assert is_within_limits is True
    
    @pytest.mark.asyncio
    async def test_check_portfolio_risk_exceeds_limits(self, risk_manager, mock_account_info):
        """Test portfolio risk check that exceeds limits."""
        # Create positions that would exceed the 10% portfolio risk limit
        positions = [
            Position(
                symbol="AAPL",
                quantity=100,
                avg_price=150.0,
                current_price=140.0,  # 10 point loss
                market_value=14000.0,
                unrealized_pnl=-1000.0,
                unrealized_pnl_percent=-0.067,
                side="long",
                created_at=1234567890,
                updated_at=1234567890
            ),
            Position(
                symbol="TSLA",
                quantity=50,
                avg_price=800.0,
                current_price=780.0,  # 20 point loss
                market_value=39000.0,
                unrealized_pnl=-1000.0,
                unrealized_pnl_percent=-0.025,
                side="long",
                created_at=1234567890,
                updated_at=1234567890
            )
        ]
        
        with patch.object(risk_manager, '_get_account_info', return_value=mock_account_info):
            with patch.object(risk_manager, '_get_current_positions', return_value=positions):
                is_within_limits = await risk_manager.check_portfolio_risk()
                assert is_within_limits is False
    
    @pytest.mark.asyncio
    async def test_get_risk_metrics(self, risk_manager, mock_account_info):
        """Test getting risk metrics."""
        positions = [
            Position(
                symbol="AAPL",
                quantity=100,
                avg_price=150.0,
                current_price=155.0,
                market_value=15500.0,
                unrealized_pnl=500.0,
                unrealized_pnl_percent=0.033,
                side="long",
                created_at=1234567890,
                updated_at=1234567890
            )
        ]
        
        with patch.object(risk_manager, '_get_account_info', return_value=mock_account_info):
            with patch.object(risk_manager, '_get_current_positions', return_value=positions):
                with patch.object(risk_manager, '_get_daily_trade_count', return_value=5):
                    metrics = await risk_manager.get_risk_metrics()
                    
                    assert "portfolio_value" in metrics
                    assert "total_exposure" in metrics
                    assert "risk_utilization" in metrics
                    assert "daily_trades" in metrics
                    assert "buying_power_utilization" in metrics
                    assert metrics["portfolio_value"] == 10000.0
                    assert metrics["daily_trades"] == 5
    
    @pytest.mark.asyncio
    async def test_validate_order_size_limits(self, risk_manager):
        """Test order size validation."""
        # Test minimum order size
        with pytest.raises(RiskException) as exc_info:
            await risk_manager._validate_order_size(0)
        assert "Order size must be positive" in str(exc_info.value)
        
        # Test maximum order size
        with pytest.raises(RiskException) as exc_info:
            await risk_manager._validate_order_size(10000)
        assert "Order size exceeds maximum" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_concentration_risk_check(self, risk_manager, mock_account_info):
        """Test concentration risk checking."""
        # Create a position that represents too much concentration in one symbol
        large_position = Position(
            symbol="AAPL",
            quantity=500,
            avg_price=150.0,
            current_price=155.0,
            market_value=77500.0,  # 77.5% of portfolio
            unrealized_pnl=2500.0,
            unrealized_pnl_percent=0.033,
            side="long",
            created_at=1234567890,
            updated_at=1234567890
        )
        
        with patch.object(risk_manager, '_get_account_info', return_value=mock_account_info):
            with patch.object(risk_manager, '_get_current_positions', return_value=[large_position]):
                concentration_risk = await risk_manager._check_concentration_risk("AAPL", 100)
                assert concentration_risk is True  # Should flag concentration risk
    
    @pytest.mark.asyncio
    async def test_market_hours_validation(self, risk_manager, sample_trading_signal):
        """Test market hours validation."""
        from datetime import datetime, time
        
        # Mock market hours (9:30 AM to 4:00 PM ET)
        with patch('src.risk.risk_manager.datetime') as mock_datetime:
            # Test during market hours
            mock_datetime.now.return_value = datetime(2023, 1, 3, 14, 30)  # Tuesday 2:30 PM
            is_valid = await risk_manager._is_market_hours()
            assert is_valid is True
            
            # Test outside market hours
            mock_datetime.now.return_value = datetime(2023, 1, 3, 20, 30)  # Tuesday 8:30 PM
            is_valid = await risk_manager._is_market_hours()
            assert is_valid is False
            
            # Test on weekend
            mock_datetime.now.return_value = datetime(2023, 1, 7, 14, 30)  # Saturday 2:30 PM
            is_valid = await risk_manager._is_market_hours()
            assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_volatility_risk_assessment(self, risk_manager, sample_trading_signal):
        """Test volatility risk assessment."""
        # Mock historical volatility data
        historical_data = [
            {"close": 150.0, "high": 155.0, "low": 145.0},
            {"close": 148.0, "high": 153.0, "low": 143.0},
            {"close": 152.0, "high": 157.0, "low": 147.0},
            {"close": 151.0, "high": 156.0, "low": 146.0},
            {"close": 149.0, "high": 154.0, "low": 144.0}
        ]
        
        with patch.object(risk_manager, '_get_historical_volatility', return_value=0.25):
            volatility_risk = await risk_manager._assess_volatility_risk(sample_trading_signal)
            assert isinstance(volatility_risk, float)
            assert volatility_risk >= 0.0
    
    @pytest.mark.asyncio
    async def test_correlation_risk_check(self, risk_manager, mock_account_info):
        """Test correlation risk checking."""
        # Create positions in highly correlated assets
        positions = [
            Position(
                symbol="AAPL",
                quantity=100,
                avg_price=150.0,
                current_price=155.0,
                market_value=15500.0,
                unrealized_pnl=500.0,
                unrealized_pnl_percent=0.033,
                side="long",
                created_at=1234567890,
                updated_at=1234567890
            ),
            Position(
                symbol="MSFT",
                quantity=50,
                avg_price=300.0,
                current_price=310.0,
                market_value=15500.0,
                unrealized_pnl=500.0,
                unrealized_pnl_percent=0.033,
                side="long",
                created_at=1234567890,
                updated_at=1234567890
            )
        ]
        
        with patch.object(risk_manager, '_get_correlation_coefficient', return_value=0.8):
            correlation_risk = await risk_manager._check_correlation_risk("GOOGL", positions)
            assert isinstance(correlation_risk, float)
            assert correlation_risk >= 0.0
    
    @pytest.mark.asyncio
    async def test_emergency_stop_conditions(self, risk_manager, mock_account_info):
        """Test emergency stop conditions."""
        # Simulate large portfolio drawdown
        large_loss_account = {
            "equity": 7000.0,  # 30% drawdown from 10000
            "cash": 5000.0,
            "buying_power": 8000.0,
            "day_trade_count": 10,
            "portfolio_value": 7000.0
        }
        
        with patch.object(risk_manager, '_get_account_info', return_value=large_loss_account):
            should_stop = await risk_manager._check_emergency_stop_conditions()
            assert should_stop is True
    
    @pytest.mark.asyncio
    async def test_risk_manager_error_handling(self, risk_manager, sample_trading_signal):
        """Test error handling in risk manager."""
        # Test when account info is unavailable
        with patch.object(risk_manager, '_get_account_info', side_effect=Exception("API Error")):
            with pytest.raises(RiskException) as exc_info:
                await risk_manager.validate_trade(sample_trading_signal, 100)
            assert "Failed to validate trade" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_dynamic_risk_adjustment(self, risk_manager, mock_account_info):
        """Test dynamic risk adjustment based on market conditions."""
        # Mock high volatility market conditions
        with patch.object(risk_manager, '_get_market_volatility', return_value=0.4):  # High volatility
            with patch.object(risk_manager, '_get_account_info', return_value=mock_account_info):
                adjusted_risk = await risk_manager._get_adjusted_risk_per_trade()
                # Risk should be reduced in high volatility
                assert adjusted_risk < 0.02  # Less than the base 2%
        
        # Mock low volatility market conditions
        with patch.object(risk_manager, '_get_market_volatility', return_value=0.1):  # Low volatility
            with patch.object(risk_manager, '_get_account_info', return_value=mock_account_info):
                adjusted_risk = await risk_manager._get_adjusted_risk_per_trade()
                # Risk can be maintained or slightly increased in low volatility
                assert adjusted_risk <= 0.02
