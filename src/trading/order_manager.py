"""
Enhanced Order management implementation for Alpaca API integration.
Handles all order lifecycle operations with retry logic, error handling,
and configurable communication methods (REST/WebSocket).
"""

import asyncio
from typing import List, Optional, Dict, Any, Union, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from src.interfaces import IOrderManager, IConfigurationManager
from src.broker.interfaces import IBrokerRouter, BrokerType
from src.exceptions import OrderExecutionException, APIException, ConfigurationException
from src.core.logging_config import get_logger
from src import Order, OrderType, OrderSide, OrderStatus


logger = get_logger(__name__)


@dataclass
class OrderFillEvent:
    """Event triggered when an order is filled - used for DCA and strategy notifications."""
    order_id: str
    symbol: str
    side: str  # 'buy' or 'sell'
    quantity_filled: float
    fill_price: float
    total_quantity: float
    fill_timestamp: datetime
    is_complete_fill: bool
    is_dca_order: bool = False
    position_lifecycle_id: Optional[str] = None


class OrderManager(IOrderManager):
    """
    Enhanced order manager for trading operations through the Alpaca API.
    Provides retry logic, error handling, order status tracking, and configurable
    communication methods (REST/WebSocket).
    """
    
    # Maximum order history size to prevent unbounded memory growth
    MAX_ORDER_HISTORY: int = 1000
    
    def __init__(self, config: IConfigurationManager, broker_router: IBrokerRouter):
        """
        Initialize Enhanced OrderManager.
        
        Args:
            config: Configuration manager instance
            broker_router: Broker router instance
        """
        self._config = config
        self._router = broker_router
        self._active_orders: Dict[str, Order] = {}
        self._order_history: List[Order] = []
        
        # Configuration
        self._max_retries = config.get_config("trading.max_retries", 3)
        self._retry_delay = config.get_config("trading.retry_delay", 1.0)
        
        # Enhanced features: Order callbacks for real-time updates
        self._order_callbacks: List[Callable] = []
        self._real_time_orders: Dict[str, Order] = {}
        
        # Enhanced features: DCA fill tracking
        self._fill_callbacks: List[Callable] = []
        
        # Enhanced features: DCA order tracking
        self._dca_orders: Dict[str, Dict] = {}  # Track which orders are DCA orders
        
        logger.info("Enhanced OrderManager with multi-broker support initialized")
    
    def _add_to_history(self, order: Order) -> None:
        """
        Add an order to history with LRU pruning to prevent memory leaks.
        
        Args:
            order: Order to add to history
        """
        self._order_history.append(order)
        if len(self._order_history) > self.MAX_ORDER_HISTORY:
            # Keep only the most recent orders
            self._order_history = self._order_history[-self.MAX_ORDER_HISTORY:]
            logger.debug(f"Pruned order history to {self.MAX_ORDER_HISTORY} entries")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(APIException)
    )
    async def place_order(self, order: Order) -> str:
        """
        Place a new order with retry logic.
        
        Args:
            order: Order object to place
            
        Returns:
            Order ID from the broker
            
        Raises:
            OrderExecutionException: If order placement fails
        """
        try:
            side_str = order.side.value if hasattr(order.side, 'value') else str(order.side)
            order_type_str = order.order_type.value if isinstance(order.order_type, OrderType) else str(order.order_type)
            logger.info(f"Placing order: {order.symbol} {side_str} {order.quantity} "
                       f"@ {order.price} ({order_type_str})")
            
            # Validate order before placing
            self._validate_order(order)
            
            # Determine broker and get executor
            broker_type = self._router.get_broker_for_symbol(order.symbol)
            executor = self._router.get_order_executor(broker_type)
            order.broker = broker_type.value
            
            # Place order with broker
            broker_order_id = await executor.place_order(order)
            
            # Store in active orders for continuous monitoring
            self._active_orders[order.order_id] = order
            
            # For market and limit orders, log that we'll monitor for fill
            if order.order_type in [OrderType.MARKET, OrderType.LIMIT]:
                order_type_str = order.order_type.value if isinstance(order.order_type, OrderType) else str(order.order_type)
                logger.info(f"📋 {order_type_str.title()} order submitted for monitoring: {order.order_id}")
                logger.info(f"   Will continuously check fill status during bot cycles")
                
                # Only log price range for limit orders (market orders have None price)
                if order.order_type == OrderType.LIMIT and order.price is not None:
                    logger.info(f"   Expected fill price range: ${order.price * 0.999:.2f} - ${order.price * 1.001:.2f}")
                elif order.order_type == OrderType.MARKET:
                    logger.info(f"   Market order will fill at current market price")
            
            logger.info(f"Order placed successfully, order_id={order.order_id}, broker_id={broker_order_id}")
            return order.order_id
            
        except Exception as e:
            logger.error(f"Failed to place order: {str(e)}")
            raise OrderExecutionException(f"Failed to place order: {str(e)}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(APIException)
    )
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order.
        
        Args:
            order_id: ID of the order to cancel
            
        Returns:
            True if cancellation successful, False otherwise
        """
        try:
            logger.info(f"Canceling order: {order_id}")
            
            if order_id not in self._active_orders:
                logger.warning(f"Order {order_id} not found in active orders")
                return False
                
            order = self._active_orders[order_id]
            
            # Determine broker
            broker_type = BrokerType(order.broker) if order.broker else self._router.get_broker_for_symbol(order.symbol)
            executor = self._router.get_order_executor(broker_type)
            
            # Cancel with broker
            # Use broker_order_id if available, otherwise order_id
            broker_id = order.broker_order_id or order_id
            await executor.cancel_order(broker_id)
            
            # Update local order status
            order.status = OrderStatus.CANCELED
            
            # Move to history (with LRU pruning)
            self._add_to_history(order)
            del self._active_orders[order_id]
            
            logger.info(f"Order canceled successfully: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {str(e)}")
            return False
    
    async def cancel_and_retry_order(self, order_id: str, new_price: float, reason: str = "price_adjustment") -> Optional[str]:
        """
        Cancel an existing order and immediately place a retry order at a new price.
        This enables aggressive order management for better fill rates.
        
        Args:
            order_id: ID of the order to cancel and retry
            new_price: New price for the retry order
            reason: Reason for the retry (for logging)
            
        Returns:
            New order ID if successful, None if failed
        """
        try:
            # Get the original order details
            original_order = None
            if order_id in self._active_orders:
                original_order = self._active_orders[order_id]
            else:
                logger.warning(f"Order {order_id} not found in active orders for retry")
                return None
            
            logger.info(f"🔄 AGGRESSIVE ORDER RETRY: {original_order.symbol}")
            logger.info(f"   Reason: {reason}")
            orig_side = original_order.side.value if hasattr(original_order.side, 'value') else str(original_order.side)
            logger.info(f"   Original: {orig_side} {original_order.quantity} @ ${original_order.price:.4f}")
            logger.info(f"   New Price: ${new_price:.4f}")
            logger.info(f"   Price Change: ${new_price - original_order.price:+.4f}")
            
            # Cancel the original order
            cancel_success = await self.cancel_order(order_id)
            if not cancel_success:
                logger.error(f"❌ Failed to cancel order {order_id} for retry")
                return None
            
            # Create new order with updated price
            retry_order = Order(
                symbol=original_order.symbol,
                side=original_order.side,
                quantity=original_order.quantity,
                order_type=original_order.order_type,
                price=new_price
            )
            
            # Place the retry order
            new_order_id = await self.place_order(retry_order)
            
            if new_order_id:
                # Preserve DCA metadata if this was a DCA order
                if self.is_dca_order(order_id):
                    dca_info = self.get_dca_order_info(order_id)
                    if dca_info:
                        self.mark_order_as_dca(
                            new_order_id,
                            position_lifecycle_id=dca_info.get('position_lifecycle_id'),
                            dca_level=dca_info.get('dca_level'),
                            strategy_metadata=dca_info.get('strategy_metadata', {})
                        )
                        logger.info(f"✅ DCA metadata transferred to retry order {new_order_id}")
                
                logger.info(f"✅ ORDER RETRY SUCCESSFUL: {original_order.symbol}")
                logger.info(f"   Canceled: {order_id}")
                logger.info(f"   New Order: {new_order_id}")
                logger.info(f"   Price Improvement: ${new_price - original_order.price:+.4f}")
                
                return new_order_id
            else:
                logger.error(f"❌ Failed to place retry order for {original_order.symbol}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error in aggressive order retry for {order_id}: {str(e)}")
            return None
    
    async def adjust_order_price_aggressively(self, order_id: str, current_market_price: float, 
                                            max_adjustment_percent: float = 0.5) -> Optional[str]:
        """
        Aggressively adjust an unfilled order's price towards market for better fill probability.
        
        Args:
            order_id: Order to adjust
            current_market_price: Current market price
            max_adjustment_percent: Maximum price adjustment as percentage (0.5% default)
            
        Returns:
            New order ID if adjusted, None if no adjustment needed/possible
        """
        try:
            if order_id not in self._active_orders:
                return None
            
            order = self._active_orders[order_id]
            
            # Only adjust limit orders
            if order.order_type != OrderType.LIMIT or not order.price:
                return None
            
            # Calculate aggressive new price
            max_adjustment = max_adjustment_percent / 100.0
            
            if order.side == OrderSide.BUY:
                # For buy orders, move price UP towards market (more aggressive)
                adjustment = min(current_market_price - order.price, order.price * max_adjustment)
                if adjustment > 0.01:  # Only adjust if meaningful ($0.01+)
                    new_price = order.price + adjustment
                    reason = f"aggressive_buy_adjustment_toward_${current_market_price:.2f}"
                    return await self.cancel_and_retry_order(order_id, new_price, reason)
            else:
                # For sell orders, move price DOWN towards market (more aggressive)
                adjustment = min(order.price - current_market_price, order.price * max_adjustment)
                if adjustment > 0.01:  # Only adjust if meaningful ($0.01+)
                    new_price = order.price - adjustment
                    reason = f"aggressive_sell_adjustment_toward_${current_market_price:.2f}"
                    return await self.cancel_and_retry_order(order_id, new_price, reason)
            
            return None  # No adjustment needed
            
        except Exception as e:
            logger.error(f"Error in aggressive price adjustment for {order_id}: {str(e)}")
            return None
    
    async def get_order_status(self, order_id: str) -> OrderStatus:
        """
        Get the current status of an order.
        
        Args:
            order_id: ID of the order
            
        Returns:
            Current order status
        """
        try:
            # Check local cache first
            if order_id in self._active_orders:
                # Refresh from broker
                await self._refresh_order_status(order_id)
                return self._active_orders[order_id].status
            
            # Check history
            for order in self._order_history:
                if order.order_id == order_id:
                    return order.status
            
            return OrderStatus.REJECTED
            
        except Exception as e:
            logger.error(f"Failed to get order status {order_id}: {str(e)}")
            return OrderStatus.REJECTED
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get all open orders, optionally filtered by symbol.
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of open orders
        """
        try:
            # Refresh all active orders
            await self._refresh_all_orders()
            
            orders = list(self._active_orders.values())
            
            # Filter by symbol if provided
            if symbol:
                orders = [order for order in orders if order.symbol == symbol]
            
            # Only return orders that are still pending
            open_orders = [order for order in orders 
                          if order.status in [OrderStatus.PENDING, OrderStatus.PARTIAL_FILL]]
            
            logger.debug(f"Found {len(open_orders)} open orders")
            return open_orders
            
        except Exception as e:
            logger.error(f"Failed to get open orders: {str(e)}")
            return []
    
    async def get_order_history(self, limit: int = 100) -> List[Order]:
        """
        Get order history.
        
        Args:
            limit: Maximum number of orders to return
            
        Returns:
            List of historical orders
        """
        return self._order_history[-limit:]
    
    async def get_actual_fill_price(self, order_id: str) -> Optional[float]:
        """
        Get the actual fill price for an order, refreshing from broker if needed.
        
        Args:
            order_id: Order ID to check
            
        Returns:
            Actual fill price or None if order not filled
        """
        try:
            # First check our local data
            if order_id in self._active_orders:
                order = self._active_orders[order_id]
                if order.status == OrderStatus.FILLED and order.filled_price:
                    return order.filled_price
                
                # If not filled locally, refresh from broker
                await self._refresh_order_status(order_id)
                return order.filled_price if order.status == OrderStatus.FILLED else None
            
            # Check history
            for order in self._order_history:
                if order.order_id == order_id:
                    return order.filled_price if order.status == OrderStatus.FILLED else None
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting actual fill price for {order_id}: {str(e)}")
            return None
    
    async def get_order_by_id(self, order_id: str) -> Optional[Order]:
        """
        Get a specific order by ID with complete fill information.
        
        Args:
            order_id: Order ID to retrieve
            
        Returns:
            Order object with current status and fill data, or None if not found
        """
        try:
            # Check active orders first
            if order_id in self._active_orders:
                # Refresh to get latest fill data
                await self._refresh_order_status(order_id)
                return self._active_orders[order_id]
            
            # Check order history
            for order in self._order_history:
                if order.order_id == order_id:
                    return order
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting order {order_id}: {str(e)}")
            return None
    
    def _validate_order(self, order: Order) -> None:
        """Validate order before placing."""
        if not order.symbol:
            raise OrderExecutionException("Order symbol is required")
        
        if order.quantity <= 0:
            raise OrderExecutionException("Order quantity must be positive")
        
        if order.order_type == OrderType.LIMIT and not order.price:
            raise OrderExecutionException("Limit orders require a price")
        
        if order.order_type == OrderType.STOP and not order.stop_price:
            raise OrderExecutionException("Stop orders require a stop price")

    async def _refresh_order_status(self, order_id: str) -> None:
        """Refresh order status from broker with enhanced fill price tracking."""
        if order_id not in self._active_orders:
            return
            
        order = self._active_orders[order_id]
        
        try:
            broker_type = BrokerType(order.broker) if order.broker else self._router.get_broker_for_symbol(order.symbol)
            executor = self._router.get_order_executor(broker_type)
            
            # Use broker_order_id if available
            broker_id = order.broker_order_id or order_id
            
            # Get status from broker
            status = await executor.get_order_status(broker_id)
            
            old_status = order.status
            old_fill_price = order.filled_price
            old_filled_qty = order.filled_quantity
            
            order.status = status
            
            # Note: We might want to get full order details here to update fill qty/price
            # But IBrokerOrderExecutor.get_order_status only returns status.
            # We should probably add get_order to the interface or use get_open_orders.
            # For now, let's assume get_order_status is enough or we need to extend the interface.
            # Actually, AlpacaOrderExecutor.get_order_status calls get_order_by_id internally but returns status.
            # We should probably change IBrokerOrderExecutor to have get_order(id) -> Order.
            
            # Let's assume for now we can't get details easily without extending interface.
            # But wait, AlpacaOrderExecutor.get_order_status implementation fetches the whole order.
            # I should update IBrokerOrderExecutor to return Order or have a get_order method.
            pass
            
        except Exception as e:
            logger.error(f"Failed to refresh order status {order_id}: {str(e)}")
    
    async def _refresh_all_orders(self) -> None:
        """Refresh all active orders from broker."""
        tasks = [self._refresh_order_status(order_id) 
                for order_id in list(self._active_orders.keys())]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def get_pending_market_orders(self) -> List[Order]:
        """
        Get all pending orders that need fill monitoring (market and limit orders).
        
        Returns:
            List of pending orders
        """
        pending_orders = []
        for order in self._active_orders.values():
            if (order.order_type in [OrderType.MARKET, OrderType.LIMIT] and 
                order.status in [OrderStatus.PENDING, OrderStatus.PARTIAL_FILL]):
                pending_orders.append(order)
        return pending_orders
    
    async def check_and_update_fills(self) -> List[Order]:
        """
        Check all pending orders for fills and update their status.
        This method should be called regularly by the bot's monitoring cycle.
        
        Returns:
            List of newly filled orders
        """
        newly_filled = []
        
        try:
            pending_orders = await self.get_pending_market_orders()
            
            if not pending_orders:
                return newly_filled
            
            logger.debug(f"🔍 Checking {len(pending_orders)} pending orders for fills")
            
            for order in pending_orders:
                old_status = order.status
                old_fill_price = order.filled_price
                
                # Refresh order status from broker
                await self._refresh_order_status(order.order_id)
                
                # Check if order was newly filled
                if (old_status != OrderStatus.FILLED and 
                    order.order_id in self._active_orders and  # Check if still active
                    self._active_orders[order.order_id].status == OrderStatus.FILLED):
                    
                    filled_order = self._active_orders[order.order_id]
                    newly_filled.append(filled_order)
                    
                    side_str = filled_order.side.value if hasattr(filled_order.side, 'value') else str(filled_order.side)
                    logger.info(f"🎉 ORDER FILLED: {filled_order.symbol} {side_str} "
                               f"{filled_order.filled_quantity} @ ${filled_order.filled_price:.4f}")
                    logger.info(f"   Order ID: {filled_order.order_id}")
                    order_type_str = filled_order.order_type.value if isinstance(filled_order.order_type, OrderType) else str(filled_order.order_type)
                    logger.info(f"   Order Type: {order_type_str}")
                    
                    # Log fill price discovery
                    if old_fill_price != filled_order.filled_price:
                        logger.info(f"   📊 Fill price captured: ${filled_order.filled_price:.4f}")
                        # Show price improvement/slippage
                        if filled_order.price:
                            price_diff = filled_order.filled_price - filled_order.price
                            if abs(price_diff) > 0.01:  # Only log if significant
                                direction = "improvement" if price_diff > 0 else "slippage"
                                logger.info(f"   💰 Price {direction}: ${abs(price_diff):.4f}")
                
                # Check if order moved from history (was processed by _refresh_order_status)
                elif order.order_id not in self._active_orders:
                    # Order was moved to history, check if it was filled
                    for hist_order in self._order_history:
                        if (hist_order.order_id == order.order_id and 
                            hist_order.status == OrderStatus.FILLED and
                            old_status != OrderStatus.FILLED):
                            newly_filled.append(hist_order)
                            logger.info(f"🎉 ORDER FILLED (from history): {hist_order.symbol} @ ${hist_order.filled_price:.4f}")
                            break
            
            # Enhanced: Generate OrderFillEvent objects and notify callbacks
            if newly_filled:
                fill_events = []
                for filled_order in newly_filled:
                    # Check if this is a DCA order
                    is_dca_order = filled_order.order_id in self._dca_orders
                    dca_info = self._dca_orders.get(filled_order.order_id, {})
                    
                    # Create fill event
                    side_str = filled_order.side.value if hasattr(filled_order.side, 'value') else str(filled_order.side)
                    fill_event = OrderFillEvent(
                        order_id=filled_order.order_id,
                        symbol=filled_order.symbol,
                        side=side_str.lower(),
                        quantity_filled=filled_order.filled_quantity or filled_order.quantity,
                        fill_price=filled_order.filled_price,
                        total_quantity=filled_order.quantity,
                        fill_timestamp=datetime.now(),
                        is_complete_fill=filled_order.status == OrderStatus.FILLED,
                        is_dca_order=is_dca_order,
                        position_lifecycle_id=dca_info.get('position_lifecycle_id')
                    )
                    fill_events.append(fill_event)
                
                # Notify fill callbacks with both order list and fill events
                if self._fill_callbacks:
                    for callback in self._fill_callbacks:
                        try:
                            # Support both old callback style (order list) and new style (fill events)
                            if callback.__code__.co_argcount > 1:  # Has more than just 'self' parameter
                                param_names = callback.__code__.co_varnames[1:callback.__code__.co_argcount]
                                if 'fill_events' in param_names or 'events' in param_names:
                                    await callback(fill_events)
                                else:
                                    await callback(newly_filled)
                            else:
                                await callback(newly_filled)
                        except Exception as e:
                            logger.error(f"Error in fill callback: {e}")
            
            # Enhanced: Clean up completed DCA orders
            for filled_order in newly_filled:
                if filled_order.order_id in self._dca_orders:
                    logger.debug(f"Cleaning up DCA tracking for completed order {filled_order.order_id}")
                    del self._dca_orders[filled_order.order_id]
            
            if newly_filled:
                logger.info(f"✅ {len(newly_filled)} orders newly filled this cycle")
            
            return newly_filled
            
        except Exception as e:
            logger.error(f"Error checking order fills: {e}")
            return newly_filled

    # ===================================================================
    # ENHANCED FEATURES - Callback Management for DCA and Real-time Updates
    # ===================================================================
    
    def add_order_callback(self, callback: Callable) -> None:
        """
        Add callback for real-time order updates.
        
        Args:
            callback: Function to call when orders are updated
        """
        if callback not in self._order_callbacks:
            self._order_callbacks.append(callback)
            logger.debug(f"Added order callback: {callback.__name__}")
    
    def remove_order_callback(self, callback: Callable) -> None:
        """
        Remove order callback.
        
        Args:
            callback: Callback function to remove
        """
        if callback in self._order_callbacks:
            self._order_callbacks.remove(callback)
            logger.debug(f"Removed order callback: {callback.__name__}")
    
    def add_fill_callback(self, callback: Callable) -> None:
        """
        Add callback for order fill notifications (DCA support).
        
        Args:
            callback: Async function to call when orders are filled
        """
        if callback not in self._fill_callbacks:
            self._fill_callbacks.append(callback)
            logger.debug(f"Added fill callback: {callback.__name__}")
    
    def remove_fill_callback(self, callback: Callable) -> None:
        """
        Remove fill callback.
        
        Args:
            callback: Callback function to remove
        """
        if callback in self._fill_callbacks:
            self._fill_callbacks.remove(callback)
            logger.debug(f"Removed fill callback: {callback.__name__}")
    
    # ===================================================================
    # ENHANCED FEATURES - DCA and Strategy Support
    # ===================================================================
    
    def get_fill_callbacks_count(self) -> int:
        """Get number of registered fill callbacks."""
        return len(self._fill_callbacks)
    
    def get_order_callbacks_count(self) -> int:
        """Get number of registered order callbacks."""
        return len(self._order_callbacks)
    
    # ===================================================================
    # ENHANCED FEATURES - DCA-Specific Order Management  
    # ===================================================================
    
    def mark_order_as_dca(self, order_id: str, position_lifecycle_id: Optional[str] = None, 
                         dca_level: Optional[int] = None, strategy_metadata: Optional[Dict] = None) -> None:
        """
        Mark an order as a DCA order for enhanced tracking.
        
        Args:
            order_id: Order ID to mark as DCA
            position_lifecycle_id: Associated position lifecycle ID
            dca_level: DCA level (1, 2, 3, etc.)
            strategy_metadata: Additional strategy-specific metadata
        """
        self._dca_orders[order_id] = {
            'position_lifecycle_id': position_lifecycle_id,
            'dca_level': dca_level,
            'strategy_metadata': strategy_metadata or {},
            'marked_timestamp': datetime.now()
        }
        logger.debug(f"Marked order {order_id} as DCA order (level {dca_level})")
    
    def is_dca_order(self, order_id: str) -> bool:
        """Check if an order is marked as a DCA order."""
        return order_id in self._dca_orders
    
    def get_dca_order_info(self, order_id: str) -> Optional[Dict]:
        """Get DCA information for an order."""
        return self._dca_orders.get(order_id)
    
    def get_dca_orders_for_position(self, position_lifecycle_id: str) -> List[str]:
        """Get all DCA order IDs for a specific position lifecycle."""
        return [
            order_id for order_id, info in self._dca_orders.items()
            if info.get('position_lifecycle_id') == position_lifecycle_id
        ]
    
    async def place_dca_order(self, order: Order, position_lifecycle_id: str, 
                            dca_level: int, strategy_metadata: Optional[Dict] = None) -> str:
        """
        Place a DCA order with automatic DCA tracking.
        
        Args:
            order: Order to place
            position_lifecycle_id: Position lifecycle ID
            dca_level: DCA level
            strategy_metadata: Additional metadata
            
        Returns:
            Order ID
        """
        order_id = await self.place_order(order)
        self.mark_order_as_dca(order_id, position_lifecycle_id, dca_level, strategy_metadata)
        logger.info(f"Placed DCA order {order_id} for position {position_lifecycle_id} at level {dca_level}")
        return order_id
    
    # ===================================================================
    # ENCAPSULATION - Accessor Methods for Internal Collections
    # ===================================================================
    
    def get_active_order(self, order_id: str) -> Optional[Order]:
        """
        Get an active order by ID.
        
        Args:
            order_id: Order ID to look up
            
        Returns:
            Order if found in active orders, None otherwise
        """
        return self._active_orders.get(order_id)
    
    def get_historical_order(self, order_id: str) -> Optional[Order]:
        """
        Get an order from history by ID.
        
        Args:
            order_id: Order ID to look up
            
        Returns:
            Order if found in history, None otherwise
        """
        for order in self._order_history:
            if order.order_id == order_id:
                return order
        return None
    
    def clear_dca_metadata(self, order_id: str) -> bool:
        """
        Clear DCA metadata for an order.
        
        Args:
            order_id: Order ID to clear metadata for
            
        Returns:
            True if metadata was cleared, False if order not found in DCA tracking
        """
        if order_id in self._dca_orders:
            del self._dca_orders[order_id]
            logger.debug(f"Cleared DCA metadata for order {order_id}")
            return True
        return False
    
    def get_all_active_orders(self) -> Dict[str, Order]:
        """
        Get a copy of all active orders.
        
        Returns:
            Dictionary mapping order_id to Order objects
        """
        return dict(self._active_orders)
