"""
Concrete Confidence Factor Implementations

Pluggable confidence scoring factors for DCA decision making.
"""

import logging
from typing import Optional

from src.domain import DecisionContext
from src.strategies.confidence.confidence_factor import IConfidenceFactor, ConfidenceScore

logger = logging.getLogger(__name__)


class TechnicalLevelConfidenceFactor(IConfidenceFactor):
    """
    Evaluate confidence based on proximity to technical support/resistance levels.
    
    Higher confidence when price is closer to established support (for longs)
    or resistance (for shorts).
    """
    
    @property
    def name(self) -> str:
        return "Technical Level Proximity"
    
    async def evaluate(self, context: DecisionContext) -> ConfidenceScore:
        """
        Score confidence based on technical level proximity.
        
        Logic:
        - For longs: Higher score when price is at/near support
        - For shorts: Higher score when price is at/near resistance
        - Score decreases with distance from levels
        """
        if context.is_long():
            # Check support level proximity
            support_level = context.at_support_level(tolerance=0.02)  # 2% tolerance
            
            if support_level:
                # Direct hit on support level
                distance_pct = abs(context.current_price - support_level) / support_level
                score = 1.0 - (distance_pct / 0.02)  # Linear decay within tolerance
                
                return self._create_score(
                    score=score,
                    reason=f"Price ${context.current_price:.2f} at support ${support_level:.2f}",
                    metadata={
                        'support_level': support_level,
                        'distance_pct': distance_pct,
                        'tolerance': 0.02
                    }
                )
            else:
                # Not at support level
                return self._create_score(
                    score=0.3,
                    reason=f"Price ${context.current_price:.2f} not at support",
                    metadata={'support_levels': context.support_levels}
                )
        
        elif context.is_short():
            # Check resistance level proximity
            resistance_level = context.at_resistance_level(tolerance=0.02)
            
            if resistance_level:
                distance_pct = abs(context.current_price - resistance_level) / resistance_level
                score = 1.0 - (distance_pct / 0.02)
                
                return self._create_score(
                    score=score,
                    reason=f"Price ${context.current_price:.2f} at resistance ${resistance_level:.2f}",
                    metadata={
                        'resistance_level': resistance_level,
                        'distance_pct': distance_pct,
                        'tolerance': 0.02
                    }
                )
            else:
                return self._create_score(
                    score=0.3,
                    reason=f"Price ${context.current_price:.2f} not at resistance",
                    metadata={'resistance_levels': context.resistance_levels}
                )
        
        # No position
        return self._create_score(
            score=0.5,
            reason="No active position",
            metadata={}
        )


class VolumeConfidenceFactor(IConfidenceFactor):
    """
    Evaluate confidence based on volume characteristics.
    
    Higher confidence when volume confirms price action.
    """
    
    def __init__(self, weight: float = 1.0, avg_volume_threshold: float = 1.5):
        """
        Initialize volume confidence factor.
        
        Args:
            weight: Relative weight of this factor
            avg_volume_threshold: Multiplier of average volume for high confidence
        """
        super().__init__(weight)
        self.avg_volume_threshold = avg_volume_threshold
    
    @property
    def name(self) -> str:
        return "Volume Confirmation"
    
    async def evaluate(self, context: DecisionContext) -> ConfidenceScore:
        """
        Score confidence based on volume.
        
        Higher scores when:
        - Volume is above average (indicates conviction)
        - Volume trend supports price action
        """
        if context.volume == 0:
            return self._create_score(
                score=0.5,
                reason="Volume data unavailable",
                metadata={}
            )
        
        # Simplified scoring: higher volume = higher confidence
        # In production, compare to moving average
        if context.volume > self.avg_volume_threshold:
            score = min(1.0, context.volume / (self.avg_volume_threshold * 2))
            return self._create_score(
                score=score,
                reason=f"Above-average volume: {context.volume:.0f}",
                metadata={
                    'volume': context.volume,
                    'threshold': self.avg_volume_threshold
                }
            )
        else:
            score = 0.4
            return self._create_score(
                score=score,
                reason=f"Below-average volume: {context.volume:.0f}",
                metadata={
                    'volume': context.volume,
                    'threshold': self.avg_volume_threshold
                }
            )


class VolatilityConfidenceFactor(IConfidenceFactor):
    """
    Evaluate confidence based on volatility levels.
    
    Lower volatility generally increases confidence for DCA.
    """
    
    def __init__(self, weight: float = 1.0, max_volatility: float = 0.05):
        """
        Initialize volatility confidence factor.
        
        Args:
            weight: Relative weight of this factor
            max_volatility: Maximum acceptable volatility (5% default)
        """
        super().__init__(weight)
        self.max_volatility = max_volatility
    
    @property
    def name(self) -> str:
        return "Volatility Assessment"
    
    async def evaluate(self, context: DecisionContext) -> ConfidenceScore:
        """
        Score confidence inversely to volatility.
        
        Lower volatility = higher confidence for DCA execution.
        """
        volatility = context.volatility
        
        if volatility == 0:
            return self._create_score(
                score=0.7,
                reason="Volatility data unavailable, assuming moderate",
                metadata={}
            )
        
        if volatility <= self.max_volatility:
            # Linear decay from 1.0 at 0% to 0.5 at max_volatility
            score = 1.0 - (volatility / self.max_volatility) * 0.5
            return self._create_score(
                score=score,
                reason=f"Acceptable volatility: {volatility:.2%}",
                metadata={
                    'volatility': volatility,
                    'max_volatility': self.max_volatility
                }
            )
        else:
            # High volatility reduces confidence significantly
            score = max(0.2, 0.5 - (volatility - self.max_volatility) * 5)
            return self._create_score(
                score=score,
                reason=f"High volatility: {volatility:.2%}",
                metadata={
                    'volatility': volatility,
                    'max_volatility': self.max_volatility
                }
            )


class TrendStrengthConfidenceFactor(IConfidenceFactor):
    """
    Evaluate confidence based on overall trend strength.
    
    DCA is more confident when trend remains intact.
    """
    
    @property
    def name(self) -> str:
        return "Trend Strength"
    
    async def evaluate(self, context: DecisionContext) -> ConfidenceScore:
        """
        Score confidence based on trend alignment.
        
        For longs: Higher score when support levels are rising
        For shorts: Higher score when resistance levels are falling
        """
        if not context.has_position():
            return self._create_score(
                score=0.5,
                reason="No active position",
                metadata={}
            )
        
        # Check if progressive DCA would improve position
        if context.last_dca_price:
            would_improve = context.price_improvement_for_dca(context.current_price)
            
            if would_improve:
                return self._create_score(
                    score=0.9,
                    reason=f"DCA would improve position average",
                    metadata={
                        'current_price': context.current_price,
                        'last_dca_price': context.last_dca_price,
                        'direction': context.position_direction.value if context.position_direction else None
                    }
                )
            else:
                return self._create_score(
                    score=0.2,
                    reason=f"DCA would NOT improve position average",
                    metadata={
                        'current_price': context.current_price,
                        'last_dca_price': context.last_dca_price
                    }
                )
        
        # First DCA attempt
        return self._create_score(
            score=0.7,
            reason="First DCA attempt",
            metadata={'dca_attempts': context.dca_attempts}
        )
