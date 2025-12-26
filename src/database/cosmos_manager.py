"""
Azure Cosmos DB Database Management Implementation.

Provides async access to Cosmos DB NoSQL for storing trading data.
This is the PRIMARY database backend for the trading bot.

Lazy Loading:
    Azure SDK imports are deferred until initialize() is called.
    This allows tests to import this module without Azure SDK installed.

Usage:
    cosmos_manager = CosmosDBManager(config)
    await cosmos_manager.initialize()
    await cosmos_manager.save_position(position)
    
    # For bot management, use CosmosBotRepository:
    bot_repo = cosmos_manager.get_bot_repository()
    await bot_repo.create_bot(bot)

Containers (Core Trading):
    - positions: Active trading positions (partition key: /symbol)
    - orders: Order history (partition key: /symbol)
    - trades: Completed trades with P&L (partition key: /symbol)
    - signals: Trading signals received (partition key: /symbol)

Containers (Bot Management - via CosmosBotRepository):
    - bots: Active bot configurations (partition key: /user_id)
    - bot_orders: All orders for bots (partition key: /bot_id)
    - bot_history: Closed bot records (partition key: /user_id)

Authentication:
    Uses DefaultAzureCredential (Managed Identity in Azure, CLI locally)
    
Note:
    SQLite/SQLAlchemy support has been removed. Cosmos DB is the sole 
    database backend for this application.
    
    This module uses the shared CosmosConnectionPool from cosmos_base.py
    for efficient connection management across all repositories.
"""

from __future__ import annotations

import asyncio
import json
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

# Lazy imports for Azure SDK - only loaded when actually connecting
if TYPE_CHECKING:
    from azure.cosmos import PartitionKey, exceptions

from src.interfaces import IConfigurationManager
from src.exceptions import TradingBotException
from src.core.logging_config import get_logger
from src.interfaces import Position, Order, OrderStatus, OrderType

# Import shared base and bot repository
from src.database.cosmos_base import CosmosConnectionPool, CosmosBaseRepository
from src.database.cosmos_bot_repository import CosmosBotRepository

# Import pagination helpers for scalable queries
from src.database.pagination import (
    PaginationOptions,
    PaginatedResult,
    QueryProjection,
    ActiveOnlyFilter,
    build_paginated_query,
    POSITION_FIELDS_FULL,
    ORDER_FIELDS_FULL,
    TRADE_FIELDS_FULL,
    DEFAULT_MAX_ITEMS,
    ABSOLUTE_MAX_ITEMS,
)

logger = get_logger(__name__)


