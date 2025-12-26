"""
Exit Order Planning Service

Centralizes exit order computation logic used across different exit scenarios:
- Signal-based close (_handle_close_signal)
- Profit taking (_execute_profit_taking)
- Manual close (manual_close_position)

This service handles:
- Order type determination (limit vs market)
- Limit price calculation with configured offset
- Order side determination based on position direction
- Price rounding for broker compliance

Fallback Behavior:
    When the configured order type is LIMIT but no market data is available
    (i.e., no IMarketDataProvider was injected and no current_price was passed),
    the service automatically falls back to a MARKET order. This ensures positions
    can always be exited even when price data is unavailable, prioritizing 
    execution over price optimization.
    
    This fallback is logged as a warning for operational visibility:
        "No market data provider available for limit order on {symbol}. 
         Falling back to MARKET order."
    
    To guarantee limit orders, ensure either:
    1. A valid IMarketDataProvider is passed to the constructor, OR
    2. A current_price is explicitly passed to plan_exit()

Thread-Safety: This service is stateless and safe for concurrent use.
"""

from dataclasses import dataclass
from typing import Optional
from decimal import Decimal, ROUND_HALF_UP

from src import Order, OrderType, OrderSide, Position
from src.core import get_logger
from src.interfaces import IConfigurationManager, IMarketDataProvider

logger = get_logger(__name__)


@dataclass(frozen=True)
class ExitOrderPlan:
    """
    Immutable plan for an exit order.
    
    Attributes:
        symbol: Trading symbol
        quantity: Number of shares to trade (always positive)
        order_type: Limit or market order
        side: Buy or sell
        price: Limit price (None for market orders)
        reason: Human-readable reason for the exit
    """
    symbol: str
    quantity: float
    order_type: OrderType
    side: OrderSide
    price: Optional[float]
    reason: str
    
    def to_order(self) -> Order:
        """Convert plan to an Order object ready for submission."""
        return Order(
            order_id=None,
            symbol=self.symbol,
            quantity=self.quantity,
            order_type=self.order_type,
            side=self.side,
            price=self.price
        )


