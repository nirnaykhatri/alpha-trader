"""
Core interfaces and abstract base classes for the trading bot system.
This module defines the contracts that all implementations must follow.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Awaitable, Coroutine, TypeVar, TYPE_CHECKING
from datetime import datetime
import uuid

if TYPE_CHECKING:
    from src.domain.bot_models import BotType


# =============================================================================
# Type Aliases for Callbacks
# =============================================================================

# Generic type for event data
EventData = Dict[str, Any]

# Sync callbacks
SignalCallback = Callable[["TradingSignal"], None]
ConfigChangeCallback = Callable[[str, Any, Any], None]  # key, old_value, new_value
OrderCallback = Callable[["Order"], None]
PositionCallback = Callable[["Position", float], Any]  # position, pnl_percent

# Async callbacks
AsyncEventCallback = Callable[[EventData], Awaitable[None]]
AsyncSignalCallback = Callable[["TradingSignal"], Awaitable[None]]
AsyncOrderCallback = Callable[["Order"], Awaitable[None]]
AsyncPositionCallback = Callable[["Position"], Awaitable[None]]
AsyncErrorCallback = Callable[[Exception], Awaitable[None]]


class SignalType(Enum):
    """Types of trading signals."""
    BUY = "buy"
    SELL = "sell"
    CLOSE = "close"


class OrderType(Enum):
    """Types of orders."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    """Order status values."""
    PENDING = "pending"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    PARTIAL_FILL = "partial_fill"


class OrderSide(Enum):
    """Order side values."""
    BUY = "buy"
    SELL = "sell"


@dataclass
class TradingSignal:
    """Represents a trading signal from TradingView or other sources."""
    signal_id: str
    symbol: str
    signal_type: SignalType
    price: float
    quantity: Optional[float] = None
    timestamp: datetime = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}
        if self.signal_id is None:
            self.signal_id = str(uuid.uuid4())


@dataclass
class Order:
    """Represents a trading order."""
    order_id: str
    symbol: str
    quantity: float
    order_type: OrderType
    side: OrderSide  # Buy or sell
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = None
    filled_at: Optional[datetime] = None
    filled_price: Optional[float] = None
    filled_quantity: Optional[float] = None
    broker: Optional[str] = None
    broker_order_id: Optional[str] = None
    is_dca_order: bool = False  # Indicates if this is a DCA (Dollar Cost Averaging) order
    is_closing: bool = False  # Indicates if this order is closing a position
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.order_id is None:
            self.order_id = str(uuid.uuid4())


@dataclass
class Position:
    """Represents a current position."""
    symbol: str
    quantity: float
    avg_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    created_at: datetime = None
    broker: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


@dataclass
class SupportLevel:
    """Represents a calculated support or resistance level."""
    price: float
    confidence: float  # 0.0 to 1.0
    method: str  # Calculation method used
    touches: int = 0  # Number of times price touched this level
    last_touch: datetime = None
    calculated_at: datetime = None
    
    def __post_init__(self):
        if self.calculated_at is None:
            self.calculated_at = datetime.utcnow()
        if self.last_touch is None:
            self.last_touch = datetime.utcnow()


@dataclass
class SupportLevelData:
    """Contains comprehensive support/resistance level data."""
    symbol: str
    timeframe: str
    levels: List[SupportLevel]
    calculated_at: datetime
    confidence: float  # Overall confidence of the analysis
    
    def get_nearest_level(self, current_price: float, level_type: str = "support") -> Optional[SupportLevel]:
        """Get the nearest support or resistance level to current price."""
        if not self.levels:
            return None
        
        if level_type == "support":
            # Find highest support below current price
            support_levels = [level for level in self.levels if level.price < current_price]
            return max(support_levels, key=lambda x: x.price) if support_levels else None
        else:
            # Find lowest resistance above current price
            resistance_levels = [level for level in self.levels if level.price > current_price]
            return min(resistance_levels, key=lambda x: x.price) if resistance_levels else None


class ISignalListener(ABC):
    """Interface for receiving trading signals."""
    
    @abstractmethod
    async def start_listening(self) -> None:
        """Start listening for signals."""
        pass
    
    @abstractmethod
    async def stop_listening(self) -> None:
        """Stop listening for signals."""
        pass
    
    @abstractmethod
    async def process_signal(self, signal_data: Dict[str, Any]) -> TradingSignal:
        """Process incoming signal data."""
        pass


class IOrderManager(ABC):
    """Interface for managing trading orders."""
    
    @abstractmethod
    async def place_order(self, order: Order) -> str:
        """Place a new order. Returns order ID."""
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        pass
    
    @abstractmethod
    async def get_order_status(self, order_id: str) -> OrderStatus:
        """Get the current status of an order."""
        pass
    
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all open orders, optionally filtered by symbol."""
        pass


class IPositionManager(ABC):
    """Interface for managing positions."""
    
    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for a symbol."""
        pass
    
    @abstractmethod
    async def get_all_positions(
        self, 
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Position]:
        """
        Get all current positions with optional pagination.
        
        Args:
            limit: Maximum number of positions to return. None for all positions.
            offset: Number of positions to skip (for pagination). Defaults to 0.
            
        Returns:
            List of positions, optionally paginated.
        """
        pass
    
    @abstractmethod
    async def update_position(self, symbol: str, quantity: float, price: float) -> None:
        """Update position after a trade."""
        pass


class IDatabaseManager(ABC):
    """
    Interface for database operations.
    
    Provides abstraction over the database layer for position, order,
    and trade record persistence.
    """
    
    @abstractmethod
    async def get_session(self):
        """Get a database session context manager."""
        pass
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize database connection and create tables."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close database connection."""
        pass


