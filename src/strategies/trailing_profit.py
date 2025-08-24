"""
Trailing profit management implementation.
Manages trailing stops and profit-taking strategies with configurable parameters.
"""

from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from ..interfaces import ITrailingProfitManager, IConfigurationManager
from ..core.logging_config import get_logger
from .. import Position


logger = get_logger(__name__)


class ConfigurableTrailingProfitManager(ITrailingProfitManager):
    """
    Manages trailing profit logic with configurable parameters.
    Supports multiple trailing strategies and risk management rules.
    """
    
    def __init__(self, config: IConfigurationManager):
        """
        Initialize trailing profit manager.
        
        Args:
            config: Configuration manager instance
        """
        self._config = config
        self._trailing_states: Dict[str, Dict] = {}  # Per-symbol trailing state
        
        # Configuration parameters - NEW STRUCTURE with fallbacks
        # Stop-loss settings (CRITICAL for risk management)
        self._stop_loss_enabled = config.get_config(
            "trading.risk_management.stop_loss.enabled", 
            config.get_config("strategies.trailing_profit.max_loss_percentage", None) is not None
        )
        self._max_loss_percentage = config.get_config(
            "trading.risk_management.stop_loss.max_loss_percentage", 
            config.get_config("strategies.trailing_profit.max_loss_percentage", 0.05)
        )
        
        # Profit-taking settings
        self._take_profit_percentage = config.get_config(
            "trading.risk_management.profit_taking.take_profit_percentage",
            config.get_config("strategies.trailing_profit.take_profit_percentage", 0.05)
        )
        
        # Trailing profit settings  
        self._activation_threshold = config.get_config(
            "trading.risk_management.profit_taking.trailing_profit.activation_threshold",
            config.get_config("strategies.trailing_profit.activation_threshold", 0.03)
        )
        self._trailing_percentage = config.get_config(
            "trading.risk_management.profit_taking.trailing_profit.trailing_percentage",
            config.get_config("strategies.trailing_profit.trailing_percentage", 0.015)
        )
        self._min_profit_lock = config.get_config(
            "trading.risk_management.profit_taking.trailing_profit.min_profit_lock",
            config.get_config("strategies.trailing_profit.min_profit_lock", 0.01)
        )
        
        # Time-based exit settings
        self._time_based_exit = config.get_config(
            "trading.risk_management.profit_taking.time_based_exit.enabled",
            config.get_config("strategies.trailing_profit.time_based_exit", False)
        )
        self._max_hold_hours = config.get_config(
            "trading.risk_management.profit_taking.time_based_exit.max_hold_hours",
            config.get_config("strategies.trailing_profit.max_hold_hours", 24)
        )
        
        # Advanced trailing settings
        self._acceleration_factor = config.get_config(
            "trading.risk_management.profit_taking.trailing_profit.acceleration_factor",
            config.get_config("strategies.trailing_profit.acceleration_factor", 1.5)
        )
        self._profit_steps = config.get_config(
            "trading.risk_management.profit_taking.trailing_profit.profit_steps",
            config.get_config("strategies.trailing_profit.profit_steps", None)
        )
        
        logger.info("TrailingProfitManager initialized with configuration")
        logger.debug(f"Stop-loss enabled: {self._stop_loss_enabled}")
        if self._stop_loss_enabled:
            logger.debug(f"Max loss percentage: {self._max_loss_percentage:.2%}")
        else:
            logger.debug("Stop-loss is DISABLED - positions will not be stopped out for losses")
        logger.debug(f"Activation threshold: {self._activation_threshold:.2%}")
        logger.debug(f"Trailing percentage: {self._trailing_percentage:.2%}")
        logger.debug(f"Take profit percentage: {self._take_profit_percentage:.2%}")
    
    async def should_trail(self, position: Position, current_price: float) -> bool:
        """
        Determine if trailing should be activated for a position.
        
        Args:
            position: Current position
            current_price: Current market price
            
        Returns:
            True if trailing should be activated
        """
        try:
            # Calculate current profit percentage
            profit_pct = self._calculate_profit_percentage(position, current_price)
            
            # Check if we've reached the activation threshold
            if profit_pct >= self._activation_threshold:
                # Initialize trailing state if not exists
                if position.symbol not in self._trailing_states:
                    self._initialize_trailing_state(position, current_price)
                    logger.info(f"Trailing activated for {position.symbol} at {profit_pct:.2%} profit")
                    return True
                
                # Already trailing
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking trailing activation for {position.symbol}: {str(e)}")
            return False
    
    async def calculate_trailing_stop(self, position: Position, 
                                    current_price: float) -> float:
        """
        Calculate the trailing stop price.
        
        Args:
            position: Current position
            current_price: Current market price
            
        Returns:
            Trailing stop price
        """
        try:
            symbol = position.symbol
            
            # Initialize trailing state if not exists
            if symbol not in self._trailing_states:
                self._initialize_trailing_state(position, current_price)
            
            state = self._trailing_states[symbol]
            
            # Calculate basic trailing stop
            if position.quantity > 0:  # Long position
                trailing_stop = current_price * (1 - self._trailing_percentage)
            else:  # Short position
                trailing_stop = current_price * (1 + self._trailing_percentage)
            
            # Apply acceleration factor if price is moving favorably
            if self._should_accelerate_trailing(position, current_price, state):
                acceleration = self._acceleration_factor
                if position.quantity > 0:
                    trailing_stop = current_price * (1 - (self._trailing_percentage * acceleration))
                else:
                    trailing_stop = current_price * (1 + (self._trailing_percentage * acceleration))
            
            # Apply stepped trailing if configured
            if self._profit_steps:
                trailing_stop = self._apply_stepped_trailing(
                    position, current_price, trailing_stop
                )
            
            # Update trailing state
            self._update_trailing_state(position, current_price, trailing_stop)
            
            # Ensure we don't trail backwards
            if position.quantity > 0:
                # Long position - stop should only move up
                trailing_stop = max(trailing_stop, state.get('highest_stop', 0))
            else:
                # Short position - stop should only move down
                trailing_stop = min(trailing_stop, state.get('lowest_stop', float('inf')))
            
            logger.debug(f"Trailing stop calculated for {symbol}: {trailing_stop:.4f}")
            return trailing_stop
            
        except Exception as e:
            logger.error(f"Error calculating trailing stop for {position.symbol}: {str(e)}")
            return position.avg_price  # Fallback to entry price
    
    async def should_take_profit(self, position: Position, 
                               current_price: float) -> bool:
        """
        Determine if profit should be taken.
        
        Args:
            position: Current position
            current_price: Current market price
            
        Returns:
            True if profit should be taken
        """
        try:
            # Calculate current profit percentage
            profit_pct = self._calculate_profit_percentage(position, current_price)
            
            # Check take profit threshold
            if profit_pct >= self._take_profit_percentage:
                logger.info(f"Take profit triggered for {position.symbol} at {profit_pct:.2%}")
                return True
            
            # Check trailing stop
            if await self.should_trail(position, current_price):
                trailing_stop = await self.calculate_trailing_stop(position, current_price)
                
                if position.quantity > 0:
                    # Long position - take profit if price falls below trailing stop
                    if current_price <= trailing_stop:
                        logger.info(f"Trailing stop triggered for {position.symbol}: "
                                   f"{current_price:.4f} <= {trailing_stop:.4f}")
                        return True
                else:
                    # Short position - take profit if price rises above trailing stop
                    if current_price >= trailing_stop:
                        logger.info(f"Trailing stop triggered for {position.symbol}: "
                                   f"{current_price:.4f} >= {trailing_stop:.4f}")
                        return True
            
            # Check time-based exit
            if self._time_based_exit and self._should_exit_time_based(position):
                logger.info(f"Time-based exit triggered for {position.symbol}")
                return True
            
            # Check maximum loss (only if stop-loss is enabled)
            if (self._stop_loss_enabled and 
                self._max_loss_percentage is not None and 
                profit_pct <= -self._max_loss_percentage):
                logger.info(f"Stop loss triggered for {position.symbol} at {profit_pct:.2%}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking take profit for {position.symbol}: {str(e)}")
            return False
    
    def _calculate_profit_percentage(self, position: Position, current_price: float) -> float:
        """Calculate current profit percentage."""
        if position.avg_price == 0:
            return 0.0
        
        if position.quantity > 0:
            # Long position
            return (current_price - position.avg_price) / position.avg_price
        else:
            # Short position
            return (position.avg_price - current_price) / position.avg_price
    
    def _initialize_trailing_state(self, position: Position, current_price: float) -> None:
        """Initialize trailing state for a position."""
        self._trailing_states[position.symbol] = {
            'activated_at': datetime.utcnow(),
            'activation_price': current_price,
            'highest_price': current_price,
            'lowest_price': current_price,
            'highest_stop': 0.0,
            'lowest_stop': float('inf'),
            'profit_locked': 0.0,
            'step_level': 0
        }
    
    def _update_trailing_state(self, position: Position, current_price: float, 
                             trailing_stop: float) -> None:
        """Update trailing state with current information."""
        symbol = position.symbol
        state = self._trailing_states[symbol]
        
        # Update price extremes
        state['highest_price'] = max(state['highest_price'], current_price)
        state['lowest_price'] = min(state['lowest_price'], current_price)
        
        # Update stop extremes
        if position.quantity > 0:
            state['highest_stop'] = max(state['highest_stop'], trailing_stop)
        else:
            state['lowest_stop'] = min(state['lowest_stop'], trailing_stop)
        
        # Update profit lock
        current_profit = self._calculate_profit_percentage(position, current_price)
        if current_profit > state['profit_locked']:
            state['profit_locked'] = max(current_profit - self._trailing_percentage, 
                                       self._min_profit_lock)
    
    def _should_accelerate_trailing(self, position: Position, current_price: float, 
                                  state: Dict) -> bool:
        """Determine if trailing should be accelerated."""
        if self._acceleration_factor <= 1.0:
            return False
        
        # Check if price is moving favorably beyond a threshold
        profit_pct = self._calculate_profit_percentage(position, current_price)
        acceleration_threshold = self._activation_threshold * 1.5
        
        return profit_pct > acceleration_threshold
    
    def _apply_stepped_trailing(self, position: Position, current_price: float, 
                              base_trailing_stop: float) -> float:
        """Apply stepped trailing based on profit levels."""
        if not self._profit_steps:
            return base_trailing_stop
        
        profit_pct = self._calculate_profit_percentage(position, current_price)
        symbol = position.symbol
        state = self._trailing_states[symbol]
        
        # Find current step level
        current_step = 0
        for i, step in enumerate(self._profit_steps):
            if profit_pct >= step['profit_threshold']:
                current_step = i
        
        # Update step level (only increase)
        if current_step > state['step_level']:
            state['step_level'] = current_step
            logger.info(f"Stepped trailing level {current_step} activated for {symbol}")
        
        # Apply step-specific trailing percentage
        if state['step_level'] < len(self._profit_steps):
            step_config = self._profit_steps[state['step_level']]
            step_trailing_pct = step_config.get('trailing_percentage', self._trailing_percentage)
            
            if position.quantity > 0:
                return current_price * (1 - step_trailing_pct)
            else:
                return current_price * (1 + step_trailing_pct)
        
        return base_trailing_stop
    
    def _should_exit_time_based(self, position: Position) -> bool:
        """Check if position should exit based on time."""
        if not self._time_based_exit:
            return False
        
        time_held = datetime.utcnow() - position.created_at
        max_hold_time = timedelta(hours=self._max_hold_hours)
        
        return time_held >= max_hold_time
    
    def get_trailing_state(self, symbol: str) -> Optional[Dict]:
        """Get current trailing state for a symbol."""
        return self._trailing_states.get(symbol)
    
    def reset_trailing_state(self, symbol: str) -> None:
        """Reset trailing state for a symbol."""
        if symbol in self._trailing_states:
            del self._trailing_states[symbol]
            logger.info(f"Trailing state reset for {symbol}")
    
    def get_trailing_summary(self) -> Dict[str, Dict]:
        """Get summary of all trailing states."""
        summary = {}
        for symbol, state in self._trailing_states.items():
            summary[symbol] = {
                'activated_at': state['activated_at'].isoformat(),
                'profit_locked': state['profit_locked'],
                'step_level': state['step_level'],
                'highest_price': state['highest_price'],
                'lowest_price': state['lowest_price']
            }
        return summary
