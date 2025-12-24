"""
Trailing Stop Manager
Manages trailing stop adjustments for profitable positions.
Tracks peak prices and adjusts trailing stops based on profit thresholds.

Implements ITrailingManager interface for polymorphic trailing stop management.
Configuration is driven exclusively by bot's BotConfiguration from database.
"""

from typing import Callable, Awaitable
from src.core.logging_config import get_logger
from src.strategies.position_state import PositionState, TradePhase
from src.domain.bot_models import BotConfiguration
from src.interfaces import ITrailingManager, PositionStateType, ClosePositionCallback

logger = get_logger(__name__)


class TrailingManager(ITrailingManager):
    """
    Manages trailing stops for long and short positions.
    Follows Single Responsibility Principle - only handles trailing stop logic.
    
    Implements ITrailingManager interface for polymorphic strategy execution.
    Configuration is driven exclusively by bot's BotConfiguration from database.
    """
    
    def __init__(self, bot_config: BotConfiguration):
        """
        Initialize the trailing manager.
        
        Args:
            bot_config: Bot's configuration from database (REQUIRED)
            
        Raises:
            ValueError: If bot_config is None
        """
        if bot_config is None:
            raise ValueError("bot_config is required - configuration must come from database")
        self._bot_config = bot_config
    
    def set_bot_config(self, bot_config: BotConfiguration) -> None:
        """
        Update the bot's configuration at runtime.
        
        Args:
            bot_config: New bot configuration from the database
            
        Raises:
            ValueError: If bot_config is None
        """
        if bot_config is None:
            raise ValueError("bot_config cannot be None - database configuration required")
        self._bot_config = bot_config
    
    def _get_trailing_percentage(self) -> float:
        """
        Get trailing stop percentage from database configuration.
        
        Returns:
            Trailing percentage as a decimal (e.g., 0.02 for 2%)
            
        Raises:
            ValueError: If take_profit configuration is missing
        """
        if (self._bot_config.dca_config and 
            self._bot_config.dca_config.take_profit):
            # Convert percentage to decimal
            return self._bot_config.dca_config.take_profit.trailing_deviation / 100.0
        raise ValueError("take_profit.trailing_deviation configuration is required in database")
    
    def _get_profit_threshold(self) -> float:
        """
        Get profit threshold from database configuration.
        
        Returns:
            Profit threshold as a decimal (e.g., 0.01 for 1%)
            
        Raises:
            ValueError: If take_profit configuration is missing
        """
        if (self._bot_config.dca_config and 
            self._bot_config.dca_config.take_profit):
            # Convert percentage to decimal
            return self._bot_config.dca_config.take_profit.price_change_percent / 100.0
        raise ValueError("take_profit.price_change_percent configuration is required in database")
    
    async def update_long_trailing(self, position: PositionState, close_position_callback) -> bool:
        """
        Update profit trailing for long positions.
        
        Args:
            position: Current position state
            close_position_callback: Callback function to close position when trailing stop hit
            
        Returns:
            True if trailing stop was hit and position closed, False otherwise
        """
        trailing_percentage = self._get_trailing_percentage()
        current_price = position.current_price
        
        # Update peak price if we have a new high
        if current_price > position.peak_price:
            old_peak = position.peak_price
            position.peak_price = current_price
            position.trail_price = current_price * (1 - trailing_percentage)
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
        trailing_percentage = self._get_trailing_percentage()
        current_price = position.current_price
        
        # Update peak price if we have a new low
        if current_price < position.peak_price:
            old_peak = position.peak_price
            position.peak_price = current_price
            position.trail_price = current_price * (1 + trailing_percentage)
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
        profit_threshold = self._get_profit_threshold()
        return position.profit_percentage >= profit_threshold
    
    def initialize_trailing(self, position: PositionState):
        """
        Initialize trailing stop for a position that just became profitable.
        
        Args:
            position: Current position state
        """
        trailing_percentage = self._get_trailing_percentage()
        
        position.phase = TradePhase.PROFIT_TRAILING
        position.peak_price = position.current_price
        position.trail_price = position.current_price * (
            1 - trailing_percentage 
            if position.direction.value == 'long' 
            else 1 + trailing_percentage
        )
        
        logger.info(f"🎯 TRAILING STARTED: {position.symbol}")
        logger.info(f"   Peak: ${position.peak_price:.2f}")
        logger.info(f"   Trail: ${position.trail_price:.2f}")

    # =========================================================================
    # ITrailingManager Interface Implementation
    # =========================================================================
    
    async def update_trailing(
        self,
        position: PositionStateType,
        close_callback: ClosePositionCallback
    ) -> bool:
        """
        Update trailing stop for a position.
        
        Implements ITrailingManager.update_trailing by delegating to
        the appropriate direction-specific update method.
        
        Updates peak price if new high/low reached, recalculates trail price,
        and triggers close callback if trailing stop is hit.
        
        Args:
            position: Position state to update
            close_callback: Async callback to close position if stop hit
            
        Returns:
            True if trailing stop was hit and position closed
        """
        from src.strategies.position_state import PositionDirection
        
        if position.direction == PositionDirection.LONG:
            return await self.update_long_trailing(position, close_callback)
        else:
            return await self.update_short_trailing(position, close_callback)
        logger.info(f"   Profit: {position.profit_percentage:.2%}")
