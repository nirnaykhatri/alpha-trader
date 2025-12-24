"""
Comprehensive test suite for the enhanced TechnicalSupportCalculator.
Tests cover edge cases, error handling, performance, and integration scenarios.
"""

import pytest
import asyncio
import math
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Assuming these imports work in the test environment
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.strategies.support_calculator import TechnicalSupportCalculator, BarData, CalculationConstants
from src.interfaces import IConfigurationManager, IMarketDataProvider, SupportLevel, SupportLevelData
from src.exceptions import MarketDataException, ConfigurationException


class TestBarData:
    """Test cases for the BarData class."""
    
    def test_valid_bar_data_creation(self):
        """Test creation of BarData with valid inputs."""
        data = {
            'high': 100.0,
            'low': 95.0,
            'open': 98.0,
            'close': 99.0,
            'volume': 1000
        }
        bar = BarData(data)
        
        assert bar.high == 100.0
        assert bar.low == 95.0
        assert bar.open == 98.0
        assert bar.close == 99.0
        assert bar.volume == 1000
    
    def test_invalid_bar_data_type(self):
        """Test BarData creation with invalid input type."""
        with pytest.raises(TypeError, match="data_dict must be a dictionary"):
            BarData("invalid")
    
    def test_negative_price_validation(self):
        """Test validation of negative prices."""
        data = {'high': -100.0, 'low': 95.0, 'open': 98.0, 'close': 99.0, 'volume': 1000}
        with pytest.raises(ValueError, match="Price values cannot be negative"):
            BarData(data)
    
    def test_high_less_than_low_validation(self):
        """Test validation when high < low."""
        data = {'high': 90.0, 'low': 95.0, 'open': 98.0, 'close': 99.0, 'volume': 1000}
        with pytest.raises(ValueError, match="High price cannot be less than low price"):
            BarData(data)
    
    def test_negative_volume_validation(self):
        """Test validation of negative volume."""
        data = {'high': 100.0, 'low': 95.0, 'open': 98.0, 'close': 99.0, 'volume': -1000}
        with pytest.raises(ValueError, match="Volume cannot be negative"):
            BarData(data)


