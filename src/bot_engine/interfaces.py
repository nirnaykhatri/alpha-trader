"""
Bot Engine Interfaces and Data Classes.

Defines the contracts for the multi-bot execution architecture.
All implementations must follow these interfaces for consistency
and testability.

Author: Trading Bot Team
Version: 1.0.0
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
import asyncio


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class BotEngineConfig:
    """
    Configuration for the Bot Engine Manager.
    
    Controls resource limits and operational parameters
    for the multi-bot execution environment.
    """
    
    # Capacity limits
    max_concurrent_bots: int = 500
    max_bots_per_symbol: int = 50
    max_bots_per_user: int = 100
    
    # Performance tuning
    event_loop_tick_ms: int = 100  # Main loop tick interval
    state_persist_interval_seconds: int = 5  # How often to persist bot state
    health_check_interval_seconds: int = 30  # Health check frequency
    
    # Resource sharing
    share_market_data: bool = True  # Share market data streams across bots
    share_broker_connections: bool = True  # Share broker connections
    
    # Graceful shutdown
    shutdown_timeout_seconds: int = 30
    force_close_positions_on_shutdown: bool = False
    
    def validate(self) -> None:
        """Validate configuration values."""
        if self.max_concurrent_bots < 1:
            raise ValueError("max_concurrent_bots must be at least 1")
        if self.max_bots_per_symbol < 1:
            raise ValueError("max_bots_per_symbol must be at least 1")
        if self.event_loop_tick_ms < 10:
            raise ValueError("event_loop_tick_ms must be at least 10ms")


@dataclass
class BotStatus:
    """
    Real-time status of a running bot.
    
    Provides comprehensive information about a bot's current
    state, performance, and operational metrics.
    """
    
    # Identification
    bot_id: str
    bot_name: str
    user_id: str
    
    # State
    is_running: bool = False
    operational_phase: str = "idle"
    state: str = "created"
    
    # Trading info
    symbol: str = ""
    exchange: str = ""
    bot_type: str = "dca"
    
    # Position info
    has_position: bool = False
    position_size: Optional[Decimal] = None
    avg_entry_price: Optional[Decimal] = None
    current_price: Optional[Decimal] = None
    unrealized_pnl: Optional[Decimal] = None
    unrealized_pnl_percent: Optional[Decimal] = None
    
    # Performance
    total_pnl: Decimal = Decimal("0")
    total_pnl_percent: Decimal = Decimal("0")
    completed_deals: int = 0
    current_deal_id: Optional[str] = None
    
    # DCA specific
    safety_orders_used: int = 0
    max_safety_orders: int = 0
    
    # Timestamps
    started_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    last_order_at: Optional[datetime] = None
    
    # Error info
    error_message: Optional[str] = None
    error_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "botId": self.bot_id,
            "botName": self.bot_name,
            "userId": self.user_id,
            "isRunning": self.is_running,
            "operationalPhase": self.operational_phase,
            "state": self.state,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "botType": self.bot_type,
            "hasPosition": self.has_position,
            "positionSize": str(self.position_size) if self.position_size else None,
            "avgEntryPrice": str(self.avg_entry_price) if self.avg_entry_price else None,
            "currentPrice": str(self.current_price) if self.current_price else None,
            "unrealizedPnl": str(self.unrealized_pnl) if self.unrealized_pnl else None,
            "unrealizedPnlPercent": str(self.unrealized_pnl_percent) if self.unrealized_pnl_percent else None,
            "totalPnl": str(self.total_pnl),
            "totalPnlPercent": str(self.total_pnl_percent),
            "completedDeals": self.completed_deals,
            "currentDealId": self.current_deal_id,
            "safetyOrdersUsed": self.safety_orders_used,
            "maxSafetyOrders": self.max_safety_orders,
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "lastActivityAt": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "lastOrderAt": self.last_order_at.isoformat() if self.last_order_at else None,
            "errorMessage": self.error_message,
            "errorCount": self.error_count,
        }


@dataclass
class MarketDataSubscription:
    """
    Represents a subscription to market data for a symbol.
    
    Tracks subscribers and manages the lifecycle of shared
    market data streams.
    """
    
    symbol: str
    subscribers: Set[str] = field(default_factory=set)  # Set of bot_ids
    last_price: Optional[Decimal] = None
    last_update: Optional[datetime] = None
    is_streaming: bool = False
    
    @property
    def subscriber_count(self) -> int:
        """Number of active subscribers."""
        return len(self.subscribers)
    
    def add_subscriber(self, bot_id: str) -> None:
        """Add a bot as subscriber."""
        self.subscribers.add(bot_id)
    
    def remove_subscriber(self, bot_id: str) -> None:
        """Remove a bot from subscribers."""
        self.subscribers.discard(bot_id)
    
    @property
    def has_subscribers(self) -> bool:
        """Check if there are any active subscribers."""
        return len(self.subscribers) > 0


@dataclass
class SignalSubscription:
    """
    Represents a bot's subscription to trading signals.
    
    Defines what signals a bot wants to receive and
    the callback to invoke when signals arrive.
    """
    
    bot_id: str
    symbols: Set[str] = field(default_factory=set)  # Symbols to receive signals for
    signal_types: Optional[Set[str]] = field(default_factory=set)  # Signal types to receive
    webhook_id: Optional[str] = None  # Unique webhook identifier for this bot
    callback: Optional[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = None
    # Tracking fields (populated by SignalRouter)
    created_at: Optional[datetime] = None
    signals_received: int = 0
    last_signal_at: Optional[datetime] = None
    
    def matches_signal(self, symbol: str, signal_type: str) -> bool:
        """Check if this subscription matches a signal."""
        symbol_match = len(self.symbols) == 0 or symbol in self.symbols
        type_match = len(self.signal_types) == 0 or signal_type in self.signal_types
        return symbol_match and type_match


# =============================================================================
# Interfaces
# =============================================================================

class IBotRunner(ABC):
    """
    Interface for bot execution wrapper.
    
    Each BotRunner is a lightweight async wrapper that executes
    a single bot's trading strategy. Designed for minimal memory
    footprint (~10KB) to support hundreds of concurrent instances.
    """
    
    @property
    @abstractmethod
    def bot_id(self) -> str:
        """Get the bot's unique identifier."""
        pass
    
    @property
    @abstractmethod
    def is_running(self) -> bool:
        """Check if the bot is currently running."""
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """
        Start the bot execution.
        
        Initializes the bot's strategy and begins the main
        execution loop. This method should be called via
        asyncio.create_task() for non-blocking execution.
        """
        pass
    
    @abstractmethod
    async def stop(self, close_positions: bool = False) -> None:
        """
        Stop the bot execution gracefully.
        
        Args:
            close_positions: Whether to close open positions before stopping
        """
        pass
    
    @abstractmethod
    async def pause(self) -> None:
        """
        Pause bot execution temporarily.
        
        Bot remains initialized but stops placing new orders.
        """
        pass
    
    @abstractmethod
    async def resume(self) -> None:
        """
        Resume paused bot execution.
        """
        pass
    
    @abstractmethod
    def get_status(self) -> BotStatus:
        """
        Get current bot status.
        
        Returns:
            BotStatus with real-time metrics and state
        """
        pass
    
    @abstractmethod
    async def handle_signal(self, signal: Dict[str, Any]) -> None:
        """
        Handle an incoming trading signal.
        
        Args:
            signal: Signal data from webhook or other source
        """
        pass
    
    @abstractmethod
    async def handle_price_update(self, symbol: str, price: Decimal) -> None:
        """
        Handle a market price update.
        
        Args:
            symbol: Trading symbol
            price: Current market price
        """
        pass


