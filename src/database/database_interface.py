"""
Database Interface Protocol.

Defines the abstract interface for database operations in the trading bot.
All database implementations (Cosmos DB, mock for testing) should implement
this protocol.

This interface supports dependency injection and testability by allowing
different implementations to be swapped without changing the consuming code.

Note:
    This module avoids importing from src/__init__.py to prevent circular
    imports. Import from src.interfaces directly instead.

Usage:
    # Production
    db: IDatabaseManager = CosmosDBManager(config)
    
    # Testing
    db: IDatabaseManager = MockDatabaseManager()
    
    # Inject into services
    service = TradingService(database=db)

Author: Trading Bot Team
Version: 1.1.0 - Added pagination support
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

# Import directly from interfaces to avoid circular import via src/__init__
from src.interfaces import Position, Order, OrderStatus, OrderSide
from src.domain.bot_state import Bot, BotOrder, BotHistoryEntry
from src.domain.bot_enums import BotState, BotOperationalPhase


# Forward reference for PaginatedResult to avoid circular import
# The actual type is defined in src.database.pagination
PaginatedResultType = Any


class IDatabaseManager(ABC):
    """
    Abstract interface for database operations.
    
    Defines the contract that all database implementations must fulfill.
    This enables dependency injection and easy testing with mock implementations.
    
    All methods are async to support non-blocking I/O operations.
    """
    
    # =========================================================================
    # Lifecycle
    # =========================================================================
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize database connection.
        
        Should be called before any other operations. Creates tables/containers
        if they don't exist and establishes the connection pool.
        
        Raises:
            TradingBotException: If initialization fails
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close database connections.
        
        Should be called during application shutdown to properly release resources.
        """
        pass
    
    # =========================================================================
    # Position Operations
    # =========================================================================
    
    @abstractmethod
    async def save_position(self, position: Position) -> None:
        """
        Save or update a position.
        
        Args:
            position: Position to save
            
        Raises:
            TradingBotException: If save fails
        """
        pass
    
    @abstractmethod
    async def get_position(self, symbol: str, broker: str = None) -> Optional[Position]:
        """
        Get a position by symbol.
        
        Args:
            symbol: Trading symbol
            broker: Optional broker name
            
        Returns:
            Position if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def get_all_positions(
        self,
        broker: str = None,
        max_items: int = 100,
        exclude_zero_quantity: bool = True,
        continuation_token: Optional[str] = None
    ) -> Union[List[Position], PaginatedResultType]:
        """
        Get positions with pagination support.
        
        Uses field projection and active-only filters to reduce RU consumption
        and memory usage. Supports continuation tokens for cursor-based pagination.
        
        Args:
            broker: Optional broker filter
            max_items: Maximum number of items per page (default 100, max 1000)
            exclude_zero_quantity: If True, excludes closed positions (default True)
            continuation_token: Token from previous query for pagination
            
        Returns:
            PaginatedResult containing positions and continuation token,
            or List[Position] for backward compatibility
        """
        pass
    
    # =========================================================================
    # Order Operations
    # =========================================================================
    
    @abstractmethod
    async def save_order(self, order: Order) -> None:
        """
        Save or update an order.
        
        Args:
            order: Order to save
        """
        pass
    
    @abstractmethod
    async def get_orders(
        self,
        symbol: Optional[str] = None,
        status: Optional[OrderStatus] = None,
        broker: Optional[str] = None
    ) -> List[Order]:
        """
        Get orders with optional filtering.
        
        Args:
            symbol: Optional symbol filter
            status: Optional status filter
            broker: Optional broker filter
            
        Returns:
            List of orders matching criteria
        """
        pass
    
    # =========================================================================
    # Trade Operations
    # =========================================================================
    
    @abstractmethod
    async def create_trade_entry(
        self,
        symbol: str,
        entry_order: Order,
        strategy_used: str = None
    ) -> str:
        """
        Create a new trade record.
        
        Args:
            symbol: Trading symbol
            entry_order: The filled entry order
            strategy_used: Strategy that initiated the trade
            
        Returns:
            trade_id: Unique identifier for the trade
        """
        pass
    
    @abstractmethod
    async def complete_trade(
        self,
        trade_id: str,
        exit_order: Order,
        exit_reason: str
    ) -> Dict[str, Any]:
        """
        Complete a trade with exit information.
        
        Args:
            trade_id: Trade identifier
            exit_order: The filled exit order
            exit_reason: Reason for exit
            
        Returns:
            Trade summary with P&L information
        """
        pass
    
    @abstractmethod
    async def get_open_trades(
        self,
        symbol: str = None,
        max_items: int = 100,
        continuation_token: Optional[str] = None
    ) -> Union[List[Dict[str, Any]], PaginatedResultType]:
        """
        Get open trades with pagination support.
        
        Uses field projection to fetch only required fields, reducing RU consumption.
        
        Args:
            symbol: Optional symbol filter
            max_items: Maximum number of items per page (default 100)
            continuation_token: Token from previous query for pagination
            
        Returns:
            PaginatedResult containing open trade dictionaries,
            or List for backward compatibility
        """
        pass
    
    @abstractmethod
    async def get_completed_trades(
        self,
        symbol: str = None,
        limit: int = 100,
        continuation_token: Optional[str] = None
    ) -> Union[List[Dict[str, Any]], PaginatedResultType]:
        """
        Get completed trades with pagination support.
        
        Uses field projection for efficient RU consumption.
        
        Args:
            symbol: Optional symbol filter
            limit: Maximum number of trades per page (default 100)
            continuation_token: Token from previous query for pagination
            
        Returns:
            PaginatedResult containing completed trade dictionaries,
            or List for backward compatibility
        """
        pass
    
    # =========================================================================
    # Statistics
    # =========================================================================
    
    @abstractmethod
    async def get_trading_history(
        self,
        symbol: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get trading history statistics.
        
        Args:
            symbol: Optional symbol filter
            days: Number of days to look back
            
        Returns:
            Dictionary with trading statistics
        """
        pass
    
    @abstractmethod
    async def get_database_stats(self) -> Dict[str, Any]:
        """
        Get database health statistics.
        
        Returns:
            Dictionary with database statistics
        """
        pass


