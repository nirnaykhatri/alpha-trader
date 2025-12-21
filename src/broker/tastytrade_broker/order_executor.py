"""
Tastytrade implementation of the order executor interface.

Updated for tastytrade v11.x API.
"""
import asyncio
from typing import List, Optional, NoReturn
from datetime import datetime
from decimal import Decimal

from tastytrade import Account
from tastytrade.order import (
    NewOrder, OrderAction, PriceEffect, OrderTimeInForce, OrderType as TTOrderType
)
from tastytrade.instruments import Equity

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.broker.interfaces import IBrokerOrderExecutor
from src.broker.tastytrade_broker.session_manager import TastytradeSessionManager
from src.broker.tastytrade_broker.account_mixin import TastytradeAccountMixin
from src.interfaces import Order, OrderType, OrderSide, OrderStatus, IConfigurationManager
from src.exceptions import (
    BrokerOrderException, BrokerAPIException, BrokerPermissionException
)
from src.core.logging_config import get_logger
from src.utils import run_blocking

logger = get_logger(__name__)

class TastytradeOrderExecutor(TastytradeAccountMixin, IBrokerOrderExecutor):
    """
    Tastytrade implementation of the order executor interface.
    
    This class handles order placement, cancellation, and status retrieval using
    the Tastytrade API. It converts internal domain Order objects to Tastytrade
    NewOrder objects.
    
    Inherits account retrieval functionality from TastytradeAccountMixin.
    """
    
    def __init__(self, session_manager: TastytradeSessionManager, config: IConfigurationManager, account_number: Optional[str] = None):
        """
        Initialize the Tastytrade order executor.
        
        Args:
            session_manager: Manager for Tastytrade API sessions.
            config: Configuration manager.
            account_number: Specific account number to use.
        """
        TastytradeAccountMixin.__init__(self, session_manager, account_number)
        self._config = config
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(BrokerAPIException),
        reraise=True
    )
    async def place_order(self, order: Order) -> str:
        """
        Place an order with Tastytrade.
        
        Args:
            order: The order to place.
            
        Returns:
            str: The broker-assigned order ID.
            
        Raises:
            BrokerOrderException: If the order cannot be placed.
            BrokerAPIException: If the API call fails (retried up to 3 times).
        """
        try:
            account = await self._get_account_object()
            session = await self._session_manager.get_session()
            
            # Convert to Tastytrade order
            tt_order = await self._convert_to_tt_order(order, session)
            
            # Execute order
            response = await run_blocking(account.place_order, session, tt_order)
            
            # Response is an Order object or similar containing ID
            order_id = str(response.id)
            
            # Update order details
            order.broker_order_id = order_id
            order.status = OrderStatus.PENDING # Assume pending initially
            
            return order_id
            
        except Exception as e:
            self._handle_tasty_error(e)
            raise # Unreachable

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order with Tastytrade.
        
        Args:
            order_id: The broker order ID to cancel.
            
        Returns:
            bool: True if cancellation request was successful.
        """
        try:
            account = await self._get_account_object()
            session = await self._session_manager.get_session()
            
            # Use delete_order method (new API)
            await run_blocking(account.delete_order, session, int(order_id))
            return True
        except Exception as e:
            logger.error(f"Failed to cancel Tastytrade order {order_id}: {str(e)}")
            return False

    async def get_order_status(self, order_id: str) -> OrderStatus:
        """
        Get order status from Tastytrade.
        
        Args:
            order_id: The broker order ID.
            
        Returns:
            OrderStatus: The current status of the order.
        """
        try:
            account = await self._get_account_object()
            session = await self._session_manager.get_session()
            
            order = await run_blocking(account.get_order, session, int(order_id))
            
            return self._convert_tt_status(str(order.status))
        except Exception as e:
            logger.error(f"Failed to get Tastytrade order status {order_id}: {str(e)}")
            return OrderStatus.REJECTED

    async def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get complete order details including fill information from Tastytrade.
        
        This method provides full order data including filled_quantity, filled_price,
        and status, which is essential for accurate fill tracking and reconciliation.
        
        Args:
            order_id: The broker order ID.
            
        Returns:
            Optional[Order]: The complete order with fill details, or None if not found.
        """
        try:
            account = await self._get_account_object()
            session = await self._session_manager.get_session()
            
            tt_order = await run_blocking(account.get_order, session, int(order_id))
            
            # Convert to domain order (single-leg only)
            if len(tt_order.legs) != 1:
                logger.warning(f"Cannot convert multi-leg order {order_id}")
                return None
                
            return self._convert_tt_order_to_domain(tt_order, tt_order.legs[0])
        except Exception as e:
            logger.error(f"Failed to get Tastytrade order {order_id}: {str(e)}")
            return None

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get open orders from Tastytrade.
        
        This implementation supports simple single-leg equity orders only.
        Multi-leg options orders are logged and skipped.
        
        Args:
            symbol: Optional symbol to filter orders by.
            
        Returns:
            List[Order]: List of open orders converted to domain objects.
            
        Note:
            Only single-leg equity orders are converted. Complex multi-leg
            orders (spreads, straddles, etc.) are skipped with a warning.
        """
        try:
            account = await self._get_account_object()
            session = await self._session_manager.get_session()
            
            # Fetch live orders from Tastytrade
            tt_orders = await run_blocking(account.get_live_orders, session)
            
            domain_orders = []
            for tt_order in tt_orders:
                try:
                    # Skip multi-leg orders (options spreads, etc.)
                    if len(tt_order.legs) != 1:
                        logger.debug(
                            f"Skipping multi-leg order {tt_order.id} with {len(tt_order.legs)} legs"
                        )
                        continue
                    
                    leg = tt_order.legs[0]
                    
                    # Skip non-equity instruments (options, futures, etc.)
                    instrument_type = getattr(leg, 'instrument_type', 'Equity')
                    if instrument_type != 'Equity':
                        logger.debug(
                            f"Skipping non-equity order {tt_order.id} (type: {instrument_type})"
                        )
                        continue
                    
                    # Extract symbol from leg
                    order_symbol = leg.symbol
                    
                    # Filter by symbol if specified
                    if symbol and order_symbol.upper() != symbol.upper():
                        continue
                    
                    # Convert to domain Order
                    domain_order = self._convert_tt_order_to_domain(tt_order, leg)
                    if domain_order:
                        domain_orders.append(domain_order)
                        
                except Exception as e:
                    logger.warning(f"Failed to convert Tastytrade order {tt_order.id}: {e}")
                    continue
            
            logger.debug(f"Retrieved {len(domain_orders)} open orders from Tastytrade")
            return domain_orders
            
        except Exception as e:
            logger.error(f"Failed to get open orders from Tastytrade: {e}")
            return []
    
    def _convert_tt_order_to_domain(self, tt_order, leg) -> Optional[Order]:
        """
        Convert a Tastytrade order to a domain Order object.
        
        Args:
            tt_order: Tastytrade order object.
            leg: The single leg of the order.
            
        Returns:
            Order: Domain order object, or None if conversion fails.
        """
        try:
            # Determine order side from action
            action = str(leg.action).upper()
            if action in ['BUY_TO_OPEN', 'BUY_TO_CLOSE']:
                side = OrderSide.BUY
            elif action in ['SELL_TO_OPEN', 'SELL_TO_CLOSE']:
                side = OrderSide.SELL
            else:
                logger.warning(f"Unknown order action: {action}")
                return None
            
            # Determine order type
            tt_order_type = str(tt_order.order_type).upper()
            if tt_order_type == 'MARKET':
                order_type = OrderType.MARKET
            elif tt_order_type == 'LIMIT':
                order_type = OrderType.LIMIT
            elif tt_order_type == 'STOP':
                order_type = OrderType.STOP
            elif tt_order_type == 'STOP_LIMIT':
                order_type = OrderType.STOP_LIMIT
            else:
                order_type = OrderType.LIMIT  # Default fallback
            
            # Extract price (may be None for market orders)
            price = float(tt_order.price) if tt_order.price else None
            
            # Extract quantity
            quantity = float(leg.quantity)
            
            # Create domain Order
            order = Order(
                order_id=str(tt_order.id),
                symbol=getattr(leg, 'symbol', 'UNKNOWN'),
                side=side,
                quantity=quantity,
                order_type=order_type,
                price=price
            )
            
            # Set additional fields
            order.broker_order_id = str(tt_order.id)
            order.status = self._convert_tt_status(str(tt_order.status))
            
            # Extract fill information for reconciliation
            order.filled_quantity = float(tt_order.filled_quantity) if hasattr(tt_order, 'filled_quantity') and tt_order.filled_quantity else 0.0
            order.filled_price = float(tt_order.average_fill_price) if hasattr(tt_order, 'average_fill_price') and tt_order.average_fill_price else None
            
            return order
            
        except Exception as e:
            logger.error(f"Error converting Tastytrade order: {e}")
            return None

    async def _convert_to_tt_order(self, order: Order, session) -> NewOrder:
        """
        Convert domain Order to Tastytrade NewOrder.
        
        Args:
            order: Domain Order object.
            session: Active Tastytrade session (needed for symbol lookup).
            
        Returns:
            NewOrder: Tastytrade order object.
            
        Raises:
            BrokerOrderException: If order validation fails or instrument not found.
        """
        # Validate order quantity
        if order.quantity is None or order.quantity <= 0:
            raise BrokerOrderException(f"Invalid order quantity: {order.quantity}")
        
        # 1. Get Instrument
        # Assuming Equity for now. TODO: Support Options
        try:
            instrument = await run_blocking(Equity.get, session, order.symbol)
        except Exception as e:
            raise BrokerOrderException(f"Failed to find instrument {order.symbol}: {str(e)}")
        
        # 2. Determine Action based on order intent
        # Use order metadata to determine if opening or closing position
        is_closing = getattr(order, 'is_closing', False)
        
        if order.side == OrderSide.BUY:
            # BUY can be: opening a long (BUY_TO_OPEN) or closing a short (BUY_TO_CLOSE)
            action = OrderAction.BUY_TO_CLOSE if is_closing else OrderAction.BUY_TO_OPEN
        else:
            # SELL can be: opening a short (SELL_TO_OPEN) or closing a long (SELL_TO_CLOSE)
            action = OrderAction.SELL_TO_CLOSE if is_closing else OrderAction.SELL_TO_OPEN
            
        # 3. Determine Order Type and Price
        if order.order_type == OrderType.MARKET:
            order_type = TTOrderType.MARKET
            price = None
        elif order.order_type == OrderType.LIMIT:
            order_type = TTOrderType.LIMIT
            price = Decimal(str(order.price))
        elif order.order_type == OrderType.STOP:
            order_type = TTOrderType.STOP
            price = Decimal(str(order.stop_price))
        else:
            raise BrokerOrderException(f"Unsupported order type: {order.order_type}")
            
        # 4. Create Leg
        leg = instrument.build_leg(Decimal(str(order.quantity)), action)
        
        # 5. Create Order
        new_order = NewOrder(
            time_in_force=OrderTimeInForce.DAY,
            order_type=order_type,
            legs=[leg],
            price=price,
            price_effect=PriceEffect.DEBIT if order.side == OrderSide.BUY else PriceEffect.CREDIT
        )
        
        return new_order

    def _convert_tt_status(self, status: str) -> OrderStatus:
        """
        Convert Tastytrade status string to OrderStatus.
        
        Args:
            status: Tastytrade status string.
            
        Returns:
            OrderStatus: Domain OrderStatus.
        """
        status = status.lower()
        if status in ['received', 'live', 'queued']:
            return OrderStatus.PENDING
        elif status == 'filled':
            return OrderStatus.FILLED
        elif status in ['cancelled', 'expired']:
            return OrderStatus.CANCELED
        elif status in ['rejected', 'failed']:
            return OrderStatus.REJECTED
        else:
            return OrderStatus.PENDING

    # Note: _get_account_object is inherited from TastytradeAccountMixin

    def _handle_tasty_error(self, e: Exception) -> NoReturn:
        """
        Handle Tastytrade API errors.
        
        Categorizes errors into retryable (BrokerAPIException) and non-retryable (BrokerOrderException/BrokerPermissionException).
        
        Args:
            e: The exception caught during API call.
            
        Raises:
            BrokerOrderException: For permanent order errors.
            BrokerPermissionException: For permission/fund errors.
            BrokerAPIException: For transient errors.
            
        Note:
            This method always raises an exception and never returns normally.
        """
        error_msg = str(e).lower()
        
        # Permission/Validation errors
        permission_errors = [
            "insufficient buying power",
            "unauthorized",
            "forbidden",
            "not authenticated"
        ]
        
        # Order specific errors
        order_errors = [
            "invalid symbol",
            "market closed",
            "invalid order",
            "instrument not found"
        ]
        
        if any(err in error_msg for err in permission_errors):
            raise BrokerPermissionException(f"Tastytrade permission error: {str(e)}")
            
        if any(err in error_msg for err in order_errors):
            raise BrokerOrderException(f"Tastytrade order error: {str(e)}")
            
        # Default to API error
        raise BrokerAPIException(f"Tastytrade API error: {str(e)}")
