"""
Strategy Interfaces.

This module defines interfaces for trading strategies, including
the main strategy contract, DCA planning, and trailing management.

Canonical location for:
- ITradingStrategy
- IDCAPlanner
- ITrailingManager
- StrategyEvaluation
- DCADecision

Author: Trading Bot Team
Version: 1.0.0
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.bot_models import BotType
    from src.interfaces.core import TradingSignal, Position


# =============================================================================
# Type Aliases
# =============================================================================

# Type alias for position state (used by DCA and trailing managers)
# Using Any to avoid circular imports - actual type is PositionState
PositionStateType = Any


# =============================================================================
# Strategy Data Classes
# =============================================================================

@dataclass
class StrategyEvaluation:
    """Result of a strategy evaluation."""
    should_act: bool
    action_type: Optional[str] = None  # "entry", "exit", "dca", "skip"
    reason: str = ""
    confidence: float = 0.0  # 0.0 to 1.0
    recommended_size: Optional[float] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class DCADecision:
    """Result of a DCA evaluation decision."""
    should_dca: bool
    reason: str
    level: Optional[float] = None
    confidence: float = 0.0
    trigger_price: Optional[float] = None
    timeframe: str = "N/A"
    message: str = ""
    distance_percent: Optional[float] = None


# =============================================================================
# Strategy Interfaces
# =============================================================================

class ITradingStrategy(ABC):
    """
    Interface for trading strategies.
    
    Defines the contract that all trading strategies must implement,
    enabling polymorphic strategy execution and easy strategy swapping.
    
    Follows the Strategy Pattern to allow different trading algorithms
    to be used interchangeably by the trading bot orchestrator.
    
    Example:
        class DCAStrategy(ITradingStrategy):
            async def evaluate_entry(self, signal, context):
                # Technical analysis-based entry logic
                return StrategyEvaluation(should_act=True, action_type="entry")
                
        class ScalpingStrategy(ITradingStrategy):
            async def evaluate_entry(self, signal, context):
                # Quick momentum-based entry
                return StrategyEvaluation(should_act=True, action_type="entry")
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the strategy.
        
        Called once before the strategy starts processing signals.
        Use for loading historical data, setting up indicators, etc.
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close the strategy and release resources.
        
        Called when the strategy is being shut down.
        Use for saving state, closing connections, etc.
        """
        pass
    
    @abstractmethod
    async def evaluate_entry(
        self,
        signal: "TradingSignal",
        position: Optional["Position"] = None,
        market_context: Optional[Dict[str, Any]] = None
    ) -> StrategyEvaluation:
        """
        Evaluate whether to enter a new position or add to existing.
        
        Args:
            signal: The incoming trading signal
            position: Existing position if any (for DCA evaluation)
            market_context: Additional market data (support levels, volatility, etc.)
            
        Returns:
            StrategyEvaluation with entry decision and recommended size
        """
        pass
    
    @abstractmethod
    async def evaluate_exit(
        self,
        position: "Position",
        current_price: float,
        market_context: Optional[Dict[str, Any]] = None
    ) -> StrategyEvaluation:
        """
        Evaluate whether to exit an existing position.
        
        Args:
            position: The current position to evaluate
            current_price: Current market price
            market_context: Additional market data (resistance levels, etc.)
            
        Returns:
            StrategyEvaluation with exit decision and size (partial/full)
        """
        pass
    
    @abstractmethod
    async def evaluate_dca(
        self,
        position: "Position",
        current_price: float,
        market_context: Optional[Dict[str, Any]] = None
    ) -> StrategyEvaluation:
        """
        Evaluate whether to execute a DCA (Dollar Cost Average) order.
        
        Args:
            position: The current position to average into
            current_price: Current market price (should be at support level)
            market_context: Additional market data (support levels, volume, etc.)
            
        Returns:
            StrategyEvaluation with DCA decision and recommended size
            
        Note:
            DCA decisions should be based on technical levels, NOT percentage drops.
            Each DCA must improve the position's average price (progressive pricing).
        """
        pass
    
    @abstractmethod
    async def execute_tick(
        self,
        current_price: float,
        market_context: Optional[Dict[str, Any]] = None
    ) -> Optional[StrategyEvaluation]:
        """
        Execute one tick of the strategy's main loop.
        
        Called periodically by BotRunner to drive strategy-specific logic
        such as checking entry/exit conditions, managing grid levels, etc.
        
        This is the primary execution hook that allows strategies to implement
        their core trading logic without the BotRunner knowing specifics.
        
        Args:
            current_price: Current market price for the strategy's symbol
            market_context: Additional market data (volume, OHLCV, indicators, etc.)
            
        Returns:
            StrategyEvaluation if any action should be taken, None otherwise.
            The BotRunner will act on the evaluation (place orders, close positions, etc.)
        """
        pass
    
    @abstractmethod
    async def handle_signal(
        self,
        signal: Dict[str, Any]
    ) -> Optional[StrategyEvaluation]:
        """
        Handle an incoming trading signal (webhook, indicator, etc.).
        
        Called by BotRunner when a signal is received for this strategy's symbol.
        The strategy decides how to interpret and act on the signal.
        
        Args:
            signal: Signal data containing at minimum:
                - action: "buy", "sell", or "close"
                - symbol: Trading pair/symbol
                - price: Optional price at signal time
                - Additional metadata varies by signal source
            
        Returns:
            StrategyEvaluation if action should be taken, None to ignore signal.
        """
        pass
    
    @abstractmethod
    def get_state(self) -> Dict[str, Any]:
        """
        Get the current state of the strategy.
        
        Returns:
            Dictionary containing strategy state for monitoring/debugging.
            Should include: active positions, pending signals, performance metrics.
        """
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Get the strategy name for identification."""
        pass
    
    @property
    @abstractmethod
    def is_active(self) -> bool:
        """Check if the strategy is currently active and processing signals."""
        pass
    
    @property
    @abstractmethod
    def bot_type(self) -> "BotType":
        """Get the bot type this strategy implements."""
        pass