class IBotRepository(ABC):
    """
    Abstract interface for bot management operations.
    
    Defines the contract for storing and retrieving bot configurations,
    orders, and historical records. Implemented by CosmosBotRepository.
    
    This abstraction enables:
    - Clear separation between domain and infrastructure
    - Easy mocking in tests
    - Future storage backend flexibility
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize bot repository connection and create containers."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close bot repository connection and release resources."""
        pass
    
    # =========================================================================
    # Bot CRUD Operations
    # =========================================================================
    
    @abstractmethod
    async def create_bot(self, bot: Bot) -> Bot:
        """
        Create a new bot.
        
        Args:
            bot: Domain Bot instance to create
            
        Returns:
            Created bot with ID and timestamps
        """
        pass
    
    @abstractmethod
    async def get_bot(self, bot_id: str, user_id: str) -> Optional[Bot]:
        """
        Get a bot by ID.
        
        Args:
            bot_id: Bot ID
            user_id: User ID (partition key for Cosmos)
            
        Returns:
            Domain Bot if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def list_bots(
        self,
        user_id: str,
        state: Optional[BotState] = None,
        symbol: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: int = 100
    ) -> List[Bot]:
        """
        List bots for a user with optional filters.
        
        Args:
            user_id: User ID to filter by
            state: Optional state filter (BotState enum)
            symbol: Optional symbol filter
            is_active: Optional active status filter
            limit: Maximum number of bots to return
            
        Returns:
            List of domain Bot instances
        """
        pass
    
    @abstractmethod
    async def update_bot(self, bot: Bot) -> Bot:
        """
        Update an existing bot.
        
        Args:
            bot: Domain Bot with updated fields
            
        Returns:
            Updated domain Bot
        """
        pass
    
    @abstractmethod
    async def delete_bot(
        self,
        bot_id: str,
        user_id: str,
        close_reason: str = "user_deleted",
        archive: bool = True
    ) -> bool:
        """
        Delete a bot, optionally archiving to history.
        
        Args:
            bot_id: Bot ID to delete
            user_id: User ID (partition key)
            close_reason: Reason for closure
            archive: If True, move to history before deleting
            
        Returns:
            True if deleted successfully
        """
        pass
    
    # =========================================================================
    # Bot State Management
    # =========================================================================
    
    @abstractmethod
    async def update_bot_state(
        self,
        bot_id: str,
        user_id: str,
        state: BotState,
        operational_phase: Optional[BotOperationalPhase] = None
    ) -> Optional[Bot]:
        """
        Update bot state and optionally operational phase.
        
        Args:
            bot_id: Bot ID
            user_id: User ID
            state: New state (BotState enum)
            operational_phase: Optional new operational phase
            
        Returns:
            Updated domain Bot or None if not found
        """
        pass
    
    # =========================================================================
    # Order Operations
    # =========================================================================
    
    @abstractmethod
    async def create_order(self, order: BotOrder) -> BotOrder:
        """Create a new order for a bot."""
        pass
    
    @abstractmethod
    async def get_order(self, order_id: str, bot_id: str) -> Optional[BotOrder]:
        """Get an order by ID."""
        pass
    
    @abstractmethod
    async def list_orders(
        self,
        bot_id: str,
        status: Optional[OrderStatus] = None,
        side: Optional[OrderSide] = None,
        limit: int = 100
    ) -> List[BotOrder]:
        """List orders for a bot with optional filters."""
        pass
    
    @abstractmethod
    async def update_order(self, order: BotOrder) -> BotOrder:
        """Update an existing order."""
        pass
    
    @abstractmethod
    async def get_open_orders(self, bot_id: str) -> List[BotOrder]:
        """Get all open orders for a bot."""
        pass
    
    # =========================================================================
    # History Operations
    # =========================================================================
    
    @abstractmethod
    async def create_history(self, history: BotHistoryEntry) -> BotHistoryEntry:
        """Create a bot history record."""
        pass
    
    @abstractmethod
    async def get_history(self, history_id: str, user_id: str) -> Optional[BotHistoryEntry]:
        """Get a history record by ID."""
        pass
    
    @abstractmethod
    async def list_history(
        self,
        user_id: str,
        symbol: Optional[str] = None,
        close_reason: Optional[str] = None,
        limit: int = 100
    ) -> List[BotHistoryEntry]:
        """List bot history for a user."""
        pass
    
    @abstractmethod
    async def get_history_stats(self, user_id: str) -> Dict[str, Any]:
        """Get aggregate statistics from bot history."""
        pass


# Export interfaces
__all__ = [
    "IDatabaseManager",
    "IBotRepository",
]