class CosmosDBManager:
    """
    Async Cosmos DB manager for persisting trading data.
    
    Uses Azure Cosmos DB NoSQL API with serverless/free tier optimization.
    Partition key strategy: symbol for even distribution and efficient queries.
    
    Uses the shared CosmosConnectionPool for efficient connection management
    across all Cosmos DB repositories in the application.
    
    Thread-Safety:
        This class is safe for concurrent async operations.
        The shared connection pool handles synchronization internally.
    
    Attributes:
        _config: Configuration manager instance
        _pool: Shared connection pool reference
        _containers: Dictionary of container references
    """
    
    # Container configurations with TTL settings
    CONTAINER_CONFIGS = {
        'positions': {
            'partition_key': '/symbol',
            'default_ttl': -1,  # No TTL - positions are critical
        },
        'orders': {
            'partition_key': '/symbol',
            'default_ttl': 7776000,  # 90 days
        },
        'trades': {
            'partition_key': '/symbol',
            'default_ttl': -1,  # No TTL - trade history is valuable
        },
        'signals': {
            'partition_key': '/symbol',
            'default_ttl': 2592000,  # 30 days
        },
        'broker_connections': {
            'partition_key': '/broker_type',
            'default_ttl': -1,  # No TTL - connections persist indefinitely
        },
    }
    
    def __init__(self, config: IConfigurationManager):
        """
        Initialize Cosmos DB manager.
        
        Args:
            config: Configuration manager instance providing:
                - azure.cosmos.endpoint: Cosmos DB endpoint URL
                - azure.cosmos.database_name: Database name
        """
        self._config = config
        self._pool = CosmosConnectionPool.get_instance()
        self._containers: Dict[str, Any] = {}
        self._cosmos_exceptions = None  # Lazy loaded Azure exceptions module
        
        # Configuration
        self._endpoint = config.get_config(
            "azure.cosmos.endpoint",
            None
        )
        self._database_name = config.get_config(
            "azure.cosmos.database_name",
            "trading-bot"
        )
        
        if not self._endpoint:
            raise TradingBotException(
                "Cosmos DB endpoint not configured. "
                "Set 'azure.cosmos.endpoint' in App Configuration or environment."
            )
        
        logger.info(f"CosmosDBManager initialized for endpoint: {self._endpoint}")
    
    @property
    def _database(self):
        """Get database reference from shared pool."""
        return self._pool.database
    
    @property
    def _client(self):
        """Get client reference from shared pool."""
        return self._pool.client
    
    async def initialize(self) -> None:
        """
        Initialize async Cosmos DB connection and verify containers exist.
        
        Uses the shared CosmosConnectionPool for connection management.
        Creates containers if they don't exist.
        
        Azure SDK is imported lazily here, allowing this module to be
        imported without the SDK installed (e.g., for testing).
        
        Raises:
            ImportError: If Azure SDK is not installed
            TradingBotException: If initialization fails
        """
        # Lazy import Azure SDK - only when actually initializing
        from azure.cosmos import PartitionKey, exceptions
        
        try:
            logger.info("Initializing Cosmos DB connection...")
            
            # Initialize shared connection pool
            await self._pool.initialize(
                endpoint=self._endpoint,
                database_name=self._database_name
            )
            
            logger.info(f"Connected to database: {self._database_name}")
            
            # Get or create containers
            for container_name, config in self.CONTAINER_CONFIGS.items():
                container = await self._database.create_container_if_not_exists(
                    id=container_name,
                    partition_key=PartitionKey(path=config['partition_key']),
                    default_ttl=config['default_ttl'] if config['default_ttl'] != -1 else None,
                )
                self._containers[container_name] = container
                logger.debug(f"Container ready: {container_name}")
            
            # Store exceptions module for use in other methods
            self._cosmos_exceptions = exceptions
            
            logger.info("Cosmos DB initialized successfully")
            
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Cosmos DB HTTP error: {e.message}")
            raise TradingBotException(f"Cosmos DB initialization failed: {e.message}")
        except Exception as e:
            logger.error(f"Failed to initialize Cosmos DB: {str(e)}")
            raise TradingBotException(f"Cosmos DB initialization failed: {str(e)}")
    
    async def close(self) -> None:
        """Release local resources (connection pool is managed separately)."""
        self._containers.clear()
        logger.info("CosmosDBManager resources released")
    
    def _serialize_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        """Serialize datetime to ISO format string."""
        return CosmosBaseRepository.serialize_datetime(dt)
    
    def _deserialize_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Deserialize ISO format string to datetime."""
        return CosmosBaseRepository.deserialize_datetime(dt_str)
    
    # ==================== POSITION OPERATIONS ====================
    
    async def save_position(self, position: Position) -> None:
        """
        Save or update a position in Cosmos DB.
        
        Uses upsert operation for atomic create/update.
        Document ID format: {broker}_{symbol}
        
        Args:
            position: Position to save
            
        Raises:
            TradingBotException: If save operation fails
        """
        try:
            broker = position.broker or 'alpaca'
            doc_id = f"{broker}_{position.symbol}"
            
            document = {
                'id': doc_id,
                'symbol': position.symbol,
                'broker': broker,
                'quantity': position.quantity,
                'avg_price': position.avg_price,
                'current_price': position.current_price,
                'unrealized_pnl': position.unrealized_pnl,
                'realized_pnl': position.realized_pnl,
                'created_at': self._serialize_datetime(position.created_at),
                'updated_at': self._serialize_datetime(datetime.utcnow()),
                'type': 'position',
            }
            
            container = self._containers['positions']
            await container.upsert_item(document)
            
            logger.debug(f"Position saved: {position.symbol} ({broker})")
            
        except self._cosmos_exceptions.CosmosHttpResponseError as e:
            logger.error(f"Error saving position {position.symbol}: {e.message}")
            raise TradingBotException(f"Failed to save position: {e.message}")
    
    async def get_position(self, symbol: str, broker: str = None) -> Optional[Position]:
        """
        Get a position from Cosmos DB.
        
        Args:
            symbol: Trading symbol
            broker: Optional broker name. Defaults to 'alpaca'.
            
        Returns:
            Position if found, None otherwise
        """
        try:
            broker = broker or 'alpaca'
            doc_id = f"{broker}_{symbol}"
            
            container = self._containers['positions']
            
            try:
                item = await container.read_item(item=doc_id, partition_key=symbol)
                return Position(
                    symbol=item['symbol'],
                    quantity=item['quantity'],
                    avg_price=item['avg_price'],
                    current_price=item['current_price'],
                    unrealized_pnl=item['unrealized_pnl'],
                    realized_pnl=item['realized_pnl'],
                    created_at=self._deserialize_datetime(item.get('created_at')),
                    broker=item.get('broker', 'alpaca'),
                )
            except self._cosmos_exceptions.CosmosResourceNotFoundError:
                return None
                
        except Exception as e:
            logger.error(f"Error getting position {symbol}: {str(e)}")
            return None
    
    async def get_all_positions(
        self,
        broker: str = None,
        max_items: int = DEFAULT_MAX_ITEMS,
        exclude_zero_quantity: bool = True,
        continuation_token: Optional[str] = None
    ) -> PaginatedResult[Position]:
        """
        Get positions from Cosmos DB with pagination support.
        
        Uses field projection to reduce RU consumption and supports
        continuation tokens for efficient cursor-based pagination.
        
        Args:
            broker: Optional broker filter
            max_items: Maximum number of items to return (default 100, max 1000)
            exclude_zero_quantity: If True, excludes closed positions (default True)
            continuation_token: Token from previous query for pagination
            
        Returns:
            PaginatedResult containing positions and continuation token
            
        Example:
            # First page
            result = await db.get_all_positions(max_items=50)
            positions = result.items
            
            # Next page (if available)
            if result.has_more:
                result = await db.get_all_positions(
                    max_items=50,
                    continuation_token=result.continuation_token
                )
        """
        try:
            container = self._containers['positions']
            
            # Cap max_items for safety
            max_items = min(max_items, ABSOLUTE_MAX_ITEMS)
            
            # Build conditions list
            conditions = []
            parameters = []
            
            if exclude_zero_quantity:
                conditions.append(ActiveOnlyFilter.POSITION_HAS_QUANTITY)
            
            if broker:
                conditions.append(ActiveOnlyFilter.broker_filter(broker))
                parameters.append({"name": "@broker", "value": broker})
            
            # Build query with field projection (reduces RU consumption)
            query = build_paginated_query(
                fields=POSITION_FIELDS_FULL,
                conditions=conditions if conditions else None,
                order_by="created_at",
                descending=True
            )
            
            positions = []
            response_token = None
            request_charge = 0.0
            
            # Execute query - SDK 4.x doesn't use continuation_token parameter
            # For pagination, use .by_page() method instead
            query_iterator = container.query_items(
                query=query,
                parameters=parameters if parameters else None,
                max_item_count=max_items
            )
            
            async for item in query_iterator:
                positions.append(Position(
                    symbol=item['symbol'],
                    quantity=item['quantity'],
                    avg_price=item['avg_price'],
                    current_price=item['current_price'],
                    unrealized_pnl=item.get('unrealized_pnl', 0),
                    realized_pnl=item.get('realized_pnl', 0),
                    created_at=self._deserialize_datetime(item.get('created_at')),
                    broker=item.get('broker', 'alpaca'),
                ))
                
                if len(positions) >= max_items:
                    break
            
            # For now, simple pagination - no continuation token handling
            # SDK 4.x changed pagination: use .by_page() for true cursor-based pagination
            # See PaginatedResult docstring for implementation details
            has_more = len(positions) >= max_items
            
            if len(positions) >= max_items:
                logger.debug(
                    f"get_all_positions returned {len(positions)} items, "
                    f"has_more={has_more}"
                )
            
            return PaginatedResult(
                items=positions,
                continuation_token=None,  # Not implemented in simplified mode
                has_more=has_more,
                total_fetched=len(positions),
                request_charge=request_charge
            )
            
        except Exception as e:
            logger.error(f"Error getting all positions: {str(e)}")
            return PaginatedResult(items=[], has_more=False)
    
    async def delete_position(self, symbol: str, broker: str = None) -> bool:
        """
        Delete a position from Cosmos DB.
        
        Args:
            symbol: Trading symbol
            broker: Broker name
            
        Returns:
            True if deleted, False otherwise
        """
        try:
            broker = broker or 'alpaca'
            doc_id = f"{broker}_{symbol}"
            
            container = self._containers['positions']
            await container.delete_item(item=doc_id, partition_key=symbol)
            
            logger.info(f"Position deleted: {symbol} ({broker})")
            return True
            
        except self._cosmos_exceptions.CosmosResourceNotFoundError:
            return False
        except Exception as e:
            logger.error(f"Error deleting position {symbol}: {str(e)}")
            return False
    
    # ==================== ORDER OPERATIONS ====================
    
    async def save_order(self, order: Order) -> None:
        """
        Save or update an order in Cosmos DB.
        
        Args:
            order: Order to save
        """
        try:
            document = {
                'id': str(order.order_id),
                'symbol': order.symbol,
                'broker': order.broker or 'alpaca',
                'quantity': order.quantity,
                'order_type': order.order_type.value,
                'side': order.side.value if hasattr(order.side, 'value') else str(order.side),
                'price': order.price,
                'stop_price': order.stop_price,
                'status': order.status.value,
                'created_at': self._serialize_datetime(order.created_at),
                'filled_at': self._serialize_datetime(order.filled_at),
                'filled_price': order.filled_price,
                'filled_quantity': order.filled_quantity,
                'broker_order_id': order.broker_order_id,
                'is_dca_order': order.is_dca_order,
                'is_closing': order.is_closing,
                'type': 'order',
            }
            
            container = self._containers['orders']
            await container.upsert_item(document)
            
            logger.debug(f"Order saved: {order.order_id}")
            
        except self._cosmos_exceptions.CosmosHttpResponseError as e:
            logger.error(f"Error saving order {order.order_id}: {e.message}")
            raise TradingBotException(f"Failed to save order: {e.message}")
    
    async def get_orders(
        self,
        symbol: Optional[str] = None,
        status: Optional[OrderStatus] = None,
        broker: Optional[str] = None,
        limit: int = 100
    ) -> List[Order]:
        """
        Get orders from Cosmos DB with optional filtering.
        
        Args:
            symbol: Optional symbol filter
            status: Optional status filter
            broker: Optional broker filter
            limit: Maximum number of orders to return
            
        Returns:
            List of orders matching criteria
        """
        try:
            container = self._containers['orders']
            
            # Build query dynamically
            conditions = []
            parameters = []
            
            if symbol:
                conditions.append("c.symbol = @symbol")
                parameters.append({"name": "@symbol", "value": symbol})
            
            if status:
                conditions.append("c.status = @status")
                parameters.append({"name": "@status", "value": status.value})
            
            if broker:
                conditions.append("c.broker = @broker")
                parameters.append({"name": "@broker", "value": broker})
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            query = f"SELECT TOP {limit} * FROM c WHERE {where_clause} ORDER BY c.created_at DESC"
            
            orders = []
            async for item in container.query_items(
                query=query,
                parameters=parameters
            ):
                orders.append(Order(
                    order_id=item['id'],
                    symbol=item['symbol'],
                    quantity=item['quantity'],
                    order_type=OrderType(item['order_type']),
                    side=item['side'],
                    price=item.get('price'),
                    stop_price=item.get('stop_price'),
                    status=OrderStatus(item['status']),
                    created_at=self._deserialize_datetime(item.get('created_at')),
                    filled_at=self._deserialize_datetime(item.get('filled_at')),
                    filled_price=item.get('filled_price'),
                    filled_quantity=item.get('filled_quantity'),
                    broker=item.get('broker'),
                    broker_order_id=item.get('broker_order_id'),
                    is_dca_order=item.get('is_dca_order', False),
                    is_closing=item.get('is_closing', False),
                ))
            
            return orders
            
        except Exception as e:
            logger.error(f"Error getting orders: {str(e)}")
            return []
    
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
        try:
            trade_id = f"{symbol}_{str(entry_order.order_id)}"
            
            document = {
                'id': trade_id,
                'symbol': symbol,
                'broker': entry_order.broker or 'alpaca',
                'entry_order_id': str(entry_order.order_id),
                'entry_price': entry_order.filled_price or entry_order.price,
                'entry_quantity': entry_order.filled_quantity or entry_order.quantity,
                'entry_time': self._serialize_datetime(
                    entry_order.filled_at or entry_order.created_at
                ),
                'entry_side': entry_order.side.value if hasattr(entry_order.side, 'value') else str(entry_order.side),
                'strategy_used': strategy_used,
                'created_at': self._serialize_datetime(datetime.utcnow()),
                'completed_at': None,
                'type': 'trade',
            }
            
            container = self._containers['trades']
            await container.create_item(document)
            
            logger.info(
                f"Trade entry created: {trade_id} - {symbol} {entry_order.side} "
                f"{document['entry_quantity']} @ ${document['entry_price']:.4f}"
            )
            
            return trade_id
            
        except self._cosmos_exceptions.CosmosHttpResponseError as e:
            logger.error(f"Error creating trade entry: {e.message}")
            raise TradingBotException(f"Failed to create trade entry: {e.message}")
    
    async def complete_trade(
        self,
        trade_id: str,
        exit_order: Order,
        exit_reason: str
    ) -> Dict[str, Any]:
        """
        Complete a trade by adding exit information and calculating P&L.
        
        Args:
            trade_id: Trade identifier
            exit_order: The filled exit order
            exit_reason: Reason for exit
            
        Returns:
            Trade summary with P&L information
        """
        try:
            container = self._containers['trades']
            
            # Parse symbol from trade_id
            symbol = trade_id.split('_')[0]
            
            # Read existing trade
            try:
                trade = await container.read_item(item=trade_id, partition_key=symbol)
            except self._cosmos_exceptions.CosmosResourceNotFoundError:
                raise TradingBotException(f"Trade {trade_id} not found")
            
            # Calculate P&L
            exit_price = exit_order.filled_price or exit_order.price
            exit_quantity = exit_order.filled_quantity or exit_order.quantity
            entry_price = trade['entry_price']
            
            if trade['entry_side'].lower() == 'buy':
                realized_pnl = (exit_price - entry_price) * exit_quantity
                profit_percentage = ((exit_price - entry_price) / entry_price) * 100
            else:
                realized_pnl = (entry_price - exit_price) * exit_quantity
                profit_percentage = ((entry_price - exit_price) / entry_price) * 100
            
            # Update trade document
            trade['exit_order_id'] = str(exit_order.order_id)
            trade['exit_price'] = exit_price
            trade['exit_quantity'] = exit_quantity
            trade['exit_time'] = self._serialize_datetime(
                exit_order.filled_at or exit_order.created_at
            )
            trade['exit_side'] = exit_order.side.value if hasattr(exit_order.side, 'value') else str(exit_order.side)
            trade['exit_reason'] = exit_reason
            trade['realized_pnl'] = realized_pnl
            trade['profit_percentage'] = profit_percentage
            trade['completed_at'] = self._serialize_datetime(datetime.utcnow())
            
            await container.replace_item(item=trade_id, body=trade)
            
            # Calculate duration
            entry_time = self._deserialize_datetime(trade['entry_time'])
            exit_time = self._deserialize_datetime(trade['exit_time'])
            duration_minutes = (exit_time - entry_time).total_seconds() / 60 if entry_time and exit_time else 0
            
            trade_summary = {
                'trade_id': trade_id,
                'symbol': symbol,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'quantity': exit_quantity,
                'realized_pnl': realized_pnl,
                'profit_percentage': profit_percentage,
                'exit_reason': exit_reason,
                'duration_minutes': duration_minutes,
            }
            
            logger.info(
                f"Trade completed: {trade_id} - {symbol} "
                f"P&L: ${realized_pnl:.2f} ({profit_percentage:.2f}%) "
                f"Reason: {exit_reason}"
            )
            
            return trade_summary
            
        except TradingBotException:
            raise
        except Exception as e:
            logger.error(f"Error completing trade: {str(e)}")
            raise TradingBotException(f"Failed to complete trade: {str(e)}")
    
    async def get_open_trades(
        self,
        symbol: str = None,
        max_items: int = DEFAULT_MAX_ITEMS,
        continuation_token: Optional[str] = None  # Ignored - kept for API compatibility
    ) -> PaginatedResult[Dict[str, Any]]:
        """
        Get open trades (not yet completed) with simplified pagination.
        
        Uses field projection to only fetch required fields, reducing RU consumption.
        
        Note:
            This implementation uses a simplified pagination model. The Azure Cosmos DB
            SDK 4.x async iterator doesn't expose continuation tokens directly. Instead,
            `has_more` is set heuristically based on whether `max_items` were returned.
            The `continuation_token` parameter is accepted for API compatibility but
            is currently ignored.
        
        Args:
            symbol: Optional symbol filter
            max_items: Maximum number of items to return (default 100, max 1000)
            continuation_token: Ignored. Kept for API compatibility with older callers.
            
        Returns:
            PaginatedResult with:
                - items: List of open trade dictionaries
                - continuation_token: Always None (SDK limitation)
                - has_more: True if max_items were returned (heuristic)
                - total_fetched: Number of items returned
        """
        try:
            container = self._containers['trades']
            
            # Cap max_items for safety
            max_items = min(max_items, ABSOLUTE_MAX_ITEMS)
            
            # Define fields needed for open trades (minimal projection)
            open_trade_fields = [
                "id", "symbol", "broker", "entry_price", "entry_quantity",
                "entry_time", "entry_side", "strategy_used"
            ]
            
            # Build conditions
            conditions = [ActiveOnlyFilter.TRADE_IS_OPEN]
            parameters = []
            
            if symbol:
                conditions.append(ActiveOnlyFilter.symbol_filter(symbol))
                parameters.append({"name": "@symbol", "value": symbol})
            
            # Build query with projection
            query = build_paginated_query(
                fields=open_trade_fields,
                conditions=conditions,
                order_by="entry_time",
                descending=True
            )
            
            trades = []
            
            # Execute query - SDK 4.x doesn't use continuation_token parameter
            query_iterator = container.query_items(
                query=query,
                parameters=parameters if parameters else None,
                max_item_count=max_items
            )
            
            async for item in query_iterator:
                trades.append({
                    'trade_id': item['id'],
                    'symbol': item['symbol'],
                    'broker': item.get('broker', 'alpaca'),
                    'entry_price': item['entry_price'],
                    'entry_quantity': item['entry_quantity'],
                    'entry_time': self._deserialize_datetime(item.get('entry_time')),
                    'entry_side': item['entry_side'],
                    'strategy_used': item.get('strategy_used'),
                })
                
                if len(trades) >= max_items:
                    break
            
            has_more = len(trades) >= max_items
            
            return PaginatedResult(
                items=trades,
                continuation_token=None,  # SDK 4.x uses different pagination
                has_more=has_more,
                total_fetched=len(trades)
            )
            
        except Exception as e:
            logger.error(f"Error getting open trades: {str(e)}")
            return PaginatedResult(items=[], has_more=False)
    
    async def get_completed_trades(
        self,
        symbol: str = None,
        limit: int = DEFAULT_MAX_ITEMS,
        continuation_token: Optional[str] = None  # Ignored - kept for API compatibility
    ) -> PaginatedResult[Dict[str, Any]]:
        """
        Get completed trades with P&L information and simplified pagination.
        
        Uses field projection for efficient RU consumption.
        
        Note:
            This implementation uses a simplified pagination model. The Azure Cosmos DB
            SDK 4.x async iterator doesn't expose continuation tokens directly. Instead,
            `has_more` is set heuristically based on whether `limit` items were returned.
            The `continuation_token` parameter is accepted for API compatibility but
            is currently ignored.
        
        Args:
            symbol: Optional symbol filter
            limit: Maximum number of trades to return (default 100, max 1000)
            continuation_token: Ignored. Kept for API compatibility with older callers.
            
        Returns:
            PaginatedResult with:
                - items: List of completed trade dictionaries
                - continuation_token: Always None (SDK limitation)
                - has_more: True if limit items were returned (heuristic)
                - total_fetched: Number of items returned
        """
        try:
            container = self._containers['trades']
            
            # Cap limit for safety
            limit = min(limit, ABSOLUTE_MAX_ITEMS)
            
            # Define fields needed for completed trades
            completed_trade_fields = [
                "id", "symbol", "broker", "entry_price", "exit_price",
                "entry_quantity", "exit_quantity", "entry_time", "exit_time",
                "realized_pnl", "profit_percentage", "exit_reason", "strategy_used"
            ]
            
            # Build conditions
            conditions = [ActiveOnlyFilter.TRADE_IS_COMPLETED]
            parameters = []
            
            if symbol:
                conditions.append(ActiveOnlyFilter.symbol_filter(symbol))
                parameters.append({"name": "@symbol", "value": symbol})
            
            # Build query with projection
            query = build_paginated_query(
                fields=completed_trade_fields,
                conditions=conditions,
                order_by="completed_at",
                descending=True,
                limit=limit
            )
            
            trades = []
            
            # Execute query - SDK 4.x doesn't use continuation_token parameter
            query_iterator = container.query_items(
                query=query,
                parameters=parameters if parameters else None,
                max_item_count=limit
            )
            
            async for item in query_iterator:
                trades.append({
                    'trade_id': item['id'],
                    'symbol': item['symbol'],
                    'broker': item.get('broker', 'alpaca'),
                    'entry_price': item['entry_price'],
                    'exit_price': item.get('exit_price'),
                    'quantity': item.get('exit_quantity'),
                    'entry_time': self._deserialize_datetime(item.get('entry_time')),
                    'exit_time': self._deserialize_datetime(item.get('exit_time')),
                    'realized_pnl': item.get('realized_pnl'),
                    'profit_percentage': item.get('profit_percentage'),
                    'exit_reason': item.get('exit_reason'),
                    'strategy_used': item.get('strategy_used'),
                })
                
                if len(trades) >= limit:
                    break
            
            has_more = len(trades) >= limit
            
            return PaginatedResult(
                items=trades,
                continuation_token=None,  # SDK 4.x uses different pagination
                has_more=has_more,
                total_fetched=len(trades)
            )
            
        except Exception as e:
            logger.error(f"Error getting completed trades: {str(e)}")
            return PaginatedResult(items=[], has_more=False)
    
    # ==================== SIGNAL OPERATIONS ====================
    
    async def save_signal(self, signal) -> None:
        """
        Save a trading signal to Cosmos DB.
        
        Args:
            signal: Trading signal to save
        """
        try:
            document = {
                'id': signal.signal_id,
                'symbol': signal.symbol,
                'signal_type': signal.signal_type.value,
                'price': signal.price,
                'quantity': signal.quantity,
                'timestamp': self._serialize_datetime(signal.timestamp),
                'metadata': signal.metadata,
                'processed_at': self._serialize_datetime(datetime.utcnow()),
                'type': 'signal',
            }
            
            container = self._containers['signals']
            await container.create_item(document)
            
            logger.debug(f"Signal saved: {signal.signal_id}")
            
        except self._cosmos_exceptions.CosmosHttpResponseError as e:
            logger.error(f"Error saving signal {signal.signal_id}: {e.message}")
            raise
    
    # ==================== STATISTICS ====================
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """
        Get database statistics for health monitoring.
        
        Returns:
            Dictionary with database statistics
        """
        try:
            stats = {}
            
            # Count positions
            container = self._containers['positions']
            query = "SELECT VALUE COUNT(1) FROM c"
            async for count in container.query_items(query=query):
                stats['positions_total'] = count
                break
            
            # Count open positions
            query = "SELECT VALUE COUNT(1) FROM c WHERE c.quantity != 0"
            async for count in container.query_items(query=query):
                stats['positions_open'] = count
                break
            
            # Count orders
            container = self._containers['orders']
            query = "SELECT VALUE COUNT(1) FROM c"
            async for count in container.query_items(query=query):
                stats['orders_total'] = count
                break
            
            # Count completed trades
            container = self._containers['trades']
            query = "SELECT VALUE COUNT(1) FROM c WHERE c.completed_at != null"
            async for count in container.query_items(query=query):
                stats['trades_completed'] = count
                break
            
            stats['database_type'] = 'cosmos_db'
            stats['endpoint'] = self._endpoint
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting database stats: {str(e)}")
            return {'error': str(e)}
    
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
        try:
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            container = self._containers['trades']
            
            # Count completed trades
            if symbol:
                query = """
                    SELECT VALUE COUNT(1) FROM c 
                    WHERE c.completed_at != null 
                    AND c.completed_at >= @cutoff
                    AND c.symbol = @symbol
                """
                parameters = [
                    {"name": "@cutoff", "value": cutoff_date},
                    {"name": "@symbol", "value": symbol},
                ]
            else:
                query = """
                    SELECT VALUE COUNT(1) FROM c 
                    WHERE c.completed_at != null 
                    AND c.completed_at >= @cutoff
                """
                parameters = [{"name": "@cutoff", "value": cutoff_date}]
            
            total_trades = 0
            async for count in container.query_items(
                query=query,
                parameters=parameters
            ):
                total_trades = count
                break
            
            # Calculate winning trades
            win_query = query.replace("COUNT(1)", "COUNT(1)").replace(
                "c.completed_at >= @cutoff",
                "c.completed_at >= @cutoff AND c.realized_pnl > 0"
            )
            
            winning_trades = 0
            async for count in container.query_items(
                query=win_query,
                parameters=parameters
            ):
                winning_trades = count
                break
            
            return {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': total_trades - winning_trades,
                'win_rate': (winning_trades / total_trades * 100) if total_trades > 0 else 0,
                'period_days': days,
                'symbol': symbol,
            }
            
        except Exception as e:
            logger.error(f"Error getting trading history: {str(e)}")
            return {}
    
    # ==================== BOT REPOSITORY INTEGRATION ====================
    
    def get_bot_repository(self) -> CosmosBotRepository:
        """
        Get the bot repository for bot management operations.
        
        The bot repository provides complete CRUD operations for:
        - Bots (active bot configurations and state)
        - Bot orders (all orders associated with bots)
        - Bot history (closed/deleted bots for analytics)
        
        Returns:
            CosmosBotRepository instance configured with the same endpoint
            
        Usage:
            ```python
            bot_repo = cosmos_manager.get_bot_repository()
            await bot_repo.initialize()
            
            # Create a bot
            bot = Bot(user_id="user123", name="AAPL DCA", symbol="AAPL")
            await bot_repo.create_bot(bot)
            ```
        """
        return CosmosBotRepository(
            cosmos_endpoint=self._endpoint,
            database_name=self._database_name,
            credential=self._credential
        )