# =============================================================================
# DCA and Trailing Interfaces
# =============================================================================

class IDCAPlanner(ABC):
    """
    Interface for DCA (Dollar-Cost Averaging) planning and execution.
    
    Defines the contract for components that manage DCA order planning,
    including martingale-based loss threshold triggers and progressive
    price validation.
    
    Example:
        class MartingaleDCAPlanner(IDCAPlanner):
            async def check_dca_opportunity(self, position, current_price):
                # Check if loss threshold is reached
                return DCADecision(should_dca=True, reason='loss_threshold')
    """
    
    @abstractmethod
    async def check_dca_opportunity(
        self,
        position: PositionStateType,
        current_price: float,
        timeframe: str = "15m"
    ) -> Dict[str, Any]:
        """
        Check if DCA should be executed for the given position.
        
        Args:
            position: Current position state
            current_price: Current market price
            timeframe: Signal timeframe for context
            
        Returns:
            Dictionary with keys: should_dca, reason, level, confidence, message
        """
        pass
    
    @abstractmethod
    def is_progressive_price(
        self,
        position: PositionStateType,
        proposed_price: float
    ) -> Dict[str, Any]:
        """
        Validate that the proposed DCA price improves the average.
        
        For LONG: new price must be BELOW last DCA (averaging down)
        For SHORT: new price must be ABOVE last DCA (averaging up)
        
        Args:
            position: Current position state
            proposed_price: Proposed DCA order price
            
        Returns:
            Dictionary with keys: is_progressive, reason, message, last_price
        """
        pass
    
    @abstractmethod
    async def execute_dca(
        self,
        position: PositionStateType,
        dca_decision: Dict[str, Any],
        calculate_size_callback: Callable
    ) -> bool:
        """
        Execute a DCA order based on the decision.
        
        Args:
            position: Current position state
            dca_decision: DCA decision from check_dca_opportunity
            calculate_size_callback: Callback to calculate position size
            
        Returns:
            True if DCA order was placed successfully
        """
        pass


class ITrailingManager(ABC):
    """
    Interface for trailing stop management.
    
    Defines the contract for components that manage trailing stop logic,
    tracking peak prices and adjusting stops based on profit thresholds.
    
    Example:
        class PercentageTrailingManager(ITrailingManager):
            def initialize_trailing(self, position):
                position.trail_price = position.current_price * 0.98  # 2% trail
    """
    
    @abstractmethod
    def initialize_trailing(self, position: PositionStateType) -> None:
        """
        Initialize trailing stop for a position that reached profit threshold.
        
        Sets up peak price and initial trail price based on current price
        and trailing percentage configuration.
        
        Args:
            position: Position state to initialize trailing for
        """
        pass
    
    @abstractmethod
    async def update_trailing(
        self,
        position: PositionStateType,
        close_callback: Callable[[str], Any]
    ) -> bool:
        """
        Update trailing stop for a position.
        
        Updates peak price if new high/low reached, recalculates trail price,
        and triggers close callback if trailing stop is hit.
        
        Args:
            position: Position state to update
            close_callback: Async callback to close position if stop hit
            
        Returns:
            True if trailing stop was hit and position closed
        """
        pass
    
    @abstractmethod
    def should_start_trailing(self, position: PositionStateType) -> bool:
        """
        Check if position has reached profit threshold for trailing.
        
        Args:
            position: Position state to check
            
        Returns:
            True if trailing should be activated
        """
        pass


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Data classes
    "StrategyEvaluation",
    "DCADecision",
    # Type aliases
    "PositionStateType",
    # Interfaces
    "ITradingStrategy",
    "IDCAPlanner",
    "ITrailingManager",
]
