"""
Position management implementation.
Tracks and manages trading positions with persistence.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from ..interfaces import IPositionManager, IConfigurationManager
from ..exceptions import PositionNotFoundException
from ..core.logging_config import get_logger
from .. import Position, Order, OrderStatus, OrderType


logger = get_logger(__name__)


class PositionManager(IPositionManager):
    """
    Manages trading positions with database persistence.
    Tracks position updates, P&L, and position history.
    """
    
    def __init__(self, config: IConfigurationManager, database_manager, trading_client=None):
        """
        Initialize position manager.
        
        Args:
            config: Configuration manager instance
            database_manager: Database manager for persistence
            trading_client: Optional Alpaca trading client for position sync
        """
        self._config = config
        self._database = database_manager
        self._trading_client = trading_client
        self._positions: Dict[str, Position] = {}
        
        logger.info("PositionManager initialized")
    
    async def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get current position for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Current position or None if no position exists
        """
        try:
            # Check memory cache first
            if symbol in self._positions:
                return self._positions[symbol]
            
            # Load from database
            position = await self._database.get_position(symbol)
            if position:
                self._positions[symbol] = position
                return position
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting position for {symbol}: {str(e)}")
            return None
    
    async def get_all_positions(self) -> List[Position]:
        """
        Get all current positions.
        
        Returns:
            List of all current positions
        """
        try:
            # Load all positions from database
            all_positions = await self._database.get_all_positions()
            
            # Update memory cache
            for position in all_positions:
                self._positions[position.symbol] = position
            
            # Filter out zero positions
            active_positions = [pos for pos in all_positions if pos.quantity != 0]
            
            logger.debug(f"Retrieved {len(active_positions)} active positions")
            return active_positions
            
        except Exception as e:
            logger.error(f"Error getting all positions: {str(e)}")
            return list(self._positions.values())
    
    async def update_position(self, symbol: str, quantity: float, price: float) -> None:
        """
        Update position after a trade.
        
        Args:
            symbol: Trading symbol
            quantity: Quantity change (positive for buy, negative for sell)
            price: Trade price
        """
        try:
            logger.debug(f"Updating position: {symbol} {quantity:+.2f} @ {price:.4f}")
            
            # Get existing position or create new one
            existing_position = await self.get_position(symbol)
            
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
                self._positions[symbol] = existing_position
                
            else:
                # Create new position
                new_position = Position(
                    symbol=symbol,
                    quantity=quantity,
                    avg_price=price,
                    current_price=price,
                    unrealized_pnl=0,
                    realized_pnl=0,
                    created_at=datetime.utcnow()
                )
                
                self._positions[symbol] = new_position
            
            # Save to database
            await self._database.save_position(self._positions[symbol])
            
            logger.info(f"Position updated: {symbol} - Qty: {self._positions[symbol].quantity}, "
                       f"Avg: {self._positions[symbol].avg_price:.4f}")
            
        except Exception as e:
            logger.error(f"Error updating position for {symbol}: {str(e)}")
            raise
    
    async def close_position(self, symbol: str) -> bool:
        """
        Close a position completely.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            True if position was closed successfully
        """
        try:
            position = await self.get_position(symbol)
            if not position or position.quantity == 0:
                logger.warning(f"No position to close for {symbol}")
                return False
            
            # Set quantity to zero
            position.quantity = 0
            position.unrealized_pnl = 0
            
            # Update cache and database
            self._positions[symbol] = position
            await self._database.save_position(position)
            
            logger.info(f"Position closed: {symbol}")
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
    
    async def sync_with_alpaca(self) -> None:
        """
        Sync local positions with Alpaca positions.
        This addresses the question: "Why store locally when Alpaca has the data?"
        
        Benefits of local storage:
        1. Faster access (no API calls for every lookup)
        2. Offline operation capability
        3. Custom P&L tracking with our specific logic
        4. Historical position data for analysis
        5. Backup if Alpaca API is temporarily unavailable
        
        This sync ensures consistency between local and Alpaca data.
        """
        if not self._trading_client:
            logger.warning("No trading client available for Alpaca sync")
            return
            
        try:
            logger.info("Syncing positions with Alpaca...")
            
            # Get positions from Alpaca
            alpaca_positions = await self._get_alpaca_positions()
            
            # Track symbols we've seen from Alpaca
            alpaca_symbols = set()
            
            for alpaca_pos in alpaca_positions:
                symbol = alpaca_pos.symbol
                alpaca_symbols.add(symbol)
                
                # Convert Alpaca position to our Position format
                position = Position(
                    symbol=symbol,
                    quantity=float(alpaca_pos.qty),
                    avg_price=float(alpaca_pos.avg_entry_price),
                    current_price=float(alpaca_pos.current_price),
                    unrealized_pnl=float(alpaca_pos.unrealized_pl or 0),
                    realized_pnl=0,  # Alpaca doesn't track this the way we do
                    created_at=datetime.utcnow()
                )
                
                # Update local position
                self._positions[symbol] = position
                await self._database.save_position(position)
                
                logger.debug(f"Synced position: {symbol} - Qty: {position.quantity}, "
                           f"Avg Price: ${position.avg_price:.2f}")
            
            # Check for positions we have locally but not in Alpaca
            local_positions = await self._database.get_all_positions()
            for local_pos in local_positions:
                if local_pos.symbol not in alpaca_symbols and local_pos.quantity != 0:
                    logger.warning(f"Local position {local_pos.symbol} not found in Alpaca - "
                                 f"may have been closed outside this bot")
                    # Optionally close the local position
                    local_pos.quantity = 0
                    local_pos.unrealized_pnl = 0
                    await self._database.save_position(local_pos)
            
            logger.info(f"Position sync complete: {len(alpaca_positions)} positions synced")
            
        except Exception as e:
            logger.error(f"Error syncing with Alpaca: {str(e)}")

    async def _get_alpaca_positions(self):
        """
        Get ALL positions from Alpaca API (async wrapper).
        
        Note: This returns ALL open positions in the account.
        Alpaca maintains one position per symbol (not multiple positions per stock).
        
        Returns:
            List[Position]: All open positions from Alpaca account
        """
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._trading_client.get_all_positions)
        except Exception as e:
            logger.error(f"Failed to get Alpaca positions: {str(e)}")
            return []

    async def get_position_source_comparison(self, symbol: str) -> Dict[str, Any]:
        """
        Compare local position with Alpaca position for debugging.
        Useful for understanding discrepancies.
        """
        result = {
            "symbol": symbol,
            "local_position": None,
            "alpaca_position": None,
            "discrepancies": []
        }
        
        try:
            # Get local position
            local_pos = await self.get_position(symbol)
            if local_pos:
                result["local_position"] = {
                    "quantity": local_pos.quantity,
                    "avg_price": local_pos.avg_price,
                    "unrealized_pnl": local_pos.unrealized_pnl
                }
            
            # Get Alpaca position
            if self._trading_client:
                alpaca_positions = await self._get_alpaca_positions()
                alpaca_pos = next((pos for pos in alpaca_positions if pos.symbol == symbol), None)
                
                if alpaca_pos:
                    result["alpaca_position"] = {
                        "quantity": float(alpaca_pos.qty),
                        "avg_price": float(alpaca_pos.avg_entry_price),
                        "unrealized_pnl": float(alpaca_pos.unrealized_pl or 0)
                    }
                    
                    # Check for discrepancies
                    if local_pos:
                        if abs(local_pos.quantity - float(alpaca_pos.qty)) > 0.001:
                            result["discrepancies"].append("quantity_mismatch")
                        if abs(local_pos.avg_price - float(alpaca_pos.avg_entry_price)) > 0.01:
                            result["discrepancies"].append("avg_price_mismatch")
            
            return result
            
        except Exception as e:
            logger.error(f"Error comparing position sources: {str(e)}")
            return result

    async def recover_database_from_alpaca(self, force_recovery: bool = False) -> Dict[str, Any]:
        """
        Recover local database from Alpaca positions after data loss.
        
        This method can rebuild your position database if the local SQLite file is lost,
        corrupted, or you're starting fresh on a new machine.
        
        Args:
            force_recovery: If True, clears existing local data before recovery
            
        Returns:
            Dictionary with recovery statistics and results
        """
        if not self._trading_client:
            raise ValueError("No trading client available for database recovery")
            
        recovery_stats = {
            "recovered_positions": 0,
            "skipped_positions": 0,
            "errors": [],
            "timestamp": datetime.utcnow(),
            "force_recovery": force_recovery
        }
        
        try:
            logger.info("Starting database recovery from Alpaca...")
            
            if force_recovery:
                logger.warning("Force recovery enabled - clearing existing local positions")
                # Clear existing positions if force recovery
                await self._clear_all_positions()
                self._positions.clear()
            
            # Get all current positions from Alpaca
            alpaca_positions = await self._get_alpaca_positions()
            logger.info(f"Found {len(alpaca_positions)} positions in Alpaca account")
            
            if not alpaca_positions:
                logger.info("No positions found in Alpaca account")
                return recovery_stats
            
            # Process each Alpaca position
            for alpaca_pos in alpaca_positions:
                try:
                    symbol = alpaca_pos.symbol
                    
                    # Check if we already have this position locally (unless force recovery)
                    if not force_recovery:
                        existing_pos = await self.get_position(symbol)
                        if existing_pos and existing_pos.quantity != 0:
                            logger.debug(f"Skipping {symbol} - already exists locally")
                            recovery_stats["skipped_positions"] += 1
                            continue
                    
                    # Create position from Alpaca data
                    recovered_position = Position(
                        symbol=symbol,
                        quantity=float(alpaca_pos.qty),
                        avg_price=float(alpaca_pos.avg_entry_price),
                        current_price=float(alpaca_pos.current_price),
                        unrealized_pnl=float(alpaca_pos.unrealized_pl or 0),
                        realized_pnl=0,  # Cannot recover historical realized P&L
                        created_at=datetime.utcnow()  # Use current time as creation date
                    )
                    
                    # Save to database and cache
                    await self._database.save_position(recovered_position)
                    self._positions[symbol] = recovered_position
                    
                    recovery_stats["recovered_positions"] += 1
                    logger.info(f"Recovered position: {symbol} - Qty: {recovered_position.quantity}, "
                              f"Avg Price: ${recovered_position.avg_price:.2f}")
                    
                except Exception as e:
                    error_msg = f"Failed to recover position {alpaca_pos.symbol}: {str(e)}"
                    logger.error(error_msg)
                    recovery_stats["errors"].append(error_msg)
            
            # Additional recovery steps
            await self._recover_recent_orders_from_alpaca(recovery_stats)
            
            logger.info(f"Database recovery completed: {recovery_stats['recovered_positions']} positions recovered, "
                       f"{recovery_stats['skipped_positions']} skipped, {len(recovery_stats['errors'])} errors")
            
            return recovery_stats
            
        except Exception as e:
            error_msg = f"Database recovery failed: {str(e)}"
            logger.error(error_msg)
            recovery_stats["errors"].append(error_msg)
            raise

    async def _clear_all_positions(self) -> None:
        """Clear all positions from local database (used in force recovery)."""
        try:
            session = self._database._session_factory()
            try:
                # Import the PositionRecord class from database module
                from ..database.database_manager import PositionRecord
                deleted_count = session.query(PositionRecord).delete()
                session.commit()
                logger.info(f"Cleared {deleted_count} positions from local database")
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Error clearing positions: {str(e)}")
            raise

    async def _recover_recent_orders_from_alpaca(self, recovery_stats: Dict[str, Any]) -> None:
        """
        Attempt to recover recent order history from Alpaca.
        Note: Alpaca has limited order history compared to your local tracking.
        """
        try:
            logger.info("Attempting to recover recent order history...")
            
            # Get recent orders from Alpaca (last 30 days)
            import asyncio
            loop = asyncio.get_event_loop()
            
            # Alpaca's get_orders method with date filtering
            from datetime import datetime, timedelta
            recent_date = datetime.now() - timedelta(days=30)
            
            # Note: This is a simplified example - actual Alpaca API calls may vary
            # You may need to adjust based on your specific Alpaca client implementation
            orders = await loop.run_in_executor(
                None, 
                lambda: self._trading_client.get_orders(
                    status='all',
                    after=recent_date.isoformat()
                )
            )
            
            recovered_orders = 0
            for alpaca_order in orders:
                try:
                    # Convert Alpaca order to your Order format
                    order = Order(
                        order_id=alpaca_order.id,
                        symbol=alpaca_order.symbol,
                        quantity=float(alpaca_order.qty),
                        order_type=OrderType.MARKET if alpaca_order.order_type == 'market' else OrderType.LIMIT,
                        side=alpaca_order.side,
                        price=float(alpaca_order.limit_price) if alpaca_order.limit_price else None,
                        status=OrderStatus.FILLED if alpaca_order.status == 'filled' else OrderStatus.CANCELED,
                        created_at=alpaca_order.created_at,
                        filled_at=alpaca_order.filled_at,
                        filled_price=float(alpaca_order.filled_avg_price) if alpaca_order.filled_avg_price else None,
                        filled_quantity=float(alpaca_order.filled_qty) if alpaca_order.filled_qty else None
                    )
                    
                    await self._database.save_order(order)
                    recovered_orders += 1
                    
                except Exception as e:
                    logger.warning(f"Failed to recover order {alpaca_order.id}: {str(e)}")
            
            recovery_stats["recovered_orders"] = recovered_orders
            logger.info(f"Recovered {recovered_orders} recent orders from Alpaca")
            
        except Exception as e:
            logger.warning(f"Could not recover order history: {str(e)}")
            recovery_stats["order_recovery_error"] = str(e)
