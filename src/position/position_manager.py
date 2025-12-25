"""
Position management implementation.
Tracks and manages trading positions with persistence.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from collections import OrderedDict
from src.interfaces import IPositionManager, IConfigurationManager
from src.exceptions import PositionNotFoundException
from src.core.logging_config import get_logger
from src import Position, Order, OrderStatus, OrderType
from src.broker.router import BrokerRouter
from src.broker.interfaces import BrokerType


logger = get_logger(__name__)


class LRUPositionCache:
    """
    LRU (Least Recently Used) cache for positions with bounded size.
    
    Prevents unbounded memory growth by evicting least recently accessed
    positions when the cache reaches its maximum size.
    
    Thread-safety: Not thread-safe. Use with asyncio event loop only.
    
    Example:
        cache = LRUPositionCache(max_size=100)
        cache["AAPL_alpaca"] = position
        position = cache.get("AAPL_alpaca")  # Moves to most recent
    """
    
    def __init__(self, max_size: int = 500):
        """
        Initialize LRU cache.
        
        Args:
            max_size: Maximum number of positions to cache. Defaults to 500.
        """
        self._max_size = max_size
        self._cache: OrderedDict[str, Position] = OrderedDict()
        self._eviction_count = 0
    
    def __setitem__(self, key: str, position: Position) -> None:
        """
        Add or update position in cache.
        
        Moves key to end (most recently used) and evicts oldest if needed.
        """
        if key in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(key)
        self._cache[key] = position
        
        # Evict oldest if over capacity
        while len(self._cache) > self._max_size:
            evicted_key, _ = self._cache.popitem(last=False)
            self._eviction_count += 1
            logger.debug(f"LRU cache evicted: {evicted_key} (total evictions: {self._eviction_count})")
    
    def __getitem__(self, key: str) -> Position:
        """Get position and mark as recently used."""
        position = self._cache[key]
        self._cache.move_to_end(key)
        return position
    
    def __contains__(self, key: str) -> bool:
        """Check if key exists in cache."""
        return key in self._cache
    
    def get(self, key: str, default: Optional[Position] = None) -> Optional[Position]:
        """Get position with default, marking as recently used if found."""
        try:
            return self[key]
        except KeyError:
            return default
    
    def values(self) -> list:
        """Get all cached positions."""
        return list(self._cache.values())
    
    def items(self):
        """Get all cache key-value pairs."""
        return self._cache.items()
    
    def clear(self) -> None:
        """Clear all cached positions."""
        self._cache.clear()
    
    def copy(self) -> Dict[str, Position]:
        """Return a copy of the cache as a dict."""
        return dict(self._cache)
    
    def __len__(self) -> int:
        """Return number of cached positions."""
        return len(self._cache)
    
    @property
    def eviction_count(self) -> int:
        """Get total number of evictions."""
        return self._eviction_count
    
    @property
    def max_size(self) -> int:
        """Get maximum cache size."""
        return self._max_size


class PositionManager(IPositionManager):
    """
    Manages trading positions with database persistence.
    Tracks position updates, P&L, and position history.
    Supports multiple brokers via BrokerRouter.
    
    Uses LRU cache for positions to prevent unbounded memory growth.
    """
    
    # Default max cache size - can be overridden via config
    DEFAULT_MAX_CACHE_SIZE = 500
    
    def __init__(self, config: IConfigurationManager, database_manager, broker_router: Optional[BrokerRouter] = None):
        """
        Initialize position manager.
        
        Args:
            config: Configuration manager instance
            database_manager: Database manager for persistence
            broker_router: Broker router for multi-broker support
        """
        self._config = config
        self._database = database_manager
        self._broker_router = broker_router
        
        # LRU cache with configurable max size
        max_cache_size = config.get_config(
            "performance.max_position_cache_size", 
            self.DEFAULT_MAX_CACHE_SIZE
        )
        self._positions = LRUPositionCache(max_size=max_cache_size)
        
        logger.info(f"PositionManager initialized with LRU cache (max_size={max_cache_size})")
    
    def _get_cache_key(self, symbol: str, broker: str) -> str:
        """Generate cache key for position."""
        return f"{symbol}_{broker}"

    async def get_position(self, symbol: str, broker: str = None) -> Optional[Position]:
        """
        Get current position for a symbol.
        
        Args:
            symbol: Trading symbol
            broker: Optional broker name. If None, tries to find any position for symbol.
            
        Returns:
            Current position or None if no position exists
        """
        try:
            # If broker is specified, check cache directly
            if broker:
                cache_key = self._get_cache_key(symbol, broker)
                if cache_key in self._positions:
                    return self._positions[cache_key]
                
                # Load from database
                position = await self._database.get_position(symbol, broker)
                if position:
                    self._positions[cache_key] = position
                    return position
                return None
            
            # If broker not specified, try to find any position for this symbol
            # Check cache first
            for key, pos in self._positions.items():
                if pos.symbol == symbol:
                    return pos
            
            # Load from database (will return first found)
            position = await self._database.get_position(symbol)
            if position:
                broker = position.broker or 'alpaca'
                self._positions[self._get_cache_key(symbol, broker)] = position
                return position
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting position for {symbol}: {str(e)}")
            return None
    
    async def get_all_positions(
        self, 
        broker: str = None,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Position]:
        """
        Get all current positions with optional pagination and broker filter.
        
        Pagination is delegated to the database layer for efficiency,
        avoiding loading all records into memory before filtering.
        
        Args:
            broker: Optional broker filter
            limit: Maximum number of positions to return. None for all positions.
            offset: Number of positions to skip (for pagination). Defaults to 0.
            
        Returns:
            List of all current positions, optionally paginated
        """
        try:
            # Delegate pagination to database layer for efficiency
            # The database now returns PaginatedResult, but we extract .items for compatibility
            # exclude_zero_quantity is now True by default at database level
            result = await self._database.get_all_positions(
                broker=broker,
                max_items=limit if limit else 1000,
                exclude_zero_quantity=True
            )
            
            # Handle both PaginatedResult and List returns for compatibility
            if hasattr(result, 'items'):
                active_positions = result.items
            else:
                active_positions = result
            
            # Update memory cache with fetched positions
            for position in active_positions:
                pos_broker = position.broker or 'alpaca'
                self._positions[self._get_cache_key(position.symbol, pos_broker)] = position
            
            logger.debug(f"Retrieved {len(active_positions)} active positions (offset={offset}, limit={limit})")
            return active_positions
            
        except Exception as e:
            logger.error(f"Error getting all positions: {str(e)}")
            # Return from cache with pagination
            cached = [pos for pos in self._positions.values() if pos.quantity != 0]
            if offset > 0:
                cached = cached[offset:]
            if limit is not None:
                cached = cached[:limit]
            return cached
    
    async def update_position(self, symbol: str, quantity: float, price: float, broker: str = 'alpaca') -> None:
        """
        Update position after a trade.
        
        Args:
            symbol: Trading symbol
            quantity: Quantity change (positive for buy, negative for sell)
            price: Trade price
            broker: Broker name
        """
        try:
            logger.debug(f"Updating position: {symbol} ({broker}) {quantity:+.2f} @ {price:.4f}")
            
            # Get existing position or create new one
            existing_position = await self.get_position(symbol, broker)
            
            if existing_position:
                # Update existing position
                old_quantity = existing_position.quantity
                old_avg_price = existing_position.avg_price
                
                # Calculate new quantity
                new_quantity = old_quantity + quantity
                
                # Calculate new average price
                if new_quantity == 0:
                    # Position closed
                    new_avg_price = 0
                    # Calculate realized P&L
                    if quantity < 0:  # Selling
                        realized_pnl = abs(quantity) * (price - old_avg_price)
                        existing_position.realized_pnl += realized_pnl
                elif (old_quantity > 0 and quantity > 0) or (old_quantity < 0 and quantity < 0):
                    # Adding to position - calculate weighted average
                    total_cost = (old_quantity * old_avg_price) + (quantity * price)
                    new_avg_price = total_cost / new_quantity
                else:
                    # Reducing position - keep old average price
                    new_avg_price = old_avg_price
                    # Calculate realized P&L for the closed portion
                    if (old_quantity > 0 and quantity < 0) or (old_quantity < 0 and quantity > 0):
                        closed_quantity = min(abs(quantity), abs(old_quantity))
                        if old_quantity > 0:
                            realized_pnl = closed_quantity * (price - old_avg_price)
                        else:
                            realized_pnl = closed_quantity * (old_avg_price - price)
                        existing_position.realized_pnl += realized_pnl
                
                # Update position
                existing_position.quantity = new_quantity
                existing_position.avg_price = new_avg_price
                existing_position.current_price = price
                
                # Calculate unrealized P&L
                if new_quantity != 0:
                    if new_quantity > 0:
                        existing_position.unrealized_pnl = (price - new_avg_price) * new_quantity
                    else:
                        existing_position.unrealized_pnl = (new_avg_price - price) * abs(new_quantity)
                else:
                    existing_position.unrealized_pnl = 0
                
                # Update cache
                self._positions[self._get_cache_key(symbol, broker)] = existing_position
                
            else:
                # Create new position
                new_position = Position(
                    symbol=symbol,
                    quantity=quantity,
                    avg_price=price,
                    current_price=price,
                    unrealized_pnl=0,
                    realized_pnl=0,
                    created_at=datetime.utcnow(),
                    broker=broker
                )
                
                self._positions[self._get_cache_key(symbol, broker)] = new_position
            
            # Save to database
            await self._database.save_position(self._positions[self._get_cache_key(symbol, broker)])
            
            logger.info(f"Position updated: {symbol} ({broker}) - Qty: {self._positions[self._get_cache_key(symbol, broker)].quantity}, "
                       f"Avg: {self._positions[self._get_cache_key(symbol, broker)].avg_price:.4f}")
            
        except Exception as e:
            logger.error(f"Error updating position for {symbol}: {str(e)}")
            raise
    
    async def close_position(self, symbol: str, broker: str = None) -> bool:
        """
        Close a position completely.
        
        Args:
            symbol: Trading symbol
            broker: Optional broker name
            
        Returns:
            True if position was closed successfully
        """
        try:
            position = await self.get_position(symbol, broker)
            if not position or position.quantity == 0:
                logger.warning(f"No position to close for {symbol} ({broker})")
                return False
            
            # Set quantity to zero
            position.quantity = 0
            position.unrealized_pnl = 0
            
            # Update cache and database
            pos_broker = position.broker or 'alpaca'
            self._positions[self._get_cache_key(symbol, pos_broker)] = position
            await self._database.save_position(position)
            
            logger.info(f"Position closed: {symbol} ({pos_broker})")
            return True
            
        except Exception as e:
            logger.error(f"Error closing position for {symbol}: {str(e)}")
            return False
    
    async def get_total_pnl(self) -> Dict[str, float]:
        """
        Get total P&L across all positions.
        
        Returns:
            Dictionary with total realized and unrealized P&L
        """
        try:
            positions = await self.get_all_positions()
            
            total_realized = sum(pos.realized_pnl for pos in positions)
            total_unrealized = sum(pos.unrealized_pnl for pos in positions)
            
            return {
                "realized_pnl": total_realized,
                "unrealized_pnl": total_unrealized,
                "total_pnl": total_realized + total_unrealized
            }
            
        except Exception as e:
            logger.error(f"Error calculating total P&L: {str(e)}")
            return {"realized_pnl": 0, "unrealized_pnl": 0, "total_pnl": 0}
    
    async def get_position_summary(self) -> Dict[str, Any]:
        """
        Get summary of all positions.
        
        Returns:
            Summary dictionary with position statistics
        """
        try:
            positions = await self.get_all_positions()
            pnl = await self.get_total_pnl()
            
            long_positions = [pos for pos in positions if pos.quantity > 0]
            short_positions = [pos for pos in positions if pos.quantity < 0]
            
            return {
                "total_positions": len(positions),
                "long_positions": len(long_positions),
                "short_positions": len(short_positions),
                "total_exposure": sum(abs(pos.quantity * pos.avg_price) for pos in positions),
                "realized_pnl": pnl["realized_pnl"],
                "unrealized_pnl": pnl["unrealized_pnl"],
                "total_pnl": pnl["total_pnl"],
                "positions": [
                    {
                        "symbol": pos.symbol,
                        "broker": pos.broker,
                        "quantity": pos.quantity,
                        "avg_price": pos.avg_price,
                        "current_price": pos.current_price,
                        "unrealized_pnl": pos.unrealized_pnl,
                        "realized_pnl": pos.realized_pnl
                    }
                    for pos in positions
                ]
            }
            
        except Exception as e:
            logger.error(f"Error getting position summary: {str(e)}")
            return {}
    
    def get_cached_positions(self) -> Dict[str, Position]:
        """Get positions from memory cache."""
        return self._positions.copy()
    
    def clear_cache(self) -> None:
        """Clear position cache."""
        self._positions.clear()
        logger.info("Position cache cleared")
    
    async def sync_positions(self) -> Dict[str, Any]:
        """
        Synchronize local positions with broker positions.
        
        Returns:
            Dictionary with sync results
        """
        logger.info("Starting position synchronization...")
        stats = {"updated": 0, "closed": 0, "created": 0, "errors": 0}
        
        try:
            # 1. Get all broker positions (fetch in parallel for performance)
            broker_positions_map = {}  # Key: f"{symbol}_{broker}" -> Position object
            
            if self._broker_router:
                brokers = self._broker_router.get_registered_brokers()
                
                async def fetch_broker_positions(broker_type):
                    """Fetch positions from a single broker."""
                    try:
                        provider = self._broker_router.get_account_provider(broker_type)
                        positions = await provider.get_positions()
                        return broker_type, positions, None
                    except Exception as e:
                        return broker_type, [], e
                
                # Fetch from all brokers in parallel with exception handling
                # return_exceptions=True ensures one broker failure doesn't break others
                import asyncio
                results = await asyncio.gather(
                    *[fetch_broker_positions(bt) for bt in brokers],
                    return_exceptions=True
                )
                
                # Process results, handling any exceptions
                for i, result in enumerate(results):
                    # Check if result is an exception (from return_exceptions=True)
                    if isinstance(result, Exception):
                        broker_type = brokers[i] if i < len(brokers) else None
                        logger.error(f"Exception fetching positions from broker {broker_type}: {result}")
                        stats["errors"] += 1
                        continue
                    
                    broker_type, positions, error = result
                    if error:
                        logger.error(f"Error fetching positions from {broker_type.value}: {error}")
                        stats["errors"] += 1
                        continue
                        
                    for pos in positions:
                        # Ensure broker field is set
                        pos.broker = broker_type.value
                        key = self._get_cache_key(pos.symbol, pos.broker)
                        broker_positions_map[key] = pos
            
            # 2. Get all local positions
            local_positions = await self.get_all_positions()
            local_positions_map = {
                self._get_cache_key(p.symbol, p.broker or 'alpaca'): p 
                for p in local_positions
            }
            
            # 3. Reconcile: Update or Create from Broker
            for key, broker_pos in broker_positions_map.items():
                if key in local_positions_map:
                    local_pos = local_positions_map[key]
                    
                    # Check for differences
                    if (local_pos.quantity != broker_pos.quantity or 
                        abs(local_pos.avg_price - broker_pos.avg_price) > 0.0001):
                        
                        logger.info(f"Syncing update for {broker_pos.symbol} ({broker_pos.broker}): "
                                   f"Qty {local_pos.quantity}->{broker_pos.quantity}, "
                                   f"Price {local_pos.avg_price}->{broker_pos.avg_price}")
                        
                        local_pos.quantity = broker_pos.quantity
                        local_pos.avg_price = broker_pos.avg_price
                        local_pos.current_price = broker_pos.current_price
                        local_pos.unrealized_pnl = broker_pos.unrealized_pnl
                        
                        await self._database.save_position(local_pos)
                        self._positions[key] = local_pos
                        stats["updated"] += 1
                else:
                    # New position found in broker
                    logger.info(f"Syncing new position {broker_pos.symbol} ({broker_pos.broker})")
                    await self._database.save_position(broker_pos)
                    self._positions[key] = broker_pos
                    stats["created"] += 1
            
            # 4. Reconcile: Close missing positions
            for key, local_pos in local_positions_map.items():
                if key not in broker_positions_map and local_pos.quantity != 0:
                    # Position exists locally but not in broker -> It was closed externally
                    logger.info(f"Syncing external close for {local_pos.symbol} ({local_pos.broker})")
                    
                    local_pos.quantity = 0
                    local_pos.unrealized_pnl = 0
                    
                    await self._database.save_position(local_pos)
                    self._positions[key] = local_pos
                    stats["closed"] += 1
            
            logger.info(f"Position sync completed: {stats}")
            return stats
            
        except Exception as e:
            logger.error(f"Error during position sync: {str(e)}")
            raise


