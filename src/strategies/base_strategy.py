"""
Base Strategy - Abstract base class for all trading strategies.

Provides common functionality and default implementations for
ITradingStrategy methods that placeholder strategies can inherit.

This module contains:
- BaseStrategy: Abstract base with common functionality
- NotImplementedStrategy: Base for placeholder strategies
- Placeholder implementations for strategies not yet implemented

Author: Trading Bot Team
Version: 1.1.0
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
from src.interfaces import (
    IOrderManager, IMarketDataProvider, IRiskManager, ITradingStrategy,
    TradingSignal, Position, StrategyEvaluation
)
from src.core.logging_config import get_logger
from src.domain.bot_models import BotConfiguration, BotType

logger = get_logger(__name__)


class BaseStrategy(ITradingStrategy, ABC):
    """
    Abstract base class for all trading strategies.
    
    Provides common functionality such as:
    - Configuration management
    - State tracking
    - Default implementations for lifecycle methods
    
    Subclasses MUST implement these abstract methods:
    - evaluate_entry() - Evaluate new position entry
    - evaluate_exit() - Evaluate position exit
    - evaluate_dca() - Evaluate DCA/averaging opportunity
    - execute_tick() - Main strategy tick execution
    - handle_signal() - Handle incoming signals
    
    Subclasses SHOULD override these class attributes:
    - STRATEGY_NAME: Unique strategy identifier
    - BOT_TYPE: Corresponding BotType enum value
    
    Example:
        class MyStrategy(BaseStrategy):
            STRATEGY_NAME = "my_strategy"
            BOT_TYPE = BotType.DCA
            
            async def evaluate_entry(self, signal, position, context):
                # Implementation required
                ...
    """
    
    # Override in subclasses
    STRATEGY_NAME = "base_strategy"
    BOT_TYPE = BotType.DCA  # Default, override in subclasses
    
    def __init__(
        self,
        order_manager: IOrderManager,
        market_data: IMarketDataProvider,
        risk_manager: IRiskManager,
        bot_config: BotConfiguration,
        position_manager=None,
        resilience_tracker=None
    ):
        """
        Initialize the base strategy.
        
        Args:
            order_manager: Order execution manager
            market_data: Market data provider
            risk_manager: Risk management service
            bot_config: Bot's configuration from database
            position_manager: Position tracking manager
            resilience_tracker: Resilience tracking service
            
        Raises:
            ValueError: If bot_config is None
        """
        if bot_config is None:
            raise ValueError("bot_config is required - configuration must come from database")
        
        self.order_manager = order_manager
        self.market_data = market_data
        self.risk_manager = risk_manager
        self.position_manager = position_manager
        self._bot_config = bot_config
        
        # Strategy state tracking
        self._is_active = False
        self._is_initialized = False
    
    async def initialize(self) -> None:
        """Initialize the strategy."""
        if self._is_initialized:
            logger.warning(f"{self.name} already initialized, skipping")
            return
        
        logger.info(f"🚀 Initializing {self.name} strategy...")
        self._is_initialized = True
        self._is_active = True
        logger.info(f"✅ {self.name} strategy initialized")
    
    async def close(self) -> None:
        """Close the strategy and release resources."""
        logger.info(f"🛑 Closing {self.name} strategy...")
        self._is_active = False
        self._is_initialized = False
        logger.info(f"✅ {self.name} strategy closed")
    
    # =========================================================================
    # Abstract Methods - MUST be implemented by subclasses
    # =========================================================================
    
    @abstractmethod
    async def evaluate_entry(
        self,
        signal: TradingSignal,
        position: Optional[Position] = None,
        market_context: Optional[Dict[str, Any]] = None
    ) -> StrategyEvaluation:
        """
        Evaluate whether to enter a new position or add to existing.
        
        Args:
            signal: The incoming trading signal
            position: Existing position if any (for DCA evaluation)
            market_context: Additional market data
            
        Returns:
            StrategyEvaluation with entry decision and recommended size
        """
        pass
    
    @abstractmethod
    async def evaluate_exit(
        self,
        position: Position,
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
        pass
    
    @abstractmethod
    async def evaluate_dca(
        self,
        position: Position,
        current_price: float,
        market_context: Optional[Dict[str, Any]] = None
    ) -> StrategyEvaluation:
        """
        Evaluate whether to execute a DCA (Dollar Cost Average) order.
        
        Args:
            position: The current position to average into
            current_price: Current market price
            market_context: Additional market data
            
        Returns:
            StrategyEvaluation with DCA decision
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
        
        Args:
            current_price: Current market price
            market_context: Additional market data
            
        Returns:
            StrategyEvaluation if action needed, None otherwise
        """
        pass
    
    @abstractmethod
    async def handle_signal(
        self,
        signal: Dict[str, Any]
    ) -> Optional[StrategyEvaluation]:
        """
        Handle an incoming trading signal.
        
        Args:
            signal: Signal data with action, symbol, price, etc.
            
        Returns:
            StrategyEvaluation if action should be taken
        """
        pass
    
    # =========================================================================
    # Concrete Methods - Shared implementation for all strategies
    # =========================================================================
    
    def get_state(self) -> Dict[str, Any]:
        """Get the current state of the strategy."""
        return {
            'name': self.name,
            'bot_type': self.bot_type.value,
            'is_active': self.is_active,
            'is_initialized': self._is_initialized,
            'implemented': False,  # Override in concrete implementations
            'message': f"{self.name} base state"
        }
    
    @property
    def name(self) -> str:
        """Get the strategy name."""
        return self.STRATEGY_NAME
    
    @property
    def is_active(self) -> bool:
        """Check if strategy is active."""
        return self._is_active
    
    @property
    def bot_type(self) -> BotType:
        """Get the bot type this strategy implements."""
        return self.BOT_TYPE


class NotImplementedStrategy(BaseStrategy):
    """
    Base class for strategies that are not yet implemented.
    
    Provides stub implementations that raise NotImplementedError
    with helpful messages about the strategy status.
    """
    
    def _not_implemented_message(self, method_name: str) -> str:
        """Generate a helpful not implemented message."""
        return (
            f"{self.name}.{method_name}() is not yet implemented. "
            f"This strategy ({self.bot_type.value}) is a placeholder. "
            f"Please use DCA strategy for production trading."
        )
    
    async def evaluate_entry(
        self,
        signal: TradingSignal,
        position: Optional[Position] = None,
        market_context: Optional[Dict[str, Any]] = None
    ) -> StrategyEvaluation:
        """Placeholder - returns skip evaluation."""
        return StrategyEvaluation(
            should_act=False,
            action_type="skip",
            reason=self._not_implemented_message("evaluate_entry"),
            confidence=0.0
        )
    
    async def evaluate_exit(
        self,
        position: Position,
        current_price: float,
        market_context: Optional[Dict[str, Any]] = None
    ) -> StrategyEvaluation:
        """Placeholder - returns skip evaluation."""
        return StrategyEvaluation(
            should_act=False,
            action_type="skip",
            reason=self._not_implemented_message("evaluate_exit"),
            confidence=0.0
        )
    
    async def evaluate_dca(
        self,
        position: Position,
        current_price: float,
        market_context: Optional[Dict[str, Any]] = None
    ) -> StrategyEvaluation:
        """Placeholder - returns skip evaluation."""
        return StrategyEvaluation(
            should_act=False,
            action_type="skip",
            reason=self._not_implemented_message("evaluate_dca"),
            confidence=0.0
        )
    
    async def execute_tick(
        self,
        current_price: float,
        market_context: Optional[Dict[str, Any]] = None
    ) -> Optional[StrategyEvaluation]:
        """Placeholder - returns None (no action)."""
        logger.debug(f"{self.name}: execute_tick called but not implemented")
        return None
    
    async def handle_signal(
        self,
        signal: Dict[str, Any]
    ) -> Optional[StrategyEvaluation]:
        """Placeholder - returns None (no action)."""
        logger.warning(
            f"{self.name}: Signal received but strategy not implemented. "
            f"Signal: {signal.get('action')} {signal.get('symbol')}"
        )
        return None


class GridStrategy(NotImplementedStrategy):
    """
    Grid Trading Strategy (Placeholder).
    
    Grid trading places buy and sell orders at predefined price levels
    (grid lines) above and below a set price. Profits are made when
    price oscillates between grid levels.
    
    Features (when implemented):
    - Automatic grid level calculation
    - Dynamic grid adjustment
    - Range-bound profit optimization
    - Works best in sideways markets
    
    Status: NOT IMPLEMENTED - Placeholder only
    """
    
    STRATEGY_NAME = "grid_strategy"
    BOT_TYPE = BotType.GRID
    
    def get_state(self) -> Dict[str, Any]:
        """Get strategy state with grid-specific info."""
        state = super().get_state()
        state.update({
            'grid_levels': [],
            'active_orders': [],
            'price_range': {'lower': None, 'upper': None},
            'grid_spacing': None,
            'message': "Grid strategy is not yet implemented. Coming in future release."
        })
        return state


class SpotLoopStrategy(NotImplementedStrategy):
    """
    Spot Loop Trading Strategy (Placeholder).
    
    Loop strategy continuously buys low and sells high within a
    defined range. Similar to grid but optimized for spot markets
    with simpler mechanics.
    
    Features (when implemented):
    - Simple buy/sell loop logic
    - Range detection
    - Profit locking on each cycle
    - Minimal capital requirement
    
    Status: NOT IMPLEMENTED - Placeholder only
    """
    
    STRATEGY_NAME = "spot_loop_strategy"
    BOT_TYPE = BotType.SPOT_LOOP
    
    def get_state(self) -> Dict[str, Any]:
        """Get strategy state with loop-specific info."""
        state = super().get_state()
        state.update({
            'loop_count': 0,
            'current_phase': 'idle',  # 'buying' or 'selling'
            'buy_price': None,
            'sell_price': None,
            'message': "Spot loop strategy is not yet implemented. Coming in future release."
        })
        return state


class ComboStrategy(NotImplementedStrategy):
    """
    Combo Trading Strategy (Placeholder).
    
    Combines multiple strategy elements (DCA + Grid, etc.) into
    a unified approach. Adapts behavior based on market conditions.
    
    Features (when implemented):
    - Multi-strategy orchestration
    - Condition-based strategy switching
    - Combined risk management
    - Adaptive behavior
    
    Status: NOT IMPLEMENTED - Placeholder only
    """
    
    STRATEGY_NAME = "combo_strategy"
    BOT_TYPE = BotType.COMBO
    
    def get_state(self) -> Dict[str, Any]:
        """Get strategy state with combo-specific info."""
        state = super().get_state()
        state.update({
            'active_sub_strategies': [],
            'current_mode': 'idle',
            'strategy_weights': {},
            'message': "Combo strategy is not yet implemented. Coming in future release."
        })
        return state


class FuturesDCAStrategy(NotImplementedStrategy):
    """
    Futures DCA Trading Strategy (Placeholder).
    
    DCA strategy adapted for futures/perpetual contracts with
    leverage support and funding rate considerations.
    
    Features (when implemented):
    - Leverage management
    - Funding rate optimization
    - Long/short position support
    - Liquidation protection
    - Margin management
    
    Status: NOT IMPLEMENTED - Placeholder only
    """
    
    STRATEGY_NAME = "futures_dca_strategy"
    BOT_TYPE = BotType.FUTURES_DCA
    
    def get_state(self) -> Dict[str, Any]:
        """Get strategy state with futures-specific info."""
        state = super().get_state()
        state.update({
            'leverage': 1,
            'margin_type': 'cross',
            'funding_rate': None,
            'liquidation_price': None,
            'position_side': None,  # 'long' or 'short'
            'message': "Futures DCA strategy is not yet implemented. Coming in future release."
        })
        return state


class FuturesComboStrategy(NotImplementedStrategy):
    """
    Futures Combo Trading Strategy (Placeholder).
    
    Combines multiple futures trading strategies with advanced
    position management and hedging capabilities.
    
    Features (when implemented):
    - Multi-strategy futures trading
    - Hedging support
    - Cross-margin optimization
    - Advanced liquidation protection
    
    Status: NOT IMPLEMENTED - Placeholder only
    """
    
    STRATEGY_NAME = "futures_combo_strategy"
    BOT_TYPE = BotType.FUTURES_COMBO
    
    def get_state(self) -> Dict[str, Any]:
        """Get strategy state with futures combo-specific info."""
        state = super().get_state()
        state.update({
            'active_sub_strategies': [],
            'leverage': 1,
            'hedge_positions': [],
            'total_margin_used': 0,
            'message': "Futures combo strategy is not yet implemented. Coming in future release."
        })
        return state