class IBotEngineManager(ABC):
    """
    Interface for the central bot orchestrator.
    
    Manages all bot instances in a single process using async tasks.
    Provides resource pooling and coordination across all bots.
    """
    
    @abstractmethod
    async def start_engine(self) -> None:
        """
        Start the bot engine and initialize shared resources.
        
        Must be called before starting any bots. Initializes:
        - Market data hub
        - Signal router
        - Broker connection pool
        - Database connections
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """
        Shutdown the bot engine gracefully.
        
        Stops all running bots and releases resources.
        """
        pass
    
    @abstractmethod
    async def start_bot(self, bot_id: str) -> IBotRunner:
        """
        Start a bot by ID.
        
        Loads bot configuration from database and creates
        an async task for execution.
        
        Args:
            bot_id: Unique identifier of the bot to start
            
        Returns:
            BotRunner instance for the started bot
            
        Raises:
            BotAlreadyRunningError: If bot is already running
            BotNotFoundError: If bot configuration not found
            ResourceLimitError: If resource limits exceeded
        """
        pass
    
    @abstractmethod
    async def stop_bot(
        self, 
        bot_id: str, 
        close_positions: bool = False,
        cancel_orders: bool = True
    ) -> None:
        """
        Stop a running bot.
        
        Args:
            bot_id: Unique identifier of the bot to stop
            close_positions: Whether to close open positions
            cancel_orders: Whether to cancel pending orders
        """
        pass
    
    @abstractmethod
    async def pause_bot(self, bot_id: str) -> None:
        """Pause a running bot."""
        pass
    
    @abstractmethod
    async def resume_bot(self, bot_id: str) -> None:
        """Resume a paused bot."""
        pass
    
    @abstractmethod
    def get_bot_status(self, bot_id: str) -> Optional[BotStatus]:
        """
        Get status of a specific bot.
        
        Args:
            bot_id: Bot identifier
            
        Returns:
            BotStatus if bot is running, None otherwise
        """
        pass
    
    @abstractmethod
    def get_all_running_bots(self) -> List[BotStatus]:
        """
        Get status of all running bots.
        
        Returns:
            List of BotStatus for all active bots
        """
        pass
    
    @abstractmethod
    def get_running_bots_by_user(self, user_id: str) -> List[BotStatus]:
        """
        Get status of all bots for a specific user.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of BotStatus for user's active bots
        """
        pass
    
    @abstractmethod
    def get_running_bots_by_symbol(self, symbol: str) -> List[BotStatus]:
        """
        Get status of all bots trading a specific symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            List of BotStatus for bots trading the symbol
        """
        pass
    
    @abstractmethod
    async def broadcast_price_update(self, symbol: str, price: Decimal) -> None:
        """
        Broadcast a price update to all bots trading a symbol.
        
        Args:
            symbol: Trading symbol
            price: Current market price
        """
        pass
    
    @abstractmethod
    async def route_signal(self, signal: Dict[str, Any]) -> int:
        """
        Route an incoming signal to appropriate bots.
        
        Args:
            signal: Signal data from webhook
            
        Returns:
            Number of bots that received the signal
        """
        pass


class IMarketDataHub(ABC):
    """
    Interface for shared market data management.
    
    Provides symbol-based stream deduplication so multiple
    bots trading the same symbol share a single data stream.
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the market data hub."""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown and cleanup all streams."""
        pass
    
    @abstractmethod
    async def subscribe(self, symbol: str, bot_id: str) -> None:
        """
        Subscribe a bot to market data for a symbol.
        
        If this is the first subscriber for the symbol,
        starts a new data stream.
        
        Args:
            symbol: Trading symbol
            bot_id: Subscribing bot's identifier
        """
        pass
    
    @abstractmethod
    async def unsubscribe(self, symbol: str, bot_id: str) -> None:
        """
        Unsubscribe a bot from market data.
        
        If this was the last subscriber for the symbol,
        stops the data stream.
        
        Args:
            symbol: Trading symbol
            bot_id: Unsubscribing bot's identifier
        """
        pass
    
    @abstractmethod
    def get_current_price(self, symbol: str) -> Optional[Decimal]:
        """
        Get the current cached price for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Current price or None if not available
        """
        pass
    
    @abstractmethod
    def get_subscription_info(self, symbol: str) -> Optional[MarketDataSubscription]:
        """
        Get subscription information for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Subscription info or None if no subscribers
        """
        pass
    
    @abstractmethod
    def get_active_symbols(self) -> List[str]:
        """
        Get list of symbols with active subscriptions.
        
        Returns:
            List of symbols being tracked
        """
        pass


