"""
Database Manager - Cosmos DB Wrapper.

This module provides backward-compatible database access by wrapping
CosmosDBManager. It maintains the same API as the legacy SQLAlchemy-based
DatabaseManager, allowing existing code to work without modification.

IMPORTANT: This is a transitional layer. New code should use
CosmosDBManager directly for better type safety and features.

Usage:
    # Legacy pattern (still works)
    from src.database import DatabaseManager
    db = DatabaseManager(config)
    await db.initialize()
    await db.save_position(position)
    
    # New recommended pattern
    from src.database.cosmos_manager import CosmosDBManager
    db = CosmosDBManager(config)
    await db.initialize()
    await db.save_position(position)

Migration:
    The APIs are intentionally compatible. Simply replace the import.
    
Architecture:
    - DatabaseManager wraps CosmosDBManager for backward compatibility
    - All data is stored in Azure Cosmos DB
    - SQLite/SQLAlchemy support has been removed
    - Pagination support added in v2.1.0
    
Author: Trading Bot Team
Version: 2.1.0 - Added pagination support
"""

from typing import List, Optional, Dict, Any, Union
from datetime import datetime

from src.interfaces import IConfigurationManager
from src.exceptions import TradingBotException
from src.core.logging_config import get_logger
from src import Position, Order, OrderStatus
from src.database.cosmos_manager import CosmosDBManager
from src.database.database_interface import IDatabaseManager
from src.database.pagination import PaginatedResult

logger = get_logger(__name__)


