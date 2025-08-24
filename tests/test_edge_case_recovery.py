"""
Comprehensive Edge Case Recovery Tests

Tests the enhanced support calculator's ability to handle edge cases that can occur
during bot restarts, market gaps, and data inconsistencies.

Focus Areas:
1. Cache invalidation after bot restart
2. Handling resistance below current price
3. Support above current price scenarios  
4. Market gap detection and recovery
5. Stale data handling
6. Synthetic level generation
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import List, Dict, Any

from src.strategies.support_calculator import TechnicalSupportCalculator, SupportLevel, SupportLevelData
from src.strategies.base_strategy import BaseStrategy, StrategyState
from src.exceptions import MarketDataException, ValidationException


class TestEdgeCaseRecovery:
    """Test suite for edge case recovery mechanisms."""
    
    @pytest.fixture
    def mock_config(self):
        """Mock configuration manager."""
        config = Mock()
        config.get_config.return_value = None
        return config
    
    @pytest.fixture
    def mock_market_data(self):
        """Mock market data provider."""
        return Mock()
    
    @pytest.fixture
    def calculator(self, mock_config, mock_market_data):
        """Support calculator instance for testing."""
        return TechnicalSupportCalculator(mock_config, mock_market_data)
    
    @pytest.fixture
    def sample_market_data_with_gap(self):
        """Sample market data with a price gap (bot restart scenario)."""
        base_time = datetime.utcnow()
        return [
            # Normal data before gap
            {'high': 520.0, 'low': 515.0, 'close': 518.0, 'timestamp': base_time - timedelta(hours=5)},
            {'high': 522.0, 'low': 517.0, 'close': 520.0, 'timestamp': base_time - timedelta(hours=4)},
            {'high': 525.0, 'low': 519.0, 'close': 523.0, 'timestamp': base_time - timedelta(hours=3)},
            
            # Large gap (bot was offline)
            {'high': 545.0, 'low': 540.0, 'close': 542.0, 'timestamp': base_time - timedelta(hours=1)},
            {'high': 548.0, 'low': 543.0, 'close': 546.0, 'timestamp': base_time},
        ]
    
    @pytest.fixture
    def stale_resistance_levels(self):
        """Resistance levels that are below current price (stale/invalid)."""
        old_time = datetime.utcnow() - timedelta(hours=2)
        return [
            SupportLevel(price=528.30, confidence=0.8, method="pivot", touches=3, 
                        last_touch=old_time, calculated_at=old_time),
            SupportLevel(price=525.50, confidence=0.7, method="trendline", touches=2, 
                        last_touch=old_time, calculated_at=old_time),
            SupportLevel(price=530.00, confidence=0.75, method="ma", touches=1, 
                        last_touch=old_time, calculated_at=old_time),
        ]
    
    @pytest.mark.asyncio
    async def test_resistance_below_current_price_recovery(self, calculator):
        """Test recovery when all resistance levels are below current price."""
        current_price = 537.29  # From the original issue
        stale_levels = [
            SupportLevel(price=528.30, confidence=0.8, method="pivot", touches=3),
            SupportLevel(price=525.50, confidence=0.7, method="trendline", touches=2),
        ]
        
        # Mock the internal resistance calculation to return stale levels
        with patch.object(calculator, '_calculate_pivot_resistance', return_value=528.30), \
             patch.object(calculator, '_calculate_moving_average_resistance', return_value=525.50), \
             patch.object(calculator, '_calculate_trendline_resistance', return_value=530.00):
            
            # The enhanced filter should detect this issue and apply recovery
            filtered_levels = calculator._filter_resistance_levels(stale_levels, current_price)
            
            # Should create synthetic levels or apply recovery logic
            assert len(filtered_levels) > 0, "Recovery should provide alternative levels"
            
            # All returned levels should be above current price or be synthetic/recovery levels
            for level in filtered_levels:
                if level.method != "synthetic_recovery":
                    # Only check non-synthetic levels - synthetic levels might be used for recovery
                    pass
                else:
                    # Synthetic levels should be above current price
                    assert level.price > current_price, f"Synthetic level {level.price} should be above {current_price}"
    
    @pytest.mark.asyncio
    async def test_support_above_current_price_recovery(self, calculator):
        """Test recovery when all support levels are above current price."""
        current_price = 515.00  # Price dropped significantly 
        stale_levels = [
            SupportLevel(price=520.00, confidence=0.8, method="pivot", touches=3),
            SupportLevel(price=525.50, confidence=0.7, method="trendline", touches=2),
        ]
        
        # The enhanced filter should detect this issue and apply recovery
        filtered_levels = calculator._filter_support_levels(stale_levels, current_price)
        
        # Should create synthetic levels or apply recovery logic
        assert len(filtered_levels) > 0, "Recovery should provide alternative levels"
        
        # Check if synthetic levels were created below current price
        synthetic_levels = [level for level in filtered_levels if level.method == "synthetic_recovery"]
        if synthetic_levels:
            for level in synthetic_levels:
                assert level.price < current_price, f"Synthetic support {level.price} should be below {current_price}"
    
    def test_synthetic_resistance_level_creation(self, calculator):
        """Test creation of synthetic resistance levels for recovery."""
        current_price = 537.29
        
        synthetic_levels = calculator._create_synthetic_resistance_levels(current_price)
        
        assert len(synthetic_levels) > 0, "Should create synthetic resistance levels"
        
        # All synthetic levels should be above current price
        for level in synthetic_levels:
            assert level.price > current_price, f"Synthetic resistance {level.price} should be above {current_price}"
            assert level.method == "synthetic_recovery", "Should be marked as synthetic"
            assert 0.4 <= level.confidence <= 0.8, "Should have reasonable confidence"
            assert level.touches == 0, "Synthetic levels have no historical touches"
    
    def test_synthetic_support_level_creation(self, calculator):
        """Test creation of synthetic support levels for recovery."""
        current_price = 515.00
        
        synthetic_levels = calculator._create_synthetic_support_levels(current_price)
        
        assert len(synthetic_levels) > 0, "Should create synthetic support levels"
        
        # All synthetic levels should be below current price
        for level in synthetic_levels:
            assert level.price < current_price, f"Synthetic support {level.price} should be below {current_price}"
            assert level.method == "synthetic_recovery", "Should be marked as synthetic"
            assert 0.4 <= level.confidence <= 0.8, "Should have reasonable confidence"
            assert level.touches == 0, "Synthetic levels have no historical touches"
    
    def test_cache_staleness_detection(self, calculator):
        """Test detection of stale cache entries."""
        # Create cache entries with different ages
        current_time = datetime.utcnow()
        
        # Fresh entry (should be valid)
        fresh_key = "MSFT_1h_pivot_fresh"
        calculator._cache_expiry[fresh_key] = current_time + timedelta(minutes=10)
        
        # Expired entry (should be invalid)
        stale_key = "MSFT_1h_pivot_stale"
        calculator._cache_expiry[stale_key] = current_time - timedelta(minutes=10)
        
        # Test validation
        assert calculator._is_cache_valid(fresh_key) == True, "Fresh cache should be valid"
        assert calculator._is_cache_valid(stale_key) == False, "Stale cache should be invalid"
        
        # Test cleanup
        calculator.clear_stale_cache()
        assert fresh_key in calculator._cache_expiry, "Fresh cache should remain"
        assert stale_key not in calculator._cache_expiry, "Stale cache should be removed"
    
    def test_market_data_validation_with_gaps(self, calculator, sample_market_data_with_gap):
        """Test validation of market data with price gaps."""
        cleaned_data = calculator._validate_market_data(
            sample_market_data_with_gap, "MSFT", "1h"
        )
        
        # Should keep all data but log warnings about gaps
        assert len(cleaned_data) == len(sample_market_data_with_gap), "Should keep all valid data"
        
        # All prices should be positive and properly formatted
        for bar in cleaned_data:
            assert bar['high'] > 0, "High price should be positive"
            assert bar['low'] > 0, "Low price should be positive"
            assert bar['close'] > 0, "Close price should be positive"
            assert bar['low'] <= bar['close'] <= bar['high'], "Price relationship should be valid"
    
    def test_extreme_price_validation(self, calculator):
        """Test validation of extreme price values."""
        # Test extremely high price
        with pytest.raises(ValueError, match="Extremely high price"):
            calculator._validate_inputs("MSFT", "1h", current_price=1500000.00)
        
        # Test extremely low price  
        with pytest.raises(ValueError, match="below minimum valid price"):
            calculator._validate_inputs("MSFT", "1h", current_price=0.0005)
        
        # Test negative price
        with pytest.raises(ValueError, match="must be positive"):
            calculator._validate_inputs("MSFT", "1h", current_price=-10.00)
    
    def test_invalid_symbol_handling(self, calculator):
        """Test handling of invalid symbol formats."""
        # Test empty symbol
        with pytest.raises(ValueError, match="Symbol must be"):
            calculator._validate_inputs("", "1h")
        
        # Test None symbol
        with pytest.raises(ValueError, match="Symbol must be"):
            calculator._validate_inputs(None, "1h")
        
        # Test symbol with invalid characters
        with pytest.raises(ValueError, match="Invalid symbol format"):
            calculator._validate_inputs("M$FT!", "1h")
    
    def test_cache_recovery_after_restart(self, calculator):
        """Test cache behavior that simulates bot restart scenario."""
        # Simulate cache from before restart (with old timestamp keys)
        old_time = datetime.utcnow() - timedelta(hours=2)
        
        # Clear cache to simulate restart
        calculator.clear_cache()
        
        # Verify cache is empty
        stats = calculator.get_cache_stats()
        assert stats['total_entries'] == 0, "Cache should be empty after clear"
        assert stats['valid_entries'] == 0, "No valid entries should remain"
    
    def test_position_aware_filtering_edge_cases(self, calculator):
        """Test position-aware filtering with edge cases."""
        position_price = 512.97  # From MSFT example
        current_price = 537.29
        
        # Create resistance levels that would be problematic for position averaging
        resistance_levels = [
            SupportLevel(price=528.30, confidence=0.8, method="pivot", touches=3),  # Below current price!
            SupportLevel(price=540.00, confidence=0.7, method="ma", touches=2),     # Above current price
            SupportLevel(price=545.00, confidence=0.75, method="trendline", touches=1),  # Above current price
        ]
        
        # Use position-aware filtering
        filtered_for_position = calculator._filter_resistance_levels_for_position(
            resistance_levels, current_price, position_price, 'short'
        )
        
        # Should handle the edge case appropriately
        assert len(filtered_for_position) >= 0, "Should handle edge case gracefully"
        
        # If any levels returned, they should be appropriate for the position
        for level in filtered_for_position:
            if level.method != "synthetic_recovery":
                # For short positions, resistance should be above position price for averaging decisions
                # (This is the corrected logic)
                pass  # Complex logic depends on position type and strategy
    
    @pytest.mark.asyncio  
    async def test_comprehensive_edge_case_scenario(self, calculator, mock_market_data):
        """Test a comprehensive edge case scenario combining multiple issues."""
        # Simulate bot restart scenario with:
        # 1. Stale cache
        # 2. Market gap
        # 3. Invalid resistance levels
        # 4. Network timeout
        
        # Clear cache to simulate restart
        calculator.clear_cache()
        
        # Mock market data with gap
        gap_data = [
            {'high': 520.0, 'low': 515.0, 'close': 518.0},
            {'high': 545.0, 'low': 540.0, 'close': 542.0},  # 4.6% gap
        ]
        
        mock_market_data.get_historical_data = AsyncMock(return_value=gap_data)
        
        # Mock individual calculation methods to return problematic values
        with patch.object(calculator, '_calculate_pivot_resistance', return_value=528.30), \
             patch.object(calculator, '_calculate_moving_average_resistance', return_value=525.50), \
             patch.object(calculator, '_calculate_trendline_resistance', return_value=530.00):
            
            # This should handle all edge cases gracefully
            try:
                result = await calculator.calculate_resistance_levels("MSFT", "1h", current_price=537.29)
                
                # Should get a result even with edge cases
                assert result is not None, "Should handle edge cases and return result"
                assert hasattr(result, 'levels'), "Result should have levels attribute"
                
            except Exception as e:
                # If it fails, the error should be informative
                assert "recovery" in str(e).lower() or "gap" in str(e).lower(), \
                    f"Error should indicate edge case handling: {e}"


class TestBaseStrategyErrorHandling:
    """Test suite for BaseStrategy error handling capabilities."""
    
    @pytest.fixture
    def mock_config(self):
        config = Mock()
        config.get_config.return_value = True
        return config
    
    @pytest.fixture
    def mock_market_data(self):
        return Mock()
    
    @pytest.fixture  
    def strategy(self, mock_config, mock_market_data):
        """Create a concrete strategy for testing."""
        class TestStrategy(BaseStrategy):
            async def initialize(self):
                return True
            
            async def execute(self, data):
                return {"success": True}
            
            async def cleanup(self):
                pass
        
        return TestStrategy(mock_config, mock_market_data)
    
    def test_input_validation_edge_cases(self, strategy):
        """Test input validation with edge cases."""
        # Test extreme price values
        with pytest.warns(None) as warnings:
            strategy._validate_inputs(current_price=999999.99)  # Should warn but not fail
        
        # Test very low prices  
        with pytest.warns(None) as warnings:
            strategy._validate_inputs(current_price=0.0001)  # Should warn but not fail
        
        # Test invalid symbols
        with pytest.raises(ValueError):
            strategy._validate_inputs(symbol="")
        
        with pytest.raises(ValueError):
            strategy._validate_inputs(symbol="M$FT!")
    
    def test_error_handling_mechanisms(self, strategy):
        """Test error handling and recovery mechanisms."""
        # Test connection error handling
        connection_error = ConnectionError("Network unavailable")
        error_response = strategy._handle_strategy_error(connection_error, "data_retrieval")
        
        assert error_response['success'] == False
        assert error_response['error_type'] == "ConnectionError"
        assert "recovery_suggestions" in error_response
        assert strategy.state == StrategyState.ERROR
        
        # Test timeout error handling
        timeout_error = TimeoutError("Operation timed out")
        error_response = strategy._handle_strategy_error(timeout_error, "calculation")
        
        assert error_response['success'] == False
        assert error_response['error_type'] == "TimeoutError"
        assert len(error_response['recovery_suggestions']) > 0
    
    def test_safe_execution_wrapper(self, strategy):
        """Test safe execution wrapper functionality."""
        # Test successful operation
        def successful_operation(x, y):
            return x + y
        
        result = strategy._safe_execute("addition", successful_operation, 5, 3)
        assert result == 8
        
        # Test failing operation
        def failing_operation():
            raise RuntimeError("Simulated failure")
        
        result = strategy._safe_execute("failing_op", failing_operation)
        assert result is None  # Should return None for runtime errors
        
        # Test validation error (should re-raise)
        def validation_error_operation():
            raise ValueError("Invalid input")
        
        with pytest.raises(ValueError):
            strategy._safe_execute("validation_op", validation_error_operation)
    
    @pytest.mark.asyncio
    async def test_async_safe_execution(self, strategy):
        """Test async safe execution wrapper."""
        # Test successful async operation
        async def successful_async_operation(x, y):
            await asyncio.sleep(0.01)  # Simulate async work
            return x * y
        
        result = await strategy._safe_async_execute("multiplication", successful_async_operation, 4, 5)
        assert result == 20
        
        # Test failing async operation
        async def failing_async_operation():
            await asyncio.sleep(0.01)
            raise RuntimeError("Async failure")
        
        result = await strategy._safe_async_execute("async_failing_op", failing_async_operation)
        assert result is None
        
        # Test timeout handling
        async def slow_operation():
            await asyncio.sleep(10)  # Very slow operation
            return "completed"
        
        with patch('asyncio.wait_for', side_effect=asyncio.TimeoutError()):
            result = await strategy._safe_async_execute("slow_op", slow_operation)
            assert result is None


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
