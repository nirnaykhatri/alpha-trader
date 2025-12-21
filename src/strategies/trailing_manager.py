"""
Trailing Stop Manager
Manages trailing stop adjustments for profitable positions.
Tracks peak prices and adjusts trailing stops based on profit thresholds.
"""

from src.interfaces import IConfigurationManager
from src.core.logging_config import get_logger
from src.strategies.position_state import PositionState, TradePhase

logger = get_logger(__name__)


class TrailingManager:
    """
    Manages trailing stops for long and short positions.
    Follows Single Responsibility Principle - only handles trailing stop logic.
    """
    
    def __init__(self, config: IConfigurationManager):
        """Initialize the trailing manager."""
        self.config = config
        
        # Load strategy configurations
        self.long_config = config.get_config('strategies.long_strategy', {})
        self.short_config = config.get_config('strategies.short_strategy', {})
    
    async def update_long_trailing(self, position: PositionState, close_position_callback) -> bool:
        """
        Update profit trailing for long positions.
        
        Args:
            position: Current position state
            close_position_callback: Callback function to close position when trailing stop hit
            
        Returns:
            True if trailing stop was hit and position closed, False otherwise
        """
        config = self.long_config
        current_price = position.current_price
        
        # Update peak price if we have a new high
        if current_price > position.peak_price:
            old_peak = position.peak_price
            position.peak_price = current_price
            position.trail_price = current_price * (1 - config.get('trailing_percentage', 0.02))
            logger.info(f"🏔️ NEW PEAK: {position.symbol} ${old_peak:.2f} → ${current_price:.2f} | Trail: ${position.trail_price:.2f}")
        
        # Check if trailing stop is hit
        if current_price <= position.trail_price:
            logger.info(f"🛑 TRAILING STOP HIT: {position.symbol} ${current_price:.2f} ≤ ${position.trail_price:.2f}")
            logger.info(f"   📊 Final profit from peak: {((position.trail_price / position.peak_price) - 1):.2%}")
            await close_position_callback(position.symbol)
            return True
        
        return False
    
    async def update_short_trailing(self, position: PositionState, close_position_callback) -> bool:
        """
        Update profit trailing for short positions.
        
        Args:
            position: Current position state
            close_position_callback: Callback function to close position when trailing stop hit
            
        Returns:
            True if trailing stop was hit and position closed, False otherwise
        """
        config = self.short_config
        current_price = position.current_price
        
        # Update peak price if we have a new low
        if current_price < position.peak_price:
            old_peak = position.peak_price
            position.peak_price = current_price
            position.trail_price = current_price * (1 + config.get('trailing_percentage', 0.02))
            logger.info(f"🏔️ NEW PEAK: {position.symbol} ${old_peak:.2f} → ${current_price:.2f} | Trail: ${position.trail_price:.2f}")
        
        # Check if trailing stop is hit
        if current_price >= position.trail_price:
            logger.info(f"🛑 TRAILING STOP HIT: {position.symbol} ${current_price:.2f} ≥ ${position.trail_price:.2f}")
            logger.info(f"   📊 Final profit from peak: {((position.peak_price / position.trail_price) - 1):.2%}")
            await close_position_callback(position.symbol)
            return True
        
        return False
    
    def should_start_trailing(self, position: PositionState) -> bool:
        """
        Check if position has reached profit threshold to start trailing.
        
        Args:
            position: Current position state
            
        Returns:
            True if trailing should start, False otherwise
        """
        config = self.long_config if position.direction.value == 'long' else self.short_config
        profit_threshold = config.get('profit_threshold', 0.01)  # Default 1%
        
        return position.profit_percentage >= profit_threshold
    
    def initialize_trailing(self, position: PositionState):
        """
        Initialize trailing stop for a position that just became profitable.
        
        Args:
            position: Current position state
        """
        config = self.long_config if position.direction.value == 'long' else self.short_config
        
        position.phase = TradePhase.PROFIT_TRAILING
        position.peak_price = position.current_price
        position.trail_price = position.current_price * (
            1 - config.get('trailing_percentage', 0.02) 
            if position.direction.value == 'long' 
            else 1 + config.get('trailing_percentage', 0.02)
        )
        
        logger.info(f"🎯 TRAILING STARTED: {position.symbol}")
        logger.info(f"   Peak: ${position.peak_price:.2f}")
        logger.info(f"   Trail: ${position.trail_price:.2f}")
        logger.info(f"   Profit: {position.profit_percentage:.2%}")
