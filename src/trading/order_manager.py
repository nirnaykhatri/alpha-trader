"""
Enhanced Order management implementation for Alpaca API integration.
Handles all order lifecycle operations with retry logic, error handling,
and configurable communication methods (REST/WebSocket).
"""

import asyncio
from typing import List, Optional, Dict, Any, Union, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest,
    OrderSide as AlpacaOrderSide, TimeInForce
)
from alpaca.trading.models import Order as AlpacaOrder
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from ..interfaces import IOrderManager, IConfigurationManager
from ..exceptions import OrderExecutionException, APIException, ConfigurationException
from ..core.logging_config import get_logger
from .. import Order, OrderType, OrderSide, OrderStatus


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
    
    def __init__(self, config: IConfigurationManager, trading_client: TradingClient):
        """
        Initialize Enhanced OrderManager.
        
        Args:
            config: Configuration manager instance
            trading_client: Alpaca trading client instance
        """
        self._config = config
        self._client = trading_client
        self._active_orders: Dict[str, Order] = {}
        self._order_history: List[Order] = []
        
        # Configuration
        self._max_retries = config.get_config("api.alpaca.max_retries", 3)
        self._retry_delay = config.get_config("api.alpaca.retry_delay", 1.0)
        
        # Enhanced features: Communication method configuration
        self._communication_method = config.get_config("api.alpaca.communication_method", "rest").lower()
        self._websocket_enabled = config.get_config("api.alpaca.websocket.enabled", False)
        
        # Validate communication configuration
        if self._communication_method not in ["rest", "websocket"]:
            raise ConfigurationException(f"Invalid communication method: {self._communication_method}")
        
        if self._communication_method == "websocket" and not self._websocket_enabled:
            logger.warning("WebSocket communication requested but not enabled in config. Using REST.")
            self._communication_method = "rest"
        
        # Enhanced features: Order callbacks for real-time updates
        self._order_callbacks: List[Callable] = []
        self._real_time_orders: Dict[str, Order] = {}
        
        # Enhanced features: DCA fill tracking
        self._fill_callbacks: List[Callable] = []
        
        # Enhanced features: DCA order tracking
        self._dca_orders: Dict[str, Dict] = {}  # Track which orders are DCA orders
        
        logger.info(f"OrderManager initialized with {self._communication_method} communication")
        logger.info("Enhanced OrderManager with DCA support and configurable communication ready")
    
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
            logger.info(f"Placing order: {order.symbol} {order.side.value} {order.quantity} "
                       f"@ {order.price} ({order.order_type.value})")
            
            # Validate order before placing
            self._validate_order(order)
            
            # Convert to Alpaca order request
            alpaca_request = self._convert_to_alpaca_request(order)
            
            # Place order with Alpaca
            alpaca_order = await self._execute_alpaca_order(alpaca_request)
            
            # Update order with broker details
            order.order_id = alpaca_order.id
            order.status = self._convert_alpaca_status(alpaca_order.status)
            order.created_at = alpaca_order.created_at or datetime.utcnow()
            
            # Initialize fill information if available immediately
            if alpaca_order.filled_qty:
                order.filled_quantity = float(alpaca_order.filled_qty)
            if alpaca_order.filled_avg_price:
                order.filled_price = float(alpaca_order.filled_avg_price)
                order.filled_at = datetime.utcnow()
                logger.info(f"Order filled immediately: {order.symbol} {order.side.value} "
                           f"{order.filled_quantity} @ ${order.filled_price:.4f}")
            
            # Store in active orders for continuous monitoring
            self._active_orders[order.order_id] = order
            
            # For market and limit orders, log that we'll monitor for fill
            if order.order_type in [OrderType.MARKET, OrderType.LIMIT]:
                logger.info(f"📋 {order.order_type.value.title()} order submitted for monitoring: {order.order_id}")
                logger.info(f"   Will continuously check fill status during bot cycles")
                
                # Only log price range for limit orders (market orders have None price)
                if order.order_type == OrderType.LIMIT and order.price is not None:
                    logger.info(f"   Expected fill price range: ${order.price * 0.999:.2f} - ${order.price * 1.001:.2f}")
                elif order.order_type == OrderType.MARKET:
                    logger.info(f"   Market order will fill at current market price")
            
            logger.info(f"Order placed successfully, order_id={order.order_id}")
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
            
            # Cancel with Alpaca
            await self._execute_alpaca_cancel(order_id)
            
            # Update local order status
            if order_id in self._active_orders:
                self._active_orders[order_id].status = OrderStatus.CANCELED
                
                # Move to history
                self._order_history.append(self._active_orders[order_id])
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
            logger.info(f"   Original: {original_order.side.value} {original_order.quantity} @ ${original_order.price:.4f}")
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
            
            # Fetch from broker
            alpaca_order = await self._get_alpaca_order(order_id)
            if alpaca_order:
                return self._convert_alpaca_status(alpaca_order.status)
            
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
            
            # Not found locally, fetch from broker
            alpaca_order = await self._get_alpaca_order(order_id)
            if alpaca_order and alpaca_order.filled_avg_price:
                return float(alpaca_order.filled_avg_price)
            
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
            
            # Not found locally, try to fetch from broker
            alpaca_order = await self._get_alpaca_order(order_id)
            if alpaca_order:
                # Create order object from Alpaca data
                order = Order(
                    symbol=alpaca_order.symbol,
                    quantity=float(alpaca_order.qty),
                    order_type=OrderType.MARKET if alpaca_order.order_type == "market" else OrderType.LIMIT,
                    side=OrderSide.BUY if alpaca_order.side == "buy" else OrderSide.SELL,
                    price=float(alpaca_order.limit_price) if alpaca_order.limit_price else None
                )
                order.order_id = alpaca_order.id
                order.status = self._convert_alpaca_status(alpaca_order.status)
                order.created_at = alpaca_order.created_at
                
                # Fill information
                if alpaca_order.filled_qty:
                    order.filled_quantity = float(alpaca_order.filled_qty)
                if alpaca_order.filled_avg_price:
                    order.filled_price = float(alpaca_order.filled_avg_price)
                if alpaca_order.filled_at:
                    order.filled_at = alpaca_order.filled_at
                
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
    
    def _convert_to_alpaca_request(self, order: Order):
        """Convert internal order to Alpaca request with extended hours support."""
        side = AlpacaOrderSide.BUY if order.side == OrderSide.BUY else AlpacaOrderSide.SELL
        
        # Check if extended hours trading is enabled and if we're actually in extended hours
        enable_extended = self._config.get_config("trading.extended_hours.enabled", True)
        is_extended_hours = self._is_extended_hours() if enable_extended else False
        
        # Get configured order type
        configured_order_type = order.order_type
        
        # FORCE limit orders during extended hours (Alpaca requirement)
        if is_extended_hours and configured_order_type == OrderType.MARKET:
            logger.info(f"🕐 Extended hours detected - converting market order to limit order (Alpaca requirement)")
            actual_order_type = OrderType.LIMIT
            # Calculate limit price based on order direction
            limit_offset = self._config.get_config("trading.limit_order_offset", 0.001)
            if side == AlpacaOrderSide.BUY:
                # Buy slightly above current price
                limit_price = order.price * (1 + limit_offset) if order.price else None
            else:
                # Sell slightly below current price  
                limit_price = order.price * (1 - limit_offset) if order.price else None
            
            # Round to nearest penny for Alpaca compliance
            if limit_price is not None:
                limit_price = round(limit_price, 2)
                logger.debug(f"Rounded extended hours limit price to: ${limit_price:.2f}")
        else:
            actual_order_type = configured_order_type
            limit_price = order.price
            
            # Round limit price to nearest penny if it's a limit order
            if actual_order_type == OrderType.LIMIT and limit_price is not None:
                limit_price = round(limit_price, 2)
                logger.debug(f"Rounded limit price to: ${limit_price:.2f}")
        
        if actual_order_type == OrderType.MARKET:
            request = MarketOrderRequest(
                symbol=order.symbol,
                qty=order.quantity,
                side=side,
                time_in_force=TimeInForce.DAY
            )
            
            # Only set extended hours flag if we're actually in extended hours
            try:
                if is_extended_hours and hasattr(request, 'extended_hours'):
                    request.extended_hours = True
                    logger.debug(f"Extended hours flag set for market order (currently in extended hours)")
                else:
                    logger.debug(f"Regular hours - no extended hours flag needed")
            except Exception as e:
                logger.debug(f"Extended hours not supported in market order: {e}")
            
            return request
            
        elif actual_order_type == OrderType.LIMIT:
            request = LimitOrderRequest(
                symbol=order.symbol,
                qty=order.quantity,
                side=side,
                limit_price=limit_price,
                time_in_force=TimeInForce.DAY
            )
            
            # Only set extended hours flag if we're actually in extended hours
            try:
                if is_extended_hours and hasattr(request, 'extended_hours'):
                    request.extended_hours = True
                    logger.debug(f"Extended hours flag set for limit order (currently in extended hours)")
                else:
                    logger.debug(f"Regular hours - no extended hours flag needed")
            except Exception as e:
                logger.debug(f"Extended hours not supported in limit order: {e}")
            
            return request
            
        elif order.order_type == OrderType.STOP:
            return StopOrderRequest(
                symbol=order.symbol,
                qty=order.quantity,
                side=side,
                stop_price=order.stop_price,
                time_in_force=TimeInForce.DAY
            )
        else:
            raise OrderExecutionException(f"Unsupported order type: {order.order_type}")
    
    async def _execute_alpaca_order(self, request) -> AlpacaOrder:
        """Execute order with Alpaca API."""
        try:
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._client.submit_order, request)
        except Exception as e:
            error_msg = str(e).lower()
            # Check for non-retryable errors by message content
            non_retryable_errors = [
                "cannot be sold short",
                "insufficient buying power", 
                "invalid symbol",
                "market is closed",
                "position size",
                "not supported",
                "forbidden"
            ]
            
            # Also check for specific Alpaca error codes that are non-retryable
            non_retryable_codes = [
                "42210000",  # cannot be sold short
                "40310000",  # insufficient buying power
                "40010001",  # invalid symbol
            ]
            
            is_non_retryable = (
                any(error in error_msg for error in non_retryable_errors) or
                any(code in str(e) for code in non_retryable_codes)
            )
            
            if is_non_retryable:
                # Raise a specific exception that won't be retried
                raise OrderExecutionException(f"Alpaca API error (non-retryable): {str(e)}")
            
            # For other errors, raise APIException which will be retried
            raise APIException(f"Alpaca API error: {str(e)}")
    
    async def _execute_alpaca_cancel(self, order_id: str) -> None:
        """Cancel order with Alpaca API."""
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._client.cancel_order_by_id, order_id)
        except Exception as e:
            raise APIException(f"Alpaca API error: {str(e)}")
    
    async def _get_alpaca_order(self, order_id: str) -> Optional[AlpacaOrder]:
        """Get order from Alpaca API."""
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._client.get_order_by_id, order_id)
        except Exception as e:
            logger.error(f"Failed to get order from Alpaca: {str(e)}")
            return None
    
    async def _refresh_order_status(self, order_id: str) -> None:
        """Refresh order status from broker with enhanced fill price tracking."""
        alpaca_order = await self._get_alpaca_order(order_id)
        if alpaca_order and order_id in self._active_orders:
            order = self._active_orders[order_id]
            old_status = order.status
            old_fill_price = order.filled_price
            old_filled_qty = order.filled_quantity
            
            order.status = self._convert_alpaca_status(alpaca_order.status)
            
            # Update fill information with detailed logging
            if alpaca_order.filled_qty:
                order.filled_quantity = float(alpaca_order.filled_qty)
                
            if alpaca_order.filled_avg_price:
                order.filled_price = float(alpaca_order.filled_avg_price)
                order.filled_at = alpaca_order.filled_at or datetime.utcnow()
                
                # Log any fill price changes for audit trail
                if old_fill_price != order.filled_price:
                    logger.info(f"🎯 FILL PRICE CAPTURED: {order.symbol} {order.side.value} "
                               f"@ ${order.filled_price:.4f} (Order: {order_id})")
                    if old_fill_price is not None:
                        logger.info(f"   Previous fill price: ${old_fill_price:.4f}")
            
            # Log quantity changes
            if old_filled_qty != order.filled_quantity:
                logger.info(f"📊 FILL QUANTITY UPDATE: {order.symbol} "
                           f"{old_filled_qty or 0} → {order.filled_quantity}")
            
            # Log status changes with detailed information
            if old_status != order.status:
                logger.info(f"📋 ORDER STATUS: {order_id} {old_status} → {order.status}")
                
                # If order is now filled, ensure we have all fill data
                if order.status == OrderStatus.FILLED:
                    if order.filled_price and order.filled_quantity:
                        logger.info(f"✅ ORDER FULLY FILLED: {order.symbol} {order.side.value} "
                                   f"{order.filled_quantity} @ ${order.filled_price:.4f}")
                    else:
                        logger.warning(f"⚠️ Order marked filled but missing fill data: {order_id}")
            
            # Move to history if completed
            if order.status in [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED]:
                logger.info(f"📁 Moving order to history: {order_id} ({order.status})")
                self._order_history.append(order)
                del self._active_orders[order_id]
    
    async def _refresh_all_orders(self) -> None:
        """Refresh all active orders from broker."""
        tasks = [self._refresh_order_status(order_id) 
                for order_id in list(self._active_orders.keys())]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    def _convert_alpaca_status(self, alpaca_status: str) -> OrderStatus:
        """Convert Alpaca order status to internal status."""
        status_mapping = {
            "new": OrderStatus.PENDING,
            "accepted": OrderStatus.PENDING,
            "pending_new": OrderStatus.PENDING,
            "partially_filled": OrderStatus.PARTIAL_FILL,
            "filled": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELED,
            "rejected": OrderStatus.REJECTED,
            "expired": OrderStatus.CANCELED,
        }
        return status_mapping.get(alpaca_status.lower(), OrderStatus.REJECTED)
    
    def _is_extended_hours(self) -> bool:
        """
        Check if current time is within extended hours (but not regular market hours).
        Returns True only during pre-market (4:00-9:30 AM ET) or after-hours (4:00-8:00 PM ET).
        
        Properly handles Daylight Saving Time transitions automatically.
        """
        try:
            from datetime import datetime
            import pytz
            
            # Get current time in Eastern Time (handles DST automatically)
            et_tz = pytz.timezone('US/Eastern')
            now_et = datetime.now(et_tz)
            
            # Skip weekends
            if now_et.weekday() >= 5:  # Saturday=5, Sunday=6
                return False
            
            current_hour = now_et.hour
            current_minute = now_et.minute
            current_time_minutes = current_hour * 60 + current_minute
            
            # Market hours in minutes since midnight ET (automatically adjusts for DST)
            regular_market_start = 9 * 60 + 30  # 9:30 AM ET
            regular_market_end = 16 * 60         # 4:00 PM ET
            
            extended_start = 4 * 60              # 4:00 AM ET  
            extended_end = 20 * 60               # 8:00 PM ET
            
            # Check if we're in extended hours but NOT regular hours
            in_extended_window = extended_start <= current_time_minutes <= extended_end
            in_regular_hours = regular_market_start <= current_time_minutes <= regular_market_end
            
            is_extended = in_extended_window and not in_regular_hours
            
            if is_extended:
                # Log with DST awareness
                dst_status = "EDT" if now_et.dst() else "EST"
                if current_time_minutes < regular_market_start:
                    logger.debug(f"Currently in pre-market hours: {now_et.strftime('%H:%M')} {dst_status}")
                else:
                    logger.debug(f"Currently in after-hours: {now_et.strftime('%H:%M')} {dst_status}")
            else:
                dst_status = "EDT" if now_et.dst() else "EST"
                logger.debug(f"Currently in regular market hours: {now_et.strftime('%H:%M')} {dst_status}")
            
            return is_extended
                
        except Exception as e:
            logger.error(f"Error checking extended hours: {e}")
            return False  # Default to regular hours if we can't determine
    
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
                    
                    logger.info(f"🎉 ORDER FILLED: {filled_order.symbol} {filled_order.side.value} "
                               f"{filled_order.filled_quantity} @ ${filled_order.filled_price:.4f}")
                    logger.info(f"   Order ID: {filled_order.order_id}")
                    logger.info(f"   Order Type: {filled_order.order_type.value}")
                    
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
                    fill_event = OrderFillEvent(
                        order_id=filled_order.order_id,
                        symbol=filled_order.symbol,
                        side=filled_order.side.value.lower(),
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
    # ENHANCED FEATURES - Communication Method Management
    # ===================================================================
    
    @property
    def communication_method(self) -> str:
        """Get the current communication method."""
        return self._communication_method
    
    @property
    def is_websocket_enabled(self) -> bool:
        """Check if WebSocket communication is enabled."""
        return self._communication_method == "websocket"
    
    @property
    def real_time_orders(self) -> Dict[str, Order]:
        """Get real-time order tracking (WebSocket mode only)."""
        return self._real_time_orders.copy()
    
    async def switch_communication_method(self, method: str) -> None:
        """
        Switch communication method at runtime.
        
        Args:
            method: New communication method ("rest" or "websocket")
        """
        if method.lower() not in ["rest", "websocket"]:
            raise ConfigurationException(f"Invalid communication method: {method}")
        
        old_method = self._communication_method
        self._communication_method = method.lower()
        
        # Validate WebSocket is enabled if switching to it
        if self._communication_method == "websocket" and not self._websocket_enabled:
            logger.warning("WebSocket not enabled in config. Falling back to REST.")
            self._communication_method = "rest"
        
        if old_method != self._communication_method:
            logger.info(f"Communication method switched from {old_method} to {self._communication_method}")
    
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
    
    async def get_actual_fill_price(self, order_id: str) -> Optional[float]:
        """
        Get the actual fill price for an order (enhanced for DCA tracking).
        
        Args:
            order_id: Order ID to check
            
        Returns:
            Actual fill price or None if not filled
        """
        try:
            # Check active orders first
            if order_id in self._active_orders:
                order = self._active_orders[order_id]
                if order.status == OrderStatus.FILLED and order.filled_price:
                    return order.filled_price
            
            # Check order history
            for order in self._order_history:
                if order.order_id == order_id and order.status == OrderStatus.FILLED:
                    return order.filled_price
            
            # Refresh from broker as last resort
            await self._refresh_order_status(order_id)
            
            # Check again after refresh
            if order_id in self._active_orders:
                order = self._active_orders[order_id]
                if order.status == OrderStatus.FILLED and order.filled_price:
                    return order.filled_price
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting actual fill price for order {order_id}: {e}")
            return None
    
    async def get_order_by_id(self, order_id: str) -> Optional[Order]:
        """
        Get order by ID from active orders or history.
        
        Args:
            order_id: Order ID to find
            
        Returns:
            Order if found, None otherwise
        """
        # Check active orders
        if order_id in self._active_orders:
            return self._active_orders[order_id]
        
        # Check history
        for order in self._order_history:
            if order.order_id == order_id:
                return order
        
        return None
    
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