class ExitPlanner:
    """
    Service for planning exit orders.
    
    Centralizes the exit order computation logic that was previously duplicated
    across multiple methods in TradingBotOrchestrator.
    
    Usage:
        planner = ExitPlanner(config, market_data)
        plan = await planner.plan_exit(position, reason="profit_taking")
        order = plan.to_order()
        await order_manager.place_order(order)
    
    The service is stateless and can be shared across different exit scenarios.
    """
    
    def __init__(
        self,
        config: IConfigurationManager,
        market_data: Optional[IMarketDataProvider]
    ) -> None:
        """
        Initialize the exit planner.
        
        Args:
            config: Configuration provider for trading settings
            market_data: Market data provider for price lookups (optional, can be None if no broker configured)
        """
        self._config = config
        self._market_data = market_data
    
    async def plan_exit(
        self,
        position: Position,
        reason: str = "close",
        quantity_override: Optional[float] = None,
        current_price: Optional[float] = None
    ) -> ExitOrderPlan:
        """
        Plan an exit order for a position.
        
        Args:
            position: The position to exit
            reason: Human-readable reason (e.g., "profit_taking", "stop_loss", "signal_close")
            quantity_override: Optional quantity to use instead of full position
            current_price: Optional pre-fetched current price (avoids redundant API call)
        
        Returns:
            ExitOrderPlan with all computed exit order parameters
        
        Raises:
            ValueError: If position has zero quantity or invalid quantity_override
        """
        if position.quantity == 0:
            raise ValueError(f"Cannot plan exit for zero-quantity position: {position.symbol}")
        
        if quantity_override is not None and quantity_override <= 0:
            raise ValueError(f"Invalid quantity_override: {quantity_override}. Must be positive.")
        
        # Determine exit quantity
        exit_quantity = quantity_override if quantity_override is not None else abs(position.quantity)
        
        # Determine order side based on position direction
        order_side = self._determine_exit_side(position)
        
        # Determine order type from config
        order_type = self._determine_order_type()
        
        # Calculate price for limit orders
        price = None
        if order_type == OrderType.LIMIT:
            if current_price is None:
                if self._market_data is None:
                    # Cannot place limit order without price data - fall back to market order
                    logger.warning(
                        f"No market data provider available for limit order on {position.symbol}. "
                        f"Falling back to MARKET order."
                    )
                    order_type = OrderType.MARKET
                else:
                    current_price = await self._market_data.get_current_price(position.symbol)
                    price = self._calculate_limit_price(current_price, order_side)
            else:
                price = self._calculate_limit_price(current_price, order_side)
        
        plan = ExitOrderPlan(
            symbol=position.symbol,
            quantity=exit_quantity,
            order_type=order_type,
            side=order_side,
            price=price,
            reason=reason
        )
        
        logger.debug(
            f"Exit plan created: {plan.symbol} {plan.side.value} {plan.quantity} @ "
            f"{'$' + str(plan.price) if plan.price else 'MARKET'} ({plan.reason})"
        )
        
        return plan
    
    def _determine_exit_side(self, position: Position) -> OrderSide:
        """
        Determine the order side needed to exit a position.
        
        Long positions (quantity > 0) require SELL to close.
        Short positions (quantity < 0) require BUY to cover.
        
        Args:
            position: The position to analyze
            
        Returns:
            OrderSide.SELL for long positions, OrderSide.BUY for short positions
        """
        return OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
    
    def _determine_order_type(self) -> OrderType:
        """
        Determine order type from configuration.
        
        Returns:
            OrderType.LIMIT or OrderType.MARKET based on config
        """
        configured_type = self._config.get_config("trading.order_type", "limit")
        return OrderType.LIMIT if configured_type.lower() == "limit" else OrderType.MARKET
    
    def _calculate_limit_price(self, current_price: float, order_side: OrderSide) -> float:
        """
        Calculate limit price with configured offset.
        
        For SELL orders: price slightly below market to ensure fill
        For BUY orders: price slightly above market to ensure fill
        
        Args:
            current_price: Current market price
            order_side: Whether this is a buy or sell order
            
        Returns:
            Limit price rounded to penny precision
        """
        limit_offset = self._config.get_config("trading.limit_order_offset", 0.001)
        
        if order_side == OrderSide.SELL:
            # Sell slightly below current price to ensure fill
            price = current_price * (1 - limit_offset)
        else:
            # Buy slightly above current price to ensure fill
            price = current_price * (1 + limit_offset)
        
        # Round to penny for broker compliance
        return round(price, 2)
    
    def validate_exit_quantity(
        self,
        requested_qty: float,
        position_qty: float,
        pending_qty: float = 0.0
    ) -> tuple[float, bool]:
        """
        Validate and adjust exit quantity based on available shares.
        
        Args:
            requested_qty: Desired exit quantity
            position_qty: Current position quantity (can be negative for shorts)
            pending_qty: Quantity tied up in pending orders
            
        Returns:
            Tuple of (adjusted_quantity, is_valid)
            - adjusted_quantity: Safe quantity to trade
            - is_valid: Whether the exit is valid (qty > 0)
        """
        available_qty = abs(position_qty) - abs(pending_qty)
        
        if available_qty <= 0:
            logger.warning(
                f"No available quantity for exit. Position: {position_qty}, Pending: {pending_qty}"
            )
            return 0.0, False
        
        # Use the smaller of requested and available
        safe_qty = min(requested_qty, available_qty)
        
        if safe_qty < requested_qty:
            logger.info(
                f"Exit quantity adjusted from {requested_qty} to {safe_qty} "
                f"due to pending orders ({pending_qty} shares)"
            )
        
        return safe_qty, safe_qty > 0