class ISignalRouter(ABC):
    """
    Interface for routing signals to bot instances.
    
    Routes incoming webhook signals to the appropriate
    bot instances based on subscription rules.
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the signal router."""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the signal router."""
        pass
    
    @abstractmethod
    def register_bot(
        self, 
        bot_id: str, 
        symbols: Set[str],
        callback: Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]
    ) -> str:
        """
        Register a bot to receive signals.
        
        Args:
            bot_id: Bot identifier
            symbols: Set of symbols to receive signals for
            callback: Async callback to invoke on signal
            
        Returns:
            Unique webhook ID for this bot
        """
        pass
    
    @abstractmethod
    def unregister_bot(self, bot_id: str) -> None:
        """
        Unregister a bot from signals.
        
        Args:
            bot_id: Bot identifier to unregister
        """
        pass
    
    @abstractmethod
    async def route_signal(self, signal: Dict[str, Any]) -> int:
        """
        Route a signal to matching bots.
        
        Args:
            signal: Signal data containing symbol and action
            
        Returns:
            Number of bots that received the signal
        """
        pass
    
    @abstractmethod
    def get_webhook_url(self, bot_id: str) -> Optional[str]:
        """
        Get the webhook URL for a specific bot.
        
        Args:
            bot_id: Bot identifier
            
        Returns:
            Webhook URL or None if bot not registered
        """
        pass


class IBrokerConnectionPool(ABC):
    """
    Interface for shared broker connections.
    
    Manages a pool of broker connections that are shared
    across all bot instances to minimize resource usage.
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the connection pool."""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown all connections."""
        pass
    
    @abstractmethod
    async def get_connection(self, broker: str) -> Any:
        """
        Get a connection from the pool.
        
        Args:
            broker: Broker identifier (e.g., 'alpaca', 'tastytrade')
            
        Returns:
            Broker connection/client instance
        """
        pass
    
    @abstractmethod
    async def release_connection(self, broker: str) -> None:
        """
        Release a connection back to the pool.
        
        Args:
            broker: Broker identifier
        """
        pass
    
    @abstractmethod
    def is_connected(self, broker: str) -> bool:
        """
        Check if a broker connection is active.
        
        Args:
            broker: Broker identifier
            
        Returns:
            True if connected, False otherwise
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> Dict[str, bool]:
        """
        Check health of all broker connections.
        
        Returns:
            Dict mapping broker name to health status
        """
        pass
