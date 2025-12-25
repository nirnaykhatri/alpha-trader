"""
DCA Position Evaluator.

Evaluates entry, exit, and DCA decisions for DCA trading strategy.
Extracted from DCAStrategy to follow Single Responsibility Principle.

Author: Trading Bot Team
Version: 1.0.0
"""

from typing import Dict, Optional, Any
from src.interfaces import (
    IRiskManager, TradingSignal, Position, StrategyEvaluation
)
from src.core.logging_config import get_logger
from src.strategies.position_state import PositionState, PositionDirection, TradePhase
from src.strategies.dca_planner import DCAPlanner
from src.domain.bot_models import BotConfiguration, TakeProfitType

logger = get_logger(__name__)


class DCAPositionEvaluator:
    """
    Evaluates DCA position decisions following Single Responsibility Principle.
    
    Handles:
    - Entry evaluation (new positions)
    - Exit evaluation (profit targets, trailing stops)
    - DCA evaluation (averaging opportunities)
    
    This class is stateless regarding positions - it receives position data
    and returns evaluations. Position state is managed by DCAStrategy.
    
    Example:
        evaluator = DCAPositionEvaluator(risk_manager, dca_planner, bot_config)
        
        # Evaluate entry
        entry_eval = await evaluator.evaluate_entry(signal, existing_position)
        
        # Evaluate exit
        exit_eval = await evaluator.evaluate_exit(position, current_price)
        
        # Evaluate DCA
        dca_eval = await evaluator.evaluate_dca(position, current_price)
    """
    
    def __init__(
        self,
        risk_manager: IRiskManager,
        dca_planner: DCAPlanner,
        bot_config: BotConfiguration,
        dca_pause_guard: Optional[Any] = None,
    ):
        """
        Initialize the position evaluator.
        
        Args:
            risk_manager: Risk management service for validation
            dca_planner: DCA planning component for averaging decisions
            bot_config: Bot configuration from database
            dca_pause_guard: Optional DCA pause guard for resilience
        """
        self.risk_manager = risk_manager
        self.dca_planner = dca_planner
        self._bot_config = bot_config
        self.dca_pause_guard = dca_pause_guard
    
    def set_bot_config(self, bot_config: BotConfiguration) -> None:
        """Update bot configuration at runtime."""
        self._bot_config = bot_config
    
    async def evaluate_entry(
        self,
        signal: TradingSignal,
        existing_position: Optional[PositionState] = None,
        market_context: Optional[Dict[str, Any]] = None
    ) -> StrategyEvaluation:
        """
        Evaluate whether to enter a new position or add to existing.
        
        Args:
            signal: The incoming trading signal
            existing_position: Existing position if any (for DCA evaluation)
            market_context: Additional market data
            
        Returns:
            StrategyEvaluation with entry decision and recommended size
        """
        symbol = signal.symbol
        
        # Check if we already have a position - delegate to DCA evaluation
        if existing_position:
            return await self.evaluate_dca(
                position=existing_position,
                current_price=signal.price,
                market_context=market_context
            )
        
        # New position evaluation
        try:
            # Validate signal with risk manager
            is_valid = await self.risk_manager.validate_order(None)
            
            if not is_valid:
                return StrategyEvaluation(
                    should_act=False,
                    action_type="skip",
                    reason="Risk validation failed",
                    confidence=0.0
                )
            
            # Calculate recommended position size
            recommended_size = await self.risk_manager.calculate_position_size(
                symbol, signal
            )
            
            return StrategyEvaluation(
                should_act=True,
                action_type="entry",
                reason=f"New {signal.signal_type.value} signal at ${signal.price:.2f}",
                confidence=0.8,
                recommended_size=recommended_size,
                metadata={
                    'signal_type': signal.signal_type.value,
                    'timeframe': signal.metadata.get('timeframe', '15m') if signal.metadata else '15m'
                }
            )
            
        except Exception as e:
            logger.error(f"Error evaluating entry for {symbol}: {e}")
            return StrategyEvaluation(
                should_act=False,
                action_type="skip",
                reason=f"Evaluation error: {str(e)}",
                confidence=0.0
            )
    
    async def evaluate_exit(
        self,
        position: PositionState,
        current_price: float,
        market_context: Optional[Dict[str, Any]] = None
    ) -> StrategyEvaluation:
        """
        Evaluate whether to exit an existing position.
        
        Args:
            position: The current position to evaluate
            current_price: Current market price
            market_context: Additional market data
            
        Returns:
            StrategyEvaluation with exit decision
        """
        symbol = position.symbol
        
        # Calculate profit percentage
        if position.direction == PositionDirection.LONG:
            profit_pct = (current_price - position.average_price) / position.average_price
        else:
            profit_pct = (position.average_price - current_price) / position.average_price
        
        # Get profit threshold from config
        profit_threshold = self._get_profit_threshold()
        
        # Check trailing stop condition
        if position.phase == TradePhase.PROFIT_TRAILING:
            if position.direction == PositionDirection.LONG:
                should_exit = current_price <= position.trail_price
            else:
                should_exit = current_price >= position.trail_price
            
            if should_exit:
                return StrategyEvaluation(
                    should_act=True,
                    action_type="exit",
                    reason=f"Trailing stop triggered at ${current_price:.2f}",
                    confidence=1.0,
                    recommended_size=abs(position.quantity),
                    metadata={
                        'exit_type': 'trailing_stop',
                        'profit_percent': profit_pct * 100,
                        'trail_price': position.trail_price,
                        'peak_price': position.peak_price
                    }
                )
        
        # Check profit target
        if profit_pct >= profit_threshold:
            return StrategyEvaluation(
                should_act=True,
                action_type="exit",
                reason=f"Profit target reached: {profit_pct*100:.2f}%",
                confidence=0.9,
                recommended_size=abs(position.quantity),
                metadata={
                    'exit_type': 'profit_target',
                    'profit_percent': profit_pct * 100
                }
            )
        
        return StrategyEvaluation(
            should_act=False,
            action_type="hold",
            reason=f"Profit {profit_pct*100:.2f}% below threshold {profit_threshold*100:.2f}%",
            confidence=0.5,
            metadata={'current_profit_percent': profit_pct * 100}
        )
    
    async def evaluate_dca(
        self,
        position: PositionState,
        current_price: float,
        timeframe: str = '15m',
        calculate_size_callback: Optional[Any] = None,
        market_context: Optional[Dict[str, Any]] = None
    ) -> StrategyEvaluation:
        """
        Evaluate whether to execute a DCA (Dollar Cost Average) order.
        
        Args:
            position: The current position to average into
            current_price: Current market price
            timeframe: Original signal timeframe
            calculate_size_callback: Callback to calculate DCA size
            market_context: Additional market data
            
        Returns:
            StrategyEvaluation with DCA decision
        """
        # Update current price on position
        position.current_price = current_price
        
        # Check DCA pause guard
        if self.dca_pause_guard:
            pause_decision = await self.dca_pause_guard.evaluate()
            if not pause_decision.allow_dca:
                return StrategyEvaluation(
                    should_act=False,
                    action_type="skip",
                    reason=f"DCA paused: {pause_decision.reason}",
                    confidence=0.0
                )
        
        # Get DCA decision from planner
        if position.direction == PositionDirection.LONG:
            dca_decision = await self.dca_planner.check_martingale_dca_long(
                position, timeframe
            )
        else:
            dca_decision = await self.dca_planner.check_martingale_dca_short(
                position, timeframe
            )
        
        if dca_decision['should_dca']:
            # Calculate DCA quantity if callback provided
            recommended_size = 0.0
            if calculate_size_callback:
                is_long = position.direction == PositionDirection.LONG
                recommended_size = await calculate_size_callback(
                    position, current_price, is_long
                )
            
            return StrategyEvaluation(
                should_act=True,
                action_type="dca",
                reason=dca_decision.get('message', 'DCA threshold reached'),
                confidence=dca_decision.get('confidence', 0.8),
                recommended_size=recommended_size,
                metadata={
                    'dca_level': position.averaging_attempts + 1,
                    'trigger_price': dca_decision.get('trigger_price', current_price),
                    'last_dca_price': position.last_dca_price
                }
            )
        
        return StrategyEvaluation(
            should_act=False,
            action_type="hold",
            reason=dca_decision.get('message', 'DCA threshold not reached'),
            confidence=0.0,
            metadata={
                'distance_percent': dca_decision.get('distance_percent', 0),
                'current_loss_percent': position.profit_percentage * -100 if position.profit_percentage < 0 else 0
            }
        )
    
    def _get_profit_threshold(self) -> float:
        """Get profit threshold from database configuration."""
        if (self._bot_config.dca_config and 
            self._bot_config.dca_config.take_profit):
            return float(self._bot_config.dca_config.take_profit.price_change_percent) / 100.0
        raise ValueError("take_profit.price_change_percent configuration is required")
    
    def is_trailing_take_profit_enabled(self) -> bool:
        """Check if trailing take profit mode is enabled."""
        if (self._bot_config.dca_config and 
            self._bot_config.dca_config.take_profit):
            return self._bot_config.dca_config.take_profit.type == TakeProfitType.TRAILING
        return False
