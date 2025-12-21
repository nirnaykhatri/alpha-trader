"""
Volatility Regime Detector
Detects market volatility regimes and adapts DCA spacing based on ATR bands
"""

import asyncio
import bisect
from typing import List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass

from src.core.logging_config import get_logger
from src.interfaces import IMarketDataProvider
from src.core import ConfigurationManager as ConfigManager
from src.utils.metrics import (
    volatility_regime_changes_total,
    volatility_regime_gauge,
    dca_spacing_multiplier_gauge
)


logger = get_logger(__name__)


class VolatilityRegime(Enum):
    """Volatility regime classification."""
    ULTRA_LOW = "ultra_low"      # < 20th percentile
    LOW = "low"                  # 20-40th percentile
    NORMAL = "normal"            # 40-60th percentile
    ELEVATED = "elevated"        # 60-80th percentile
    HIGH = "high"                # 80-95th percentile
    EXTREME = "extreme"          # > 95th percentile


@dataclass
class VolatilityMetrics:
    """Volatility analysis metrics."""
    symbol: str
    current_atr: float
    atr_percentile: float
    regime: VolatilityRegime
    lookback_period: int
    timestamp: datetime
    
    # Regime-based multipliers for DCA spacing
    spacing_multiplier: float
    max_attempts_adjustment: int
    
    def __str__(self) -> str:
        return (
            f"VolatilityMetrics(symbol={self.symbol}, regime={self.regime.value}, "
            f"atr={self.current_atr:.4f}, percentile={self.atr_percentile:.1f}%, "
            f"spacing_mult={self.spacing_multiplier:.2f}x)"
        )


