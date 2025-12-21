"""
DCA Level Selector

Handles support/resistance level calculation, technical analysis logic,
level filtering by confidence, and progressive DCA validation.
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from src.strategies.support_calculator import TechnicalSupportCalculator
from src.strategies.config_accessor import StrategyConfigAccessor
from src.interfaces import IConfigurationManager

logger = logging.getLogger(__name__)


@dataclass
class DCADecision:
    """Result of DCA evaluation."""
    should_dca: bool
    reason: str
    message: str
    support_level: Optional[float] = None
    confidence: Optional[float] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class ProgressiveValidation:
    """Result of progressive DCA price validation."""
    is_progressive: bool
    reason: str
    message: str
    last_price: Optional[float] = None
    required_direction: Optional[str] = None


class DCALevelSelector:
    """
    Selects DCA entry levels based on technical analysis.
    
    Uses support/resistance levels and progressive price validation
    to determine optimal DCA entry points.
    """
    
    def __init__(
        self,
        support_calculator: TechnicalSupportCalculator,
        config: IConfigurationManager
    ):
        """
        Initialize DCA level selector.
        
        Args:
            support_calculator: Technical support calculator
            config: Configuration manager
        """
        self.support_calculator = support_calculator
        self.config = config
        self.config_accessor = StrategyConfigAccessor(config)
        logger.info("DCALevelSelector initialized")
    
    def validate_progressive_dca(
        self,
        proposed_price: float,
        last_dca_price: Optional[float],
        direction: str
    ) -> ProgressiveValidation:
        """
        Validate that DCA price is progressive (improves position average).
        
        Args:
            proposed_price: Proposed DCA entry price
            last_dca_price: Last DCA entry price
            direction: Position direction ('long' or 'short')
            
        Returns:
            ProgressiveValidation result
        """
        if last_dca_price is None:
            return ProgressiveValidation(
                is_progressive=True,
                reason='first_dca',
                message='First DCA entry - no price comparison needed'
            )
        
        if direction.lower() == 'long':
            # Long: New DCA must be LOWER than last
            if proposed_price >= last_dca_price:
                logger.warning(
                    f"🚫 NON-PROGRESSIVE DCA REJECTED: Long position "
                    f"${proposed_price:.2f} >= ${last_dca_price:.2f}"
                )
                return ProgressiveValidation(
                    is_progressive=False,
                    reason='non_progressive_price',
                    message=f'Price ${proposed_price:.2f} not below last DCA ${last_dca_price:.2f}',
                    last_price=last_dca_price,
                    required_direction='below'
                )
        else:
            # Short: New DCA must be HIGHER than last
            if proposed_price <= last_dca_price:
                logger.warning(
                    f"🚫 NON-PROGRESSIVE DCA REJECTED: Short position "
                    f"${proposed_price:.2f} <= ${last_dca_price:.2f}"
                )
                return ProgressiveValidation(
                    is_progressive=False,
                    reason='non_progressive_price',
                    message=f'Price ${proposed_price:.2f} not above last DCA ${last_dca_price:.2f}',
                    last_price=last_dca_price,
                    required_direction='above'
                )
        
        return ProgressiveValidation(
            is_progressive=True,
            reason='progressive_price',
            message=f'Price ${proposed_price:.2f} is progressive',
            last_price=last_dca_price
        )
    
    async def evaluate_support_breach(
        self,
        symbol: str,
        current_price: float,
        position_average: float,
        timeframe: str
    ) -> DCADecision:
        """
        Evaluate if current price has breached support levels for long DCA.
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            position_average: Position average price
            timeframe: Analysis timeframe
            
        Returns:
            DCADecision with recommendation
        """
        try:
            logger.debug(
                f"🔍 SUPPORT ANALYSIS: {symbol} @ ${current_price:.2f} using {timeframe}"
            )
            
            # Calculate position-aware support levels
            support_data = await self.support_calculator.calculate_support_levels_for_position(
                symbol, timeframe, position_average, "long"
            )
            
            if not support_data or not support_data.levels:
                logger.warning(
                    f"⚠️ NO SUPPORT DATA: {symbol} ({timeframe}) - technical analysis unavailable"
                )
                return DCADecision(
                    should_dca=False,
                    reason='no_support_data',
                    message=f'No support levels found for {timeframe} timeframe'
                )
            
            # Filter by confidence
            min_confidence = self.config_accessor.get_min_support_confidence()
            
            valid_supports = [
                level for level in support_data.levels
                if level.confidence >= min_confidence
            ]
            
            logger.info(f"🔍 SUPPORT ANALYSIS: {symbol}")
            logger.info(f"   Valid Support Levels: {len(valid_supports)}")
            
            if not valid_supports:
                return DCADecision(
                    should_dca=False,
                    reason='no_position_support',
                    message=f'No support levels suitable for position averaging'
                )
            
            # Get nearest strong support
            nearest_support = max(valid_supports, key=lambda x: x.price)
            support_price = nearest_support.price
            support_confidence = nearest_support.confidence
            
            # Check breach with buffer
            support_buffer = self.config_accessor.get_support_buffer_percent()
            trigger_price = support_price * (1 - support_buffer)
            
            if current_price <= trigger_price:
                logger.info(
                    f"🎯 SUPPORT BREACH: {symbol} @ ${current_price:.2f} "
                    f"(support: ${support_price:.2f}, conf: {support_confidence:.1%})"
                )
                return DCADecision(
                    should_dca=True,
                    reason='support_breach',
                    message=f'Price breached support at ${support_price:.2f}',
                    support_level=support_price,
                    confidence=support_confidence,
                    details={
                        'current_price': current_price,
                        'support_price': support_price,
                        'trigger_price': trigger_price,
                        'confidence': support_confidence
                    }
                )
            
            return DCADecision(
                should_dca=False,
                reason='no_breach',
                message=f'Price above support trigger ${trigger_price:.2f}',
                support_level=support_price,
                confidence=support_confidence
            )
            
        except Exception as e:
            logger.error(f"Error evaluating support breach for {symbol}: {e}")
            return DCADecision(
                should_dca=False,
                reason='error',
                message=f'Error during analysis: {str(e)}'
            )
    
    async def evaluate_resistance_breach(
        self,
        symbol: str,
        current_price: float,
        position_average: float,
        timeframe: str
    ) -> DCADecision:
        """
        Evaluate if current price has breached resistance levels for short DCA.
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            position_average: Position average price
            timeframe: Analysis timeframe
            
        Returns:
            DCADecision with recommendation
        """
        try:
            logger.debug(
                f"🔍 RESISTANCE ANALYSIS: {symbol} @ ${current_price:.2f} using {timeframe}"
            )
            
            # Calculate position-aware resistance levels
            resistance_data = await self.support_calculator.calculate_resistance_levels_for_position(
                symbol=symbol, timeframe=timeframe, 
                position_avg_price=position_average, position_type="short"
            )
            
            if not resistance_data or not resistance_data.levels:
                logger.warning(
                    f"⚠️ NO RESISTANCE DATA: {symbol} ({timeframe})"
                )
                return DCADecision(
                    should_dca=False,
                    reason='no_resistance_data',
                    message=f'No resistance levels found for {timeframe} timeframe'
                )
            
            # Filter by confidence
            min_confidence = self.config_accessor.get_min_resistance_confidence()
            
            valid_resistances = [
                level for level in resistance_data.levels
                if level.confidence >= min_confidence
            ]
            
            if not valid_resistances:
                return DCADecision(
                    should_dca=False,
                    reason='no_position_resistance',
                    message=f'No resistance levels suitable for position averaging'
                )
            
            # Get nearest strong resistance
            nearest_resistance = min(valid_resistances, key=lambda x: x.price)
            resistance_price = nearest_resistance.price
            resistance_confidence = nearest_resistance.confidence
            
            # Check breach with buffer
            resistance_buffer = self.config_accessor.get_resistance_buffer_percent()
            trigger_price = resistance_price * (1 + resistance_buffer)
            
            if current_price >= trigger_price:
                logger.info(
                    f"🎯 RESISTANCE BREACH: {symbol} @ ${current_price:.2f} "
                    f"(resistance: ${resistance_price:.2f}, conf: {resistance_confidence:.1%})"
                )
                return DCADecision(
                    should_dca=True,
                    reason='resistance_breach',
                    message=f'Price breached resistance at ${resistance_price:.2f}',
                    support_level=resistance_price,
                    confidence=resistance_confidence,
                    details={
                        'current_price': current_price,
                        'resistance_price': resistance_price,
                        'trigger_price': trigger_price,
                        'confidence': resistance_confidence
                    }
                )
            
            return DCADecision(
                should_dca=False,
                reason='no_breach',
                message=f'Price below resistance trigger ${trigger_price:.2f}',
                support_level=resistance_price,
                confidence=resistance_confidence
            )
            
        except Exception as e:
            logger.error(f"Error evaluating resistance breach for {symbol}: {e}")
            return DCADecision(
                should_dca=False,
                reason='error',
                message=f'Error during analysis: {str(e)}'
            )
