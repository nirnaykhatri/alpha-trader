"""
Azure Cosmos DB database management implementation.

Provides async access to Cosmos DB NoSQL for storing trading data.
Implements the same interface patterns as database_manager.py for seamless migration.

Usage:
    cosmos_manager = CosmosDBManager(config)
    await cosmos_manager.initialize()
    await cosmos_manager.save_position(position)

Containers:
    - positions: Active trading positions (partition key: symbol)
    - orders: Order history (partition key: symbol)
    - trades: Completed trades with P&L (partition key: symbol)
    - signals: Trading signals received (partition key: symbol)

Authentication:
    Uses DefaultAzureCredential (Managed Identity in Azure, CLI locally)
"""

import asyncio
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

from azure.cosmos.aio import CosmosClient
from azure.cosmos import PartitionKey, exceptions
from azure.identity.aio import DefaultAzureCredential

from src.interfaces import IConfigurationManager
from src.exceptions import TradingBotException
from src.core.logging_config import get_logger
from src import Position, Order, OrderStatus, OrderType

logger = get_logger(__name__)


class CosmosDBManager:
    """
    Async Cosmos DB manager for persisting trading data.
    
    Uses Azure Cosmos DB NoSQL API with serverless/free tier optimization.
    Partition key strategy: symbol for even distribution and efficient queries.
    
    Thread-Safety:
        This class is safe for concurrent async operations.
        The Cosmos client handles connection pooling internally.
    
    Attributes:
        _config: Configuration manager instance
        _client: Async Cosmos DB client
        _database: Database reference
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
        self._client: Optional[CosmosClient] = None
        self._database = None
        self._containers: Dict[str, Any] = {}
        self._credential: Optional[DefaultAzureCredential] = None
        
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
    
    async def initialize(self) -> None:
        """
        Initialize async Cosmos DB connection and verify containers exist.
        
        Creates database and containers if they don't exist.
        Uses DefaultAzureCredential for authentication (Managed Identity in Azure).
        
        Raises:
            TradingBotException: If initialization fails
        """
        try:
            logger.info("Initializing Cosmos DB connection...")
            
            # Create credential for authentication
            self._credential = DefaultAzureCredential()
            
            # Create async Cosmos client
            self._client = CosmosClient(
                url=self._endpoint,
                credential=self._credential,
            )
            
            # Get or create database
            self._database = await self._client.create_database_if_not_exists(
                id=self._database_name
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
            
            logger.info("Cosmos DB initialized successfully")
            
        except exceptions.CosmosHttpResponseError as e:
            logger.error(f"Cosmos DB HTTP error: {e.message}")
            raise TradingBotException(f"Cosmos DB initialization failed: {e.message}")
        except Exception as e:
            logger.error(f"Failed to initialize Cosmos DB: {str(e)}")
            raise TradingBotException(f"Cosmos DB initialization failed: {str(e)}")
    
    async def close(self) -> None:
        """Close async Cosmos DB connections."""
        try:
            if self._client:
                await self._client.close()
                logger.info("Cosmos DB connections closed")
            if self._credential:
                await self._credential.close()
        except Exception as e:
            logger.error(f"Error closing Cosmos DB: {str(e)}")
    
    def _serialize_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        """Serialize datetime to ISO format string."""
        return dt.isoformat() if dt else None
    
    def _deserialize_datetime(self, dt_str: Optional[str]) -> Optional[datetime]:
        """Deserialize ISO format string to datetime."""
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        except ValueError:
            return None
    
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
            
        except exceptions.CosmosHttpResponseError as e:
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
            except exceptions.CosmosResourceNotFoundError:
                return None
                
        except Exception as e:
            logger.error(f"Error getting position {symbol}: {str(e)}")
            return None
    
    async def get_all_positions(self, broker: str = None) -> List[Position]:
        """
        Get all positions from Cosmos DB.
        
        Args:
            broker: Optional broker filter
            
        Returns:
            List of all positions
        """
        try:
            container = self._containers['positions']
            
            if broker:
                query = "SELECT * FROM c WHERE c.broker = @broker AND c.quantity != 0"
                parameters = [{"name": "@broker", "value": broker}]
            else:
                query = "SELECT * FROM c WHERE c.quantity != 0"
                parameters = []
            
            positions = []
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ):
                positions.append(Position(
                    symbol=item['symbol'],
                    quantity=item['quantity'],
                    avg_price=item['avg_price'],
                    current_price=item['current_price'],
                    unrealized_pnl=item['unrealized_pnl'],
                    realized_pnl=item['realized_pnl'],
                    created_at=self._deserialize_datetime(item.get('created_at')),
                    broker=item.get('broker', 'alpaca'),
                ))
            
            return positions
            
        except Exception as e:
            logger.error(f"Error getting all positions: {str(e)}")
            return []
    
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
            
        except exceptions.CosmosResourceNotFoundError:
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
            
        except exceptions.CosmosHttpResponseError as e:
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
                parameters=parameters,
                enable_cross_partition_query=True
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
            
        except exceptions.CosmosHttpResponseError as e:
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
            except exceptions.CosmosResourceNotFoundError:
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
    
    async def get_open_trades(self, symbol: str = None) -> List[Dict[str, Any]]:
        """
        Get all open trades (not yet completed).
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of open trade dictionaries
        """
        try:
            container = self._containers['trades']
            
            if symbol:
                query = "SELECT * FROM c WHERE c.completed_at = null AND c.symbol = @symbol"
                parameters = [{"name": "@symbol", "value": symbol}]
            else:
                query = "SELECT * FROM c WHERE c.completed_at = null"
                parameters = []
            
            trades = []
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ):
                trades.append({
                    'trade_id': item['id'],
                    'symbol': item['symbol'],
                    'entry_price': item['entry_price'],
                    'entry_quantity': item['entry_quantity'],
                    'entry_time': self._deserialize_datetime(item.get('entry_time')),
                    'entry_side': item['entry_side'],
                    'strategy_used': item.get('strategy_used'),
                })
            
            return trades
            
        except Exception as e:
            logger.error(f"Error getting open trades: {str(e)}")
            return []
    
    async def get_completed_trades(
        self,
        symbol: str = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get completed trades with P&L information.
        
        Args:
            symbol: Optional symbol filter
            limit: Maximum number of trades to return
            
        Returns:
            List of completed trade dictionaries
        """
        try:
            container = self._containers['trades']
            
            if symbol:
                query = f"SELECT TOP {limit} * FROM c WHERE c.completed_at != null AND c.symbol = @symbol ORDER BY c.completed_at DESC"
                parameters = [{"name": "@symbol", "value": symbol}]
            else:
                query = f"SELECT TOP {limit} * FROM c WHERE c.completed_at != null ORDER BY c.completed_at DESC"
                parameters = []
            
            trades = []
            async for item in container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ):
                trades.append({
                    'trade_id': item['id'],
                    'symbol': item['symbol'],
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
            
            return trades
            
        except Exception as e:
            logger.error(f"Error getting completed trades: {str(e)}")
            return []
    
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
            
        except exceptions.CosmosHttpResponseError as e:
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
            async for count in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
                stats['positions_total'] = count
                break
            
            # Count open positions
            query = "SELECT VALUE COUNT(1) FROM c WHERE c.quantity != 0"
            async for count in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
                stats['positions_open'] = count
                break
            
            # Count orders
            container = self._containers['orders']
            query = "SELECT VALUE COUNT(1) FROM c"
            async for count in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
                stats['orders_total'] = count
                break
            
            # Count completed trades
            container = self._containers['trades']
            query = "SELECT VALUE COUNT(1) FROM c WHERE c.completed_at != null"
            async for count in container.query_items(
                query=query,
                enable_cross_partition_query=True
            ):
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
                parameters=parameters,
                enable_cross_partition_query=True
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
                parameters=parameters,
                enable_cross_partition_query=True
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
