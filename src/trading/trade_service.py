"""
Trade Service - Manages trade lifecycle and completion logic.

This service encapsulates all trade-related database operations,
following Single Responsibility Principle by separating trade
management from the main orchestrator.

SOLID Compliance:
- SRP: Single responsibility for trade lifecycle management
- OCP: Extensible for new trade completion strategies
- LSP: N/A (no inheritance hierarchy)
- ISP: Focused interface for trade operations only
- DIP: Depends on IOrderManager abstraction

Thread Safety: Async-safe (uses async database operations)

Author: Trading Bot Team
Date: 2025
"""

import logging
from typing import Optional, Dict, List, Any
from datetime import datetime

from src import Order, OrderStatus, OrderSide
from src.database.cosmos_manager import CosmosDBManager
from src.database.pagination import extract_items
from src.interfaces import IOrderManager

logger = logging.getLogger(__name__)


class TradeService:
    """
    Service for managing trade lifecycle and completion.
    
    This service handles:
    - Finding matching trades for exit orders
    - Completing trades with proper audit trails
    - Querying open trades
    - Reconciling externally closed positions
    
    Responsibilities:
    - Trade database operations (CRUD)
    - Trade-to-order matching logic
    - Trade completion audit logging
    
    NOT responsible for:
    - Position management (that's PositionManager)
    - Order placement (that's OrderManager)
    - Strategy decisions (that's TradingStrategy)
    
    Example Usage:
        ```python
        trade_service = TradeService(database, order_manager)
        
        # Find and complete trade for externally closed position
        trade = await trade_service.find_matching_trade(symbol)
        if trade:
            exit_order = await trade_service.find_exit_order_for_position(
                symbol, position_quantity
            )
            if exit_order:
                await trade_service.complete_trade(
                    trade['trade_id'],
                    exit_order,
                    reason="external_close"
                )
        ```
    """
    
    def __init__(
        self,
        database: CosmosDBManager,
        order_manager: IOrderManager
    ):
        """
        Initialize TradeService.
        
        Args:
            database: Database manager for trade persistence
            order_manager: Order manager for querying order history
        """
        self.database = database
        self.order_manager = order_manager
        logger.debug("TradeService initialized")
    
    async def find_matching_trade(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Find an open trade matching the given symbol.
        
        Args:
            symbol: Symbol to search for
            
        Returns:
            Trade dict if found, None otherwise
            
        Example:
            ```python
            trade = await service.find_matching_trade("AAPL")
            if trade:
                print(f"Found trade: {trade['trade_id']}")
            ```
        """
        try:
            open_trades_result = await self.database.get_open_trades()
            open_trades = extract_items(open_trades_result)
            for trade in open_trades:
                if trade['symbol'] == symbol:
                    logger.debug(f"Found matching trade for {symbol}: {trade['trade_id']}")
                    return trade
            
            logger.debug(f"No matching open trade found for {symbol}")
            return None
            
        except Exception as e:
            logger.error(f"Error finding matching trade for {symbol}: {e}")
            return None
    
    async def find_exit_order_for_position(
        self,
        symbol: str,
        position_quantity: float,
        limit: int = 50
    ) -> Optional[Order]:
        """
        Find the exit order that closed a position from order history.
        
        This searches order history for a filled order that would have
        closed the given position (SELL for long positions, BUY for short).
        
        Args:
            symbol: Position symbol
            position_quantity: Position quantity (positive for long, negative for short)
            limit: Maximum number of historical orders to search
            
        Returns:
            Filled exit order if found, None otherwise
            
        Example:
            ```python
            # For a long position that was closed externally
            exit_order = await service.find_exit_order_for_position("AAPL", 100.0)
            if exit_order:
                print(f"Found exit at ${exit_order.filled_price:.2f}")
            ```
        """
        try:
            order_history = await self.order_manager.get_order_history(limit=limit)
            
            for order in order_history:
                if order.symbol != symbol:
                    continue
                    
                if order.status != OrderStatus.FILLED:
                    continue
                
                # Check if order direction matches position close
                # Long position -> SELL order closes it
                # Short position -> BUY order closes it
                is_long_exit = position_quantity > 0 and order.side == OrderSide.SELL
                is_short_exit = position_quantity < 0 and order.side == OrderSide.BUY
                
                if is_long_exit or is_short_exit:
                    logger.debug(
                        f"Found exit order for {symbol}: {order.order_id} @ "
                        f"${order.filled_price:.4f}"
                    )
                    return order
            
            logger.debug(f"No exit order found for {symbol} in last {limit} orders")
            return None
            
        except Exception as e:
            logger.error(f"Error finding exit order for {symbol}: {e}")
            return None
    
    async def complete_trade(
        self,
        trade_id: str,
        exit_order: Order,
        reason: str = "normal_close"
    ) -> bool:
        """
        Complete a trade with the given exit order.
        
        Args:
            trade_id: ID of the trade to complete
            exit_order: Exit order that closed the position
            reason: Completion reason (e.g., "external_close", "profit_target", "signal_close")
            
        Returns:
            True if successful, False otherwise
            
        Example:
            ```python
            success = await service.complete_trade(
                trade_id="TRADE_123",
                exit_order=exit_order,
                reason="external_close"
            )
            ```
        """
        try:
            logger.info(f"💰 COMPLETING TRADE: {trade_id}")
            logger.debug(f"   Exit order: {exit_order.order_id} @ ${exit_order.filled_price:.4f}")
            logger.debug(f"   Reason: {reason}")
            
            await self.database.complete_trade(
                trade_id,
                exit_order,
                reason
            )
            
            logger.info(f"✅ TRADE COMPLETED: {trade_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error completing trade {trade_id}: {e}")
            return False
    
    async def get_open_trades(self) -> List[Dict[str, Any]]:
        """
        Get all currently open trades.
        
        Returns:
            List of open trade dictionaries
            
        Example:
            ```python
            open_trades = await service.get_open_trades()
            for trade in open_trades:
                print(f"{trade['symbol']}: {trade['entry_price']}")
            ```
        """
        try:
            result = await self.database.get_open_trades()
            return extract_items(result)
        except Exception as e:
            logger.error(f"Error getting open trades: {e}")
            return []
    
    async def handle_externally_closed_position(
        self,
        symbol: str,
        position_quantity: float
    ) -> bool:
        """
        Handle a position that was closed externally (outside the bot).
        
        This method uses DETERMINISTIC database lookup instead of heuristics:
        1. Finds the exit order from order history
        2. Queries the database for a trade with matching exit_order_id
        3. If found, marks trade as completed (already linked in DB)
        4. If not found, falls back to heuristic (finds open trade + links exit order)
        
        Why deterministic?
        - The trades table tracks exit_order_id as a foreign key
        - Direct DB query eliminates ambiguity with multiple positions
        - Works reliably even with concurrent positions in same symbol
        
        Args:
            symbol: Symbol of the closed position
            position_quantity: Original position quantity (for finding exit order)
            
        Returns:
            True if trade was completed successfully, False otherwise
            
        Example:
            ```python
            # Position was closed externally
            success = await service.handle_externally_closed_position(
                symbol="AAPL",
                position_quantity=100.0
            )
            ```
        """
        try:
            logger.info(f"🎯 COMPLETING TRADE AUDIT: {symbol}")
            
            # Step 1: Find the exit order from broker's order history
            exit_order = await self.find_exit_order_for_position(
                symbol,
                position_quantity
            )
            
            if not exit_order:
                logger.warning(f"⚠️ No exit order found for {symbol}")
                return False
            
            logger.info(f"📄 Found exit order: {exit_order.order_id} @ ${exit_order.filled_price:.4f}")
            
            # Step 2: DETERMINISTIC LOOKUP - Query trade by exit_order_id
            trade = await self.database.get_trade_by_exit_order_id(exit_order.order_id)
            
            if trade:
                # Trade already linked to this exit order (normal exit path)
                logger.info(f"✅ Trade already completed via normal flow: {trade['trade_id']}")
                return True
            
            # Step 3: FALLBACK - Find matching open trade (external close scenario)
            logger.debug("No trade found by exit_order_id, searching for open trade")
            trade = await self.find_matching_trade(symbol)
            
            if not trade:
                logger.warning(f"⚠️ No matching open trade found for {symbol}")
                return False
            
            # Step 4: Complete the trade (links exit_order_id in database)
            return await self.complete_trade(
                trade['trade_id'],
                exit_order,
                "external_close"
            )
            
        except Exception as e:
            logger.error(f"❌ Error handling externally closed position {symbol}: {e}")
            return False