class ISupportCalculator(ABC):
    """Interface for calculating support levels."""
    
    @abstractmethod
    async def calculate_support(self, symbol: str, timeframe: str) -> SupportLevel:
        """Calculate support level for a symbol and timeframe."""
        pass


class ITrailingProfitManager(ABC):
    """Interface for managing trailing profit logic."""
    
    @abstractmethod
    async def should_trail(self, position: Position, current_price: float) -> bool:
        """Determine if trailing should be activated."""
        pass
    
    @abstractmethod
    async def calculate_trailing_stop(self, position: Position, 
                                    current_price: float) -> float:
        """Calculate trailing stop price."""
        pass
    
    @abstractmethod
    async def should_take_profit(self, position: Position, 
                               current_price: float) -> bool:
        """Determine if profit should be taken."""
        pass


# Type alias for position state (used by DCA and trailing managers)
# Using Any to avoid circular imports - actual type is PositionState
PositionStateType = Any


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


# Type alias for close position callback
ClosePositionCallback = Callable[[str], Awaitable[None]]


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
        close_callback: ClosePositionCallback
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


class IRiskManager(ABC):
    """Interface for risk management."""
    
    @abstractmethod
    async def validate_order(self, order: Order) -> bool:
        """Validate order against risk parameters."""
        pass
    
    @abstractmethod
    async def calculate_position_size(self, symbol: str, signal: TradingSignal) -> float:
        """Calculate appropriate position size."""
        pass
    
    @abstractmethod
    async def get_max_exposure(self, symbol: str) -> float:
        """Get maximum allowed exposure for a symbol."""
        pass


class IMarketDataProvider(ABC):
    """Interface for market data access."""
    
    @abstractmethod
    async def get_current_price(self, symbol: str) -> float:
        """Get current market price for a symbol."""
        pass
    
    @abstractmethod
    async def get_historical_data(self, symbol: str, timeframe: str, 
                                count: int) -> List[Dict[str, Any]]:
        """Get historical market data."""
        pass


class IConfigurationManager(ABC):
    """
    Interface for configuration management.
    
    Supports both synchronous (cached) and asynchronous access patterns.
    Async methods are preferred for Azure-native configuration.
    """
    
    @abstractmethod
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key (synchronous, from cache).
        
        For async access with Azure priority, use get_config_async().
        """
        pass
    
    @abstractmethod
    def set_config(self, key: str, value: Any) -> None:
        """Set configuration value (local cache only, use set_config_async for persistence)."""
        pass
    
    @abstractmethod
    def reload_config(self) -> None:
        """Reload configuration from source."""
        pass


class IAsyncConfigurationManager(ABC):
    """
    Async interface for Azure-native configuration management.
    
    Uses Azure Key Vault for secrets and App Configuration for runtime settings.
    Supports hot-reload and Managed Identity authentication.
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize Azure clients using Managed Identity."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close Azure clients and stop background tasks."""
        pass
    
    @abstractmethod
    async def get_secret(self, name: str, default: str = "") -> str:
        """Get secret from Azure Key Vault."""
        pass
    
    @abstractmethod
    async def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration from Azure App Configuration."""
        pass
    
    @abstractmethod
    async def set_config(self, key: str, value: Any) -> None:
        """Set configuration in Azure App Configuration."""
        pass
    
    @abstractmethod
    async def refresh(self) -> None:
        """Force refresh configuration from Azure."""
        pass
    
    @abstractmethod
    def on_change(self, callback) -> None:
        """Register callback for configuration changes (hot-reload)."""
        pass


class IAccountProvider(ABC):
    """Interface for accessing account information."""
    
    @abstractmethod
    async def get_account_value(self) -> float:
        """Get current account value/equity."""
        pass
    
    @abstractmethod
    async def get_buying_power(self) -> float:
        """Get available buying power."""
        pass
    
    @abstractmethod
    async def get_portfolio_value(self) -> float:
        """Get total portfolio value including positions."""
        pass
    
    @abstractmethod
    async def get_cash(self) -> float:
        """Get available cash (not including margin)."""
        pass


class IAsyncContextManager(ABC):
    """
    Interface for components requiring async runtime lifecycle management.
    
    Use this interface for components that have an active runtime state:
    - Signal listeners
    - Trading bots
    - Market data streams
    - Event processors
    
    Pattern: start() -> [active processing] -> stop()
    
    For resource management (connections, clients), use IAsyncResource instead.
    """
    
    @abstractmethod
    async def start(self) -> None:
        """Start the component's active processing."""
        pass
        
    @abstractmethod
    async def stop(self) -> None:
        """Stop the component and cleanup resources."""
        pass
    
    @property
    def is_running(self) -> bool:
        """Check if the component is currently running."""
        return False


class IAsyncResource(ABC):
    """
    Interface for components requiring async resource lifecycle management.
    
    Use this interface for components that manage external resources:
    - Database connections
    - Azure clients (Key Vault, App Configuration)
    - Message queue connections
    - Cache clients
    
    Pattern: initialize() -> [resource available] -> close()
    
    For runtime processing components, use IAsyncContextManager instead.
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the resource connection.
        
        Called once during application startup to establish
        connections and configure the resource.
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close the resource and release connections.
        
        Called during application shutdown to properly
        cleanup resources and close connections.
        """
        pass
    
    @property
    def is_initialized(self) -> bool:
        """Check if the resource has been initialized."""
        return False


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
        signal: TradingSignal,
        position: Optional[Position] = None,
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
        position: Position,
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
        position: Position,
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
