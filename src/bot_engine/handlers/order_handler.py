"""
Order Handler - Extracted from BotRunner.

Handles all order placement and execution logic for bot trading:
- Base order placement
- Safety order (DCA) placement
- Take profit execution
- Stop loss execution
- Position closing

This class follows Single Responsibility Principle by focusing
exclusively on order execution concerns.

Author: Trading Bot Team
Version: 1.1.0 (Added IOrderManager integration)
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, TYPE_CHECKING, Callable, Awaitable

from src.core.logging_config import get_logger
from src.domain.bot_models import BotOperationalPhase

if TYPE_CHECKING:
    from src.domain.bot_models import Bot, DCAConfiguration
    from src.interfaces import IOrderManager
    from src.bot_engine.interfaces import IBrokerConnectionPool

logger = get_logger(__name__)


# Type alias for phase update callback
PhaseUpdateCallback = Callable[[BotOperationalPhase], Awaitable[None]]
PersistCallback = Callable[[], Awaitable[None]]


class OrderHandler:
    """
    Handles order placement and execution for a trading bot.
    
    Extracted from BotRunner to separate order execution concerns
    from the main bot lifecycle management.
    
    Responsibilities:
    - Place base orders to enter positions
    - Place safety orders (DCA) for averaging down
    - Execute take profit orders
    - Execute stop loss orders
    - Close positions
    
    Thread Safety:
    - All methods are async and run in single event loop
    - State mutations are atomic within coroutines
    
    Usage:
        handler = OrderHandler(bot, order_manager=order_manager)
        await handler.place_base_order(
            current_price=150.00,
            on_phase_update=update_phase_callback,
            on_persist=persist_callback
        )
    """
    
    def __init__(
        self,
        bot: "Bot",
        broker_pool: Optional["IBrokerConnectionPool"] = None,
        order_manager: Optional["IOrderManager"] = None,
    ):
        """
        Initialize the order handler.
        
        Args:
            bot: Bot domain model with configuration
            broker_pool: Optional broker connection pool (legacy, for backward compatibility)
            order_manager: Optional order manager for actual order execution
            
        Note:
            If order_manager is provided, it will be used for actual trade execution.
            Otherwise, orders are simulated for testing/demo purposes.
        """
        self._bot = bot
        self._broker_pool = broker_pool
        self._order_manager = order_manager
        
        # Position state (mirrors BotRunner state for now)
        self.has_position: bool = False
        self.position_size: Optional[Decimal] = None
        self.avg_entry_price: Optional[Decimal] = None
        self.base_order_price: Optional[Decimal] = None
        self.safety_orders_used: int = 0
        self.last_order_at: Optional[datetime] = None
        
        # Deal tracking
        self.current_deal_id: Optional[str] = None
        self.deal_start_time: Optional[datetime] = None
        self.active_deals_count: int = 0
    
    @property
    def has_order_manager(self) -> bool:
        """Check if actual order execution is available."""
        return self._order_manager is not None
    
    # =========================================================================
    # Order Placement Methods
    # =========================================================================
    
    async def place_base_order(
        self,
        current_price: Decimal,
        on_phase_update: PhaseUpdateCallback,
        on_persist: PersistCallback,
    ) -> bool:
        """
        Place the base order to enter a position.
        
        Args:
            current_price: Current market price
            on_phase_update: Callback to update bot operational phase
            on_persist: Callback to persist bot state
            
        Returns:
            True if order was placed successfully
        """
        dca_config = self._bot.configuration.dca_config
        if not dca_config:
            logger.warning(f"Bot {self._bot.id}: No DCA config for base order")
            return False
        
        # Start new deal
        self.current_deal_id = str(uuid.uuid4())
        self.deal_start_time = datetime.utcnow()
        self.active_deals_count += 1
        
        base_amount = Decimal(str(dca_config.start_settings.base_order_amount))
        order_type = dca_config.start_settings.base_order_type
        
        logger.info(
            f"Bot {self._bot.id} placing base order: "
            f"{base_amount} {self._bot.symbol} ({order_type})"
        )
        
        # Execute order via order_manager if available
        if self._order_manager:
            try:
                # Import Order types for actual execution
                from src.interfaces import Order, OrderSide, OrderType
                
                # Calculate quantity based on amount and current price
                quantity = base_amount / current_price if current_price else Decimal("0")
                
                order = Order(
                    symbol=self._bot.symbol,
                    side=OrderSide.BUY,  # DCA starts with buy
                    order_type=OrderType.MARKET if order_type == "market" else OrderType.LIMIT,
                    quantity=quantity,
                    price=current_price if order_type == "limit" else None,
                )
                
                result = await self._order_manager.place_order(order)
                if result and result.id:
                    logger.info(f"Bot {self._bot.id} base order placed: {result.id}")
                    self.has_position = True
                    self.position_size = quantity
                    self.avg_entry_price = result.filled_avg_price or current_price
                    self.base_order_price = self.avg_entry_price
                    self.safety_orders_used = 0
                    self.last_order_at = datetime.utcnow()
                else:
                    logger.error(f"Bot {self._bot.id} base order failed: no result")
                    return False
            except Exception as e:
                logger.error(f"Bot {self._bot.id} base order error: {e}")
                return False
        else:
            # Simulate order placement (demo mode)
            self.has_position = True
            self.position_size = base_amount / current_price if current_price else Decimal("0")
            self.avg_entry_price = current_price
            self.base_order_price = current_price
            self.safety_orders_used = 0
            self.last_order_at = datetime.utcnow()
        
        await on_phase_update(BotOperationalPhase.IN_POSITION)
        await on_persist()
        
        return True
    
    async def place_safety_order(
        self,
        current_price: Decimal,
        on_phase_update: PhaseUpdateCallback,
        on_persist: PersistCallback,
    ) -> bool:
        """
        Place a safety order (DCA) to average down.
        
        Args:
            current_price: Current market price
            on_phase_update: Callback to update bot operational phase
            on_persist: Callback to persist bot state
            
        Returns:
            True if order was placed successfully
        """
        logger.info(
            f"Bot {self._bot.id} placing safety order #{self.safety_orders_used + 1}"
        )
        
        dca_config = self._bot.configuration.dca_config
        
        # Execute via order_manager if available
        if self._order_manager and dca_config:
            try:
                from src.interfaces import Order, OrderSide, OrderType
                
                # Calculate safety order size (multiplied by step scale)
                base_amount = Decimal(str(dca_config.start_settings.base_order_amount))
                scale = Decimal(str(dca_config.averaging_orders.step_scale_percent / 100 + 1))
                safety_amount = base_amount * (scale ** self.safety_orders_used)
                quantity = safety_amount / current_price if current_price else Decimal("0")
                
                order = Order(
                    symbol=self._bot.symbol,
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    quantity=quantity,
                )
                
                result = await self._order_manager.place_order(order)
                if result and result.id:
                    logger.info(f"Bot {self._bot.id} safety order placed: {result.id}")
                    # Update average entry price
                    if self.position_size and self.avg_entry_price:
                        total_value = (self.position_size * self.avg_entry_price) + (quantity * current_price)
                        self.position_size += quantity
                        self.avg_entry_price = total_value / self.position_size
                else:
                    logger.error(f"Bot {self._bot.id} safety order failed")
                    return False
            except Exception as e:
                logger.error(f"Bot {self._bot.id} safety order error: {e}")
                return False
        
        self.safety_orders_used += 1
        self.last_order_at = datetime.utcnow()
        
        await on_phase_update(BotOperationalPhase.IN_POSITION)
        await on_persist()
        
        return True
    
    async def execute_take_profit(
        self,
        on_phase_update: PhaseUpdateCallback,
        on_persist: PersistCallback,
    ) -> bool:
        """
        Execute take profit order.
        
        Args:
            on_phase_update: Callback to update bot operational phase
            on_persist: Callback to persist bot state
            
        Returns:
            True if take profit was executed successfully
        """
        logger.info(f"Bot {self._bot.id} executing take profit")
        
        # Execute via order_manager if available
        if self._order_manager and self.has_position and self.position_size:
            try:
                from src.interfaces import Order, OrderSide, OrderType
                
                order = Order(
                    symbol=self._bot.symbol,
                    side=OrderSide.SELL,  # Close long position
                    order_type=OrderType.MARKET,
                    quantity=self.position_size,
                )
                
                result = await self._order_manager.place_order(order)
                if result and result.id:
                    logger.info(f"Bot {self._bot.id} take profit executed: {result.id}")
                else:
                    logger.warning(f"Bot {self._bot.id} take profit may have failed")
            except Exception as e:
                logger.error(f"Bot {self._bot.id} take profit error: {e}")
                # Continue to update state even on error
        
        self.has_position = False
        self.position_size = None
        self.avg_entry_price = None
        self.last_order_at = datetime.utcnow()
        
        await on_phase_update(BotOperationalPhase.POSITION_CLOSED)
        await on_persist()
        
        return True
    
    async def execute_stop_loss(
        self,
        on_phase_update: PhaseUpdateCallback,
        on_persist: PersistCallback,
    ) -> bool:
        """
        Execute stop loss order.
        
        Args:
            on_phase_update: Callback to update bot operational phase
            on_persist: Callback to persist bot state
            
        Returns:
            True if stop loss was executed successfully
        """
        logger.info(f"Bot {self._bot.id} executing stop loss")
        
        # Execute via order_manager if available
        if self._order_manager and self.has_position and self.position_size:
            try:
                from src.interfaces import Order, OrderSide, OrderType
                
                order = Order(
                    symbol=self._bot.symbol,
                    side=OrderSide.SELL,  # Close long position
                    order_type=OrderType.MARKET,
                    quantity=self.position_size,
                )
                
                result = await self._order_manager.place_order(order)
                if result and result.id:
                    logger.info(f"Bot {self._bot.id} stop loss executed: {result.id}")
                else:
                    logger.warning(f"Bot {self._bot.id} stop loss may have failed")
            except Exception as e:
                logger.error(f"Bot {self._bot.id} stop loss error: {e}")
                # Continue to update state even on error
        
        self.has_position = False
        self.position_size = None
        self.avg_entry_price = None
        self.last_order_at = datetime.utcnow()
        
        await on_phase_update(BotOperationalPhase.POSITION_CLOSED)
        await on_persist()
        
        return True
    
    async def close_position(
        self,
        on_phase_update: PhaseUpdateCallback,
        on_persist: PersistCallback,
    ) -> bool:
        """
        Close the current position.
        
        Args:
            on_phase_update: Callback to update bot operational phase
            on_persist: Callback to persist bot state
            
        Returns:
            True if position was closed successfully
        """
        if not self.has_position:
            return False
        
        logger.info(f"Bot {self._bot.id} closing position")
        
        await on_phase_update(BotOperationalPhase.CLOSING_POSITION)
        
        # Execute via order_manager if available
        if self._order_manager and self.position_size:
            try:
                from src.interfaces import Order, OrderSide, OrderType
                
                order = Order(
                    symbol=self._bot.symbol,
                    side=OrderSide.SELL,  # Close long position
                    order_type=OrderType.MARKET,
                    quantity=self.position_size,
                )
                
                result = await self._order_manager.place_order(order)
                if result and result.id:
                    logger.info(f"Bot {self._bot.id} position closed: {result.id}")
                else:
                    logger.warning(f"Bot {self._bot.id} position close may have failed")
            except Exception as e:
                logger.error(f"Bot {self._bot.id} position close error: {e}")
                # Continue to update state even on error
        
        self.has_position = False
        self.position_size = None
        self.avg_entry_price = None
        
        await on_phase_update(BotOperationalPhase.POSITION_CLOSED)
        
        return True
    
    # =========================================================================
    # State Management
    # =========================================================================
    
    def reset_for_new_deal(self) -> None:
        """Reset state for a new deal/cycle."""
        self.current_deal_id = None
        self.deal_start_time = None
        self.safety_orders_used = 0
        self.active_deals_count = max(0, self.active_deals_count - 1)
        self.base_order_price = None
    
    def sync_from_runner(
        self,
        has_position: bool,
        position_size: Optional[Decimal],
        avg_entry_price: Optional[Decimal],
        base_order_price: Optional[Decimal],
        safety_orders_used: int,
    ) -> None:
        """
        Sync state from BotRunner (for backward compatibility).
        
        Args:
            has_position: Whether there's an active position
            position_size: Current position size
            avg_entry_price: Average entry price
            base_order_price: Base order price
            safety_orders_used: Number of safety orders used
        """
        self.has_position = has_position
        self.position_size = position_size
        self.avg_entry_price = avg_entry_price
        self.base_order_price = base_order_price
        self.safety_orders_used = safety_orders_used
    
    def sync_to_runner(self) -> dict:
        """
        Export state to sync back to BotRunner.
        
        Returns:
            Dictionary of state values to sync
        """
        return {
            "has_position": self.has_position,
            "position_size": self.position_size,
            "avg_entry_price": self.avg_entry_price,
            "base_order_price": self.base_order_price,
            "safety_orders_used": self.safety_orders_used,
            "last_order_at": self.last_order_at,
            "current_deal_id": self.current_deal_id,
            "deal_start_time": self.deal_start_time,
            "active_deals_count": self.active_deals_count,
        }