class VolatilityRegimeDetector:
    """
    Detects market volatility regimes using Average True Range (ATR) analysis.
    
    Adapts DCA strategy parameters based on volatility:
    - ULTRA_LOW/LOW: Tighter DCA spacing (more aggressive)
    - NORMAL: Standard DCA spacing
    - ELEVATED/HIGH: Wider DCA spacing (more conservative)
    - EXTREME: Maximum spacing + reduced attempts
    
    Uses percentile ranking of ATR over lookback period to classify regime.
    """
    
    def __init__(self,
                 market_data: IMarketDataProvider,
                 config: Optional[ConfigManager] = None,
                 lookback_days: int = 60,
                 atr_period: int = 14):
        """
        Initialize volatility regime detector.
        
        Args:
            market_data: Market data provider for historical data
            config: Configuration manager
            lookback_days: Days of history for percentile calculation
            atr_period: Period for ATR calculation
        """
        self.market_data = market_data
        self.config = config or ConfigManager()
        self.lookback_days = lookback_days
        self.atr_period = atr_period
        
        # Cache for ATR history
        self._atr_cache: dict[str, List[Tuple[datetime, float]]] = {}
        self._cache_ttl = timedelta(hours=1)
        self._last_cache_update: dict[str, datetime] = {}
        
        # Cache for sorted distributions (for fast percentile lookup)
        self._sorted_cache: dict[str, List[float]] = {}
        
        # Track previous regime for change detection
        self._previous_regime: dict[str, VolatilityRegime] = {}
        
        logger.info(
            f"VolatilityRegimeDetector initialized "
            f"(lookback={lookback_days}d, atr_period={atr_period})"
        )
    
    async def detect_regime(self, symbol: str, timeframe: str = "1Day") -> VolatilityMetrics:
        """
        Detect current volatility regime for a symbol.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe for bars ("1Day", "1Hour", etc.)
        
        Returns:
            VolatilityMetrics with regime classification and adjustments
        """
        # Calculate current ATR
        current_atr = await self._calculate_current_atr(symbol, timeframe)
        
        # Get historical ATR distribution
        atr_history = await self._get_atr_history(symbol, timeframe)
        
        # Calculate percentile
        percentile = self._calculate_percentile(current_atr, atr_history)
        
        # Classify regime
        regime = self._classify_regime(percentile)
        
        # Check for regime change and emit metrics
        self._track_regime_change(symbol, regime)
        
        # Get regime-based adjustments
        spacing_mult, attempts_adj = self._get_regime_adjustments(regime)
        
        # Update metrics
        self._update_metrics(symbol, regime, spacing_mult)
        
        metrics = VolatilityMetrics(
            symbol=symbol,
            current_atr=current_atr,
            atr_percentile=percentile,
            regime=regime,
            lookback_period=self.lookback_days,
            timestamp=datetime.utcnow(),
            spacing_multiplier=spacing_mult,
            max_attempts_adjustment=attempts_adj
        )
        
        logger.info(f"Volatility regime detected: {metrics}")
        return metrics
    
    async def _calculate_current_atr(self, symbol: str, timeframe: str) -> float:
        """
        Calculate current Average True Range.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe for calculation
        
        Returns:
            Current ATR value
        """
        # Get recent bars for ATR calculation
        bars = await self.market_data.get_bars(
            symbol=symbol,
            timeframe=timeframe,
            limit=self.atr_period + 1
        )
        
        if not bars or len(bars) < 2:
            logger.warning(f"Insufficient data for ATR calculation: {symbol}")
            return 0.0
        
        # Calculate True Range for each period
        true_ranges = []
        for i in range(1, len(bars)):
            high = bars[i].high
            low = bars[i].low
            prev_close = bars[i-1].close
            
            # True Range = max(high-low, abs(high-prev_close), abs(low-prev_close))
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            true_ranges.append(tr)
        
        # Average True Range (simple moving average)
        atr = sum(true_ranges[-self.atr_period:]) / min(self.atr_period, len(true_ranges))
        
        return atr
    
    async def _get_atr_history(self, symbol: str, timeframe: str) -> List[float]:
        """
        Get historical ATR values for percentile calculation.
        
        Uses caching to avoid excessive API calls.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe for calculation
        
        Returns:
            List of historical ATR values
        """
        # Check cache freshness
        cache_key = f"{symbol}_{timeframe}"
        now = datetime.utcnow()
        
        if (cache_key in self._atr_cache and 
            cache_key in self._last_cache_update and
            now - self._last_cache_update[cache_key] < self._cache_ttl):
            # Use cached data
            cached_data = self._atr_cache[cache_key]
            return [atr for _, atr in cached_data]
        
        # Fetch fresh data
        logger.debug(f"Fetching ATR history for {symbol} ({self.lookback_days} days)")
        
        # Get historical bars
        bars = await self.market_data.get_bars(
            symbol=symbol,
            timeframe=timeframe,
            limit=self.lookback_days + self.atr_period
        )
        
        if not bars or len(bars) < self.atr_period + 1:
            logger.warning(f"Insufficient historical data for {symbol}")
            return [0.0]
        
        # Calculate ATR for each period
        atr_values = []
        for i in range(self.atr_period, len(bars)):
            period_bars = bars[i-self.atr_period:i+1]
            
            true_ranges = []
            for j in range(1, len(period_bars)):
                high = period_bars[j].high
                low = period_bars[j].low
                prev_close = period_bars[j-1].close
                
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                true_ranges.append(tr)
            
            atr = sum(true_ranges) / len(true_ranges)
            timestamp = period_bars[-1].timestamp
            atr_values.append((timestamp, atr))
        
        # Update cache
        self._atr_cache[cache_key] = atr_values
        self._last_cache_update[cache_key] = now
        
        return [atr for _, atr in atr_values]
    
    def _calculate_percentile(self, value: float, distribution: List[float]) -> float:
        """
        Calculate percentile rank of a value in a distribution.
        
        Optimized with binary search for O(log N) performance.
        
        Args:
            value: Value to rank
            distribution: Historical distribution
        
        Returns:
            Percentile (0-100)
        """
        if not distribution:
            return 50.0  # Default to median
        
        # Use cached sorted list if available
        cache_key = f"{len(distribution)}_{hash(tuple(distribution[:5]))}"
        
        if cache_key in self._sorted_cache:
            sorted_dist = self._sorted_cache[cache_key]
        else:
            sorted_dist = sorted(distribution)
            self._sorted_cache[cache_key] = sorted_dist
            
            # Limit cache size (keep only 10 most recent)
            if len(self._sorted_cache) > 10:
                # Remove oldest entry
                oldest_key = next(iter(self._sorted_cache))
                del self._sorted_cache[oldest_key]
        
        # Binary search for insertion point (O(log N))
        insert_pos = bisect.bisect_left(sorted_dist, value)
        percentile = (insert_pos / len(sorted_dist)) * 100
        
        return percentile
    
    def _classify_regime(self, percentile: float) -> VolatilityRegime:
        """
        Classify volatility regime based on percentile.
        
        Args:
            percentile: ATR percentile (0-100)
        
        Returns:
            VolatilityRegime classification
        """
        if percentile < 20:
            return VolatilityRegime.ULTRA_LOW
        elif percentile < 40:
            return VolatilityRegime.LOW
        elif percentile < 60:
            return VolatilityRegime.NORMAL
        elif percentile < 80:
            return VolatilityRegime.ELEVATED
        elif percentile < 95:
            return VolatilityRegime.HIGH
        else:
            return VolatilityRegime.EXTREME
    
    def _get_regime_adjustments(self, regime: VolatilityRegime) -> Tuple[float, int]:
        """
        Get DCA spacing and attempt adjustments for volatility regime.
        
        Args:
            regime: Volatility regime
        
        Returns:
            Tuple of (spacing_multiplier, max_attempts_adjustment)
        """
        # Regime-based adjustments
        adjustments = {
            VolatilityRegime.ULTRA_LOW: (0.5, +1),    # Tighter spacing, +1 attempt
            VolatilityRegime.LOW: (0.75, 0),          # Slightly tighter spacing
            VolatilityRegime.NORMAL: (1.0, 0),        # Standard spacing
            VolatilityRegime.ELEVATED: (1.5, 0),      # Wider spacing
            VolatilityRegime.HIGH: (2.0, -1),         # Much wider spacing, -1 attempt
            VolatilityRegime.EXTREME: (3.0, -2),      # Maximum spacing, -2 attempts
        }
        
        return adjustments[regime]
    
    def get_adjusted_support_level(self,
                                   base_support: float,
                                   current_price: float,
                                   volatility_metrics: VolatilityMetrics) -> float:
        """
        Adjust support level based on volatility regime.
        
        In high volatility, widen the spacing to avoid premature DCA triggers.
        In low volatility, tighten spacing for more aggressive averaging.
        
        Args:
            base_support: Base support level
            current_price: Current market price
            volatility_metrics: Current volatility metrics
        
        Returns:
            Adjusted support level
        """
        # Calculate base distance
        distance = current_price - base_support
        
        # Apply regime multiplier
        adjusted_distance = distance * volatility_metrics.spacing_multiplier
        
        # Calculate adjusted support
        adjusted_support = current_price - adjusted_distance
        
        logger.debug(
            f"Support adjustment: base={base_support:.2f}, "
            f"adjusted={adjusted_support:.2f} "
            f"(regime={volatility_metrics.regime.value}, mult={volatility_metrics.spacing_multiplier:.2f}x)"
        )
        
        return adjusted_support
    
    def get_adjusted_max_attempts(self,
                                  base_max_attempts: int,
                                  volatility_metrics: VolatilityMetrics) -> int:
        """
        Adjust maximum DCA attempts based on volatility regime.
        
        Args:
            base_max_attempts: Base maximum attempts from config
            volatility_metrics: Current volatility metrics
        
        Returns:
            Adjusted maximum attempts (minimum 1)
        """
        adjusted = base_max_attempts + volatility_metrics.max_attempts_adjustment
        
        # Ensure at least 1 attempt
        adjusted = max(1, adjusted)
        
        logger.debug(
            f"Max attempts adjustment: base={base_max_attempts}, "
            f"adjusted={adjusted} (regime={volatility_metrics.regime.value})"
        )
        
        return adjusted
    
    def _track_regime_change(self, symbol: str, new_regime: VolatilityRegime):
        """
        Track regime changes and emit metrics.
        
        Args:
            symbol: Trading symbol
            new_regime: New volatility regime
        """
        if symbol in self._previous_regime:
            old_regime = self._previous_regime[symbol]
            
            if old_regime != new_regime:
                # Regime changed - emit metric
                volatility_regime_changes_total.labels(
                    symbol=symbol,
                    from_regime=old_regime.value,
                    to_regime=new_regime.value
                ).inc()
                
                logger.info(
                    f"📊 Volatility regime change: {symbol} {old_regime.value} → {new_regime.value}",
                    extra={
                        'component': 'VolatilityRegimeDetector',
                        'symbol': symbol,
                        'from_regime': old_regime.value,
                        'to_regime': new_regime.value
                    }
                )
        
        # Update previous regime
        self._previous_regime[symbol] = new_regime
    
    def _update_metrics(self, symbol: str, regime: VolatilityRegime, spacing_mult: float):
        """
        Update Prometheus metrics.
        
        Args:
            symbol: Trading symbol
            regime: Current volatility regime
            spacing_mult: Spacing multiplier
        """
        # Map regime to numeric value
        regime_values = {
            VolatilityRegime.ULTRA_LOW: 0,
            VolatilityRegime.LOW: 1,
            VolatilityRegime.NORMAL: 2,
            VolatilityRegime.ELEVATED: 3,
            VolatilityRegime.HIGH: 4,
            VolatilityRegime.EXTREME: 5,
        }
        
        volatility_regime_gauge.labels(symbol=symbol).set(regime_values[regime])
        dca_spacing_multiplier_gauge.labels(symbol=symbol, regime=regime.value).set(spacing_mult)
    
    async def get_regime_summary(self, symbols: List[str]) -> dict[str, VolatilityMetrics]:
        """
        Get volatility regime summary for multiple symbols.
        
        Args:
            symbols: List of symbols to analyze
        
        Returns:
            Dictionary mapping symbol to VolatilityMetrics
        """
        tasks = [self.detect_regime(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        summary = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to detect regime for {symbol}: {result}")
            else:
                summary[symbol] = result
        
        return summary
