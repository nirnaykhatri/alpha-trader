"""
Alpaca implementation of IBrokerOrderExecutor.
"""
import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest,
    OrderSide as AlpacaOrderSide, TimeInForce
)
from alpaca.trading.models import Order as AlpacaOrder
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.broker.interfaces import IBrokerOrderExecutor
from src.interfaces import Order, OrderType, OrderSide, OrderStatus, IConfigurationManager
from src.exceptions import (
    OrderExecutionException, APIException,
    BrokerOrderException, BrokerAPIException, BrokerPermissionException
)
from src.core.logging_config import get_logger
from src.utils import run_blocking

logger = get_logger(__name__)

class AlpacaOrderExecutor(IBrokerOrderExecutor):
    """
    Alpaca implementation of the order executor interface.
    
    This class handles order placement, cancellation, and status retrieval using
    the Alpaca API. It includes logic for handling extended hours trading and
    converting between internal domain objects and Alpaca API models.
    """
    
    def __init__(self, trading_client: TradingClient, config: IConfigurationManager):
        """
        Initialize the Alpaca order executor.
        
        Args:
            trading_client: Authenticated Alpaca TradingClient instance.
            config: Configuration manager for accessing trading settings.
        """
        self._client = trading_client
        self._config = config
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(BrokerAPIException)
    )
    async def place_order(self, order: Order) -> str:
        """
        Place an order with Alpaca.
        
        Converts the internal Order object to an Alpaca request and submits it.
        Updates the order object with the broker order ID and initial status.
        
        Args:
            order: The order to place.
            
        Returns:
            str: The broker-assigned order ID.
            
        Raises:
            BrokerOrderException: If the order cannot be placed (e.g. invalid parameters).
            BrokerAPIException: If the API call fails (retryable).
            BrokerPermissionException: If the account lacks permissions/funds.
        """
        try:
            # Convert to Alpaca request
            request = self._convert_to_alpaca_request(order)
            
            # Execute
            alpaca_order = await run_blocking(self._client.submit_order, request)
            
            # Update order with broker details
            order.broker_order_id = alpaca_order.id
            # We also set the main order_id to broker_order_id if it wasn't set (though it usually is UUID)
            # But the interface says place_order returns broker order ID.
            
            # Update status and fill info if available immediately
            order.status = self._convert_alpaca_status(alpaca_order.status)
            if alpaca_order.filled_qty:
                order.filled_quantity = float(alpaca_order.filled_qty)
            if alpaca_order.filled_avg_price:
                order.filled_price = float(alpaca_order.filled_avg_price)
                order.filled_at = datetime.utcnow()
            
            return alpaca_order.id
            
        except Exception as e:
            self._handle_alpaca_error(e)
            # Note: _handle_alpaca_error always raises, so this line is unreachable
            # but required for type checker to understand the function signature

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(BrokerAPIException)
    )
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order with Alpaca.
        
        Args:
            order_id: The broker order ID to cancel.
            
        Returns:
            bool: True if cancellation request was successful, False otherwise.
        """
        try:
            await run_blocking(self._client.cancel_order_by_id, order_id)
            return True
        except Exception as e:
            logger.error(f"Failed to cancel Alpaca order {order_id}: {str(e)}")
            return False

    async def get_order_status(self, order_id: str) -> OrderStatus:
        """
        Get order status from Alpaca.
        
        Args:
            order_id: The broker order ID.
            
        Returns:
            OrderStatus: The current status of the order.
        """
        try:
            alpaca_order = await run_blocking(self._client.get_order_by_id, order_id)
            return self._convert_alpaca_status(alpaca_order.status)
        except Exception as e:
            logger.error(f"Failed to get Alpaca order status {order_id}: {str(e)}")
            return OrderStatus.REJECTED

    async def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get complete order details including fill information from Alpaca.
        
        This method provides full order data including filled_quantity, filled_price,
        and status, which is essential for accurate fill tracking and reconciliation.
        
        Args:
            order_id: The broker order ID.
            
        Returns:
            Optional[Order]: The complete order with fill details, or None if not found.
        """
        try:
            alpaca_order = await run_blocking(self._client.get_order_by_id, order_id)
            return self._convert_alpaca_order_to_domain(alpaca_order)
        except Exception as e:
            logger.error(f"Failed to get Alpaca order {order_id}: {str(e)}")
            return None

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get open orders from Alpaca.
        
        Args:
            symbol: Optional symbol to filter orders by.
            
        Returns:
            List[Order]: List of open orders converted to domain objects.
        """
        try:
            # Get all open orders
            alpaca_orders = await run_blocking(self._client.get_all_open_orders)
            
            orders = []
            for ao in alpaca_orders:
                if symbol and ao.symbol != symbol:
                    continue
                    
                order = self._convert_alpaca_order_to_domain(ao)
                orders.append(order)
                
            return orders
        except Exception as e:
            logger.error(f"Failed to get open orders from Alpaca: {str(e)}")
            return []

    def _convert_to_alpaca_request(self, order: Order):
        """
        Convert internal order to Alpaca request with extended hours support.
        
        This method handles the complexity of:
        1. Mapping internal OrderSide to AlpacaOrderSide.
        2. Checking if extended hours trading is enabled and active.
        3. Converting MARKET orders to LIMIT orders during extended hours (Alpaca requirement).
        4. Calculating appropriate limit prices for converted orders.
        
        Args:
            order: The internal Order object.
            
        Returns:
            Union[MarketOrderRequest, LimitOrderRequest, StopOrderRequest]: The Alpaca API request object.
            
        Raises:
            BrokerOrderException: If the order type is unsupported.
        """
        side = AlpacaOrderSide.BUY if order.side == OrderSide.BUY else AlpacaOrderSide.SELL
        
        # Check if extended hours trading is enabled and if we're actually in extended hours
        enable_extended = self._config.get_config("trading.extended_hours.enabled", True)
        is_extended_hours = self._is_extended_hours() if enable_extended else False
        
        # Get configured order type
        configured_order_type = order.order_type
        
        # FORCE limit orders during extended hours (Alpaca requirement)
        # Alpaca does not support market orders during extended hours.
        if is_extended_hours and configured_order_type == OrderType.MARKET:
            actual_order_type = OrderType.LIMIT
            # Calculate limit price based on order direction to ensure execution
            # For BUY: Price slightly above current (to buy immediately)
            # For SELL: Price slightly below current (to sell immediately)
            limit_offset = self._config.get_config("trading.limit_order_offset", 0.001)
            if side == AlpacaOrderSide.BUY:
                limit_price = order.price * (1 + limit_offset) if order.price else None
            else:
                limit_price = order.price * (1 - limit_offset) if order.price else None
            
            if limit_price is not None:
                limit_price = round(limit_price, 2)
        else:
            actual_order_type = configured_order_type
            limit_price = order.price
            if actual_order_type == OrderType.LIMIT and limit_price is not None:
                limit_price = round(limit_price, 2)
        
        if actual_order_type == OrderType.MARKET:
            request = MarketOrderRequest(
                symbol=order.symbol,
                qty=order.quantity,
                side=side,
                time_in_force=TimeInForce.DAY
            )
            if is_extended_hours and hasattr(request, 'extended_hours'):
                request.extended_hours = True
            return request
            
        elif actual_order_type == OrderType.LIMIT:
            request = LimitOrderRequest(
                symbol=order.symbol,
                qty=order.quantity,
                side=side,
                limit_price=limit_price,
                time_in_force=TimeInForce.DAY
            )
            if is_extended_hours and hasattr(request, 'extended_hours'):
                request.extended_hours = True
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
            raise BrokerOrderException(f"Unsupported order type: {order.order_type}")

    def _convert_alpaca_status(self, alpaca_status: str) -> OrderStatus:
        """
        Convert Alpaca order status to internal status.
        
        Args:
            alpaca_status: Status string from Alpaca API.
            
        Returns:
            OrderStatus: Corresponding internal OrderStatus enum.
        """
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

    def _convert_alpaca_order_to_domain(self, ao: AlpacaOrder) -> Order:
        """
        Convert Alpaca order model to domain Order.
        
        Args:
            ao: Alpaca Order object.
            
        Returns:
            Order: Internal domain Order object.
        """
        order = Order(
            symbol=ao.symbol,
            quantity=float(ao.qty),
            order_type=OrderType.MARKET if ao.order_type == "market" else OrderType.LIMIT,
            side=OrderSide.BUY if ao.side == "buy" else OrderSide.SELL,
            price=float(ao.limit_price) if ao.limit_price else None
        )
        order.order_id = ao.id  # Use Alpaca ID as order ID for now, or map it
        order.broker_order_id = ao.id
        order.broker = "alpaca"
        order.status = self._convert_alpaca_status(ao.status)
        order.created_at = ao.created_at
        
        if ao.filled_qty:
            order.filled_quantity = float(ao.filled_qty)
        if ao.filled_avg_price:
            order.filled_price = float(ao.filled_avg_price)
        if ao.filled_at:
            order.filled_at = ao.filled_at
            
        return order

    def _handle_alpaca_error(self, e: Exception):
        """
        Handle Alpaca API errors.
        
        Categorizes errors into retryable (BrokerAPIException) and non-retryable (BrokerOrderException/BrokerPermissionException).
        
        Args:
            e: The exception caught during API call.
            
        Raises:
            BrokerOrderException: For permanent order errors.
            BrokerPermissionException: For permission/fund errors.
            BrokerAPIException: For transient errors.
        """
        error_msg = str(e).lower()
        
        # Permission/Validation errors (Non-retryable)
        permission_errors = [
            "insufficient buying power", 
            "forbidden",
            "not supported",
            "account is restricted",
            "insufficient funds"
        ]
        
        # Order specific errors (Non-retryable)
        order_errors = [
            "cannot be sold short",
            "invalid symbol",
            "market is closed",
            "position size",
            "invalid order",
            "pattern day trader"
        ]
        
        if any(err in error_msg for err in permission_errors):
            raise BrokerPermissionException(f"Alpaca permission error: {str(e)}")
            
        if any(err in error_msg for err in order_errors):
            raise BrokerOrderException(f"Alpaca order error: {str(e)}")
            
        # Default to API error (potentially retryable)
        raise BrokerAPIException(f"Alpaca API error: {str(e)}")

    def _is_extended_hours(self) -> bool:
        """
        Check if current time is within extended hours.
        
        Returns:
            bool: True if current time is in pre-market or after-hours, False otherwise.
        """
        try:
            import pytz
            et_tz = pytz.timezone('US/Eastern')
            now_et = datetime.now(et_tz)
            
            if now_et.weekday() >= 5:
                return False
            
            current_time_minutes = now_et.hour * 60 + now_et.minute
            regular_market_start = 9 * 60 + 30
            regular_market_end = 16 * 60
            extended_start = 4 * 60
            extended_end = 20 * 60
            
            in_extended_window = extended_start <= current_time_minutes <= extended_end
            in_regular_hours = regular_market_start <= current_time_minutes <= regular_market_end
            
            return in_extended_window and not in_regular_hours
        except Exception as e:
            logger.error(f"Error checking extended hours: {e}")
            return False
