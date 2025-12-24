"""
Phase Manager
Manages trade phase transitions and phase-specific logic.
Handles the state machine for different trading phases.
NO technical analysis - simplified martingale-only logic.

Configuration is driven exclusively by bot's BotConfiguration from database.
"""

from src.core.logging_config import get_logger
from src.strategies.position_state import PositionState, PositionDirection, TradePhase
from src.domain.bot_models import BotConfiguration

logger = get_logger(__name__)


class PhaseManager:
    """
    Manages trade phase state machine and transitions.
    Follows Single Responsibility Principle - only handles phase management.
    
    Configuration is driven exclusively by bot's BotConfiguration from database.
    """
    
    def __init__(self, bot_config: BotConfiguration):
        """
        Initialize the phase manager.
        
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
    
    async def check_support_averaging_transition(self, position: PositionState) -> bool:
        """
        DEPRECATED - No longer used in martingale-only mode.
        Phase transitions now handled automatically by DCA logic.
        
        Args:
            position: Current position state
            
        Returns:
            False (no transition)
        """
        logger.debug(f"Support averaging transition check skipped for {position.symbol} (martingale-only mode)")
        return False
    
    async def check_resistance_averaging_transition(self, position: PositionState) -> bool:
        """
        DEPRECATED - No longer used in martingale-only mode.
        Phase transitions now handled automatically by DCA logic.
        
        Args:
            position: Current position state
            
        Returns:
            False (no transition)
        """
        logger.debug(f"Resistance averaging transition check skipped for {position.symbol} (martingale-only mode)")
        return False
    
    def update_support_averaging_phase(self, position: PositionState):
        """
        DEPRECATED - No longer used in martingale-only mode.
        
        Args:
            position: Current position state
        """
        logger.debug(f"Support averaging phase update skipped for {position.symbol} (martingale-only mode)")
    
    def update_resistance_averaging_phase(self, position: PositionState):
        """
        DEPRECATED - No longer used in martingale-only mode.
        
        Args:
            position: Current position state
        """
        logger.debug(f"Resistance averaging phase update skipped for {position.symbol} (martingale-only mode)")
    
    def get_current_phase_description(self, position: PositionState) -> str:
        """
        Get human-readable description of current phase.
        
        Args:
            position: Current position state
            
        Returns:
            Description string
        """
        # Build dynamic descriptions based on position state
        if position.phase == TradePhase.ENTRY:
            return "Waiting for entry order fill"
        elif position.phase == TradePhase.PROFIT_TRAILING:
            peak = position.peak_price if position.peak_price else 0
            trail = position.trail_price if position.trail_price else 0
            return f"Trailing profit (peak: ${peak:.2f}, trail: ${trail:.2f})"
        elif position.phase == TradePhase.SUPPORT_AVERAGING:
            # Deprecated in martingale-only mode - show DCA info instead
            return f"Martingale DCA active (attempts: {position.averaging_attempts}, avg: ${position.average_price:.2f})"
        elif position.phase == TradePhase.RESISTANCE_AVERAGING:
            # Deprecated in martingale-only mode - show DCA info instead  
            return f"Martingale DCA active (attempts: {position.averaging_attempts}, avg: ${position.average_price:.2f})"
        elif position.phase == TradePhase.EXIT:
            return "Closing position"
        else:
            return f"Unknown phase: {position.phase}"
