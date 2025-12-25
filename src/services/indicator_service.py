"""
Technical Indicator Calculation Service.

Provides RSI, MACD, and Stochastic indicator calculations for signal-based
bot start conditions. Uses pandas for calculations without external TA library
dependencies.

This service is designed for:
- Bot creation UI: Show historical signal counts
- Bot execution: Evaluate indicator conditions for entry signals
- Signal monitoring: Real-time indicator value tracking

Author: Trading Bot Team
Version: 1.0.0
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import numpy as np
import pandas as pd

from src.core.logging_config import get_logger
from src.domain.bot_enums import IndicatorType, IndicatorTimeframe
from src.exceptions import TradingBotException

if TYPE_CHECKING:
    from src.interfaces import IMarketDataProvider


logger = get_logger(__name__)


# =============================================================================
# Exceptions
# =============================================================================

class IndicatorCalculationException(TradingBotException):
    """Exception raised when indicator calculation fails."""
    
    def __init__(self, message: str, indicator: Optional[str] = None):
        super().__init__(message)
        self.indicator = indicator


# =============================================================================
# Data Transfer Objects
# =============================================================================

@dataclass
class IndicatorValue:
    """
    Single indicator value at a point in time.
    
    Attributes:
        timestamp: When this value was calculated
        value: Primary indicator value (e.g., RSI value, MACD histogram)
        signal: Signal state: 'buy', 'sell', or 'neutral'
        components: Additional indicator components (e.g., MACD line, signal line)
    """
    
    timestamp: datetime
    value: float
    signal: str  # 'buy', 'sell', 'neutral'
    components: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "signal": self.signal,
            "components": self.components,
        }


@dataclass
class IndicatorResult:
    """
    Complete indicator calculation result.
    
    Attributes:
        indicator_type: Type of indicator (RSI, MACD, Stochastic)
        timeframe: Calculation timeframe
        current_value: Most recent indicator value
        current_signal: Current signal state
        signal_count_buy: Number of buy signals in lookback period
        signal_count_sell: Number of sell signals in lookback period
        history: Historical indicator values (optional, for charting)
    """
    
    indicator_type: IndicatorType
    timeframe: IndicatorTimeframe
    current_value: IndicatorValue
    signal_count_buy: int = 0
    signal_count_sell: int = 0
    history: List[IndicatorValue] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "indicatorType": self.indicator_type.value,
            "timeframe": self.timeframe.value,
            "currentValue": self.current_value.to_dict(),
            "signalCountBuy": self.signal_count_buy,
            "signalCountSell": self.signal_count_sell,
            "history": [v.to_dict() for v in self.history] if self.history else [],
        }


@dataclass
class CombinedSignalResult:
    """
    Combined signal result from multiple indicators.
    
    Attributes:
        symbol: Trading symbol
        indicators: Individual indicator results
        combined_signal_count: Total unique signals across all enabled indicators
        aligned_buy_signals: Timestamps where all indicators agree on buy
        aligned_sell_signals: Timestamps where all indicators agree on sell
        lookback_days: Number of days analyzed
    """
    
    symbol: str
    indicators: List[IndicatorResult]
    combined_signal_count: int = 0
    aligned_buy_signals: int = 0
    aligned_sell_signals: int = 0
    lookback_days: int = 30
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "symbol": self.symbol,
            "indicators": [i.to_dict() for i in self.indicators],
            "combinedSignalCount": self.combined_signal_count,
            "alignedBuySignals": self.aligned_buy_signals,
            "alignedSellSignals": self.aligned_sell_signals,
            "lookbackDays": self.lookback_days,
        }


# =============================================================================
# Indicator Service Interface
# =============================================================================

class IIndicatorService(ABC):
    """
    Interface for technical indicator calculation service.
    
    Follows Dependency Inversion Principle (DIP) - business logic depends
    on this abstraction rather than concrete implementations.
    """
    
    @abstractmethod
    async def calculate_indicator(
        self,
        symbol: str,
        indicator_type: IndicatorType,
        timeframe: IndicatorTimeframe,
        lookback_days: int = 30,
    ) -> IndicatorResult:
        """
        Calculate a single indicator for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., 'AAPL', 'BTC/USD')
            indicator_type: Type of indicator to calculate
            timeframe: Candle timeframe for calculation
            lookback_days: Number of days to analyze
            
        Returns:
            IndicatorResult with current value and signal counts
            
        Raises:
            IndicatorCalculationException: If calculation fails
        """
        pass
    
    @abstractmethod
    async def calculate_combined_signals(
        self,
        symbol: str,
        indicators: List[Tuple[IndicatorType, IndicatorTimeframe]],
        lookback_days: int = 30,
    ) -> CombinedSignalResult:
        """
        Calculate multiple indicators and combine their signals.
        
        Args:
            symbol: Trading symbol
            indicators: List of (indicator_type, timeframe) tuples
            lookback_days: Number of days to analyze
            
        Returns:
            CombinedSignalResult with all indicator data and combined counts
        """
        pass
    
    @abstractmethod
    async def get_current_indicator_status(
        self,
        symbol: str,
        indicator_type: IndicatorType,
        timeframe: IndicatorTimeframe,
    ) -> IndicatorValue:
        """
        Get the current (real-time) indicator value.
        
        Used for evaluating bot start conditions.
        
        Args:
            symbol: Trading symbol
            indicator_type: Type of indicator
            timeframe: Candle timeframe
            
        Returns:
            Current IndicatorValue with signal state
        """
        pass


# =============================================================================
# Indicator Calculation Helpers
# =============================================================================

class IndicatorCalculator:
    """
    Pure calculation functions for technical indicators.
    
    All methods are stateless and operate on pandas DataFrames.
    Uses standard indicator formulas without external TA libraries.
    """
    
    # RSI default settings
    RSI_PERIOD = 14
    RSI_OVERBOUGHT = 70
    RSI_OVERSOLD = 30
    
    # MACD default settings
    MACD_FAST = 12
    MACD_SLOW = 26
    MACD_SIGNAL = 9
    
    # Stochastic default settings
    STOCH_K_PERIOD = 14
    STOCH_D_PERIOD = 3
    STOCH_OVERBOUGHT = 80
    STOCH_OVERSOLD = 20
    
    @staticmethod
    def calculate_rsi(
        df: pd.DataFrame,
        period: int = None,
        overbought: float = None,
        oversold: float = None,
    ) -> pd.DataFrame:
        """
        Calculate RSI (Relative Strength Index).
        
        RSI = 100 - (100 / (1 + RS))
        RS = Average Gain / Average Loss
        
        Args:
            df: DataFrame with 'close' column
            period: RSI period (default: 14)
            overbought: Overbought threshold (default: 70)
            oversold: Oversold threshold (default: 30)
            
        Returns:
            DataFrame with 'rsi', 'rsi_signal' columns added
        """
        period = period or IndicatorCalculator.RSI_PERIOD
        overbought = overbought or IndicatorCalculator.RSI_OVERBOUGHT
        oversold = oversold or IndicatorCalculator.RSI_OVERSOLD
        
        # Calculate price changes
        delta = df['close'].diff()
        
        # Separate gains and losses
        gains = delta.where(delta > 0, 0.0)
        losses = (-delta).where(delta < 0, 0.0)
        
        # Calculate exponential moving averages
        avg_gain = gains.ewm(span=period, adjust=False).mean()
        avg_loss = losses.ewm(span=period, adjust=False).mean()
        
        # Calculate RS and RSI
        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        
        # Generate signals
        df = df.copy()
        df['rsi'] = rsi
        df['rsi_signal'] = 'neutral'
        df.loc[df['rsi'] <= oversold, 'rsi_signal'] = 'buy'
        df.loc[df['rsi'] >= overbought, 'rsi_signal'] = 'sell'
        
        return df
    
    @staticmethod
    def calculate_macd(
        df: pd.DataFrame,
        fast_period: int = None,
        slow_period: int = None,
        signal_period: int = None,
    ) -> pd.DataFrame:
        """
        Calculate MACD (Moving Average Convergence Divergence).
        
        MACD Line = Fast EMA - Slow EMA
        Signal Line = EMA of MACD Line
        Histogram = MACD Line - Signal Line
        
        Buy signal: Histogram crosses above 0 (bullish momentum)
        Sell signal: Histogram crosses below 0 (bearish momentum)
        
        Args:
            df: DataFrame with 'close' column
            fast_period: Fast EMA period (default: 12)
            slow_period: Slow EMA period (default: 26)
            signal_period: Signal line period (default: 9)
            
        Returns:
            DataFrame with 'macd', 'macd_signal_line', 'macd_histogram', 'macd_signal' columns
        """
        fast_period = fast_period or IndicatorCalculator.MACD_FAST
        slow_period = slow_period or IndicatorCalculator.MACD_SLOW
        signal_period = signal_period or IndicatorCalculator.MACD_SIGNAL
        
        # Calculate EMAs
        fast_ema = df['close'].ewm(span=fast_period, adjust=False).mean()
        slow_ema = df['close'].ewm(span=slow_period, adjust=False).mean()
        
        # MACD Line
        macd_line = fast_ema - slow_ema
        
        # Signal Line
        signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
        
        # Histogram
        histogram = macd_line - signal_line
        
        df = df.copy()
        df['macd'] = macd_line
        df['macd_signal_line'] = signal_line
        df['macd_histogram'] = histogram
        
        # Generate signals based on histogram crossover
        df['macd_signal'] = 'neutral'
        
        # Histogram crosses above 0 -> buy signal
        histogram_cross_up = (histogram > 0) & (histogram.shift(1) <= 0)
        df.loc[histogram_cross_up, 'macd_signal'] = 'buy'
        
        # Histogram crosses below 0 -> sell signal
        histogram_cross_down = (histogram < 0) & (histogram.shift(1) >= 0)
        df.loc[histogram_cross_down, 'macd_signal'] = 'sell'
        
        return df
    
    @staticmethod
    def calculate_stochastic(
        df: pd.DataFrame,
        k_period: int = None,
        d_period: int = None,
        overbought: float = None,
        oversold: float = None,
    ) -> pd.DataFrame:
        """
        Calculate Stochastic Oscillator.
        
        %K = 100 * (Close - Lowest Low) / (Highest High - Lowest Low)
        %D = SMA of %K
        
        Buy signal: %K crosses above %D in oversold zone
        Sell signal: %K crosses below %D in overbought zone
        
        Args:
            df: DataFrame with 'high', 'low', 'close' columns
            k_period: %K period (default: 14)
            d_period: %D smoothing period (default: 3)
            overbought: Overbought threshold (default: 80)
            oversold: Oversold threshold (default: 20)
            
        Returns:
            DataFrame with 'stoch_k', 'stoch_d', 'stoch_signal' columns
        """
        k_period = k_period or IndicatorCalculator.STOCH_K_PERIOD
        d_period = d_period or IndicatorCalculator.STOCH_D_PERIOD
        overbought = overbought or IndicatorCalculator.STOCH_OVERBOUGHT
        oversold = oversold or IndicatorCalculator.STOCH_OVERSOLD
        
        # Calculate %K
        lowest_low = df['low'].rolling(window=k_period).min()
        highest_high = df['high'].rolling(window=k_period).max()
        
        stoch_k = 100 * (df['close'] - lowest_low) / (highest_high - lowest_low)
        stoch_k = stoch_k.replace([np.inf, -np.inf], np.nan)
        
        # Calculate %D (smoothed %K)
        stoch_d = stoch_k.rolling(window=d_period).mean()
        
        df = df.copy()
        df['stoch_k'] = stoch_k
        df['stoch_d'] = stoch_d
        df['stoch_signal'] = 'neutral'
        
        # Buy: %K crosses above %D in oversold zone
        k_crosses_above_d = (stoch_k > stoch_d) & (stoch_k.shift(1) <= stoch_d.shift(1))
        in_oversold = stoch_k <= oversold
        df.loc[k_crosses_above_d & in_oversold, 'stoch_signal'] = 'buy'
        
        # Sell: %K crosses below %D in overbought zone
        k_crosses_below_d = (stoch_k < stoch_d) & (stoch_k.shift(1) >= stoch_d.shift(1))
        in_overbought = stoch_k >= overbought
        df.loc[k_crosses_below_d & in_overbought, 'stoch_signal'] = 'sell'
        
        return df


# =============================================================================
# Indicator Service Implementation
# =============================================================================

class IndicatorService(IIndicatorService):
    """
    Technical indicator calculation service implementation.
    
    Fetches historical market data from a market data provider and
    calculates technical indicators for bot signal evaluation.
    
    Thread-safe for concurrent indicator calculations.
    Implements TTL-based caching to avoid redundant API calls.
    
    Example:
        service = IndicatorService(market_data_provider)
        
        # Calculate RSI for AAPL on 1-hour timeframe
        result = await service.calculate_indicator(
            symbol='AAPL',
            indicator_type=IndicatorType.RSI,
            timeframe=IndicatorTimeframe.ONE_HOUR,
            lookback_days=30
        )
        
        print(f"Current RSI: {result.current_value.value}")
        print(f"Buy signals in last 30 days: {result.signal_count_buy}")
    """
    
    # Timeframe to pandas frequency mapping
    TIMEFRAME_MAP = {
        IndicatorTimeframe.ONE_MINUTE: '1min',
        IndicatorTimeframe.FIVE_MINUTES: '5min',
        IndicatorTimeframe.FIFTEEN_MINUTES: '15min',
        IndicatorTimeframe.THIRTY_MINUTES: '30min',
        IndicatorTimeframe.ONE_HOUR: '1h',
        IndicatorTimeframe.FOUR_HOURS: '4h',
        IndicatorTimeframe.ONE_DAY: '1d',
    }
    
    # Cache TTL based on timeframe (shorter timeframes = shorter TTL)
    CACHE_TTL_MAP = {
        IndicatorTimeframe.ONE_MINUTE: timedelta(seconds=30),
        IndicatorTimeframe.FIVE_MINUTES: timedelta(minutes=2),
        IndicatorTimeframe.FIFTEEN_MINUTES: timedelta(minutes=5),
        IndicatorTimeframe.THIRTY_MINUTES: timedelta(minutes=10),
        IndicatorTimeframe.ONE_HOUR: timedelta(minutes=15),
        IndicatorTimeframe.FOUR_HOURS: timedelta(minutes=30),
        IndicatorTimeframe.ONE_DAY: timedelta(hours=1),
    }
    
    # Default TTL for cache entries
    DEFAULT_CACHE_TTL = timedelta(minutes=5)
    
    def __init__(self, market_data_provider: "IMarketDataProvider"):
        """
        Initialize indicator service.
        
        Args:
            market_data_provider: Provider for fetching historical market data
        """
        self._market_data = market_data_provider
        
        # TTL cache: {cache_key: (expiry_time, IndicatorResult)}
        self._cache: Dict[str, Tuple[datetime, IndicatorResult]] = {}
        
        logger.info("IndicatorService initialized with TTL caching")
    
    def _get_cache_key(
        self,
        symbol: str,
        indicator_type: IndicatorType,
        timeframe: IndicatorTimeframe,
        lookback_days: int,
    ) -> str:
        """Generate unique cache key for indicator request."""
        return f"{symbol}:{indicator_type.value}:{timeframe.value}:{lookback_days}"
    
    def _get_from_cache(self, cache_key: str) -> Optional[IndicatorResult]:
        """
        Get cached result if not expired.
        
        Args:
            cache_key: The cache key to look up
            
        Returns:
            Cached IndicatorResult if valid, None if expired or not found
        """
        if cache_key not in self._cache:
            return None
        
        expiry_time, result = self._cache[cache_key]
        
        if datetime.now() > expiry_time:
            # Cache expired, remove entry
            del self._cache[cache_key]
            logger.debug(f"Cache expired for key: {cache_key}")
            return None
        
        logger.debug(f"Cache hit for key: {cache_key}")
        return result
    
    def _set_cache(
        self,
        cache_key: str,
        result: IndicatorResult,
        timeframe: IndicatorTimeframe,
    ) -> None:
        """
        Store result in cache with TTL based on timeframe.
        
        Args:
            cache_key: The cache key
            result: The indicator result to cache
            timeframe: The timeframe (determines TTL)
        """
        ttl = self.CACHE_TTL_MAP.get(timeframe, self.DEFAULT_CACHE_TTL)
        expiry_time = datetime.now() + ttl
        self._cache[cache_key] = (expiry_time, result)
        logger.debug(f"Cached result for key: {cache_key}, TTL: {ttl}")
    
    def clear_cache(self, symbol: Optional[str] = None) -> int:
        """
        Clear cached indicator results.
        
        Args:
            symbol: If provided, only clear cache for this symbol.
                   If None, clear entire cache.
                   
        Returns:
            Number of cache entries removed
        """
        if symbol is None:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cleared entire indicator cache ({count} entries)")
            return count
        
        # Clear only entries for this symbol
        keys_to_remove = [k for k in self._cache if k.startswith(f"{symbol}:")]
        for key in keys_to_remove:
            del self._cache[key]
        
        logger.info(f"Cleared cache for symbol {symbol} ({len(keys_to_remove)} entries)")
        return len(keys_to_remove)
    
    async def _fetch_historical_data(
        self,
        symbol: str,
        timeframe: IndicatorTimeframe,
        lookback_days: int,
    ) -> pd.DataFrame:
        """
        Fetch historical OHLCV data for indicator calculation.
        
        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            lookback_days: Number of days to fetch
            
        Returns:
            DataFrame with timestamp, open, high, low, close, volume columns
            
        Raises:
            IndicatorCalculationException: If data fetch fails
        """
        try:
            # Calculate number of candles needed based on timeframe
            timeframe_str = self.TIMEFRAME_MAP.get(timeframe, '1h')
            
            # Estimate candles per day for each timeframe
            candles_per_day = {
                '1min': 390,   # 6.5 trading hours * 60
                '5min': 78,    # 6.5 trading hours * 12
                '15min': 26,   # 6.5 trading hours * 4
                '30min': 13,   # 6.5 trading hours * 2
                '1h': 7,       # ~7 hours of trading
                '4h': 2,       # ~2 4-hour candles per day
                '1d': 1,       # 1 daily candle
            }
            
            cpd = candles_per_day.get(timeframe_str, 24)
            count = lookback_days * cpd + 50  # Extra for indicator warm-up
            
            # Fetch data via market data provider
            raw_data = await self._market_data.get_historical_data(
                symbol=symbol,
                timeframe=timeframe_str,
                count=min(count, 5000),  # Cap at 5000 candles
            )
            
            if not raw_data:
                raise IndicatorCalculationException(
                    f"No historical data available for {symbol}",
                    indicator="data_fetch"
                )
            
            # Convert to DataFrame
            df = pd.DataFrame(raw_data)
            
            # Ensure required columns exist
            required_columns = ['timestamp', 'open', 'high', 'low', 'close']
            for col in required_columns:
                if col not in df.columns:
                    # Try alternative column names
                    alternatives = {
                        'timestamp': ['time', 'date', 'datetime', 't'],
                        'open': ['o'],
                        'high': ['h'],
                        'low': ['l'],
                        'close': ['c'],
                    }
                    found = False
                    for alt in alternatives.get(col, []):
                        if alt in df.columns:
                            df[col] = df[alt]
                            found = True
                            break
                    if not found and col != 'timestamp':
                        raise IndicatorCalculationException(
                            f"Missing required column: {col}",
                            indicator="data_validation"
                        )
            
            # Convert timestamp to datetime
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df = df.set_index('timestamp')
            
            # Sort by timestamp
            df = df.sort_index()
            
            # Convert price columns to float
            for col in ['open', 'high', 'low', 'close']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Drop any rows with NaN values
            df = df.dropna(subset=['open', 'high', 'low', 'close'])
            
            logger.debug(f"Fetched {len(df)} candles for {symbol} ({timeframe_str})")
            
            return df
            
        except IndicatorCalculationException:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch historical data for {symbol}: {e}")
            raise IndicatorCalculationException(
                f"Failed to fetch data for {symbol}: {str(e)}",
                indicator="data_fetch"
            )
    
    def _calculate_indicator_values(
        self,
        df: pd.DataFrame,
        indicator_type: IndicatorType,
    ) -> Tuple[pd.DataFrame, str, str]:
        """
        Calculate indicator values and add to DataFrame.
        
        Args:
            df: DataFrame with OHLCV data
            indicator_type: Type of indicator to calculate
            
        Returns:
            Tuple of (DataFrame with indicator columns, value_column, signal_column)
        """
        if indicator_type == IndicatorType.RSI:
            df = self._calculator.calculate_rsi(df)
            return df, 'rsi', 'rsi_signal'
        
        elif indicator_type == IndicatorType.MACD:
            df = self._calculator.calculate_macd(df)
            return df, 'macd_histogram', 'macd_signal'
        
        elif indicator_type == IndicatorType.STOCHASTIC:
            df = self._calculator.calculate_stochastic(df)
            return df, 'stoch_k', 'stoch_signal'
        
        else:
            raise IndicatorCalculationException(
                f"Unknown indicator type: {indicator_type}",
                indicator=str(indicator_type)
            )
    
    async def calculate_indicator(
        self,
        symbol: str,
        indicator_type: IndicatorType,
        timeframe: IndicatorTimeframe,
        lookback_days: int = 30,
    ) -> IndicatorResult:
        """
        Calculate a single indicator for a symbol.
        
        Uses TTL-based caching to avoid redundant API calls for the same
        indicator/symbol/timeframe combination.
        
        Args:
            symbol: Trading symbol
            indicator_type: Type of indicator to calculate
            timeframe: Candle timeframe
            lookback_days: Number of days to analyze
            
        Returns:
            IndicatorResult with current value and signal counts
        """
        # Check cache first
        cache_key = self._get_cache_key(symbol, indicator_type, timeframe, lookback_days)
        cached_result = self._get_from_cache(cache_key)
        
        if cached_result is not None:
            logger.info(
                f"Returning cached {indicator_type.value} for {symbol} "
                f"({timeframe.value}, {lookback_days}d lookback)"
            )
            return cached_result
        
        logger.info(
            f"Calculating {indicator_type.value} for {symbol} "
            f"({timeframe.value}, {lookback_days}d lookback)"
        )
        
        # Fetch historical data
        df = await self._fetch_historical_data(symbol, timeframe, lookback_days)
        
        if len(df) < 20:
            raise IndicatorCalculationException(
                f"Insufficient data for {symbol}: {len(df)} candles",
                indicator=indicator_type.value
            )
        
        # Calculate indicator
        df, value_col, signal_col = self._calculate_indicator_values(df, indicator_type)
        
        # Get current value
        latest = df.iloc[-1]
        current_value = IndicatorValue(
            timestamp=latest.name if isinstance(latest.name, datetime) else datetime.now(),
            value=float(latest[value_col]) if not pd.isna(latest[value_col]) else 0.0,
            signal=str(latest[signal_col]) if not pd.isna(latest[signal_col]) else 'neutral',
            components=self._get_indicator_components(latest, indicator_type),
        )
        
        # Count signals in lookback period
        lookback_start = datetime.now() - timedelta(days=lookback_days)
        lookback_df = df[df.index >= lookback_start] if hasattr(df.index, '__iter__') else df
        
        signal_count_buy = int((lookback_df[signal_col] == 'buy').sum())
        signal_count_sell = int((lookback_df[signal_col] == 'sell').sum())
        
        # Build history (last 100 values for charting)
        history = []
        for idx, row in df.tail(100).iterrows():
            if not pd.isna(row[value_col]):
                history.append(IndicatorValue(
                    timestamp=idx if isinstance(idx, datetime) else datetime.now(),
                    value=float(row[value_col]),
                    signal=str(row[signal_col]) if not pd.isna(row[signal_col]) else 'neutral',
                    components=self._get_indicator_components(row, indicator_type),
                ))
        
        result = IndicatorResult(
            indicator_type=indicator_type,
            timeframe=timeframe,
            current_value=current_value,
            signal_count_buy=signal_count_buy,
            signal_count_sell=signal_count_sell,
            history=history,
        )
        
        # Cache the result
        self._set_cache(cache_key, result, timeframe)
        
        logger.info(
            f"{indicator_type.value} for {symbol}: "
            f"current={current_value.value:.2f} ({current_value.signal}), "
            f"buy_signals={signal_count_buy}, sell_signals={signal_count_sell}"
        )
        
        return result
    
    def _get_indicator_components(
        self,
        row: pd.Series,
        indicator_type: IndicatorType,
    ) -> Dict[str, float]:
        """Extract indicator-specific components from a row."""
        components = {}
        
        if indicator_type == IndicatorType.RSI:
            if 'rsi' in row and not pd.isna(row['rsi']):
                components['rsi'] = float(row['rsi'])
        
        elif indicator_type == IndicatorType.MACD:
            if 'macd' in row and not pd.isna(row['macd']):
                components['macdLine'] = float(row['macd'])
            if 'macd_signal_line' in row and not pd.isna(row['macd_signal_line']):
                components['signalLine'] = float(row['macd_signal_line'])
            if 'macd_histogram' in row and not pd.isna(row['macd_histogram']):
                components['histogram'] = float(row['macd_histogram'])
        
        elif indicator_type == IndicatorType.STOCHASTIC:
            if 'stoch_k' in row and not pd.isna(row['stoch_k']):
                components['kValue'] = float(row['stoch_k'])
            if 'stoch_d' in row and not pd.isna(row['stoch_d']):
                components['dValue'] = float(row['stoch_d'])
        
        return components
    
    async def calculate_combined_signals(
        self,
        symbol: str,
        indicators: List[Tuple[IndicatorType, IndicatorTimeframe]],
        lookback_days: int = 30,
    ) -> CombinedSignalResult:
        """
        Calculate multiple indicators and combine their signals.
        
        Args:
            symbol: Trading symbol
            indicators: List of (indicator_type, timeframe) tuples
            lookback_days: Number of days to analyze
            
        Returns:
            CombinedSignalResult with all indicator data
        """
        logger.info(f"Calculating combined signals for {symbol} with {len(indicators)} indicators")
        
        results = []
        total_buy_signals = 0
        total_sell_signals = 0
        
        for indicator_type, timeframe in indicators:
            try:
                result = await self.calculate_indicator(
                    symbol=symbol,
                    indicator_type=indicator_type,
                    timeframe=timeframe,
                    lookback_days=lookback_days,
                )
                results.append(result)
                total_buy_signals += result.signal_count_buy
                total_sell_signals += result.signal_count_sell
            except IndicatorCalculationException as e:
                logger.warning(f"Failed to calculate {indicator_type.value} for {symbol}: {e}")
                # Continue with other indicators
        
        combined = CombinedSignalResult(
            symbol=symbol,
            indicators=results,
            combined_signal_count=total_buy_signals + total_sell_signals,
            aligned_buy_signals=total_buy_signals,
            aligned_sell_signals=total_sell_signals,
            lookback_days=lookback_days,
        )
        
        logger.info(
            f"Combined signals for {symbol}: "
            f"total={combined.combined_signal_count}, "
            f"buy={combined.aligned_buy_signals}, sell={combined.aligned_sell_signals}"
        )
        
        return combined
    
    async def get_current_indicator_status(
        self,
        symbol: str,
        indicator_type: IndicatorType,
        timeframe: IndicatorTimeframe,
    ) -> IndicatorValue:
        """
        Get the current (real-time) indicator value.
        
        Used for evaluating bot start conditions in real-time.
        
        Args:
            symbol: Trading symbol
            indicator_type: Type of indicator
            timeframe: Candle timeframe
            
        Returns:
            Current IndicatorValue with signal state
        """
        # Calculate with minimal lookback just to get current value
        result = await self.calculate_indicator(
            symbol=symbol,
            indicator_type=indicator_type,
            timeframe=timeframe,
            lookback_days=5,  # Minimal data for current value
        )
        
        return result.current_value


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Exceptions
    "IndicatorCalculationException",
    # Data Transfer Objects
    "IndicatorValue",
    "IndicatorResult",
    "CombinedSignalResult",
    # Interface
    "IIndicatorService",
    # Implementation
    "IndicatorService",
    "IndicatorCalculator",
]
