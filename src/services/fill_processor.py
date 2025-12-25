"""
Fill Processor Service
Handles order fill processing, position updates, and DCA tracking.

Extracted from TradingBotOrchestrator to follow Single Responsibility Principle.
This service focuses exclusively on processing order fills and updating related state.
"""

from datetime import datetime
from typing import Optional, Protocol, Dict, Any, Awaitable, Callable
from src.core.logging_config import get_logger
from src.interfaces import (
    IOrderManager, 
    IPositionManager,
    Order, 
    OrderSide, 
    OrderStatus
)
from src.database.database_interface import IDatabaseManager
from src.exceptions import OrderExecutionException

logger = get_logger(__name__)


class IStrategyPositionAccess(Protocol):
    """Protocol for accessing strategy position data."""
    
    @property
    def positions(self) -> Dict[str, Any]:
        """Get positions dictionary."""
        ...
    
    async def _save_position_dca_metadata(
        self,
        symbol: str,
        attempts: int,
        prices: list,
        last_price: float
    ) -> None:
        """Save DCA metadata to database."""
        ...


class FillProcessor:
    """
    Processes order fills and updates positions accordingly.
    
    Follows Single Responsibility Principle - only handles fill processing logic.
    Extracted from TradingBotOrchestrator to reduce class complexity.
    
    Responsibilities:
    - Capture and validate actual fill prices from broker
    - Update position manager with fill data
    - Update strategy positions and average prices
    - Track DCA fills with correct fill prices
    - Record trades for audit trail
    
    Example:
        fill_processor = FillProcessor(
            order_manager=order_manager,
            position_manager=position_manager,
            database=database
        )
        await fill_processor.process_fill(order)
    """
    
    def __init__(
        self,
        order_manager: IOrderManager,
        position_manager: IPositionManager,
        database: IDatabaseManager,
        strategy: Optional[IStrategyPositionAccess] = None
    ):
        """
        Initialize fill processor with required dependencies.
        
        Args:
            order_manager: Order management service
            position_manager: Position tracking service
            database: Database access for persistence
            strategy: Optional strategy for position updates
        """
        self._order_manager = order_manager
        self._position_manager = position_manager
        self._database = database
        self._strategy = strategy
        
    def set_strategy(self, strategy: IStrategyPositionAccess) -> None:
        """
        Set the strategy reference for position updates.
        
        Args:
            strategy: Strategy with positions dictionary
        """
        self._strategy = strategy
    
    async def process_fill(self, order: Order) -> None:
        """
        Process an order fill with enhanced fill price validation.
        
        Main entry point for fill processing. Orchestrates:
        1. Fill price capture from broker
        2. Position update with actual fill price
        3. Strategy position recalculation
        4. DCA tracking with correct prices
        5. Trade record creation
        
        Args:
            order: The filled order to process
            
        Raises:
            OrderExecutionException: If fill price cannot be determined
        """
        try:
            logger.info(f"🔄 Processing order fill: {order.order_id}")
            
            # Step 1: Capture actual fill price from broker
            fill_price = await self._capture_fill_price(order)
            
            # Step 2: Update position manager
            await self._update_position(order, fill_price)
            
            # Step 3: Update strategy position (if strategy is set)
            if self._strategy:
                await self._update_strategy_position(order, fill_price)
            
            # Step 4: Log and track
            logger.info(f"📊 Position updated: {order.symbol} "
                       f"{order.quantity if order.side == OrderSide.BUY else -order.quantity:+.2f} "
                       f"@ ${fill_price:.4f}")
            
            # Step 5: Record trade for audit
            await self._record_trade(order)
            
            # Step 6: Save order to database
            await self._database.save_order(order)
            
        except Exception as e:
            logger.error(f"Error handling order fill: {str(e)}")
            raise
    
    async def _capture_fill_price(self, order: Order) -> float:
        """
        Capture the actual fill price from broker.
        
        Uses multiple attempts to ensure we get the real fill price,
        including force refresh if initial capture fails.
        
        Args:
            order: The filled order
            
        Returns:
            The actual fill price from broker
            
        Raises:
            OrderExecutionException: If fill price cannot be determined
        """
        # CRITICAL: Always get the actual fill price from broker
        actual_fill_price = await self._order_manager.get_actual_fill_price(order.order_id)
        
        if actual_fill_price is not None:
            # Update order with actual fill price
            original_price = order.price
            order.filled_price = actual_fill_price
            order.filled_at = datetime.utcnow()
            
            logger.info(f"✅ ACTUAL FILL PRICE CAPTURED: {order.symbol} {order.side.value} "
                       f"@ ${actual_fill_price:.4f}")
            
            if original_price and abs(actual_fill_price - original_price) > 0.01:
                price_diff = actual_fill_price - original_price
                logger.info(f"📊 PRICE SLIPPAGE: Order: ${original_price:.4f}, "
                           f"Fill: ${actual_fill_price:.4f}, "
                           f"Difference: ${price_diff:+.4f}")
            
            return actual_fill_price
        
        # Force refresh and retry
        logger.warning(f"⚠️ Initial fill price capture failed for {order.order_id}")
        logger.info("🔄 Forcing order refresh to capture fill price...")
        
        await self._order_manager._refresh_order_status(order.order_id)
        
        # Try to get the fill price again
        updated_order = await self._order_manager.get_order_by_id(order.order_id)
        if updated_order and updated_order.filled_price:
            order.filled_price = updated_order.filled_price
            order.filled_at = updated_order.filled_at
            logger.info(f"✅ Fill price recovered: ${order.filled_price:.4f}")
            return order.filled_price
        
        # Last resort: use order price with warning
        if order.price:
            logger.warning(f"⚠️ Using order price ${order.price:.4f} as fallback for fill price")
            order.filled_price = order.price
            order.filled_at = datetime.utcnow()
            return order.price
        
        raise OrderExecutionException(
            f"Cannot process fill without fill price for order {order.order_id}"
        )
    
    async def _update_position(self, order: Order, fill_price: float) -> None:
        """
        Update position manager with fill data.
        
        Args:
            order: The filled order
            fill_price: The actual fill price
        """
        quantity_change = order.quantity if order.side == OrderSide.BUY else -order.quantity
        await self._position_manager.update_position(
            order.symbol, 
            quantity_change, 
            fill_price  # Use actual fill price for position calculations
        )
        
        logger.info(f"📈 PROCESSING FILL: {order.symbol} {order.side.value} "
                   f"{order.quantity} @ ${fill_price:.4f}")
    
    async def _update_strategy_position(self, order: Order, fill_price: float) -> None:
        """
        Update strategy position with fill data and recalculate averages.
        
        Also handles DCA tracking with correct fill prices instead of order prices.
        
        Args:
            order: The filled order
            fill_price: The actual fill price
        """
        if order.symbol not in self._strategy.positions:
            return
        
        strategy_position = self._strategy.positions[order.symbol]
        quantity_change = order.quantity if order.side == OrderSide.BUY else -order.quantity
        
        # Check if this is a DCA order
        is_dca_order = self._order_manager.is_dca_order(order.order_id)
        
        # Recalculate average price with actual fill price
        if strategy_position.quantity != 0:
            old_total_cost = strategy_position.quantity * strategy_position.average_price
            old_avg_price = strategy_position.average_price
            
            # Add this order's contribution with actual fill price
            new_total_cost = old_total_cost + (quantity_change * fill_price)
            new_total_quantity = strategy_position.quantity + quantity_change
            
            if new_total_quantity != 0:
                strategy_position.average_price = abs(new_total_cost / new_total_quantity)
                strategy_position.quantity = new_total_quantity
                
                logger.info(f"🔄 STRATEGY POSITION UPDATED: {order.symbol}")
                logger.info(f"   Old avg: ${old_avg_price:.4f}, New avg: ${strategy_position.average_price:.4f}")
                logger.info(f"   Quantity: {strategy_position.quantity}")
        
        # Handle DCA tracking with actual fill price
        if is_dca_order:
            await self._update_dca_tracking(order, fill_price, strategy_position)
    
    async def _update_dca_tracking(
        self, 
        order: Order, 
        fill_price: float, 
        strategy_position: Any
    ) -> None:
        """
        Update DCA tracking with actual fill price.
        
        CRITICAL: Replaces order price with fill price for accurate DCA progression.
        
        Args:
            order: The filled DCA order
            fill_price: The actual fill price
            strategy_position: The strategy position state
        """
        # CRITICAL: Increment DCA attempt counter only on successful fill
        strategy_position.averaging_attempts += 1
        logger.info(f"🔢 DCA ATTEMPT COMPLETED: {order.symbol} "
                   f"attempt #{strategy_position.averaging_attempts}")
        
        # Get the original order price that was tracked
        original_order_price = order.price
        
        # Update DCA tracking to use FILL price instead of ORDER price
        if strategy_position.last_dca_price == original_order_price:
            logger.info(f"🔧 FIXING DCA PRICE TRACKING: {order.symbol}")
            logger.info(f"   Replacing ORDER price ${original_order_price:.4f} "
                       f"with FILL price ${fill_price:.4f}")
            
            # Update the last DCA price to the actual fill price
            strategy_position.last_dca_price = fill_price
            
            # Update the DCA price history as well
            if (strategy_position.dca_order_prices and 
                strategy_position.dca_order_prices[-1] == original_order_price):
                strategy_position.dca_order_prices[-1] = fill_price
                logger.info(f"   Updated DCA history: "
                           f"{[f'${p:.2f}' for p in strategy_position.dca_order_prices]}")
            
            # Save the corrected DCA metadata to database
            try:
                await self._strategy._save_position_dca_metadata(
                    symbol=order.symbol,
                    attempts=strategy_position.averaging_attempts,
                    prices=strategy_position.dca_order_prices,
                    last_price=strategy_position.last_dca_price
                )
                logger.info(f"✅ DCA metadata updated with actual fill price: ${fill_price:.4f}")
            except Exception as dca_save_error:
                logger.error(f"❌ Failed to save corrected DCA metadata: {dca_save_error}")
        
        logger.info(f"🎯 DCA ORDER FILL PROCESSED: {order.symbol}")
        logger.info(f"   Order Price: ${original_order_price:.4f}")
        logger.info(f"   Fill Price: ${fill_price:.4f}")
        logger.info(f"   Price Diff: ${fill_price - original_order_price:+.4f}")
        logger.info(f"   DCA Level: {strategy_position.averaging_attempts}")
        logger.info(f"   Next DCA will use: ${fill_price:.4f} as reference price")
    
    async def _record_trade(self, order: Order) -> None:
        """
        Record trade entry/exit for audit trail.
        
        Args:
            order: The filled order
        """
        try:
            # Convert OrderSide enum to string for comparison
            side_str = order.side.value if hasattr(order.side, 'value') else str(order.side)
            
            if side_str.lower() == "buy":
                # Entry order - create new trade record
                await self._database.create_trade_entry(
                    symbol=order.symbol,
                    entry_order=order,
                    strategy_used="signal_based"
                )
                logger.info(f"Trade entry recorded: {order.symbol} LONG "
                           f"{order.filled_quantity} @ ${order.filled_price:.4f}")
            else:
                # Exit order - complete existing trade
                await self._complete_trade(order)
                
        except Exception as e:
            logger.warning(f"Trade tracking failed (non-critical): {e}")
    
    async def _complete_trade(self, order: Order) -> None:
        """
        Complete an existing trade with exit order.
        
        Args:
            order: The exit order
        """
        open_trades = await self._database.get_open_trades(order.symbol)
        
        if open_trades:
            # Complete the most recent open trade
            latest_trade = open_trades[-1]
            trade_summary = await self._database.complete_trade(
                trade_id=latest_trade['trade_id'],
                exit_order=order,
                exit_reason="profit_taking"
            )
            
            logger.info(f"Trade completed: {order.symbol} - "
                       f"P&L: ${trade_summary['realized_pnl']:.2f} "
                       f"({trade_summary['profit_percentage']:.2f}%)")
        else:
            logger.warning(f"Exit order {order.order_id} filled but no open trade "
                          f"found for {order.symbol}")