class DatabaseManager(IDatabaseManager):
    """
    Database manager that wraps CosmosDBManager for backward compatibility.
    
    This class implements the IDatabaseManager interface and delegates all
    operations to CosmosDBManager. It provides the same API as the legacy
    SQLAlchemy-based DatabaseManager.
    
    Note:
        New code should use CosmosDBManager directly. This wrapper is
        maintained for backward compatibility with existing code.
    
    Attributes:
        _cosmos_manager: The underlying CosmosDBManager instance
        _config: Configuration manager instance
    
    Example:
        ```python
        db: IDatabaseManager = DatabaseManager(config)
        await db.initialize()
        
        # Save a position
        await db.save_position(position)
        
        # Get all positions
        positions = await db.get_all_positions()
        ```
    """
    
    def __init__(self, config: IConfigurationManager):
        """
        Initialize database manager.
        
        Args:
            config: Configuration manager instance providing Cosmos DB settings
        
        Raises:
            TradingBotException: If Cosmos DB endpoint is not configured
        """
        self._config = config
        self._cosmos_manager: Optional[CosmosDBManager] = None
        
        # Check if Cosmos DB is configured
        cosmos_endpoint = config.get_config("azure.cosmos.endpoint")
        if not cosmos_endpoint:
            logger.warning(
                "Cosmos DB endpoint not configured. "
                "Set 'azure.cosmos.endpoint' in configuration."
            )
        
        logger.info("DatabaseManager initialized (Cosmos DB backend)")
    
    async def initialize(self) -> None:
        """
        Initialize database connection to Cosmos DB.
        
        Creates the CosmosDBManager and initializes the connection.
        All containers will be created if they don't exist.
        
        Raises:
            TradingBotException: If initialization fails
        """
        try:
            logger.info("Initializing database connection (Cosmos DB)...")
            
            self._cosmos_manager = CosmosDBManager(self._config)
            await self._cosmos_manager.initialize()
            
            logger.info("Database initialized successfully (Cosmos DB)")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {str(e)}")
            raise TradingBotException(f"Database initialization failed: {str(e)}")
    
    async def close(self) -> None:
        """Close database connections."""
        try:
            if self._cosmos_manager:
                await self._cosmos_manager.close()
                logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database: {str(e)}")
    
    # ==================== POSITION OPERATIONS ====================
    
    async def save_position(self, position: Position) -> None:
        """
        Save or update a position.
        
        Args:
            position: Position to save
            
        Raises:
            TradingBotException: If save operation fails
        """
        await self._ensure_initialized()
        await self._cosmos_manager.save_position(position)
    
    async def get_position(self, symbol: str, broker: str = None) -> Optional[Position]:
        """
        Get a position by symbol.
        
        Args:
            symbol: Trading symbol
            broker: Optional broker name
            
        Returns:
            Position if found, None otherwise
        """
        await self._ensure_initialized()
        return await self._cosmos_manager.get_position(symbol, broker)
    
    async def get_all_positions(
        self,
        broker: str = None,
        limit: Optional[int] = None,
        offset: int = 0,
        exclude_zero_quantity: bool = True,
        max_items: int = 100,
        continuation_token: Optional[str] = None,
        return_paginated: bool = False
    ) -> Union[List[Position], PaginatedResult[Position]]:
        """
        Get all positions with optional pagination.
        
        Supports both legacy list-based returns and new paginated returns.
        By default, returns a simple list for backward compatibility.
        
        Args:
            broker: Optional broker filter
            limit: Maximum positions (legacy param, use max_items instead)
            offset: Skip positions (legacy param, use continuation_token instead)
            exclude_zero_quantity: If True, excludes closed positions (default True)
            max_items: Maximum items per page for pagination (default 100)
            continuation_token: Token from previous query for pagination
            return_paginated: If True, returns PaginatedResult; else List
            
        Returns:
            List[Position] for backward compatibility, or
            PaginatedResult[Position] if return_paginated=True
        """
        await self._ensure_initialized()
        
        # Use limit if provided (legacy support), otherwise use max_items
        effective_max = limit if limit is not None else max_items
        
        # Call the updated cosmos_manager method
        result = await self._cosmos_manager.get_all_positions(
            broker=broker,
            max_items=effective_max,
            exclude_zero_quantity=exclude_zero_quantity,
            continuation_token=continuation_token
        )
        
        # Return format based on caller preference
        if return_paginated:
            return result
        else:
            # Backward compatibility: return just the items list
            return result.items
    
    # ==================== ORDER OPERATIONS ====================
    
    async def save_order(self, order: Order) -> None:
        """
        Save or update an order.
        
        Args:
            order: Order to save
        """
        await self._ensure_initialized()
        await self._cosmos_manager.save_order(order)
    
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
        await self._ensure_initialized()
        return await self._cosmos_manager.get_orders(symbol, status, broker)
    
    # ==================== TRADE OPERATIONS ====================
    
    async def create_trade_entry(
        self,
        symbol: str,
        entry_order: Order,
        strategy_used: str = None
    ) -> str:
        """
        Create a new trade record when an entry order is filled.
        
        Args:
            symbol: Trading symbol
            entry_order: The filled entry order
            strategy_used: Strategy that initiated the trade
            
        Returns:
            trade_id: Unique identifier for the trade
        """
        await self._ensure_initialized()
        return await self._cosmos_manager.create_trade_entry(
            symbol, entry_order, strategy_used
        )
    
    async def complete_trade(
        self,
        trade_id: str,
        exit_order: Order,
        exit_reason: str
    ) -> Dict[str, Any]:
        """
        Complete a trade with exit information and P&L.
        
        Args:
            trade_id: Trade identifier
            exit_order: The filled exit order
            exit_reason: Reason for exit
            
        Returns:
            Trade summary with P&L information
        """
        await self._ensure_initialized()
        return await self._cosmos_manager.complete_trade(
            trade_id, exit_order, exit_reason
        )
    
    async def get_open_trades(
        self,
        symbol: str = None,
        max_items: int = 100,
        continuation_token: Optional[str] = None,
        return_paginated: bool = False
    ) -> Union[List[Dict[str, Any]], PaginatedResult[Dict[str, Any]]]:
        """
        Get all open trades (not yet completed) with optional pagination.
        
        Args:
            symbol: Optional symbol filter
            max_items: Maximum items per page (default 100)
            continuation_token: Token for pagination
            return_paginated: If True, returns PaginatedResult
            
        Returns:
            List of open trade dictionaries, or PaginatedResult if requested
        """
        await self._ensure_initialized()
        result = await self._cosmos_manager.get_open_trades(
            symbol=symbol,
            max_items=max_items,
            continuation_token=continuation_token
        )
        return result if return_paginated else result.items
    
    async def get_completed_trades(
        self,
        symbol: str = None,
        limit: int = 100,
        continuation_token: Optional[str] = None,
        return_paginated: bool = False
    ) -> Union[List[Dict[str, Any]], PaginatedResult[Dict[str, Any]]]:
        """
        Get completed trades with P&L information and optional pagination.
        
        Args:
            symbol: Optional symbol filter
            limit: Maximum number of trades to return
            continuation_token: Token for pagination
            return_paginated: If True, returns PaginatedResult
            
        Returns:
            List of completed trade dictionaries, or PaginatedResult if requested
        """
        await self._ensure_initialized()
        result = await self._cosmos_manager.get_completed_trades(
            symbol=symbol,
            limit=limit,
            continuation_token=continuation_token
        )
        return result if return_paginated else result.items
    
    # ==================== SIGNAL OPERATIONS ====================
    
    async def save_signal(self, signal) -> None:
        """
        Save a trading signal.
        
        Args:
            signal: Trading signal to save
        """
        await self._ensure_initialized()
        await self._cosmos_manager.save_signal(signal)
    
    # ==================== STATISTICS ====================
    
    async def get_trading_history(
        self,
        symbol: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get trading history for analysis.
        
        Args:
            symbol: Optional symbol filter
            days: Number of days to look back
            
        Returns:
            Dictionary with trading statistics
        """
        await self._ensure_initialized()
        return await self._cosmos_manager.get_trading_history(symbol, days)
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """
        Get database statistics for health monitoring.
        
        Returns:
            Dictionary with database statistics
        """
        await self._ensure_initialized()
        return await self._cosmos_manager.get_database_stats()
    
    # ==================== DEPRECATED METHODS ====================
    # These methods existed in the SQLite version but are no longer applicable
    
    async def cleanup_old_data(self, days: int = 90) -> None:
        """
        Clean up old data.
        
        Note: Cosmos DB uses TTL for automatic cleanup. This method is a no-op
        but maintained for backward compatibility.
        
        Args:
            days: Number of days of data to keep (not used)
        """
        logger.info(
            "cleanup_old_data is a no-op for Cosmos DB. "
            "Data cleanup is handled by container TTL settings."
        )
    
    async def backup_database(self, backup_path: str = None) -> str:
        """
        Create a backup of the database.
        
        Note: Cosmos DB has built-in continuous backup. This method is a no-op
        but maintained for backward compatibility.
        
        Args:
            backup_path: Optional backup path (not used)
            
        Returns:
            Message indicating backup is handled by Azure
        """
        logger.info(
            "backup_database is a no-op for Cosmos DB. "
            "Backups are managed by Azure Cosmos DB continuous backup feature."
        )
        return "cosmos_db_continuous_backup"
    
    async def restore_database(self, backup_path: str) -> None:
        """
        Restore database from backup.
        
        Note: Cosmos DB point-in-time restore is managed via Azure Portal.
        This method is a no-op but maintained for backward compatibility.
        
        Args:
            backup_path: Path to backup file (not used)
        """
        logger.info(
            "restore_database is a no-op for Cosmos DB. "
            "Use Azure Portal for point-in-time restore."
        )
    
    # ==================== POSITION TRACKING (Legacy) ====================
    # These methods were specific to SQLite tracking tables
    
    async def save_position_tracking(
        self,
        symbol: str,
        quantity: float,
        avg_price: float,
        cost_basis: float,
        is_trailing: bool = False,
        activation_price: float = None,
        peak_price: float = None,
        stop_price: float = None
    ) -> None:
        """
        Save position tracking information.
        
        Note: In Cosmos DB, tracking info is stored with the position.
        This method updates the position directly.
        """
        await self._ensure_initialized()
        
        # Get existing position
        position = await self.get_position(symbol)
        if position:
            position.quantity = quantity
            position.avg_price = avg_price
            await self.save_position(position)
        else:
            logger.warning(f"Position {symbol} not found for tracking update")
    
    async def get_position_tracking(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get position tracking information.
        
        Note: Returns basic position info from Cosmos DB.
        """
        await self._ensure_initialized()
        
        position = await self.get_position(symbol)
        if position:
            return {
                'symbol': position.symbol,
                'total_quantity': position.quantity,
                'avg_entry_price': position.avg_price,
                'total_cost_basis': position.quantity * position.avg_price,
                'is_trailing': False,  # Not tracked in Cosmos
            }
        return None
    
    # ==================== HELPERS ====================
    
    async def _ensure_initialized(self) -> None:
        """Ensure database is initialized."""
        if not self._cosmos_manager:
            raise TradingBotException(
                "Database not initialized. Call initialize() first."
            )
    
    def get_cosmos_manager(self) -> CosmosDBManager:
        """
        Get the underlying CosmosDBManager.
        
        Use this to access Cosmos-specific features not exposed by
        the backward-compatible API.
        
        Returns:
            CosmosDBManager instance
        """
        return self._cosmos_manager
    
    def get_bot_repository(self):
        """
        Get the bot repository for bot management.
        
        Returns:
            CosmosBotRepository instance
        """
        if not self._cosmos_manager:
            raise TradingBotException(
                "Database not initialized. Call initialize() first."
            )
        return self._cosmos_manager.get_bot_repository()
