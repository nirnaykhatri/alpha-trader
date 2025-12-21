"""
Confidence Calibration Store

Implements dynamic confidence weighting based on realized outcomes.
Adjusts factor weights using feedback from actual trade performance.
"""

import logging
from collections import defaultdict
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class OutcomeRecord:
    """Record of a single trade outcome."""
    factor_name: str
    realized_profit_pct: float
    timestamp: datetime
    symbol: str
    confidence_score: float


class ConfidenceCalibrationStore:
    """
    Dynamic confidence calibration using feedback from realized outcomes.
    
    Tracks the accuracy of confidence factors by comparing their predictions
    to actual trade outcomes, then adjusts weights accordingly.
    
    Example:
        store = ConfidenceCalibrationStore(window_size=50)
        
        # Record outcome when position closes
        store.record_outcome(
            factor_name='TechnicalFactor',
            realized_profit=2.5,  # 2.5% profit
            symbol='AAPL',
            confidence_score=0.85
        )
        
        # Get dynamic weight (1.0 = baseline)
        weight = store.get_dynamic_weight('TechnicalFactor')
        # Returns value between 0.5 and 1.5 based on historical accuracy
    """
    
    def __init__(
        self,
        window_size: int = 50,
        min_samples: int = 10,
        weight_range: tuple = (0.5, 1.5)
    ):
        """
        Initialize calibration store.
        
        Args:
            window_size: Number of recent outcomes to consider
            min_samples: Minimum samples before adjusting weights
            weight_range: (min_weight, max_weight) bounds
        """
        self.window_size = window_size
        self.min_samples = min_samples
        self.min_weight, self.max_weight = weight_range
        
        # Store outcomes per factor
        self.outcomes: Dict[str, List[OutcomeRecord]] = defaultdict(list)
        
        # Cache computed weights
        self._weight_cache: Dict[str, tuple[float, datetime]] = {}
        self._cache_ttl = timedelta(minutes=5)
        
        logger.info(
            f"ConfidenceCalibrationStore initialized: "
            f"window={window_size}, min_samples={min_samples}, "
            f"range={weight_range}"
        )
    
    def record_outcome(
        self,
        factor_name: str,
        realized_profit_pct: float,
        symbol: str,
        confidence_score: float
    ) -> None:
        """
        Record outcome of a trade for calibration.
        
        Args:
            factor_name: Name of confidence factor
            realized_profit_pct: Realized profit/loss percentage
            symbol: Trading symbol
            confidence_score: Original confidence score (0-1)
        """
        record = OutcomeRecord(
            factor_name=factor_name,
            realized_profit_pct=realized_profit_pct,
            timestamp=datetime.utcnow(),
            symbol=symbol,
            confidence_score=confidence_score
        )
        
        self.outcomes[factor_name].append(record)
        
        # Trim to window size
        if len(self.outcomes[factor_name]) > self.window_size:
            self.outcomes[factor_name] = self.outcomes[factor_name][-self.window_size:]
        
        # Invalidate cache for this factor
        if factor_name in self._weight_cache:
            del self._weight_cache[factor_name]
        
        logger.info(
            f"Recorded outcome: {factor_name} on {symbol}: "
            f"{realized_profit_pct:+.2f}% (confidence: {confidence_score:.2f})"
        )
    
    def get_dynamic_weight(self, factor_name: str) -> float:
        """
        Get dynamic weight for a confidence factor based on performance.
        
        Args:
            factor_name: Name of confidence factor
            
        Returns:
            Dynamic weight between min_weight and max_weight
            Default 1.0 if insufficient data
        """
        # Check cache
        if factor_name in self._weight_cache:
            cached_weight, cached_time = self._weight_cache[factor_name]
            if datetime.utcnow() - cached_time < self._cache_ttl:
                return cached_weight
        
        outcomes = self.outcomes.get(factor_name, [])
        
        # Need minimum samples for calibration
        if len(outcomes) < self.min_samples:
            logger.debug(
                f"{factor_name}: Insufficient samples "
                f"({len(outcomes)}/{self.min_samples}), using default weight 1.0"
            )
            return 1.0
        
        # Calculate performance metrics
        recent_outcomes = outcomes[-self.window_size:]
        
        # Average realized profit
        avg_profit = sum(r.realized_profit_pct for r in recent_outcomes) / len(recent_outcomes)
        
        # Win rate (positive outcomes)
        wins = sum(1 for r in recent_outcomes if r.realized_profit_pct > 0)
        win_rate = wins / len(recent_outcomes)
        
        # Confidence-weighted performance (rewards accurate high-confidence predictions)
        weighted_perf = sum(
            r.realized_profit_pct * r.confidence_score
            for r in recent_outcomes
        ) / len(recent_outcomes)
        
        # Combine metrics (normalized to range -1 to +1)
        profit_score = max(-1.0, min(1.0, avg_profit / 10.0))  # ±10% profit → ±1
        win_score = (win_rate - 0.5) * 2  # 0-100% → -1 to +1
        weighted_score = max(-1.0, min(1.0, weighted_perf / 10.0))
        
        # Weighted combination
        combined_score = (
            0.4 * profit_score +
            0.3 * win_score +
            0.3 * weighted_score
        )
        
        # Map to weight range (0.5 - 1.5)
        # Score of -1 → min_weight (0.5)
        # Score of 0 → 1.0 (baseline)
        # Score of +1 → max_weight (1.5)
        weight = 1.0 + (combined_score * 0.5)
        weight = max(self.min_weight, min(self.max_weight, weight))
        
        # Cache result
        self._weight_cache[factor_name] = (weight, datetime.utcnow())
        
        logger.info(
            f"{factor_name} calibration: "
            f"samples={len(recent_outcomes)}, "
            f"avg_profit={avg_profit:.2f}%, "
            f"win_rate={win_rate:.1%}, "
            f"weight={weight:.3f}"
        )
        
        return weight
    
    def get_factor_statistics(self, factor_name: str) -> Optional[Dict]:
        """
        Get detailed statistics for a factor.
        
        Args:
            factor_name: Name of confidence factor
            
        Returns:
            Dictionary with performance metrics or None
        """
        outcomes = self.outcomes.get(factor_name, [])
        
        if not outcomes:
            return None
        
        recent = outcomes[-self.window_size:]
        
        profits = [r.realized_profit_pct for r in recent]
        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p <= 0]
        
        return {
            'total_trades': len(recent),
            'avg_profit_pct': sum(profits) / len(profits) if profits else 0,
            'win_rate': len(wins) / len(recent) if recent else 0,
            'avg_win_pct': sum(wins) / len(wins) if wins else 0,
            'avg_loss_pct': sum(losses) / len(losses) if losses else 0,
            'best_trade_pct': max(profits) if profits else 0,
            'worst_trade_pct': min(profits) if profits else 0,
            'current_weight': self.get_dynamic_weight(factor_name)
        }
    
    def get_all_statistics(self) -> Dict[str, Dict]:
        """Get statistics for all tracked factors."""
        return {
            factor: self.get_factor_statistics(factor)
            for factor in self.outcomes.keys()
        }
    
    def reset_factor(self, factor_name: str) -> None:
        """Reset calibration data for a specific factor."""
        if factor_name in self.outcomes:
            del self.outcomes[factor_name]
        
        if factor_name in self._weight_cache:
            del self._weight_cache[factor_name]
        
        logger.info(f"Reset calibration for {factor_name}")
    
    def reset_all(self) -> None:
        """Reset all calibration data."""
        self.outcomes.clear()
        self._weight_cache.clear()
        logger.info("Reset all calibration data")