class TestTechnicalSupportCalculator:
    """Test cases for the TechnicalSupportCalculator class."""
    
    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration manager."""
        config = Mock(spec=IConfigurationManager)
        config.get_config.side_effect = lambda key, default=None: {
            "technical_analysis.support.cache_duration_minutes": 15,
            "technical_analysis.support.lookback_periods": 50,
            "technical_analysis.support.min_confidence": 0.7,
            "technical_analysis.support.max_cache_size": 100,
            "technical_analysis.support.min_valid_price": 0.01,
            "logging.price_precision": 2,
            "logging.percentage_precision": 1,
        }.get(key, default)
        return config
    
    @pytest.fixture
    def mock_market_data(self):
        """Create a mock market data provider."""
        market_data = Mock(spec=IMarketDataProvider)
        market_data.get_current_price = AsyncMock(return_value=100.0)
        market_data.get_historical_data = AsyncMock(return_value=[
            {'high': 102.0, 'low': 98.0, 'open': 100.0, 'close': 101.0, 'volume': 1000},
            {'high': 103.0, 'low': 99.0, 'open': 101.0, 'close': 102.0, 'volume': 1100},
            {'high': 104.0, 'low': 100.0, 'open': 102.0, 'close': 103.0, 'volume': 1200},
        ])
        return market_data
    
    @pytest.fixture
    def calculator(self, mock_config, mock_market_data):
        """Create a TechnicalSupportCalculator instance for testing."""
        return TechnicalSupportCalculator(mock_config, mock_market_data)
    
    def test_initialization_with_valid_inputs(self, mock_config, mock_market_data):
        """Test successful initialization with valid inputs."""
        calculator = TechnicalSupportCalculator(mock_config, mock_market_data)
        assert calculator._config == mock_config
        assert calculator._market_data == mock_market_data
        assert isinstance(calculator._support_cache, dict)
        assert isinstance(calculator._resistance_cache, dict)
    
    def test_initialization_with_invalid_config_type(self, mock_market_data):
        """Test initialization fails with invalid config type."""
        with pytest.raises(TypeError, match="config must implement IConfigurationManager interface"):
            TechnicalSupportCalculator("invalid", mock_market_data)
    
    def test_initialization_with_invalid_market_data_type(self, mock_config):
        """Test initialization fails with invalid market data type."""
        with pytest.raises(TypeError, match="market_data_provider must implement IMarketDataProvider interface"):
            TechnicalSupportCalculator(mock_config, "invalid")
    
    def test_config_validation_with_invalid_values(self):
        """Test configuration validation with invalid values."""
        config = Mock(spec=IConfigurationManager)
        market_data = Mock(spec=IMarketDataProvider)
        
        # Set invalid configuration values
        config.get_config.side_effect = lambda key, default=None: {
            "technical_analysis.support.cache_duration_minutes": 15,
            "technical_analysis.support.lookback_periods": 5,  # Too small
            "technical_analysis.support.min_confidence": 1.5,  # Too high
            "technical_analysis.support.max_cache_size": 5,  # Too small
            "technical_analysis.support.min_valid_price": -0.01,  # Negative
            "logging.price_precision": -1,  # Negative
            "logging.percentage_precision": 15,  # Too high
        }.get(key, default)
        
        # Should not raise exception but correct the values
        calculator = TechnicalSupportCalculator(config, market_data)
        
        assert calculator._lookback_periods == CalculationConstants.MIN_LOOKBACK_PERIODS
        assert calculator._min_confidence == CalculationConstants.DEFAULT_MIN_CONFIDENCE
        assert calculator._max_cache_size == CalculationConstants.MIN_CACHE_SIZE
        assert calculator._min_valid_price == CalculationConstants.DEFAULT_MIN_VALID_PRICE
        assert calculator._price_precision == CalculationConstants.DEFAULT_PRICE_PRECISION
        assert calculator._percentage_precision == CalculationConstants.DEFAULT_PERCENTAGE_PRECISION
    
    @pytest.mark.asyncio
    async def test_calculate_support_with_valid_inputs(self, calculator, mock_market_data):
        """Test support calculation with valid inputs."""
        result = await calculator.calculate_support("AAPL", "1h")
        
        assert isinstance(result, SupportLevel)
        assert result.price > 0
        assert 0 <= result.confidence <= 1
        assert result.method == "combined"
        assert isinstance(result.calculated_at, datetime)
    
    @pytest.mark.asyncio
    async def test_calculate_support_with_invalid_symbol_type(self, calculator):
        """Test support calculation with invalid symbol type."""
        with pytest.raises(TypeError, match="Symbol must be string"):
            await calculator.calculate_support(123, "1h")
    
    @pytest.mark.asyncio
    async def test_calculate_support_with_empty_symbol(self, calculator):
        """Test support calculation with empty symbol."""
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            await calculator.calculate_support("", "1h")
    
    @pytest.mark.asyncio
    async def test_calculate_support_with_invalid_timeframe(self, calculator):
        """Test support calculation with invalid timeframe."""
        with pytest.raises(ValueError, match="Invalid timeframe"):
            await calculator.calculate_support("AAPL", "invalid")
    
    @pytest.mark.asyncio
    async def test_calculate_support_with_insufficient_data(self, calculator, mock_market_data):
        """Test support calculation with insufficient historical data."""
        mock_market_data.get_historical_data.return_value = [
            {'high': 102.0, 'low': 98.0, 'open': 100.0, 'close': 101.0, 'volume': 1000}
        ]
        
        with pytest.raises(MarketDataException, match="Insufficient historical data"):
            await calculator.calculate_support("AAPL", "1h")
    
    @pytest.mark.asyncio
    async def test_calculate_support_with_market_data_timeout(self, calculator, mock_market_data):
        """Test support calculation with market data timeout."""
        async def slow_data_fetch(*args, **kwargs):
            await asyncio.sleep(35)  # Longer than 30s timeout
            return []
        
        mock_market_data.get_historical_data.side_effect = slow_data_fetch
        
        with pytest.raises(MarketDataException, match="Support calculation timeout"):
            await calculator.calculate_support("AAPL", "1h")
    
    def test_confidence_calculation_with_no_levels(self, calculator):
        """Test confidence calculation with no valid levels."""
        result = calculator._calculate_confidence([])
        assert result == 0.0
    
    def test_confidence_calculation_with_single_level(self, calculator):
        """Test confidence calculation with single level."""
        result = calculator._calculate_confidence([100.0])
        assert result == 0.6
    
    def test_confidence_calculation_with_convergent_levels(self, calculator):
        """Test confidence calculation with convergent levels."""
        result = calculator._calculate_confidence([100.0, 100.5, 99.5])
        assert result > 0.7  # Should have high confidence for convergent levels
    
    def test_confidence_calculation_with_divergent_levels(self, calculator):
        """Test confidence calculation with divergent levels."""
        result = calculator._calculate_confidence([100.0, 120.0, 80.0])
        assert result < 0.5  # Should have low confidence for divergent levels
    
    def test_cache_cleanup_removes_expired_entries(self, calculator):
        """Test that cache cleanup removes expired entries."""
        # Add some cache entries
        calculator._support_cache["AAPL_1h"] = []
        calculator._resistance_cache["AAPL_1h_resistance"] = Mock()
        calculator._cache_expiry["AAPL_1h"] = datetime.utcnow() - timedelta(hours=1)  # Expired
        calculator._cache_expiry["AAPL_1h_resistance"] = datetime.utcnow() - timedelta(hours=1)  # Expired
        
        # Add non-expired entry
        calculator._support_cache["TSLA_1h"] = []
        calculator._cache_expiry["TSLA_1h"] = datetime.utcnow() + timedelta(hours=1)  # Not expired
        
        calculator._cleanup_expired_cache()
        
        # Expired entries should be removed
        assert "AAPL_1h" not in calculator._support_cache
        assert "AAPL_1h_resistance" not in calculator._resistance_cache
        assert "AAPL_1h" not in calculator._cache_expiry
        
        # Non-expired entry should remain
        assert "TSLA_1h" in calculator._support_cache
        assert "TSLA_1h" in calculator._cache_expiry
    
    def test_lru_eviction_when_cache_size_exceeded(self, calculator):
        """Test LRU eviction when cache size limit is exceeded."""
        # Set small cache size for testing
        calculator._max_cache_size = 2
        
        # Add entries that exceed cache size
        base_time = datetime.utcnow()
        calculator._support_cache["AAPL_1h"] = []
        calculator._cache_expiry["AAPL_1h"] = base_time + timedelta(minutes=1)
        
        calculator._support_cache["TSLA_1h"] = []
        calculator._cache_expiry["TSLA_1h"] = base_time + timedelta(minutes=2)
        
        calculator._support_cache["MSFT_1h"] = []
        calculator._cache_expiry["MSFT_1h"] = base_time + timedelta(minutes=3)  # Newest
        
        calculator._cleanup_expired_cache()
        
        # Should keep only the 2 newest entries
        assert len(calculator._cache_expiry) == 2
        assert "AAPL_1h" not in calculator._cache_expiry  # Oldest should be removed
        assert "TSLA_1h" in calculator._cache_expiry
        assert "MSFT_1h" in calculator._cache_expiry


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])
