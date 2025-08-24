"""
Support level calculation implementation using technical analysis.

This module provides comprehensive support and resistance level calculations using multiple
technical analysis methods including pivot points, moving averages, volume profile analysis,
and Fibonacci retracements/extensions.

Classes:
    BarData: Optimized wrapper for historical price/volume data
    TechnicalSupportCalculator: Main calculator implementing multiple TA methods

Configuration Options:
    technical_analysis.support.cache_duration_minutes: Cache duration in minutes (default: 15)
    technical_analysis.support.lookback_periods: Number of historical periods to analyze (default: 50)
    technical_analysis.support.min_confidence: Minimum confidence threshold for levels (default: 0.7)
    technical_analysis.support.max_cache_size: Maximum number of cached entries (default: 100)
    technical_analysis.support.min_valid_price: Minimum valid price to avoid division by zero (default: 0.01)
    logging.price_precision: Decimal places for price display in logs (default: 2)
    logging.percentage_precision: Decimal places for percentage display in logs (default: 1)

Example:
    >>> config = ConfigurationManager("config.yaml")
    >>> market_data = AlpacaMarketDataProvider(config)
    >>> calculator = TechnicalSupportCalculator(config, market_data)
    >>> support_data = await calculator.calculate_support_levels("AAPL", "1h")
    >>> print(f"Found {len(support_data.levels)} support levels")

Author: Trading Bot System
Version: 2.0
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import math
from ..interfaces import ISupportCalculator, IMarketDataProvider, IConfigurationManager, SupportLevel, SupportLevelData
from ..exceptions import MarketDataException
from ..core.logging_config import get_logger


# Constants for improved maintainability
class CalculationConstants:
    """Constants used throughout the support calculator."""
    
    # Default configuration values
    DEFAULT_CACHE_DURATION_MINUTES = 15
    DEFAULT_LOOKBACK_PERIODS = 50
    DEFAULT_MIN_CONFIDENCE = 0.7
    DEFAULT_MAX_CACHE_SIZE = 100
    DEFAULT_MIN_VALID_PRICE = 0.01
    DEFAULT_PRICE_PRECISION = 2
    DEFAULT_PERCENTAGE_PRECISION = 1
    
    # Validation limits
    MIN_LOOKBACK_PERIODS = 10
    MIN_CACHE_SIZE = 10
    MIN_CONFIDENCE_THRESHOLD = 0.1
    MAX_CONFIDENCE_THRESHOLD = 1.0
    
    # Calculation weights for combined methods
    PIVOT_WEIGHT = 0.4
    MOVING_AVERAGE_WEIGHT = 0.3
    TRENDLINE_WEIGHT = 0.3
    
    # Price tolerance and buffers
    DEFAULT_PRICE_TOLERANCE = 0.002  # 0.2%
    DEFAULT_CONSOLIDATION_TOLERANCE = 0.005  # 0.5%
    MAX_PRICE_DEVIATION = 0.1  # 10%
    
    # Edge case handling constants
    DEFAULT_RECOVERY_PROXIMITY_THRESHOLD = 0.02  # 2% proximity for recovery mode
    DEFAULT_RECENT_THRESHOLD_MINUTES = 30        # Consider levels from last 30 minutes as "recent"
    DEFAULT_SYNTHETIC_LEVEL_COUNT = 5            # Number of synthetic levels to create
    
    # Position-aware filtering constants
    DEFAULT_POSITION_BUFFER_PERCENT = 0.001      # 0.1% buffer around position price
    MIN_POSITION_BUFFER = 0.0001                 # 0.01% minimum buffer  
    MAX_POSITION_BUFFER = 0.01                   # 1% maximum buffer
    
    # Cache management constants
    MAX_CACHE_SIZE = 1000                        # Maximum cache entries
    MIN_CACHE_DURATION_MINUTES = 1               # Minimum cache duration
    MAX_CACHE_DURATION_MINUTES = 120             # Maximum cache duration
    
    # Moving average periods
    MA_PERIODS = [20, 50, 100, 200]
    
    # Fibonacci levels
    FIBONACCI_RETRACEMENT_LEVELS = [0.236, 0.382, 0.5, 0.618, 0.786]
    FIBONACCI_EXTENSION_LEVELS = [1.272, 1.414, 1.618, 2.0, 2.618]


logger = get_logger(__name__)


class BarData:
    """Wrapper class for historical bar data with memory optimization."""
    __slots__ = ('high', 'low', 'open', 'close', 'volume')
    
    def __init__(self, data_dict: Dict[str, Any]):
        if not isinstance(data_dict, dict):
            raise TypeError("data_dict must be a dictionary")
        
        self.high = float(data_dict.get('high', 0.0))
        self.low = float(data_dict.get('low', 0.0))
        self.open = float(data_dict.get('open', 0.0))
        self.close = float(data_dict.get('close', 0.0))
        self.volume = int(data_dict.get('volume', 0))
        
        # Validate data integrity
        if self.high < 0 or self.low < 0 or self.open < 0 or self.close < 0:
            raise ValueError("Price values cannot be negative")
        if self.high < self.low:
            raise ValueError("High price cannot be less than low price")
        if self.volume < 0:
            raise ValueError("Volume cannot be negative")


class TechnicalSupportCalculator(ISupportCalculator):
    """
    Calculates support levels using technical analysis methods.
    Supports multiple calculation methods: pivot points, moving averages, and trend lines.
    """
    
    def __init__(self, config: IConfigurationManager, 
                 market_data_provider: IMarketDataProvider):
        """
        Initialize support calculator.
        
        Args:
            config: Configuration manager instance
            market_data_provider: Market data provider instance
            
        Raises:
            TypeError: If arguments are not of expected type
            ConfigurationException: If configuration is invalid
        """
        # Type validation
        if not isinstance(config, IConfigurationManager):
            raise TypeError("config must implement IConfigurationManager interface")
        if not isinstance(market_data_provider, IMarketDataProvider):
            raise TypeError("market_data_provider must implement IMarketDataProvider interface")
        
        self._config = config
        self._market_data = market_data_provider
        
        # Initialize cache dictionaries with type hints
        self._support_cache: Dict[str, List[SupportLevel]] = {}
        self._resistance_cache: Dict[str, SupportLevelData] = {}
        self._cache_expiry: Dict[str, datetime] = {}
        
        # Load and validate configuration
        self._load_configuration()
        self._validate_config()
        
        logger.info("TechnicalSupportCalculator initialized with validated configuration")
    
    def _load_configuration(self) -> None:
        """Load configuration values with fallbacks to constants."""
        # Load configuration values with sensible defaults and backward compatibility
        cache_duration_minutes = (
            self._config.get_config("technical_analysis.support.cache_duration_minutes") or
            self._config.get_config("technical_analysis.support.cache_duration", 
                                  CalculationConstants.DEFAULT_CACHE_DURATION_MINUTES)
        )
        self._cache_duration = timedelta(minutes=cache_duration_minutes)
        
        # Core calculation parameters
        self._lookback_periods = self._config.get_config(
            "technical_analysis.support.lookback_periods", 
            CalculationConstants.DEFAULT_LOOKBACK_PERIODS)
        self._min_confidence = self._config.get_config(
            "technical_analysis.support.min_confidence", 
            CalculationConstants.DEFAULT_MIN_CONFIDENCE)
        self._max_cache_size = self._config.get_config(
            "technical_analysis.support.max_cache_size", 
            CalculationConstants.DEFAULT_MAX_CACHE_SIZE)
        
        # Validation and logging configuration
        self._min_valid_price = self._config.get_config(
            "technical_analysis.support.min_valid_price", 
            CalculationConstants.DEFAULT_MIN_VALID_PRICE)
        self._price_precision = self._config.get_config(
            "logging.price_precision", 
            CalculationConstants.DEFAULT_PRICE_PRECISION)
        self._percentage_precision = self._config.get_config(
            "logging.percentage_precision", 
            CalculationConstants.DEFAULT_PERCENTAGE_PRECISION)
    
    def _validate_config(self) -> None:
        """Validate configuration parameters with comprehensive checks."""
        validation_issues = []
        
        # Validate lookback periods
        if self._lookback_periods < CalculationConstants.MIN_LOOKBACK_PERIODS:
            validation_issues.append(f"Lookback periods too small: {self._lookback_periods}")
            self._lookback_periods = CalculationConstants.MIN_LOOKBACK_PERIODS
        
        # Validate confidence threshold
        if not (CalculationConstants.MIN_CONFIDENCE_THRESHOLD <= self._min_confidence <= CalculationConstants.MAX_CONFIDENCE_THRESHOLD):
            validation_issues.append(f"Invalid min confidence: {self._min_confidence}")
            self._min_confidence = CalculationConstants.DEFAULT_MIN_CONFIDENCE
        
        # Validate cache size
        if self._max_cache_size < CalculationConstants.MIN_CACHE_SIZE:
            validation_issues.append(f"Cache size too small: {self._max_cache_size}")
            self._max_cache_size = CalculationConstants.MIN_CACHE_SIZE
        
        # Validate minimum valid price
        if self._min_valid_price <= 0:
            validation_issues.append(f"Invalid min valid price: {self._min_valid_price}")
            self._min_valid_price = CalculationConstants.DEFAULT_MIN_VALID_PRICE
        
        # Validate precision values
        if self._price_precision < 0 or self._price_precision > 10:
            validation_issues.append(f"Invalid price precision: {self._price_precision}")
            self._price_precision = CalculationConstants.DEFAULT_PRICE_PRECISION
        
        if self._percentage_precision < 0 or self._percentage_precision > 10:
            validation_issues.append(f"Invalid percentage precision: {self._percentage_precision}")
            self._percentage_precision = CalculationConstants.DEFAULT_PERCENTAGE_PRECISION
        
        # Log any validation issues that were automatically corrected
        if validation_issues:
            logger.warning(f"Configuration validation issues corrected: {'; '.join(validation_issues)}")
        else:
            logger.debug("Configuration validation passed")
    
    async def calculate_support(self, symbol: str, timeframe: str) -> SupportLevel:
        """
        Calculate the primary support level for a symbol.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe for calculation (e.g., '1h', '4h', '1d')
            
        Returns:
            Calculated support level
            
        Raises:
            MarketDataException: If market data is unavailable
            ValueError: If inputs are invalid
            TypeError: If inputs are of wrong type
        """
        # Comprehensive input validation and sanitization
        if not isinstance(symbol, str):
            raise TypeError(f"Symbol must be string, got {type(symbol).__name__}")
        if not isinstance(timeframe, str):
            raise TypeError(f"Timeframe must be string, got {type(timeframe).__name__}")
        # Enhanced input validation with edge case handling
        if not symbol or not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("Symbol must be a non-empty string")
        if not timeframe or not isinstance(timeframe, str) or not timeframe.strip():
            raise ValueError("Timeframe must be a non-empty string")
        
        # Sanitize inputs to prevent injection attacks and normalize format
        symbol = symbol.strip().upper()
        timeframe = timeframe.strip().lower()
        
        # Enhanced symbol validation with edge case handling
        if not symbol.replace('.', '').replace('-', '').replace('_', '').isalnum():
            raise ValueError(f"Invalid symbol format: {symbol}. Only alphanumeric, dots, dashes, and underscores allowed")
        
        # Check for unreasonably long symbols (potential data corruption)
        if len(symbol) > 15:
            logger.warning(f"⚠️ Unusually long symbol detected: {symbol}")
        
        # Enhanced timeframe validation
        valid_timeframes = {'1m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d', '1w', '1M'}
        if timeframe not in valid_timeframes:
            # Try to normalize common timeframe variations
            timeframe_map = {
                '1min': '1m', '5min': '5m', '15min': '15m', '30min': '30m',
                '1hour': '1h', '1hr': '1h', 'daily': '1d', 'day': '1d',
                'weekly': '1w', 'week': '1w', 'monthly': '1M', 'month': '1M'
            }
            
            if timeframe in timeframe_map:
                timeframe = timeframe_map[timeframe]
                logger.debug(f"Normalized timeframe to: {timeframe}")
            else:
                raise ValueError(f"Invalid timeframe: {timeframe}. Valid options: {valid_timeframes}")
        
        # Current price validation if provided
        if current_price is not None:
            if not isinstance(current_price, (int, float)):
                raise ValueError(f"Current price must be numeric, got: {type(current_price).__name__}")
            
            if current_price <= 0:
                raise ValueError(f"Current price must be positive, got: {current_price}")
            
            if current_price < self._min_valid_price:
                raise ValueError(f"Current price {current_price} below minimum valid price {self._min_valid_price}")
            
            # Check for extreme values that might indicate data errors
            if current_price > 100000:  # $100K per share - very unusual
                logger.warning(f"⚠️ Extremely high price detected: ${current_price:,.2f} for {symbol}")
            elif current_price < 0.01:  # Less than 1 cent - very unusual for most stocks
                logger.warning(f"⚠️ Very low price detected: ${current_price:.4f} for {symbol}")

        try:
            logger.debug(f"📊 Calculating support for {symbol} on {timeframe}")
            
            # Enhanced cache cleanup with staleness detection
            self._cleanup_expired_cache()
            self.clear_stale_cache()  # Additional cleanup for edge cases
            
            # Get historical data with robust timeout and retry logic
            try:
                historical_data = await asyncio.wait_for(
                    self._get_historical_data(symbol, timeframe),
                    timeout=30.0  # 30 second timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"⏰ Timeout getting historical data for {symbol}")
                raise MarketDataException(f"Timeout retrieving data for {symbol}")
            except Exception as e:
                logger.error(f"❌ Failed to get historical data for {symbol}: {e}")
                raise MarketDataException(f"Data retrieval failed for {symbol}: {str(e)}")
            
            # Enhanced data validation with edge case detection
            if not historical_data:
                raise MarketDataException(f"No historical data returned for {symbol}")
            
            if len(historical_data) < 3:
                raise MarketDataException(f"Insufficient historical data for {symbol}: {len(historical_data)} bars (minimum 3 required)")
            
            # Log data quality for debugging
            if len(historical_data) < self._lookback_periods:
                logger.warning(f"⚠️ Limited data for {symbol}: {len(historical_data)} bars (recommended {self._lookback_periods})")
            
            # Validate data integrity before calculations
            try:
                cleaned_data = self._validate_market_data(historical_data, symbol, timeframe)
                if len(cleaned_data) < len(historical_data):
                    logger.info(f"📊 Data cleaning for {symbol}: {len(cleaned_data)}/{len(historical_data)} bars kept")
                historical_data = cleaned_data
            except Exception as e:
                logger.warning(f"Data validation warning for {symbol}: {e}")
                # Continue with original data but flag the issue
            
            # Calculate multiple support levels using different methods with error isolation
            methods_results = {}
            
            try:
                methods_results['pivot'] = self._calculate_pivot_support(historical_data)
            except Exception as e:
                logger.warning(f"Pivot support calculation failed for {symbol}: {e}")
                methods_results['pivot'] = 0.0
            
            try:
                methods_results['ma'] = self._calculate_moving_average_support(historical_data)
            except Exception as e:
                logger.warning(f"MA support calculation failed for {symbol}: {e}")
                methods_results['ma'] = 0.0
            
            try:
                methods_results['trendline'] = self._calculate_trendline_support(historical_data)
            except Exception as e:
                logger.warning(f"Trendline support calculation failed for {symbol}: {e}")
                methods_results['trendline'] = 0.0
            
            # Ensure we have at least one valid result
            valid_results = [v for v in methods_results.values() if v > 0]
            if not valid_results:
                raise MarketDataException(f"All support calculation methods failed for {symbol}")
            
            # Combine and weight the support levels
            combined_support = self._combine_support_levels(list(methods_results.values()))
            
            # Calculate confidence based on convergence
            confidence = self._calculate_confidence(list(methods_results.values()))
            
            # Validate final results
            if combined_support <= 0 or math.isnan(combined_support) or math.isinf(combined_support):
                raise MarketDataException(f"Invalid support level calculated for {symbol}: {combined_support}")
            
            support_level = SupportLevel(
                price=combined_support,
                confidence=confidence,
                method="combined",
                touches=1,
                last_touch=datetime.utcnow(),
                calculated_at=datetime.utcnow()
            )
            
            logger.info(f"Support calculated for {symbol}: {support_level.price:.4f} "
                       f"(confidence: {support_level.confidence:.2f})")
            
            return support_level
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout calculating support for {symbol}")
            raise MarketDataException(f"Support calculation timeout for {symbol}")
        except Exception as e:
            logger.error(f"Failed to calculate support for {symbol}: {str(e)}")
            # Re-raise known exceptions, wrap unknown ones
            if isinstance(e, (MarketDataException, ValueError, TypeError)):
                raise
            else:
                raise MarketDataException(f"Support calculation failed: {str(e)}")
    
    async def _get_historical_data(self, symbol: str, timeframe: str, 
                                 count: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get historical market data."""
        try:
            count = count or self._lookback_periods
            data = await self._market_data.get_historical_data(symbol, timeframe, count)
            
            if not data:
                raise MarketDataException(f"No historical data available for {symbol}")
            
            return data
            
        except Exception as e:
            logger.error(f"Failed to get historical data for {symbol}: {str(e)}")
            raise MarketDataException(f"Historical data unavailable: {str(e)}")
    
    def _calculate_pivot_support(self, data: List[Dict[str, Any]]) -> float:
        """
        Calculate support using pivot points method.
        
        Args:
            data: Historical price data
            
        Returns:
            Pivot-based support level
        """
        if len(data) < 3:
            return data[-1]['low'] if data else 0.0
        
        # Use the most recent complete period
        last_candle = data[-1]
        high = last_candle['high']
        low = last_candle['low']
        close = last_candle['close']
        
        # Calculate pivot point
        pivot = (high + low + close) / 3
        
        # Calculate support levels
        support1 = 2 * pivot - high
        support2 = pivot - (high - low)
        
        # Return the stronger (higher) support
        return max(support1, support2)
    
    def _calculate_moving_average_support(self, data: List[Dict[str, Any]]) -> float:
        """
        Calculate support using moving averages.
        
        Args:
            data: Historical price data
            
        Returns:
            Moving average-based support level
        """
        if len(data) < 20:
            return data[-1]['low'] if data else 0.0
        
        # Calculate 20-period moving average of lows
        recent_lows = [candle['low'] for candle in data[-20:]]
        ma_low = sum(recent_lows) / len(recent_lows)
        
        # Calculate 50-period moving average if enough data
        if len(data) >= 50:
            longer_lows = [candle['low'] for candle in data[-50:]]
            ma_long = sum(longer_lows) / len(longer_lows)
            
            # Use the higher of the two as support
            return max(ma_low, ma_long)
        
        return ma_low
    
    def _calculate_trendline_support(self, data: List[Dict[str, Any]]) -> float:
        """
        Calculate support using trendline analysis.
        
        Args:
            data: Historical price data
            
        Returns:
            Trendline-based support level
        """
        if len(data) < 10:
            return data[-1]['low'] if data else 0.0
        
        # Find local minimums (swing lows)
        swing_lows = []
        
        for i in range(2, len(data) - 2):
            current_low = data[i]['low']
            
            # Check if it's a local minimum
            if (current_low < data[i-1]['low'] and 
                current_low < data[i-2]['low'] and
                current_low < data[i+1]['low'] and 
                current_low < data[i+2]['low']):
                
                swing_lows.append((i, current_low))
        
        if len(swing_lows) < 2:
            # Fallback to recent low
            recent_lows = [candle['low'] for candle in data[-10:]]
            return min(recent_lows)
        
        # Calculate trendline from last two swing lows
        x1, y1 = swing_lows[-2]
        x2, y2 = swing_lows[-1]
        
        # Calculate slope
        if x2 == x1:
            return y2  # Horizontal line
        
        slope = (y2 - y1) / (x2 - x1)
        
        # Project trendline to current point
        current_x = len(data) - 1
        projected_support = y2 + slope * (current_x - x2)
        
        # Ensure support is reasonable (not too far from current price)
        current_price = data[-1]['low']
        max_deviation = current_price * 0.1  # 10% max deviation
        
        if abs(projected_support - current_price) > max_deviation:
            return current_price * 0.98  # 2% below current price
        
        return max(projected_support, current_price * 0.9)  # At least 10% below current
    
    def _combine_support_levels(self, levels: List[float]) -> float:
        """
        Combine multiple support levels into a single level.
        
        Args:
            levels: List of support levels from different methods
            
        Returns:
            Combined support level
        """
        # Remove any invalid levels
        valid_levels = [level for level in levels if level > 0]
        
        if not valid_levels:
            return 0.0
        
        # Use weighted average (you can adjust weights based on method reliability)
        weights = [0.4, 0.3, 0.3]  # Pivot, MA, Trendline
        
        if len(valid_levels) != len(weights):
            # Simple average if lengths don't match
            return sum(valid_levels) / len(valid_levels)
        
        weighted_sum = sum(level * weight for level, weight in zip(valid_levels, weights))
        return weighted_sum
    
    def _calculate_confidence(self, levels: List[float]) -> float:
        """
        Calculate confidence based on convergence of different methods.
        
        Args:
            levels: List of support levels from different methods
            
        Returns:
            Confidence score (0.0 to 1.0)
        """
        valid_levels = [level for level in levels if level > 0]
        
        if len(valid_levels) == 0:
            return 0.0  # No valid levels = no confidence
        elif len(valid_levels) == 1:
            return 0.6  # Single method = moderate confidence
        
        # Calculate coefficient of variation (lower = more convergence)
        mean_level = sum(valid_levels) / len(valid_levels)
        
        # Guard against division by zero
        if mean_level <= 0:
            return 0.0
        
        variance = sum((level - mean_level) ** 2 for level in valid_levels) / len(valid_levels)
        std_dev = math.sqrt(variance)
        
        cv = std_dev / mean_level
        
        # Convert to confidence (inverse relationship)
        # cv of 0 = confidence of 1.0, cv of 0.1 = confidence of 0.5
        # Use more conservative scaling factor
        confidence = max(0.0, min(1.0, 1.0 - (cv * 3)))
        
        return confidence
    
    async def calculate_resistance_levels_for_position(self, symbol: str, timeframe: str, 
                                                      position_avg_price: float, position_type: str = "short") -> SupportLevelData:
        """
        Calculate resistance levels for position averaging (position-aware filtering).
        
        For SHORT positions: Returns resistance levels ABOVE the position average price
        For LONG positions: This method should not be used (use support instead)
        
        Args:
            symbol: Stock symbol to analyze
            timeframe: Timeframe for analysis (e.g., "1h", "4h", "1d")
            position_avg_price: Average price of the existing position
            position_type: Type of position ("short" or "long")
            
        Returns:
            SupportLevelData containing resistance levels relevant for position averaging
            
        Raises:
            MarketDataException: If resistance calculation fails
            ValueError: If inputs are invalid
        """
        # Input validation
        if not symbol or not symbol.strip():
            raise ValueError("Symbol cannot be empty")
        if not timeframe or not timeframe.strip():
            raise ValueError("Timeframe cannot be empty")
        if position_avg_price <= 0:
            raise ValueError("Position average price must be positive")
        if position_type not in ["short", "long"]:
            raise ValueError("Position type must be 'short' or 'long'")
        
        symbol = symbol.strip().upper()
        timeframe = timeframe.strip().lower()
        
        try:
            logger.debug(f"Calculating position-aware resistance levels for {symbol} on {timeframe}")
            logger.debug(f"Position: {position_type} @ ${position_avg_price:.2f}")
            
            # Get current market price for context
            try:
                current_price = await self._market_data.get_current_price(symbol)
                logger.debug(f"🔴 POSITION-AWARE RESISTANCE: {symbol} @ ${current_price:.2f} (position avg: ${position_avg_price:.2f})")
            except Exception as e:
                logger.warning(f"Could not get current price for {symbol}: {e}")
                current_price = None
            
            # Get historical data
            bars_data = await self._market_data.get_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                count=self._lookback_periods
            )
            
            if not bars_data:
                raise MarketDataException(f"No historical data available for {symbol}")
            
            # Convert dict data to bar objects
            bars = [BarData(bar_dict) for bar_dict in bars_data]
            
            # Calculate resistance levels using multiple methods
            resistance_levels = []
            
            # Method 1: Pivot Point Resistance
            if self._config.get_config("technical_analysis.resistance.calculation_methods.pivot_points", True):
                pivot_resistance = self._calculate_pivot_resistance_for_position(bars, position_avg_price, position_type)
                resistance_levels.extend(pivot_resistance)
            
            # Method 2: Moving Average Resistance
            if self._config.get_config("technical_analysis.resistance.calculation_methods.moving_averages", True):
                ma_resistance = self._calculate_moving_average_resistance_for_position(bars, position_avg_price, position_type)
                resistance_levels.extend(ma_resistance)
            
            # Method 3: Volume Profile Resistance
            if self._config.get_config("technical_analysis.resistance.calculation_methods.volume_profile", True):
                volume_resistance = self._calculate_volume_resistance_for_position(bars, position_avg_price, position_type)
                resistance_levels.extend(volume_resistance)
            
            # Filter and sort resistance levels using position-aware filtering
            filtered_levels = self._filter_resistance_levels_for_position(resistance_levels, position_avg_price, position_type)
            
            # Add position context logging
            if current_price is not None:
                above_avg = [level for level in filtered_levels if level.price > position_avg_price]
                below_avg = [level for level in filtered_levels if level.price <= position_avg_price]
                logger.info(f"🔴 POSITION RESISTANCE CONTEXT: {len(above_avg)} above avg ${position_avg_price:.2f}, {len(below_avg)} at/below avg")
            
            # Create resistance level data
            resistance_data = SupportLevelData(
                symbol=symbol,
                timeframe=timeframe,
                levels=filtered_levels,
                calculated_at=datetime.utcnow(),
                confidence=self._calculate_overall_confidence(filtered_levels)
            )
            
            # Enhanced logging
            self._log_level_summary(filtered_levels, symbol, f"resistance (for {position_type} position)", current_price)
            return resistance_data
            
        except Exception as e:
            logger.error(f"Failed to calculate position-aware resistance levels for {symbol}: {str(e)}")
            raise MarketDataException(f"Position-aware resistance calculation failed: {str(e)}")

    async def calculate_support_levels_for_position(self, symbol: str, timeframe: str, 
                                                   position_avg_price: float, position_type: str = "long") -> SupportLevelData:
        """
        Calculate support levels for position averaging (position-aware filtering).
        
        For LONG positions: Returns support levels BELOW the position average price
        For SHORT positions: This method should not be used (use resistance instead)
        
        Args:
            symbol: Stock symbol to analyze
            timeframe: Timeframe for analysis (e.g., "1h", "4h", "1d")
            position_avg_price: Average price of the existing position
            position_type: Type of position ("long" or "short")
            
        Returns:
            SupportLevelData containing support levels relevant for position averaging
        """
        # Input validation
        if not symbol or not symbol.strip():
            raise ValueError("Symbol cannot be empty")
        if not timeframe or not timeframe.strip():
            raise ValueError("Timeframe cannot be empty")
        if position_avg_price <= 0:
            raise ValueError("Position average price must be positive")
        if position_type not in ["short", "long"]:
            raise ValueError("Position type must be 'short' or 'long'")
        
        symbol = symbol.strip().upper()
        timeframe = timeframe.strip().lower()
        
        try:
            logger.debug(f"Calculating position-aware support levels for {symbol} on {timeframe}")
            logger.debug(f"Position: {position_type} @ ${position_avg_price:.2f}")
            
            # Get current market price for context
            try:
                current_price = await self._market_data.get_current_price(symbol)
                logger.debug(f"🟢 POSITION-AWARE SUPPORT: {symbol} @ ${current_price:.2f} (position avg: ${position_avg_price:.2f})")
            except Exception as e:
                logger.warning(f"Could not get current price for {symbol}: {e}")
                current_price = None
            
            # Get historical data
            bars_data = await self._market_data.get_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                count=self._lookback_periods
            )
            
            if not bars_data:
                raise MarketDataException(f"No historical data available for {symbol}")
            
            # Convert dict data to bar objects
            bars = [BarData(bar_dict) for bar_dict in bars_data]
            
            # Calculate support levels using multiple methods
            support_levels = []
            
            # Method 1: Pivot Point Support
            if self._config.get_config("technical_analysis.support.calculation_methods.pivot_points", True):
                pivot_support = self._calculate_pivot_support_levels_for_position(bars, position_avg_price, position_type)
                support_levels.extend(pivot_support)
            
            # Method 2: Moving Average Support
            if self._config.get_config("technical_analysis.support.calculation_methods.moving_averages", True):
                ma_support = self._calculate_moving_average_support_levels_for_position(bars, position_avg_price, position_type)
                support_levels.extend(ma_support)
            
            # Method 3: Volume Profile Support
            if self._config.get_config("technical_analysis.support.calculation_methods.volume_profile", True):
                volume_support = self._calculate_volume_support_levels_for_position(bars, position_avg_price, position_type)
                support_levels.extend(volume_support)
            
            # Filter and sort support levels using position-aware filtering
            filtered_levels = self._filter_support_levels_for_position(support_levels, position_avg_price, position_type)
            
            # Add position context logging
            if current_price is not None:
                below_avg = [level for level in filtered_levels if level.price < position_avg_price]
                above_avg = [level for level in filtered_levels if level.price >= position_avg_price]
                logger.info(f"🟢 POSITION SUPPORT CONTEXT: {len(below_avg)} below avg ${position_avg_price:.2f}, {len(above_avg)} at/above avg")
            
            # Create support level data
            support_data = SupportLevelData(
                symbol=symbol,
                timeframe=timeframe,
                levels=filtered_levels,
                calculated_at=datetime.utcnow(),
                confidence=self._calculate_overall_confidence(filtered_levels)
            )
            
            # Enhanced logging
            self._log_level_summary(filtered_levels, symbol, f"support (for {position_type} position)", current_price)
            return support_data
            
        except Exception as e:
            logger.error(f"Failed to calculate position-aware support levels for {symbol}: {str(e)}")
            raise MarketDataException(f"Position-aware support calculation failed: {str(e)}")
        """
        Calculate resistance levels for a symbol.
        
        Args:
            symbol: Stock symbol to analyze
            timeframe: Timeframe for analysis (e.g., "1h", "4h", "1d")
            
        Returns:
            SupportLevelData containing resistance levels
            
        Raises:
            MarketDataException: If resistance calculation fails
            ValueError: If inputs are invalid
        """
        # Input validation
        if not symbol or not symbol.strip():
            raise ValueError("Symbol cannot be empty")
        if not timeframe or not timeframe.strip():
            raise ValueError("Timeframe cannot be empty")
        
        symbol = symbol.strip().upper()
        timeframe = timeframe.strip().lower()
        
        try:
            # Clean up cache before proceeding
            self._cleanup_expired_cache()
            # Check cache first
            cache_key = f"{symbol}_{timeframe}_resistance"
            if self._is_cache_valid(cache_key):
                logger.debug(f"Using cached resistance levels for {symbol}")
                return self._resistance_cache[cache_key]
            
            logger.debug(f"Calculating resistance levels for {symbol} on {timeframe}")
            
            # Get current market price for context
            try:
                current_price = await self._market_data.get_current_price(symbol)
                logger.debug(f"🔴 RESISTANCE CALCULATION: {symbol} @ ${current_price:.2f} ({timeframe})")
            except Exception as e:
                logger.warning(f"Could not get current price for {symbol}: {e}")
                current_price = None
            
            # Get historical data
            bars_data = await self._market_data.get_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                count=self._lookback_periods
            )
            
            if not bars_data:
                raise MarketDataException(f"No historical data available for {symbol}")
            
            # Convert dict data to bar objects with necessary attributes
            bars = [BarData(bar_dict) for bar_dict in bars_data]
            
            # Calculate resistance levels using multiple methods
            resistance_levels = []
            
            # Method 1: Pivot Point Resistance
            if self._config.get_config("technical_analysis.resistance.calculation_methods.pivot_points", True):
                pivot_resistance = self._calculate_pivot_resistance(bars)
                resistance_levels.extend(pivot_resistance)
            
            # Method 2: Moving Average Resistance
            if self._config.get_config("technical_analysis.resistance.calculation_methods.moving_averages", True):
                ma_resistance = self._calculate_moving_average_resistance(bars)
                resistance_levels.extend(ma_resistance)
            
            # Method 3: Volume Profile Resistance
            if self._config.get_config("technical_analysis.resistance.calculation_methods.volume_profile", True):
                volume_resistance = self._calculate_volume_resistance(bars)
                resistance_levels.extend(volume_resistance)
            
            # Method 4: Fibonacci Extension Resistance
            if self._config.get_config("technical_analysis.resistance.calculation_methods.fibonacci_extensions", True):
                fib_resistance = self._calculate_fibonacci_resistance(bars)
                resistance_levels.extend(fib_resistance)
            
            # Filter and sort resistance levels
            filtered_levels = self._filter_resistance_levels(resistance_levels, bars[-1].close)
            
            # Add market context logging if we have current price
            if current_price is not None:
                above_price = [level for level in filtered_levels if level.price > current_price]
                below_price = [level for level in filtered_levels if level.price <= current_price]
                logger.debug(f"🔴 RESISTANCE CONTEXT: {len(above_price)} above ${current_price:.2f}, {len(below_price)} at/below")
            
            # Create resistance level data
            resistance_data = SupportLevelData(
                symbol=symbol,
                timeframe=timeframe,
                levels=filtered_levels,
                calculated_at=datetime.utcnow(),
                confidence=self._calculate_overall_confidence(filtered_levels)
            )
            
            # Cache the results
            self._resistance_cache[cache_key] = resistance_data
            self._cache_expiry[cache_key] = datetime.utcnow() + self._cache_duration
            
            # Enhanced logging using centralized method
            self._log_level_summary(filtered_levels, symbol, "resistance", current_price)
            return resistance_data
            
        except Exception as e:
            logger.error(f"Failed to calculate resistance levels for {symbol}: {str(e)}")
            raise MarketDataException(f"Resistance calculation failed: {str(e)}")

    def _calculate_pivot_resistance(self, bars: List[BarData]) -> List[SupportLevel]:
        """Calculate resistance levels using pivot points."""
        resistance_levels = []
        
        if len(bars) < 3:
            logger.warning("Insufficient data for pivot resistance calculation")
            return resistance_levels
        
        try:
            # Calculate traditional pivot points
            last_bar = bars[-1]
            high = last_bar.high
            low = last_bar.low
            close = last_bar.close
            
            # Validate data
            if high <= 0 or low <= 0 or close <= 0:
                logger.warning("Invalid price data for pivot calculation")
                return resistance_levels
            
            pivot = (high + low + close) / 3
            r1 = (2 * pivot) - low  # First resistance
            r2 = pivot + (high - low)  # Second resistance
            r3 = high + 2 * (pivot - low)  # Third resistance
            
            current_price = close
            current_time = datetime.utcnow()
            
            # Only include resistance levels above current price
            resistance_data = [
                (r1, 0.8, "pivot_r1"),
                (r2, 0.7, "pivot_r2"),
                (r3, 0.6, "pivot_r3")
            ]
            
            for price, confidence, method in resistance_data:
                if price > 0 and price > current_price:
                    resistance_levels.append(SupportLevel(
                        price=price,
                        confidence=confidence,
                        method=method,
                        touches=1,
                        last_touch=current_time,
                        calculated_at=current_time
                    ))
        
        except Exception as e:
            logger.error(f"Error in pivot resistance calculation: {e}")
        
        return resistance_levels

    def _calculate_moving_average_resistance(self, bars) -> List[SupportLevel]:
        """Calculate resistance levels using moving averages."""
        resistance_levels = []
        
        if len(bars) < 50:
            return resistance_levels
        
        closes = [bar.close for bar in bars]
        current_price = closes[-1]
        
        # Calculate different period moving averages
        periods = [20, 50, 100, 200]
        
        for period in periods:
            if len(closes) >= period:
                ma = sum(closes[-period:]) / period
                
                # If MA is above current price, it acts as resistance
                if ma > current_price:
                    # Calculate confidence based on how recently price was below MA
                    confidence = 0.6
                    touches = 0
                    
                    # Count touches near this MA level
                    tolerance = ma * 0.002  # 0.2% tolerance
                    for bar in bars[-20:]:  # Check last 20 bars
                        if abs(bar.high - ma) <= tolerance:
                            touches += 1
                    
                    confidence = min(0.9, 0.5 + (touches * 0.1))
                    
                    resistance_levels.append(SupportLevel(
                        price=ma,
                        confidence=confidence,
                        method=f"ma_{period}",
                        touches=touches,
                        last_touch=datetime.utcnow()
                    ))
        
        return resistance_levels

    def _calculate_volume_resistance(self, bars) -> List[SupportLevel]:
        """Calculate resistance levels using volume profile analysis."""
        resistance_levels = []
        
        if len(bars) < 20:
            return resistance_levels
        
        # Create price levels and volume mapping
        price_volume_map = {}
        current_price = bars[-1].close
        
        for bar in bars[-50:]:  # Use last 50 bars
            # Create price bins
            price_range = (bar.high - bar.low) / 10  # Divide each bar into 10 price levels
            
            for i in range(10):
                price_level = bar.low + (i * price_range)
                if price_level not in price_volume_map:
                    price_volume_map[price_level] = 0
                price_volume_map[price_level] += bar.volume / 10
        
        # Find high volume areas above current price
        sorted_levels = sorted(price_volume_map.items(), key=lambda x: x[1], reverse=True)
        
        for price, volume in sorted_levels[:5]:  # Top 5 volume levels
            if price > current_price:
                # Calculate confidence based on volume relative to average
                avg_volume = sum(price_volume_map.values()) / len(price_volume_map)
                confidence = min(0.9, 0.4 + (volume / avg_volume) * 0.1)
                
                resistance_levels.append(SupportLevel(
                    price=price,
                    confidence=confidence,
                    method="volume_profile",
                    touches=1,
                    last_touch=datetime.utcnow()
                ))
        
        return resistance_levels

    def _calculate_fibonacci_resistance(self, bars) -> List[SupportLevel]:
        """Calculate resistance levels using Fibonacci extensions."""
        resistance_levels = []
        
        if len(bars) < 20:
            return resistance_levels
        
        # Find recent swing points
        swing_high = max(bar.high for bar in bars[-20:])
        swing_low = min(bar.low for bar in bars[-20:])
        current_price = bars[-1].close
        
        # Calculate Fibonacci extension levels
        fib_range = swing_high - swing_low
        fib_levels = [1.272, 1.414, 1.618, 2.0, 2.618]  # Extension levels
        
        for fib_ratio in fib_levels:
            fib_resistance = swing_high + (fib_range * (fib_ratio - 1))
            
            if fib_resistance > current_price:
                confidence = 0.8 - (fib_ratio - 1.272) * 0.1  # Decreasing confidence for higher levels
                
                resistance_levels.append(SupportLevel(
                    price=fib_resistance,
                    confidence=max(0.4, confidence),
                    method=f"fibonacci_{fib_ratio}",
                    touches=1,
                    last_touch=datetime.utcnow()
                ))
        
        return resistance_levels

    def _filter_resistance_levels(self, levels: List[SupportLevel], current_price: float) -> List[SupportLevel]:
        """
        Filter and consolidate resistance levels with robust edge case handling.
        
        This method handles scenarios where bot was offline and market conditions changed,
        including cases where calculated resistance might be below current price due to gaps.
        """
        if not levels:
            return []
        
        # Filter by confidence first
        min_confidence = self._config.get_config("technical_analysis.resistance.min_confidence", CalculationConstants.DEFAULT_MIN_CONFIDENCE)
        filtered = [level for level in levels if level.confidence >= min_confidence]
        
        # EDGE CASE HANDLING: Check if we have reasonable resistance levels
        levels_above_current = [level for level in filtered if level.price > current_price]
        levels_below_current = [level for level in filtered if level.price <= current_price]
        
        # Log the situation for debugging
        if levels_below_current and not levels_above_current:
            logger.warning(f"⚠️ EDGE CASE: All resistance levels ({len(levels_below_current)}) are below current price ${current_price:.2f}")
            logger.warning("This can happen after bot shutdown with market gaps. Applying recovery logic...")
        
        # RECOVERY STRATEGY 1: Try to salvage usable levels
        if levels_above_current:
            # Normal case: we have resistance above current price
            filtered = levels_above_current
            logger.debug(f"✅ Found {len(filtered)} resistance levels above current price ${current_price:.2f}")
        else:
            # EDGE CASE: No resistance above current price
            logger.warning(f"🔧 RECOVERY MODE: No resistance above ${current_price:.2f}, applying fallback strategies")
            
            # Strategy A: Use levels slightly below current price if they're very recent and close
            recent_threshold = datetime.utcnow() - timedelta(minutes=30)  # Last 30 minutes
            close_levels = [
                level for level in levels_below_current 
                if (level.calculated_at > recent_threshold and 
                    abs(level.price - current_price) / current_price < 0.02)  # Within 2%
            ]
            
            if close_levels:
                logger.info(f"🔧 Using {len(close_levels)} recent resistance levels close to current price")
                filtered = close_levels
            else:
                # Strategy B: Create synthetic resistance levels above current price
                logger.warning("🔧 Creating synthetic resistance levels for recovery")
                filtered = self._create_synthetic_resistance_levels(current_price)
        
        # Remove duplicate/very close levels
        consolidated = self._consolidate_levels(filtered, current_price)
        
        # Sort by proximity to current price and confidence
        consolidated.sort(key=lambda x: (abs(x.price - current_price), -x.confidence))
        
        # Return top 5 most relevant resistance levels
        result = consolidated[:5]
        
        # Final validation and logging
        if result:
            prices = [level.price for level in result]
            logger.debug(f"🔴 Final resistance levels: {[f'${p:.2f}' for p in prices]}")
        else:
            logger.error("❌ No valid resistance levels found after filtering and recovery")
        
        return result

    def _filter_support_levels(self, levels: List[SupportLevel], current_price: float) -> List[SupportLevel]:
        """
        Filter and consolidate support levels with robust edge case handling.
        
        Handles scenarios where bot was offline and market conditions changed.
        """
        if not levels:
            return []
        
        # Filter by confidence first
        min_confidence = self._config.get_config("technical_analysis.support.min_confidence", CalculationConstants.DEFAULT_MIN_CONFIDENCE)
        filtered = [level for level in levels if level.confidence >= min_confidence]
        
        # EDGE CASE HANDLING: Check if we have reasonable support levels
        levels_below_current = [level for level in filtered if level.price < current_price]
        levels_above_current = [level for level in filtered if level.price >= current_price]
        
        # Log the situation for debugging
        if levels_above_current and not levels_below_current:
            logger.warning(f"⚠️ EDGE CASE: All support levels ({len(levels_above_current)}) are above current price ${current_price:.2f}")
            logger.warning("This can happen after bot shutdown with market gaps. Applying recovery logic...")
        
        # RECOVERY STRATEGY 1: Try to salvage usable levels
        if levels_below_current:
            # Normal case: we have support below current price
            filtered = levels_below_current
            logger.debug(f"✅ Found {len(filtered)} support levels below current price ${current_price:.2f}")
        else:
            # EDGE CASE: No support below current price
            logger.warning(f"🔧 RECOVERY MODE: No support below ${current_price:.2f}, applying fallback strategies")
            
            # Strategy A: Use levels slightly above current price if they're very recent and close
            recent_threshold = datetime.utcnow() - timedelta(minutes=30)
            close_levels = [
                level for level in levels_above_current 
                if (level.calculated_at > recent_threshold and 
                    abs(level.price - current_price) / current_price < 0.02)  # Within 2%
            ]
            
            if close_levels:
                logger.info(f"🔧 Using {len(close_levels)} recent support levels close to current price")
                filtered = close_levels
            else:
                # Strategy B: Create synthetic support levels below current price
                logger.warning("🔧 Creating synthetic support levels for recovery")
                filtered = self._create_synthetic_support_levels(current_price)
        
        # Remove duplicate/very close levels
        consolidated = self._consolidate_levels(filtered, current_price)
        
        # Sort by proximity to current price and confidence (support = highest first)
        consolidated.sort(key=lambda x: (current_price - x.price, -x.confidence))
        
        # Return top 5 most relevant support levels
        result = consolidated[:5]
        
        # Final validation and logging
        if result:
            prices = [level.price for level in result]
            logger.debug(f"🟢 Final support levels: {[f'${p:.2f}' for p in prices]}")
        else:
            logger.error("❌ No valid support levels found after filtering and recovery")
        
        return result

    def _create_synthetic_resistance_levels(self, current_price: float) -> List[SupportLevel]:
        """
        Create synthetic resistance levels when normal calculations fail.
        
        This is a fallback mechanism for edge cases like market gaps or stale data.
        """
        synthetic_levels = []
        current_time = datetime.utcnow()
        
        # Create resistance levels at psychological levels above current price
        resistance_offsets = [0.01, 0.02, 0.03, 0.05, 0.08]  # 1%, 2%, 3%, 5%, 8% above
        
        for i, offset in enumerate(resistance_offsets):
            resistance_price = current_price * (1 + offset)
            
            # Decrease confidence for levels further away
            confidence = 0.8 - (i * 0.1)  # Start at 0.8, decrease by 0.1 each level
            confidence = max(0.4, confidence)  # Minimum 0.4 confidence
            
            synthetic_levels.append(SupportLevel(
                price=resistance_price,
                confidence=confidence,
                method="synthetic_recovery",
                touches=0,  # Synthetic levels have no historical touches
                last_touch=current_time,
                calculated_at=current_time
            ))
        
        logger.info(f"🔧 Created {len(synthetic_levels)} synthetic resistance levels above ${current_price:.2f}")
        return synthetic_levels

    def _create_synthetic_support_levels(self, current_price: float) -> List[SupportLevel]:
        """
        Create synthetic support levels when normal calculations fail.
        
        This is a fallback mechanism for edge cases like market gaps or stale data.
        """
        synthetic_levels = []
        current_time = datetime.utcnow()
        
        # Create support levels at psychological levels below current price
        support_offsets = [0.01, 0.02, 0.03, 0.05, 0.08]  # 1%, 2%, 3%, 5%, 8% below
        
        for i, offset in enumerate(support_offsets):
            support_price = current_price * (1 - offset)
            
            # Decrease confidence for levels further away
            confidence = 0.8 - (i * 0.1)  # Start at 0.8, decrease by 0.1 each level
            confidence = max(0.4, confidence)  # Minimum 0.4 confidence
            
            synthetic_levels.append(SupportLevel(
                price=support_price,
                confidence=confidence,
                method="synthetic_recovery",
                touches=0,  # Synthetic levels have no historical touches
                last_touch=current_time,
                calculated_at=current_time
            ))
        
        logger.info(f"🔧 Created {len(synthetic_levels)} synthetic support levels below ${current_price:.2f}")
        return synthetic_levels

    def _consolidate_levels(self, levels: List[SupportLevel], reference_price: float) -> List[SupportLevel]:
        """
        Consolidate duplicate or very close levels with improved logic.
        
        Args:
            levels: List of support/resistance levels to consolidate
            reference_price: Reference price for calculating tolerance
            
        Returns:
            Consolidated list of levels
        """
        if not levels:
            return []
        
        consolidated = []
        tolerance = reference_price * CalculationConstants.DEFAULT_CONSOLIDATION_TOLERANCE
        
        # Sort levels by price for consistent processing
        sorted_levels = sorted(levels, key=lambda x: x.price)
        
        for level in sorted_levels:
            is_duplicate = False
            
            # Check against existing consolidated levels
            for i, existing in enumerate(consolidated):
                if abs(level.price - existing.price) <= tolerance:
                    # Found a duplicate - keep the one with higher confidence
                    if level.confidence > existing.confidence:
                        consolidated[i] = level
                    elif level.confidence == existing.confidence:
                        # Same confidence - prefer the one with more touches
                        if level.touches > existing.touches:
                            consolidated[i] = level
                        elif level.touches == existing.touches:
                            # Same touches - prefer more recent calculation
                            if level.calculated_at > existing.calculated_at:
                                consolidated[i] = level
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                consolidated.append(level)
        
        return consolidated

    def _calculate_pivot_resistance_for_position(self, bars: List[BarData], position_avg_price: float, position_type: str) -> List[SupportLevel]:
        """Calculate resistance levels using pivot points for position averaging."""
        resistance_levels = []
        
        if len(bars) < 3:
            logger.warning("Insufficient data for pivot resistance calculation")
            return resistance_levels
        
        try:
            last_bar = bars[-1]
            high = last_bar.high
            low = last_bar.low
            close = last_bar.close
            
            if high <= 0 or low <= 0 or close <= 0:
                logger.warning("Invalid price data for pivot calculation")
                return resistance_levels
            
            pivot = (high + low + close) / 3
            r1 = (2 * pivot) - low
            r2 = pivot + (high - low)
            r3 = high + 2 * (pivot - low)
            
            current_time = datetime.utcnow()
            
            # For SHORT positions: only include resistance ABOVE position average price
            # For LONG positions: include all resistance levels (not typically used for averaging)
            resistance_data = [
                (r1, 0.8, "pivot_r1"),
                (r2, 0.7, "pivot_r2"),
                (r3, 0.6, "pivot_r3")
            ]
            
            for price, confidence, method in resistance_data:
                if price > 0:
                    if position_type == "short" and price > position_avg_price:
                        resistance_levels.append(SupportLevel(
                            price=price,
                            confidence=confidence,
                            method=method,
                            touches=1,
                            last_touch=current_time,
                            calculated_at=current_time
                        ))
                    elif position_type == "long":  # Include all for long positions
                        resistance_levels.append(SupportLevel(
                            price=price,
                            confidence=confidence,
                            method=method,
                            touches=1,
                            last_touch=current_time,
                            calculated_at=current_time
                        ))
        
        except Exception as e:
            logger.error(f"Error in position-aware pivot resistance calculation: {e}")
        
        return resistance_levels

    def _calculate_moving_average_resistance_for_position(self, bars: List[BarData], position_avg_price: float, position_type: str) -> List[SupportLevel]:
        """Calculate resistance levels using moving averages for position averaging."""
        resistance_levels = []
        
        if len(bars) < 50:
            return resistance_levels
        
        closes = [bar.close for bar in bars]
        periods = CalculationConstants.MA_PERIODS
        
        for period in periods:
            if len(closes) >= period:
                ma = sum(closes[-period:]) / period
                
                # For SHORT positions: only include MA levels ABOVE position average price
                include_level = False
                if position_type == "short" and ma > position_avg_price:
                    include_level = True
                elif position_type == "long":  # Include all for long positions
                    include_level = True
                
                if include_level and ma > 0:
                    confidence = 0.6
                    touches = 0
                    
                    # Count touches near this MA level
                    tolerance = ma * CalculationConstants.DEFAULT_PRICE_TOLERANCE
                    for bar in bars[-20:]:
                        if abs(bar.high - ma) <= tolerance:
                            touches += 1
                    
                    confidence = min(0.9, 0.5 + (touches * 0.1))
                    
                    resistance_levels.append(SupportLevel(
                        price=ma,
                        confidence=confidence,
                        method=f"ma_{period}",
                        touches=touches,
                        last_touch=datetime.utcnow(),
                        calculated_at=datetime.utcnow()
                    ))
        
        return resistance_levels

    def _calculate_volume_resistance_for_position(self, bars: List[BarData], position_avg_price: float, position_type: str) -> List[SupportLevel]:
        """Calculate resistance levels using volume profile for position averaging."""
        resistance_levels = []
        
        if len(bars) < 20:
            return resistance_levels
        
        # Create price levels and volume mapping
        price_volume_map = {}
        
        for bar in bars[-50:]:
            price_range = (bar.high - bar.low) / 10
            
            for i in range(10):
                price_level = bar.low + (i * price_range)
                if price_level not in price_volume_map:
                    price_volume_map[price_level] = 0
                price_volume_map[price_level] += bar.volume / 10
        
        # Find high volume areas above position average price (for short positions)
        sorted_levels = sorted(price_volume_map.items(), key=lambda x: x[1], reverse=True)
        
        for price, volume in sorted_levels[:5]:
            include_level = False
            if position_type == "short" and price > position_avg_price:
                include_level = True
            elif position_type == "long":  # Include all for long positions
                include_level = True
            
            if include_level:
                avg_volume = sum(price_volume_map.values()) / len(price_volume_map)
                confidence = min(0.9, 0.4 + (volume / avg_volume) * 0.1)
                
                resistance_levels.append(SupportLevel(
                    price=price,
                    confidence=confidence,
                    method="volume_profile",
                    touches=1,
                    last_touch=datetime.utcnow(),
                    calculated_at=datetime.utcnow()
                ))
        
        return resistance_levels

    def _filter_resistance_levels_for_position(self, levels: List[SupportLevel], position_avg_price: float, position_type: str) -> List[SupportLevel]:
        """Filter resistance levels based on position requirements."""
        if not levels:
            return []
        
        # Filter by confidence
        min_confidence = self._config.get_config("technical_analysis.resistance.min_confidence", CalculationConstants.DEFAULT_MIN_CONFIDENCE)
        filtered = [level for level in levels if level.confidence >= min_confidence]
        
        # Position-aware filtering
        if position_type == "short":
            # For short positions: only keep resistance levels ABOVE position average price
            filtered = [level for level in filtered if level.price > position_avg_price]
        # For long positions, keep all levels (no additional filtering needed)
        
        # Remove duplicate/very close levels
        consolidated = []
        tolerance = position_avg_price * CalculationConstants.DEFAULT_CONSOLIDATION_TOLERANCE
        
        for level in sorted(filtered, key=lambda x: x.price):
            is_duplicate = False
            for existing in consolidated:
                if abs(level.price - existing.price) <= tolerance:
                    if level.confidence > existing.confidence:
                        consolidated.remove(existing)
                        consolidated.append(level)
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                consolidated.append(level)
        
        # Sort by proximity to position average price and confidence
        consolidated.sort(key=lambda x: (abs(x.price - position_avg_price), -x.confidence))
        
        return consolidated[:5]

    def _calculate_pivot_support_levels_for_position(self, bars: List[BarData], position_avg_price: float, position_type: str) -> List[SupportLevel]:
        """Calculate support levels using pivot points for position averaging."""
        support_levels = []
        
        if len(bars) < 3:
            logger.warning("Insufficient data for pivot support calculation")
            return support_levels
        
        try:
            last_bar = bars[-1]
            high = last_bar.high
            low = last_bar.low
            close = last_bar.close
            
            if high <= 0 or low <= 0 or close <= 0:
                logger.warning("Invalid price data for pivot calculation")
                return support_levels
            
            pivot = (high + low + close) / 3
            s1 = (2 * pivot) - high
            s2 = pivot - (high - low)
            s3 = low - 2 * (high - pivot)
            
            current_time = datetime.utcnow()
            
            # For LONG positions: only include support BELOW position average price
            support_data = [
                (s1, 0.8, "pivot_s1"),
                (s2, 0.7, "pivot_s2"),
                (s3, 0.6, "pivot_s3")
            ]
            
            for price, confidence, method in support_data:
                if price > 0:
                    if position_type == "long" and price < position_avg_price:
                        support_levels.append(SupportLevel(
                            price=price,
                            confidence=confidence,
                            method=method,
                            touches=1,
                            last_touch=current_time,
                            calculated_at=current_time
                        ))
                    elif position_type == "short":  # Include all for short positions
                        support_levels.append(SupportLevel(
                            price=price,
                            confidence=confidence,
                            method=method,
                            touches=1,
                            last_touch=current_time,
                            calculated_at=current_time
                        ))
        
        except Exception as e:
            logger.error(f"Error in position-aware pivot support calculation: {e}")
        
        return support_levels

    def _calculate_moving_average_support_levels_for_position(self, bars: List[BarData], position_avg_price: float, position_type: str) -> List[SupportLevel]:
        """Calculate support levels using moving averages for position averaging."""
        support_levels = []
        
        if len(bars) < 20:
            logger.warning("Insufficient data for moving average support calculation")
            return support_levels
        
        try:
            closes = [bar.close for bar in bars]
            current_time = datetime.utcnow()
            periods = CalculationConstants.MA_PERIODS
            
            for period in periods:
                if len(closes) >= period:
                    ma = sum(closes[-period:]) / period
                    
                    # For LONG positions: only include MA levels BELOW position average price
                    include_level = False
                    if position_type == "long" and ma < position_avg_price:
                        include_level = True
                    elif position_type == "short":  # Include all for short positions
                        include_level = True
                    
                    if include_level and ma > 0:
                        confidence = self._calculate_ma_confidence(bars, ma, period)
                        
                        if confidence >= self._min_confidence:
                            support_levels.append(SupportLevel(
                                price=ma,
                                confidence=confidence,
                                method=f"ma_{period}",
                                touches=self._count_ma_touches(bars, ma),
                                last_touch=current_time,
                                calculated_at=current_time
                            ))
        
        except Exception as e:
            logger.error(f"Error in position-aware moving average support calculation: {e}")
        
        return support_levels

    def _calculate_volume_support_levels_for_position(self, bars: List[BarData], position_avg_price: float, position_type: str) -> List[SupportLevel]:
        """Calculate support levels using volume profile for position averaging."""
        support_levels = []
        
        if len(bars) < 20:
            return support_levels
        
        # Create price levels and volume mapping
        price_volume_map = {}
        
        for bar in bars[-50:]:
            price_range = (bar.high - bar.low) / 10
            
            for i in range(10):
                price_level = bar.low + (i * price_range)
                if price_level not in price_volume_map:
                    price_volume_map[price_level] = 0
                price_volume_map[price_level] += bar.volume / 10
        
        # Find high volume areas below position average price (for long positions)
        sorted_levels = sorted(price_volume_map.items(), key=lambda x: x[1], reverse=True)
        
        for price, volume in sorted_levels[:5]:
            include_level = False
            if position_type == "long" and price < position_avg_price:
                include_level = True
            elif position_type == "short":  # Include all for short positions
                include_level = True
            
            if include_level:
                avg_volume = sum(price_volume_map.values()) / len(price_volume_map)
                confidence = min(0.9, 0.4 + (volume / avg_volume) * 0.1)
                
                support_levels.append(SupportLevel(
                    price=price,
                    confidence=confidence,
                    method="volume_profile",
                    touches=1,
                    last_touch=datetime.utcnow(),
                    calculated_at=datetime.utcnow()
                ))
        
        return support_levels

    def _filter_support_levels_for_position(self, levels: List[SupportLevel], position_avg_price: float, position_type: str) -> List[SupportLevel]:
        """Filter support levels based on position requirements."""
        if not levels:
            return []
        
        # Filter by confidence first
        min_confidence = self._config.get_config("technical_analysis.support.min_confidence", CalculationConstants.DEFAULT_MIN_CONFIDENCE)
        filtered = [level for level in levels if level.confidence >= min_confidence]
        
        # Position-aware filtering with more intelligent logic
        if position_type == "long":
            # For long positions: We want support levels that make sense for DCA
            # Keep levels that are below the HIGHER of (current_price, position_avg_price)
            # This ensures we find support levels suitable for averaging down
            
            # Get the reference price - use position average as the ceiling
            # This prevents finding "support" above our buy price, which would be resistance
            reference_price = position_avg_price
            
            # Keep support levels below the position average price (logical for DCA)
            # But be less restrictive - allow levels within 20% of position average
            min_support_level = reference_price * 0.80  # Support can be up to 20% below position
            max_support_level = reference_price * 0.98  # Support should be at least 2% below position
            
            filtered = [
                level for level in filtered 
                if min_support_level <= level.price <= max_support_level
            ]
            
            # If we still have no levels, relax the constraint and allow any level below position average
            if not filtered:
                logger.debug(f"🔧 Relaxing support constraints for {position_type} position below ${reference_price:.2f}")
                filtered = [level for level in levels if level.confidence >= min_confidence and level.price < reference_price]
                
        elif position_type == "short":
            # For short positions: We want resistance levels above position average for DCA
            reference_price = position_avg_price
            
            # Keep resistance levels above the position average price (logical for short DCA)
            min_resistance_level = reference_price * 1.02  # Resistance should be at least 2% above position
            max_resistance_level = reference_price * 1.20  # Resistance can be up to 20% above position
            
            filtered = [
                level for level in filtered 
                if min_resistance_level <= level.price <= max_resistance_level
            ]
            
            # If we still have no levels, relax the constraint
            if not filtered:
                logger.debug(f"🔧 Relaxing resistance constraints for {position_type} position above ${reference_price:.2f}")
                filtered = [level for level in levels if level.confidence >= min_confidence and level.price > reference_price]
        
        # Remove duplicate/very close levels
        consolidated = []
        tolerance = position_avg_price * CalculationConstants.DEFAULT_CONSOLIDATION_TOLERANCE
        
        for level in sorted(filtered, key=lambda x: x.price, reverse=True):
            is_duplicate = False
            for existing in consolidated:
                if abs(level.price - existing.price) <= tolerance:
                    if level.confidence > existing.confidence:
                        consolidated.remove(existing)
                        consolidated.append(level)
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                consolidated.append(level)
        
        # Sort by proximity to position average price and confidence
        consolidated.sort(key=lambda x: (abs(position_avg_price - x.price), -x.confidence))
        
        return consolidated[:5]

    async def calculate_resistance_levels(self, symbol: str, timeframe: str) -> SupportLevelData:
        """
        Calculate resistance levels for a symbol (original method, kept for backward compatibility).
        
        Note: For position averaging, use calculate_resistance_levels_for_position() instead
        as it provides position-aware filtering.
        
        Args:
            symbol: Stock symbol to analyze
            timeframe: Timeframe for analysis (e.g., "1h", "4h", "1d")
            
        Returns:
            SupportLevelData containing resistance levels
        """
        # Input validation
        if not symbol or not symbol.strip():
            raise ValueError("Symbol cannot be empty")
        if not timeframe or not timeframe.strip():
            raise ValueError("Timeframe cannot be empty")
        
        symbol = symbol.strip().upper()
        timeframe = timeframe.strip().lower()
        
        try:
            # Clean up cache before proceeding
            self._cleanup_expired_cache()
            # Check cache first
            cache_key = f"{symbol}_{timeframe}_resistance"
            if self._is_cache_valid(cache_key):
                logger.debug(f"Using cached resistance levels for {symbol}")
                return self._resistance_cache[cache_key]
            
            logger.debug(f"Calculating resistance levels for {symbol} on {timeframe}")
            
            # Get current market price for context
            try:
                current_price = await self._market_data.get_current_price(symbol)
                logger.debug(f"🔴 RESISTANCE CALCULATION: {symbol} @ ${current_price:.2f} ({timeframe})")
            except Exception as e:
                logger.warning(f"Could not get current price for {symbol}: {e}")
                current_price = None
            
            # Get historical data
            bars_data = await self._market_data.get_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                count=self._lookback_periods
            )
            
            if not bars_data:
                raise MarketDataException(f"No historical data available for {symbol}")
            
            # Convert dict data to bar objects with necessary attributes
            bars = [BarData(bar_dict) for bar_dict in bars_data]
            
            # Calculate resistance levels using multiple methods
            resistance_levels = []
            
            # Method 1: Pivot Point Resistance
            if self._config.get_config("technical_analysis.resistance.calculation_methods.pivot_points", True):
                pivot_resistance = self._calculate_pivot_resistance(bars)
                resistance_levels.extend(pivot_resistance)
            
            # Method 2: Moving Average Resistance
            if self._config.get_config("technical_analysis.resistance.calculation_methods.moving_averages", True):
                ma_resistance = self._calculate_moving_average_resistance(bars)
                resistance_levels.extend(ma_resistance)
            
            # Method 3: Volume Profile Resistance
            if self._config.get_config("technical_analysis.resistance.calculation_methods.volume_profile", True):
                volume_resistance = self._calculate_volume_resistance(bars)
                resistance_levels.extend(volume_resistance)
            
            # Method 4: Fibonacci Extension Resistance
            if self._config.get_config("technical_analysis.resistance.calculation_methods.fibonacci_extensions", True):
                fib_resistance = self._calculate_fibonacci_resistance(bars)
                resistance_levels.extend(fib_resistance)
            
            # Filter and sort resistance levels
            filtered_levels = self._filter_resistance_levels(resistance_levels, bars[-1].close)
            
            # Add market context logging if we have current price
            if current_price is not None:
                above_price = [level for level in filtered_levels if level.price > current_price]
                below_price = [level for level in filtered_levels if level.price <= current_price]
                logger.debug(f"🔴 RESISTANCE CONTEXT: {len(above_price)} above ${current_price:.2f}, {len(below_price)} at/below")
            
            # Create resistance level data
            resistance_data = SupportLevelData(
                symbol=symbol,
                timeframe=timeframe,
                levels=filtered_levels,
                calculated_at=datetime.utcnow(),
                confidence=self._calculate_overall_confidence(filtered_levels)
            )
            
            # Cache the results
            self._resistance_cache[cache_key] = resistance_data
            self._cache_expiry[cache_key] = datetime.utcnow() + self._cache_duration
            
            # Enhanced logging using centralized method
            self._log_level_summary(filtered_levels, symbol, "resistance", current_price)
            return resistance_data
            
        except Exception as e:
            logger.error(f"Failed to calculate resistance levels for {symbol}: {str(e)}")
            raise MarketDataException(f"Resistance calculation failed: {str(e)}")

    def _is_cache_valid(self, cache_key: str) -> bool:
        """
        Enhanced cache validation with market condition awareness.
        
        Handles edge cases like bot restarts, market gaps, and stale data.
        
        Args:
            cache_key: The cache key to check
            
        Returns:
            True if cache is valid, False otherwise
        """
        if cache_key not in self._cache_expiry:
            return False
        
        current_time = datetime.utcnow()
        expiry_time = self._cache_expiry[cache_key]
        
        # Basic expiry check
        if current_time >= expiry_time:
            logger.debug(f"🗑️ Cache expired for key: {cache_key}")
            return False
        
        # Additional staleness checks for edge cases
        try:
            # Check if market conditions have changed significantly
            # (This helps detect bot restarts and market gaps)
            cache_age_minutes = (current_time - (expiry_time - self._cache_duration)).total_seconds() / 60
            
            # During trading hours: be more aggressive about cache invalidation
            if self._is_trading_hours():
                max_age_minutes = 5  # 5 minutes during trading
                if cache_age_minutes > max_age_minutes:
                    logger.debug(f"🗑️ Cache too old during trading hours: {cache_age_minutes:.1f}min")
                    return False
            else:
                # Outside trading hours: allow longer cache but still reasonable
                max_age_minutes = 60  # 1 hour outside trading
                if cache_age_minutes > max_age_minutes:
                    logger.debug(f"🗑️ Cache too old outside trading hours: {cache_age_minutes:.1f}min")
                    return False
            
            return True
            
        except Exception as e:
            logger.warning(f"Cache validation error for {cache_key}: {e}")
            # If we can't validate properly, assume it's invalid for safety
            return False

    def _is_trading_hours(self) -> bool:
        """
        Check if current time is during market trading hours.
        
        Returns:
            True if during trading hours, False otherwise
        """
        try:
            # Get current time in ET (market timezone)
            import pytz
            et_tz = pytz.timezone('US/Eastern')
            current_et = datetime.now(et_tz)
            
            # Market is closed on weekends
            if current_et.weekday() >= 5:  # Saturday = 5, Sunday = 6
                return False
            
            # Market hours: 9:30 AM to 4:00 PM ET
            market_open = current_et.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = current_et.replace(hour=16, minute=0, second=0, microsecond=0)
            
            return market_open <= current_et <= market_close
            
        except Exception as e:
            logger.warning(f"Failed to determine trading hours: {e}")
            # Default to trading hours if we can't determine (safer for cache invalidation)
            return True

    def clear_cache(self) -> None:
        """
        Clear all cached calculations.
        
        Useful for forcing fresh calculations after bot restart or market gaps.
        This is a recovery mechanism for edge cases.
        """
        try:
            cache_counts = {
                'support': len(self._support_cache),
                'resistance': len(self._resistance_cache),
                'expiry': len(self._cache_expiry)
            }
            
            self._support_cache.clear()
            self._resistance_cache.clear()
            self._cache_expiry.clear()
            
            total_cleared = sum(cache_counts.values())
            logger.info(f"🗑️ Cache cleared - removed {total_cleared} entries "
                       f"(support: {cache_counts['support']}, "
                       f"resistance: {cache_counts['resistance']}, "
                       f"expiry: {cache_counts['expiry']})")
                       
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")

    def clear_stale_cache(self) -> None:
        """
        Remove only stale cache entries, keeping valid ones.
        
        This is automatically called but can be manually triggered for recovery.
        """
        try:
            current_time = datetime.utcnow()
            stale_keys = []
            
            # Find all stale entries
            for cache_key, expiry_time in self._cache_expiry.items():
                if not self._is_cache_valid(cache_key):
                    stale_keys.append(cache_key)
            
            # Remove stale entries
            removed_counts = {'support': 0, 'resistance': 0}
            
            for key in stale_keys:
                if key in self._cache_expiry:
                    del self._cache_expiry[key]
                    
                if key in self._support_cache:
                    del self._support_cache[key]
                    removed_counts['support'] += 1
                    
                if key in self._resistance_cache:
                    del self._resistance_cache[key]
                    removed_counts['resistance'] += 1
            
            if stale_keys:
                logger.info(f"🗑️ Removed {len(stale_keys)} stale cache entries "
                           f"(support: {removed_counts['support']}, "
                           f"resistance: {removed_counts['resistance']})")
            else:
                logger.debug("✅ No stale cache entries found")
            
        except Exception as e:
            logger.error(f"Failed to clear stale cache: {e}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics for monitoring and debugging.
        
        Returns:
            Dictionary with cache statistics
        """
        try:
            current_time = datetime.utcnow()
            
            # Count valid vs expired entries
            valid_entries = 0
            expired_entries = 0
            
            for cache_key in self._cache_expiry:
                if self._is_cache_valid(cache_key):
                    valid_entries += 1
                else:
                    expired_entries += 1
            
            stats = {
                'total_entries': len(self._cache_expiry),
                'valid_entries': valid_entries,
                'expired_entries': expired_entries,
                'support_cache_size': len(self._support_cache),
                'resistance_cache_size': len(self._resistance_cache),
                'max_cache_size': self._max_cache_size,
                'cache_utilization_pct': (len(self._cache_expiry) / self._max_cache_size) * 100,
                'is_trading_hours': self._is_trading_hours(),
                'cache_duration_minutes': self._cache_duration.total_seconds() / 60
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {'error': str(e)}

    def _validate_market_data(self, data: List[Dict[str, Any]], 
                             symbol: str, timeframe: str) -> List[Dict[str, Any]]:
        """
        Validate and clean market data for calculations.
        
        Handles edge cases like missing data, gaps, and inconsistencies that can
        occur during bot restarts or market disruptions.
        
        Args:
            data: Raw market data
            symbol: Stock symbol
            timeframe: Timeframe
            
        Returns:
            Cleaned and validated market data
            
        Raises:
            MarketDataException: If data is insufficient or invalid
        """
        if not data:
            raise MarketDataException(f"No market data provided for {symbol} {timeframe}")
        
        if len(data) < 3:
            raise MarketDataException(f"Insufficient data for {symbol}: got {len(data)}, minimum 3 required")
        
        cleaned_data = []
        skipped_count = 0
        
        for i, bar in enumerate(data):
            try:
                # Validate required fields
                required_fields = ['high', 'low', 'close']
                missing_fields = [field for field in required_fields if field not in bar or bar[field] is None]
                
                if missing_fields:
                    logger.debug(f"Skipping bar {i} for {symbol}: missing fields {missing_fields}")
                    skipped_count += 1
                    continue
                
                # Validate and convert price values
                try:
                    high = float(bar['high'])
                    low = float(bar['low']) 
                    close = float(bar['close'])
                except (ValueError, TypeError) as e:
                    logger.debug(f"Skipping bar {i} for {symbol}: invalid price data - {e}")
                    skipped_count += 1
                    continue
                
                # Basic price validation
                if high <= 0 or low <= 0 or close <= 0:
                    logger.debug(f"Skipping bar {i} for {symbol}: non-positive prices")
                    skipped_count += 1
                    continue
                
                # High-Low-Close relationship validation
                if not (low <= close <= high):
                    logger.debug(f"Skipping bar {i} for {symbol}: invalid price relationship "
                               f"(L:{low:.2f}, C:{close:.2f}, H:{high:.2f})")
                    skipped_count += 1
                    continue
                
                # Check for extreme price values (potential data errors)
                if high > 1000000 or low > 1000000 or close > 1000000:
                    logger.warning(f"⚠️ Extremely high prices in bar {i} for {symbol}")
                    # Still include but flag for attention
                
                if high < 0.001 or low < 0.001 or close < 0.001:
                    logger.warning(f"⚠️ Extremely low prices in bar {i} for {symbol}")
                    # Still include but flag for attention
                
                # Check for extreme price gaps (potential data errors)
                if cleaned_data:
                    prev_close = cleaned_data[-1]['close']
                    gap_pct = abs(close - prev_close) / prev_close
                    
                    if gap_pct > 0.5:  # 50% gap - very unusual
                        logger.warning(f"⚠️ Large price gap detected for {symbol} at bar {i}: "
                                     f"{prev_close:.2f} -> {close:.2f} ({gap_pct:.1%})")
                        # Still include the data but flag it
                
                # Add validated bar to cleaned data
                cleaned_bar = {
                    'high': high,
                    'low': low,
                    'close': close,
                    'timestamp': bar.get('timestamp', None)
                }
                
                # Include volume if available
                if 'volume' in bar and bar['volume'] is not None:
                    try:
                        cleaned_bar['volume'] = float(bar['volume'])
                    except (ValueError, TypeError):
                        pass  # Skip volume if invalid
                
                cleaned_data.append(cleaned_bar)
                
            except Exception as e:
                logger.warning(f"Error processing bar {i} for {symbol}: {e}")
                skipped_count += 1
                continue
        
        if not cleaned_data:
            raise MarketDataException(f"No valid market data found for {symbol} after validation")
        
        if skipped_count > 0:
            skip_pct = (skipped_count / len(data)) * 100
            logger.info(f"📊 Data validation for {symbol}: kept {len(cleaned_data)} bars, "
                       f"skipped {skipped_count} ({skip_pct:.1f}%)")
        
        return cleaned_data

    def _cleanup_expired_cache(self) -> None:
        """
        Clean up expired cache entries to prevent memory leaks.
        This implements a proper cache eviction policy with optimized cleanup.
        """
        current_time = datetime.utcnow()
        
        # Batch collect expired keys for atomic operations
        expired_keys = [
            key for key, expiry_time in self._cache_expiry.items()
            if current_time >= expiry_time
        ]
        
        # Atomic cleanup to avoid race conditions
        if expired_keys:
            for key in expired_keys:
                self._cache_expiry.pop(key, None)
                self._support_cache.pop(key, None)
                if key.endswith('_resistance'):
                    self._resistance_cache.pop(key, None)
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
        
        # Implement efficient LRU eviction if cache exceeds size limits
        total_entries = len(self._cache_expiry)
        if total_entries > self._max_cache_size:
            # Remove oldest entries - sort by expiry time (oldest first)
            entries_to_remove = total_entries - self._max_cache_size
            sorted_entries = sorted(self._cache_expiry.items(), key=lambda x: x[1])
            
            # Remove in batch for efficiency
            lru_keys = [key for key, _ in sorted_entries[:entries_to_remove]]
            for key in lru_keys:
                self._cache_expiry.pop(key, None)
                self._support_cache.pop(key, None)
                if key.endswith('_resistance'):
                    self._resistance_cache.pop(key, None)
            
            logger.debug(f"LRU eviction: removed {len(lru_keys)} oldest cache entries")

    def _log_level_summary(self, levels: List[SupportLevel], symbol: str, 
                          level_type: str, current_price: Optional[float] = None) -> None:
        """
        Centralized method for logging support/resistance level summaries.
        
        Args:
            levels: List of calculated levels
            symbol: Stock symbol
            level_type: Either 'support' or 'resistance'
            current_price: Current market price for context
        """
        if not levels:
            emoji = "🟢" if level_type == "support" else "🔴"
            logger.info(f"{emoji} No {level_type} levels calculated for {symbol}")
            return
            
        try:
            # Determine sort order: support = highest first, resistance = lowest first
            is_support = level_type == "support"
            sorted_levels = sorted(levels, key=lambda x: x.price, reverse=is_support)
            
            # Build levels detail string efficiently
            levels_detail = ", ".join(
                f"${level.price:.{self._price_precision}f}({level.method},{level.confidence:.{self._price_precision}f})" 
                for level in sorted_levels
            )
            
            emoji = "🟢" if is_support else "🔴"
            logger.info(f"{emoji} Calculated {len(levels)} {level_type} levels for {symbol}: {levels_detail}")
            
            # Add nearest level summary if current price available
            if current_price is not None and current_price > self._min_valid_price:
                self._log_nearest_level(levels, symbol, level_type, current_price)
                
        except Exception as log_error:
            logger.warning(f"Error formatting {level_type} level logs for {symbol}: {log_error}")
            # Fallback to basic logging
            emoji = "🟢" if level_type == "support" else "🔴"
            logger.info(f"{emoji} Calculated {len(levels)} {level_type} levels for {symbol}")
    
    def _log_nearest_level(self, levels: List[SupportLevel], symbol: str, 
                          level_type: str, current_price: float) -> None:
        """
        Log the nearest support or resistance level to current price.
        
        Args:
            levels: List of calculated levels
            symbol: Stock symbol
            level_type: Either 'support' or 'resistance' 
            current_price: Current market price
        """
        try:
            # Input validation with more robust checks
            if current_price is None or math.isnan(current_price) or current_price <= self._min_valid_price:
                logger.warning(f"Invalid current price {current_price} for {symbol}, skipping nearest level calculation")
                return
                
            if level_type == "support":
                # Find nearest support below current price
                levels_below = [level for level in levels if level.price < current_price and level.price > 0]
                if levels_below:
                    nearest = max(levels_below, key=lambda x: x.price)
                    # Guard against division by zero
                    distance = ((current_price - nearest.price) / max(nearest.price, self._min_valid_price)) * 100
                    logger.info(f"🎯 NEAREST SUPPORT: ${nearest.price:.{self._price_precision}f} "
                               f"({distance:.{self._percentage_precision}f}% below current ${current_price:.{self._price_precision}f})")
                else:
                    logger.debug(f"🟢 No support levels below current price ${current_price:.{self._price_precision}f} for {symbol}")
            else:
                # Find nearest resistance above current price  
                levels_above = [level for level in levels if level.price > current_price]
                if levels_above:
                    nearest = min(levels_above, key=lambda x: x.price)
                    # Guard against division by zero
                    distance = ((nearest.price - current_price) / max(current_price, self._min_valid_price)) * 100
                    logger.info(f"🎯 NEAREST RESISTANCE: ${nearest.price:.{self._price_precision}f} "
                               f"({distance:.{self._percentage_precision}f}% above current ${current_price:.{self._price_precision}f})")
                else:
                    logger.debug(f"🔴 No resistance levels above current price ${current_price:.{self._price_precision}f} for {symbol}")
                    
        except Exception as e:
            logger.warning(f"Error calculating nearest {level_type} for {symbol}: {e}")
            # Log stack trace for debugging but don't crash the application
            logger.debug(f"Stack trace for nearest {level_type} calculation error", exc_info=True)

    async def calculate_support_levels(self, symbol: str, timeframe: str, 
                                     current_price: Optional[float] = None) -> SupportLevelData:
        """
        Calculate comprehensive support levels for a symbol with enhanced edge case handling.
        
        Args:
            symbol: Stock symbol to analyze
            timeframe: Timeframe for analysis (e.g., "1h", "4h", "1d")
            current_price: Current market price for validation and context (optional)
            
        Returns:
            SupportLevelData containing support levels
            
        Raises:
            MarketDataException: If support calculation fails
            ValueError: If inputs are invalid
        """
        # Input validation
        if not symbol or not symbol.strip():
            raise ValueError("Symbol cannot be empty")
        if not timeframe or not timeframe.strip():
            raise ValueError("Timeframe cannot be empty")
        
        symbol = symbol.strip().upper()
        timeframe = timeframe.strip().lower()
        
        try:
            # Clean up cache before proceeding
            self._cleanup_expired_cache()
            # Check cache first
            cache_key = f"{symbol}_{timeframe}_support"
            if cache_key in self._support_cache and self._is_cache_valid(cache_key):
                logger.debug(f"Using cached support levels for {symbol}")
                # Convert cached support levels to SupportLevelData format
                cached_levels = self._support_cache[cache_key]
                return SupportLevelData(
                    symbol=symbol,
                    timeframe=timeframe,
                    levels=cached_levels,  # Already in correct format
                    calculated_at=cached_levels[0].calculated_at if cached_levels else datetime.utcnow(),
                    confidence=sum(level.confidence for level in cached_levels) / len(cached_levels) if cached_levels else 0.0
                )

            logger.debug(f"Calculating support levels for {symbol} on {timeframe}")
            
            # Get current market price for context
            try:
                current_price = await self._market_data.get_current_price(symbol)
                logger.debug(f"🟢 SUPPORT CALCULATION: {symbol} @ ${current_price:.2f} ({timeframe})")
            except Exception as e:
                logger.warning(f"Could not get current price for {symbol}: {e}")
                current_price = None
            
            # Get historical data
            bars_data = await self._market_data.get_historical_data(
                symbol=symbol,
                timeframe=timeframe,
                count=self._lookback_periods
            )
            
            if not bars_data:
                raise MarketDataException(f"No historical data available for {symbol}")
            
            # Convert dict data to bar objects with necessary attributes
            bars = [BarData(bar_dict) for bar_dict in bars_data]
            
            # Calculate support levels using multiple methods
            support_levels = []
            
            # Method 1: Pivot Point Support
            if self._config.get_config("technical_analysis.support.calculation_methods.pivot_points", True):
                pivot_support = self._calculate_pivot_support_levels(bars)
                support_levels.extend(pivot_support)
            
            # Method 2: Moving Average Support
            if self._config.get_config("technical_analysis.support.calculation_methods.moving_averages", True):
                ma_support = self._calculate_moving_average_support_levels(bars)
                support_levels.extend(ma_support)
            
            # Method 3: Volume Profile Support
            if self._config.get_config("technical_analysis.support.calculation_methods.volume_profile", True):
                volume_support = self._calculate_volume_support_levels(bars)
                support_levels.extend(volume_support)
            
            # Method 4: Fibonacci Retracement Support
            if self._config.get_config("technical_analysis.support.calculation_methods.fibonacci_retracements", True):
                fib_support = self._calculate_fibonacci_support_levels(bars)
                support_levels.extend(fib_support)
            
            # Filter and sort support levels
            filtered_levels = self._filter_support_levels(support_levels, bars[-1].close)
            
            # Add market context logging if we have current price
            if current_price is not None:
                below_price = [level for level in filtered_levels if level.price < current_price]
                above_price = [level for level in filtered_levels if level.price >= current_price]
                logger.debug(f"🟢 SUPPORT CONTEXT: {len(below_price)} below ${current_price:.2f}, {len(above_price)} at/above")
            
            # Create support level data
            support_data = SupportLevelData(
                symbol=symbol,
                timeframe=timeframe,
                levels=filtered_levels,
                calculated_at=datetime.utcnow(),
                confidence=self._calculate_overall_confidence(filtered_levels)
            )
            
            # Cache the results
            self._support_cache[cache_key] = filtered_levels
            self._cache_expiry[cache_key] = datetime.utcnow() + self._cache_duration
            
            # Enhanced logging using centralized method
            self._log_level_summary(filtered_levels, symbol, "support", current_price)
            return support_data
            
        except Exception as e:
            logger.error(f"Failed to calculate support levels for {symbol}: {str(e)}")
            raise MarketDataException(f"Support calculation failed: {str(e)}")

    def _calculate_pivot_support_levels(self, bars: List[BarData]) -> List[SupportLevel]:
        """Calculate support levels using pivot points."""
        support_levels = []
        
        if len(bars) < 3:
            logger.warning("Insufficient data for pivot support calculation")
            return support_levels
        
        try:
            # Calculate traditional pivot points
            last_bar = bars[-1]
            high = last_bar.high
            low = last_bar.low
            close = last_bar.close
            
            # Validate data
            if high <= 0 or low <= 0 or close <= 0:
                logger.warning("Invalid price data for pivot calculation")
                return support_levels
            
            pivot = (high + low + close) / 3
            s1 = (2 * pivot) - high  # First support
            s2 = pivot - (high - low)  # Second support
            s3 = low - 2 * (high - pivot)  # Third support
            
            current_price = close
            current_time = datetime.utcnow()
            
            # Only include support levels below current price
            support_data = [
                (s1, 0.8, "pivot_s1"),
                (s2, 0.7, "pivot_s2"), 
                (s3, 0.6, "pivot_s3")
            ]
            
            for price, confidence, method in support_data:
                if price > 0 and price < current_price:
                    support_levels.append(SupportLevel(
                        price=price,
                        confidence=confidence,
                        method=method,
                        touches=1,
                        last_touch=current_time,
                        calculated_at=current_time
                    ))
        
        except Exception as e:
            logger.error(f"Error in pivot support calculation: {e}")
        
        return support_levels

    def _calculate_moving_average_support_levels(self, bars: List[BarData]) -> List[SupportLevel]:
        """Calculate support levels using moving averages."""
        support_levels = []
        
        if len(bars) < 20:
            logger.warning("Insufficient data for moving average support calculation")
            return support_levels
        
        try:
            closes = [bar.close for bar in bars]
            current_price = closes[-1]
            current_time = datetime.utcnow()
            
            # Calculate different period moving averages efficiently
            periods = [20, 50, 100, 200]
            
            for period in periods:
                if len(closes) >= period:
                    # Use efficient calculation
                    ma = sum(closes[-period:]) / period
                    
                    # If MA is below current price, it acts as support
                    if ma > 0 and ma < current_price:
                        # Calculate confidence based on price touches near MA
                        confidence = self._calculate_ma_confidence(bars, ma, period)
                        
                        if confidence >= self._min_confidence:
                            support_levels.append(SupportLevel(
                                price=ma,
                                confidence=confidence,
                                method=f"ma_{period}",
                                touches=self._count_ma_touches(bars, ma),
                                last_touch=current_time,
                                calculated_at=current_time
                            ))
        
        except Exception as e:
            logger.error(f"Error in moving average support calculation: {e}")
        
        return support_levels
    
    def _calculate_ma_confidence(self, bars: List[BarData], ma_level: float, period: int) -> float:
        """Calculate confidence for moving average levels based on touches and period."""
        base_confidence = 0.6
        touches = self._count_ma_touches(bars, ma_level)
        
        # Higher confidence for more touches and longer periods
        touch_bonus = min(0.3, touches * 0.1)
        period_bonus = min(0.1, (period - 20) / 180 * 0.1)  # Scale with period length
        
        return min(0.9, base_confidence + touch_bonus + period_bonus)
    
    def _count_ma_touches(self, bars: List[BarData], ma_level: float) -> int:
        """Count how many times price touched the moving average level."""
        tolerance = ma_level * 0.002  # 0.2% tolerance
        touches = 0
        
        # Check last 20 bars for efficiency
        check_bars = bars[-20:] if len(bars) > 20 else bars
        
        for bar in check_bars:
            if abs(bar.low - ma_level) <= tolerance or abs(bar.high - ma_level) <= tolerance:
                touches += 1
        
        return touches

    def _calculate_volume_support_levels(self, bars) -> List[SupportLevel]:
        """Calculate support levels using volume profile analysis."""
        support_levels = []
        
        if len(bars) < 20:
            return support_levels
        
        # Create price levels and volume mapping
        price_volume_map = {}
        current_price = bars[-1].close
        
        for bar in bars[-50:]:  # Use last 50 bars
            # Create price bins
            price_range = (bar.high - bar.low) / 10  # Divide each bar into 10 price levels
            
            for i in range(10):
                price_level = bar.low + (i * price_range)
                if price_level not in price_volume_map:
                    price_volume_map[price_level] = 0
                price_volume_map[price_level] += bar.volume / 10
        
        # Find high volume areas below current price
        sorted_levels = sorted(price_volume_map.items(), key=lambda x: x[1], reverse=True)
        
        for price, volume in sorted_levels[:5]:  # Top 5 volume levels
            if price < current_price:
                # Calculate confidence based on volume relative to average
                avg_volume = sum(price_volume_map.values()) / len(price_volume_map)
                confidence = min(0.9, 0.4 + (volume / avg_volume) * 0.1)
                
                support_levels.append(SupportLevel(
                    price=price,
                    confidence=confidence,
                    method="volume_profile",
                    touches=1,
                    last_touch=datetime.utcnow()
                ))
        
        return support_levels

    def _calculate_fibonacci_support_levels(self, bars) -> List[SupportLevel]:
        """Calculate support levels using Fibonacci retracements."""
        support_levels = []
        
        if len(bars) < 20:
            return support_levels
        
        # Find recent swing points
        swing_high = max(bar.high for bar in bars[-20:])
        swing_low = min(bar.low for bar in bars[-20:])
        current_price = bars[-1].close
        
        # Calculate Fibonacci retracement levels
        fib_range = swing_high - swing_low
        fib_levels = [0.236, 0.382, 0.5, 0.618, 0.786]  # Retracement levels
        
        for fib_ratio in fib_levels:
            fib_support = swing_high - (fib_range * fib_ratio)
            
            if fib_support < current_price:
                confidence = 0.8 - (fib_ratio - 0.236) * 0.1  # Decreasing confidence for deeper retracements
                
                support_levels.append(SupportLevel(
                    price=fib_support,
                    confidence=max(0.4, confidence),
                    method=f"fibonacci_{fib_ratio}",
                    touches=1,
                    last_touch=datetime.utcnow()
                ))
        
        return support_levels

    def _filter_support_levels(self, levels: List[SupportLevel], current_price: float) -> List[SupportLevel]:
        """Filter and consolidate support levels."""
        if not levels:
            return []
        
        # Filter by confidence
        min_confidence = self._config.get_config("technical_analysis.support.min_confidence", 0.7)
        filtered = [level for level in levels if level.confidence >= min_confidence]
        
        # Only keep support levels below current price
        filtered = [level for level in filtered if level.price < current_price]
        
        # Remove duplicate/very close levels
        consolidated = []
        tolerance = current_price * 0.005  # 0.5% tolerance
        
        for level in sorted(filtered, key=lambda x: x.price, reverse=True):
            is_duplicate = False
            for existing in consolidated:
                if abs(level.price - existing.price) <= tolerance:
                    # Keep the one with higher confidence
                    if level.confidence > existing.confidence:
                        consolidated.remove(existing)
                        consolidated.append(level)
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                consolidated.append(level)
        
        # Sort by proximity to current price and confidence
        consolidated.sort(key=lambda x: (current_price - x.price, -x.confidence))
        
        # Return top 5 most relevant support levels
        return consolidated[:5]

    def _calculate_overall_confidence(self, levels: List[SupportLevel]) -> float:
        """Calculate overall confidence based on the quality and convergence of support levels."""
        if not levels:
            return 0.0
        
        # Calculate average confidence
        avg_confidence = sum(level.confidence for level in levels) / len(levels)
        
        # Bonus for having multiple support levels
        level_bonus = min(0.2, len(levels) * 0.05)
        
        return min(1.0, avg_confidence + level_bonus)
