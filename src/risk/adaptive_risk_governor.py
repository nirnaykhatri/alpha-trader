"""
Adaptive Risk Governor

Dynamically adjusts risk exposure based on recent rejection rate history.
Provides throttle factor that reduces position sizing during periods of high
risk rejection to prevent compounding failures.
"""

import logging
from collections import deque
from typing import Deque, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class ThrottleSnapshot:
    """Snapshot of current throttle state."""
    throttle_factor: float  # 0.5 - 1.0
    rejection_rate: float  # 0.0 - 1.0
    window_size: int
    decisions_tracked: int
    timestamp: datetime


class AdaptiveRiskGovernor:
    """
    Adaptive risk governor that adjusts sizing based on rejection history.
    
    Monitors recent risk decision outcomes and reduces position sizing when
    rejection rates are high, with hysteresis to prevent oscillation.
    
    Throttle Factor Mapping:
    - 0% rejection rate → 1.0 (no throttling)
    - 30% rejection rate → 0.85
    - 60% rejection rate → 0.5 (maximum throttling)
    - >60% rejection rate → 0.5 (floor)
    
    Example:
        governor = AdaptiveRiskGovernor(window=50, min_throttle=0.5)
        
        # Record decision outcomes
        governor.record_decision(approved=True)
        governor.record_decision(approved=False)
        
        # Get current throttle factor
        throttle = governor.get_throttle_factor()
        adjusted_size = base_size * throttle
        
        # Check if governor is in protective mode
        if governor.is_throttled():
            logger.warning(f"Risk throttling active: {throttle:.2%}")
    """
    
    def __init__(
        self,
        window: int = 50,
        min_throttle: float = 0.5,
        max_throttle: float = 1.0,
        hysteresis: float = 0.05
    ):
        """
        Initialize adaptive risk governor.
        
        Args:
            window: Number of recent decisions to track
            min_throttle: Minimum throttle factor (maximum restriction)
            max_throttle: Maximum throttle factor (no restriction)
            hysteresis: Hysteresis band to prevent oscillation
        """
        self.window = window
        self.min_throttle = min_throttle
        self.max_throttle = max_throttle
        self.hysteresis = hysteresis
        
        # Use deque for O(1) append/pop
        self.decisions: Deque[bool] = deque(maxlen=window)
        
        # Track consecutive rejections for rapid response
        self.consecutive_rejections = 0
        
        # Last computed throttle (for hysteresis)
        self._last_throttle: Optional[float] = None
        
        logger.info(
            f"AdaptiveRiskGovernor initialized: "
            f"window={window}, throttle_range=[{min_throttle}, {max_throttle}], "
            f"hysteresis={hysteresis}"
        )
    
    def record_decision(self, approved: bool) -> None:
        """
        Record a risk decision outcome.
        
        Args:
            approved: Whether the risk decision was approved
        """
        self.decisions.append(approved)
        
        # Update consecutive rejection counter
        if approved:
            self.consecutive_rejections = 0
        else:
            self.consecutive_rejections += 1
        
        # Log if entering high-rejection zone
        if len(self.decisions) >= 10:  # Need minimum samples
            rejection_rate = self.get_rejection_rate()
            
            if rejection_rate >= 0.5:
                logger.warning(
                    f"High rejection rate: {rejection_rate:.1%} "
                    f"({sum(not d for d in self.decisions)}/{len(self.decisions)} rejected)"
                )
            
            if self.consecutive_rejections >= 5:
                logger.error(
                    f"Consecutive rejections: {self.consecutive_rejections} "
                    f"(circuit breaker zone)"
                )
    
    def get_rejection_rate(self) -> float:
        """
        Calculate current rejection rate.
        
        Returns:
            Rejection rate (0.0 - 1.0), or 0.0 if no decisions recorded
        """
        if not self.decisions:
            return 0.0
        
        rejections = sum(not approved for approved in self.decisions)
        return rejections / len(self.decisions)
    
    def get_throttle_factor(self) -> float:
        """
        Calculate current throttle factor with hysteresis.
        
        Returns:
            Throttle factor between min_throttle and max_throttle
        """
        if not self.decisions:
            return self.max_throttle
        
        rejection_rate = self.get_rejection_rate()
        
        # Emergency circuit breaker for consecutive rejections
        if self.consecutive_rejections >= 10:
            logger.critical(
                f"Circuit breaker activated: {self.consecutive_rejections} "
                f"consecutive rejections"
            )
            return self.min_throttle
        
        # Calculate base throttle factor
        # Linear interpolation: 0% rejection → 1.0, 60%+ rejection → 0.5
        if rejection_rate <= 0.0:
            raw_throttle = self.max_throttle
        elif rejection_rate >= 0.6:
            raw_throttle = self.min_throttle
        else:
            # Linear scale between max and min
            raw_throttle = self.max_throttle - (
                (rejection_rate / 0.6) * (self.max_throttle - self.min_throttle)
            )
        
        # Apply hysteresis to prevent oscillation
        if self._last_throttle is not None:
            delta = abs(raw_throttle - self._last_throttle)
            
            if delta < self.hysteresis:
                # Within hysteresis band - keep previous value
                return self._last_throttle
        
        # Update and return
        self._last_throttle = raw_throttle
        return raw_throttle
    
    def is_throttled(self) -> bool:
        """
        Check if governor is currently throttling.
        
        Returns:
            True if throttle factor < max_throttle
        """
        return self.get_throttle_factor() < self.max_throttle
    
    def get_snapshot(self) -> ThrottleSnapshot:
        """
        Get current throttle state snapshot.
        
        Returns:
            ThrottleSnapshot with current state
        """
        return ThrottleSnapshot(
            throttle_factor=self.get_throttle_factor(),
            rejection_rate=self.get_rejection_rate(),
            window_size=self.window,
            decisions_tracked=len(self.decisions),
            timestamp=datetime.utcnow()
        )
    
    def reset(self) -> None:
        """Reset governor state (for testing or manual intervention)."""
        self.decisions.clear()
        self.consecutive_rejections = 0
        self._last_throttle = None
        logger.info("AdaptiveRiskGovernor reset")
    
    def get_statistics(self) -> dict:
        """
        Get detailed statistics for monitoring.
        
        Returns:
            Dictionary with throttle statistics
        """
        if not self.decisions:
            return {
                'throttle_factor': self.max_throttle,
                'rejection_rate': 0.0,
                'decisions_tracked': 0,
                'consecutive_rejections': 0,
                'is_throttled': False
            }
        
        approvals = sum(self.decisions)
        rejections = len(self.decisions) - approvals
        
        return {
            'throttle_factor': self.get_throttle_factor(),
            'rejection_rate': self.get_rejection_rate(),
            'decisions_tracked': len(self.decisions),
            'approvals': approvals,
            'rejections': rejections,
            'consecutive_rejections': self.consecutive_rejections,
            'is_throttled': self.is_throttled(),
            'window_size': self.window,
            'min_throttle': self.min_throttle,
            'max_throttle': self.max_throttle
        }
