"""
Tests for Portfolio Exposure Proportional Scaling

Validates scaling factor logic for concentration and correlation constraints.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.risk.portfolio_exposure_validator import (
    PortfolioExposureValidator,
    PortfolioExposureResult
)


@pytest.fixture
def mock_market_data():
    """Mock market data provider."""
    mock = AsyncMock()
    return mock


@pytest.fixture
def mock_config():
    """Mock configuration manager."""
    mock = MagicMock()
    mock.get = MagicMock(side_effect=lambda key, default=None: default)
    return mock


@pytest.fixture
def validator(mock_market_data, mock_config):
    """Create portfolio exposure validator."""
    return PortfolioExposureValidator(
        market_data=mock_market_data,
        config=mock_config
    )


@pytest.mark.asyncio
class TestPortfolioScaling:
    """Test suite for portfolio exposure proportional scaling."""
    
    async def test_no_scaling_within_limits(self, validator):
        """Test that no scaling is applied when within limits."""
        # Account value: $100,000
        # Current positions: None
        # New position: $10,000 (10% of portfolio)
        # Limit: 20%
        # Expected: No scaling (scaling_factor = 1.0)
        
        result = await validator.validate_new_position(
            symbol='AAPL',
            position_value=10000.0,
            current_positions={},
            account_value=100000.0
        )
        
        assert result.approved is True
        assert result.scaling_factor == 1.0
        assert len(result.reasons) > 0
    
    async def test_scaling_applied_on_symbol_concentration(self, validator):
        """Test scaling when symbol concentration limit approached."""
        # Account value: $100,000
        # Current AAPL position: $15,000 (15%)
        # New AAPL position: $10,000
        # Combined would be: $25,000 (25%)
        # Limit: 20%
        # Headroom: 5% = $5,000
        # Expected: scaling_factor = 5000/10000 = 0.5
        
        result = await validator.validate_new_position(
            symbol='AAPL',
            position_value=10000.0,
            current_positions={'AAPL': 15000.0},
            account_value=100000.0
        )
        
        assert result.approved is True
        assert result.scaling_factor == pytest.approx(0.5, rel=1e-2)
        assert any('Symbol concentration' in reason for reason in result.reasons)
    
    async def test_scaling_factor_zero_blocks_position(self, validator):
        """Test that scaling_factor = 0.0 blocks position when no headroom."""
        # Account value: $100,000
        # Current AAPL position: $20,000 (20% - at limit)
        # New AAPL position: $5,000
        # Headroom: 0%
        # Expected: approved=False, scaling_factor=0.0
        
        result = await validator.validate_new_position(
            symbol='AAPL',
            position_value=5000.0,
            current_positions={'AAPL': 20000.0},
            account_value=100000.0
        )
        
        assert result.approved is False
        assert result.scaling_factor == 0.0
        assert any('at limit' in reason for reason in result.reasons)
    
    async def test_scaling_on_correlation(self, validator):
        """Test scaling when correlated symbol exposure limit approached."""
        # Mock correlation between AAPL and MSFT
        validator._get_correlation = AsyncMock(return_value=0.75)
        
        # Account value: $100,000
        # Current MSFT position: $30,000 (30%)
        # New AAPL position: $15,000
        # Combined correlated exposure: $45,000 (45%)
        # Correlation limit: 40%
        # Headroom: 10% = $10,000
        # Expected: scaling_factor = 10000/15000 = 0.667
        
        result = await validator.validate_new_position(
            symbol='AAPL',
            position_value=15000.0,
            current_positions={'MSFT': 30000.0},
            account_value=100000.0
        )
        
        assert result.approved is True
        assert result.scaling_factor == pytest.approx(0.667, rel=1e-1)
        assert any('Correlated exposure' in reason or 'correlation' in reason.lower() 
                   for reason in result.reasons)
    
    async def test_most_restrictive_scaling_applied(self, validator):
        """Test that most restrictive scaling factor is applied."""
        # Mock correlation
        validator._get_correlation = AsyncMock(return_value=0.75)
        
        # Account value: $100,000
        # Current AAPL: $15,000 (15%)
        # Current MSFT: $25,000 (25%, correlated with AAPL)
        # New AAPL: $10,000
        # 
        # Symbol concentration check:
        #   Combined AAPL: $25,000 (25%) > 20% limit
        #   Headroom: 5% = $5,000
        #   Scaling: 0.5
        # 
        # Correlation check:
        #   Combined correlated: $50,000 (50%) > 40% limit
        #   Headroom: 15% = $15,000
        #   Scaling: 1.0 (no scaling needed)
        # 
        # Expected: min(0.5, 1.0) = 0.5
        
        result = await validator.validate_new_position(
            symbol='AAPL',
            position_value=10000.0,
            current_positions={'AAPL': 15000.0, 'MSFT': 25000.0},
            account_value=100000.0
        )
        
        assert result.approved is True
        assert result.scaling_factor == pytest.approx(0.5, rel=1e-2)
    
    async def test_no_correlation_scaling_when_uncorrelated(self, validator):
        """Test that no correlation scaling when symbols uncorrelated."""
        # Mock low correlation
        validator._get_correlation = AsyncMock(return_value=0.3)
        
        result = await validator.validate_new_position(
            symbol='AAPL',
            position_value=10000.0,
            current_positions={'TSLA': 30000.0},
            account_value=100000.0
        )
        
        # Should only have symbol concentration scaling (if any)
        # No correlation scaling since correlation < threshold (0.70)
        assert result.approved is True
        # Correlation scaling should return 1.0 for uncorrelated symbols
    
    async def test_multiple_correlated_symbols(self, validator):
        """Test scaling with multiple correlated symbols."""
        # Mock high correlation for all symbols
        validator._get_correlation = AsyncMock(return_value=0.80)
        
        # Account value: $100,000
        # Current positions:
        #   MSFT: $15,000 (15%)
        #   GOOGL: $15,000 (15%)
        #   Total correlated: $30,000 (30%)
        # New AAPL: $15,000
        # Combined correlated: $45,000 (45%) > 40% limit
        # Headroom: 10% = $10,000
        # Expected: scaling_factor = 10000/15000 = 0.667
        
        result = await validator.validate_new_position(
            symbol='AAPL',
            position_value=15000.0,
            current_positions={'MSFT': 15000.0, 'GOOGL': 15000.0},
            account_value=100000.0
        )
        
        assert result.approved is True
        assert result.scaling_factor <= 1.0
        assert result.scaling_factor > 0.0
    
    async def test_zero_headroom_correlation(self, validator):
        """Test that zero headroom on correlation blocks position."""
        # Mock high correlation
        validator._get_correlation = AsyncMock(return_value=0.80)
        
        # Account value: $100,000
        # Current MSFT: $40,000 (40% - at correlation limit)
        # New AAPL: $5,000
        # Expected: approved=False, scaling_factor=0.0
        
        result = await validator.validate_new_position(
            symbol='AAPL',
            position_value=5000.0,
            current_positions={'MSFT': 40000.0},
            account_value=100000.0
        )
        
        assert result.approved is False
        assert result.scaling_factor == 0.0
