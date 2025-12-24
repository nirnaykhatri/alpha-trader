"""
Admin Service Implementations.

Concrete implementations of admin service interfaces that delegate
to the trading bot components.

Author: Trading Bot Team
Version: 1.0.0
"""

from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import datetime
import asyncio

from src.core.logging_config import get_logger
from src.interfaces import Order, OrderSide, OrderType
from src.services.admin_interfaces import (
    IOrderService,
    IPositionService,
    IBotLifecycleService,
    IConfigService,
    IRiskValidationService,
    IFundService,
    OrderDTO,
    PositionDTO,
    BotStatus,
    BotState,
)

logger = get_logger(__name__)


class BotOrderService(IOrderService):
    """
    Order service implementation using trading bot components.
    
    Delegates to the bot's order manager while providing a clean
    interface for the admin API.
    """
    
    def __init__(self, bot_instance, risk_service: Optional['IRiskValidationService'] = None):
        """
        Initialize order service.
        
        Args:
            bot_instance: Trading bot instance with order_manager
            risk_service: Optional risk validation service
        """
        self._bot = bot_instance
        self._risk_service = risk_service
    
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        order_type: OrderType,
        limit_price: Optional[Decimal] = None,
        time_in_force: str = "day"
    ) -> str:
        """Place a new order with risk validation."""
        if not self._bot or not hasattr(self._bot, 'order_manager'):
            raise RuntimeError("Order manager not available")
        
        # Validate against risk limits
        if self._risk_service:
            is_valid, error = await self._risk_service.validate_order(
                symbol, side, quantity, limit_price
            )
            if not is_valid:
                raise ValueError(f"Risk validation failed: {error}")
        
        # Build order
        order_params = {
            "symbol": symbol.upper(),
            "side": side,
            "qty": quantity,
            "order_type": order_type,
            "time_in_force": time_in_force,
        }
        
        if limit_price:
            order_params["limit_price"] = limit_price
        
        # Place through order manager
        order_id = await self._bot.order_manager.place_order(Order(**order_params))
        logger.info(f"Order placed via admin: {order_id}")
        
        return order_id
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        if not self._bot or not hasattr(self._bot, 'order_manager'):
            raise RuntimeError("Order manager not available")
        
        result = await self._bot.order_manager.cancel_order(order_id)
        logger.info(f"Order cancel via admin: {order_id} - {'success' if result else 'failed'}")
        return result
    
    async def get_pending_orders(self) -> List[OrderDTO]:
        """Get all pending orders."""
        if not self._bot or not hasattr(self._bot, 'order_manager'):
            return []
        
        orders = await self._bot.order_manager.get_open_orders()
        return [self._to_dto(order) for order in orders]
    
    async def get_order(self, order_id: str) -> Optional[OrderDTO]:
        """Get order by ID."""
        if not self._bot or not hasattr(self._bot, 'order_manager'):
            return None
        
        order = await self._bot.order_manager.get_order(order_id)
        return self._to_dto(order) if order else None
    
    def _to_dto(self, order) -> OrderDTO:
        """Convert order to DTO."""
        return OrderDTO(
            id=str(order.id) if hasattr(order, 'id') else "",
            symbol=order.symbol,
            side=order.side.value if hasattr(order.side, 'value') else str(order.side),
            quantity=float(order.qty),
            filled_quantity=float(getattr(order, 'filled_qty', 0)),
            order_type=order.order_type.value if hasattr(order.order_type, 'value') else str(order.order_type),
            status=order.status.value if hasattr(order.status, 'value') else str(getattr(order, 'status', 'unknown')),
            limit_price=float(order.limit_price) if hasattr(order, 'limit_price') and order.limit_price else None,
            created_at=getattr(order, 'created_at', None)
        )


class BotPositionService(IPositionService):
    """
    Position service implementation using trading bot components.
    """
    
    def __init__(self, bot_instance):
        """
        Initialize position service.
        
        Args:
            bot_instance: Trading bot instance
        """
        self._bot = bot_instance
    
    async def get_positions(self) -> List[PositionDTO]:
        """Get all open positions."""
        if not self._bot:
            return []
        
        positions = await self._bot.get_positions()
        return [self._to_dto(pos) for pos in positions]
    
    async def get_position(self, symbol: str) -> Optional[PositionDTO]:
        """Get position for a specific symbol."""
        positions = await self.get_positions()
        return next((p for p in positions if p.symbol == symbol.upper()), None)
    
    async def close_position(
        self,
        symbol: str,
        quantity: Optional[Decimal] = None,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[Decimal] = None
    ) -> str:
        """Close a position."""
        if not self._bot:
            raise RuntimeError("Bot not available")
        
        symbol = symbol.upper()
        position = await self.get_position(symbol)
        
        if not position:
            raise ValueError(f"No position found for {symbol}")
        
        qty_to_close = quantity or Decimal(str(abs(position.quantity)))
        
        # Determine close side
        close_side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
        
        # Place close order
        order_params = {
            "symbol": symbol,
            "side": close_side,
            "qty": qty_to_close,
            "order_type": order_type,
            "time_in_force": "day",
        }
        
        if limit_price:
            order_params["limit_price"] = limit_price
        
        order_id = await self._bot.order_manager.place_order(Order(**order_params))
        logger.info(f"Position close order placed: {order_id}")
        
        return order_id
    
    async def close_all_positions(self, order_type: OrderType = OrderType.MARKET) -> Dict[str, str]:
        """Close all open positions."""
        positions = await self.get_positions()
        results = {}
        
        for position in positions:
            try:
                order_id = await self.close_position(
                    position.symbol,
                    order_type=order_type
                )
                results[position.symbol] = order_id
            except Exception as e:
                logger.error(f"Failed to close {position.symbol}: {e}")
                results[position.symbol] = f"error: {str(e)}"
        
        return results
    
    def _to_dto(self, position) -> PositionDTO:
        """Convert position to DTO."""
        qty = float(getattr(position, 'quantity', 0) or getattr(position, 'qty', 0))
        avg_price = float(getattr(position, 'avg_price', 0) or getattr(position, 'avg_entry_price', 0))
        current = float(getattr(position, 'current_price', avg_price))
        market_value = qty * current
        pnl = (current - avg_price) * qty if qty > 0 else (avg_price - current) * abs(qty)
        pnl_pct = (pnl / (avg_price * abs(qty))) * 100 if avg_price and qty else 0
        
        return PositionDTO(
            symbol=position.symbol,
            quantity=qty,
            avg_price=avg_price,
            current_price=current,
            unrealized_pnl=pnl,
            unrealized_pnl_pct=pnl_pct,
            market_value=market_value,
            direction="long" if qty > 0 else "short"
        )


class BotLifecycleService(IBotLifecycleService):
    """
    Bot lifecycle service implementation.
    """
    
    def __init__(self, bot_instance):
        """
        Initialize lifecycle service.
        
        Args:
            bot_instance: Trading bot instance
        """
        self._bot = bot_instance
        self._state = BotState.RUNNING
        self._start_time = datetime.utcnow()
        self._state_lock = asyncio.Lock()
    
    async def get_status(self) -> BotStatus:
        """Get current bot status."""
        uptime = (datetime.utcnow() - self._start_time).total_seconds()
        
        positions_count = 0
        pending_orders = 0
        
        if self._bot:
            try:
                positions = await self._bot.get_positions()
                positions_count = len(positions) if positions else 0
            except Exception as e:
                logger.warning(f"Failed to get positions for status: {e}")
            
            try:
                if hasattr(self._bot, 'order_manager'):
                    orders = await self._bot.order_manager.get_open_orders()
                    pending_orders = len(orders) if orders else 0
            except Exception as e:
                logger.warning(f"Failed to get pending orders for status: {e}")
        
        return BotStatus(
            state=self._state,
            uptime_seconds=uptime,
            positions_count=positions_count,
            pending_orders=pending_orders
        )
    
    async def start(self) -> bool:
        """Start the bot."""
        async with self._state_lock:
            if self._state == BotState.RUNNING:
                return True
            
            if self._bot and hasattr(self._bot, 'start'):
                await self._bot.start()
            
            self._state = BotState.RUNNING
            self._start_time = datetime.utcnow()
            logger.info("Bot started via admin")
            return True
    
    async def stop(self) -> bool:
        """Stop the bot gracefully."""
        async with self._state_lock:
            if self._state == BotState.STOPPED:
                return True
            
            if self._bot and hasattr(self._bot, 'stop'):
                await self._bot.stop()
            
            self._state = BotState.STOPPED
            logger.info("Bot stopped via admin")
            return True
    
    async def pause(self) -> bool:
        """Pause trading."""
        async with self._state_lock:
            if self._state == BotState.PAUSED:
                return True
            
            self._state = BotState.PAUSED
            logger.info("Bot paused via admin")
            return True
    
    async def resume(self) -> bool:
        """Resume trading."""
        async with self._state_lock:
            if self._state == BotState.RUNNING:
                return True
            
            self._state = BotState.RUNNING
            logger.info("Bot resumed via admin")
            return True


class BotConfigService(IConfigService):
    """
    Configuration service implementation.
    """
    
    def __init__(self, config_manager):
        """
        Initialize config service.
        
        Args:
            config_manager: Configuration manager instance
        """
        self._config = config_manager
    
    async def get_config(self, section: Optional[str] = None) -> Dict[str, Any]:
        """Get configuration values."""
        if not self._config:
            return {}
        
        if section:
            return self._config.get_config(section, {})
        
        return self._config.get_all_config()
    
    async def update_config(self, section: str, settings: Dict[str, Any]) -> bool:
        """Update configuration values."""
        if not self._config:
            return False
        
        try:
            for key, value in settings.items():
                full_key = f"{section}.{key}"
                self._config.set_config(full_key, value)
            
            logger.info(f"Config updated via admin: {section}")
            return True
        except Exception as e:
            logger.error(f"Config update failed: {e}")
            return False
    
    async def reload_config(self) -> bool:
        """Reload configuration."""
        if not self._config:
            return False
        
        try:
            self._config.reload_config()
            logger.info("Config reloaded via admin")
            return True
        except Exception as e:
            logger.error(f"Config reload failed: {e}")
            return False


class BotRiskValidationService(IRiskValidationService):
    """
    Risk validation service implementation.
    """
    
    def __init__(self, risk_manager, config_manager):
        """
        Initialize risk service.
        
        Args:
            risk_manager: Risk manager instance
            config_manager: Configuration manager instance
        """
        self._risk = risk_manager
        self._config = config_manager
    
    async def validate_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        price: Optional[Decimal] = None
    ) -> tuple[bool, Optional[str]]:
        """Validate order against risk parameters."""
        if not self._risk:
            # No risk manager - allow but log warning
            logger.warning("No risk manager configured - skipping validation")
            return (True, None)
        
        try:
            # Build minimal order for validation
            order = Order(
                symbol=symbol,
                side=side,
                qty=quantity,
                order_type=OrderType.LIMIT if price else OrderType.MARKET,
                limit_price=price
            )
            
            is_valid = await self._risk.validate_order(order)
            
            if not is_valid:
                return (False, "Order exceeds risk limits")
            
            return (True, None)
            
        except Exception as e:
            logger.error(f"Risk validation error: {e}")
            return (False, str(e))
    
    async def get_risk_limits(self) -> Dict[str, Any]:
        """Get current risk limits."""
        if not self._config:
            return {}
        
        return {
            "max_position_size": self._config.get_config("risk.max_position_size", 10000),
            "max_daily_loss": self._config.get_config("risk.max_daily_loss", 500),
            "max_open_positions": self._config.get_config("risk.max_open_positions", 5),
            "max_drawdown_percent": self._config.get_config("risk.max_drawdown_percent", 5.0),
            "risk_per_trade": self._config.get_config("trading.risk_per_trade", 0.02),
        }


class BotFundService(IFundService):
    """
    Fund management service implementation.
    """
    
    def __init__(self, bot_instance, config_manager):
        """
        Initialize fund service.
        
        Args:
            bot_instance: Trading bot instance
            config_manager: Configuration manager instance
        """
        self._bot = bot_instance
        self._config = config_manager
        self._deposits: List[Dict] = []
        self._withdrawals: List[Dict] = []
        self._allocations: Dict[str, Decimal] = {}
    
    async def get_account_summary(self) -> Dict[str, Any]:
        """Get account summary."""
        if not self._bot:
            return {}
        
        try:
            # Get from broker adapter
            if hasattr(self._bot, 'broker_adapter'):
                account = await self._bot.broker_adapter.get_account()
                return {
                    "equity": float(getattr(account, 'equity', 0)),
                    "cash": float(getattr(account, 'cash', 0)),
                    "buying_power": float(getattr(account, 'buying_power', 0)),
                    "portfolio_value": float(getattr(account, 'portfolio_value', 0)),
                }
        except Exception as e:
            logger.error(f"Failed to get account summary: {e}")
        
        return {}
    
    async def record_deposit(self, amount: Decimal, notes: Optional[str] = None) -> str:
        """Record a deposit."""
        import uuid
        
        tx_id = str(uuid.uuid4())[:8]
        self._deposits.append({
            "id": tx_id,
            "amount": float(amount),
            "notes": notes,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        logger.info(f"Deposit recorded: ${amount} (tx: {tx_id})")
        return tx_id
    
    async def record_withdrawal(self, amount: Decimal, notes: Optional[str] = None) -> str:
        """Record a withdrawal."""
        import uuid
        
        tx_id = str(uuid.uuid4())[:8]
        self._withdrawals.append({
            "id": tx_id,
            "amount": float(amount),
            "notes": notes,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        logger.info(f"Withdrawal recorded: ${amount} (tx: {tx_id})")
        return tx_id
    
    async def allocate_funds(self, symbol: str, amount: Decimal) -> bool:
        """Allocate funds to a symbol."""
        symbol = symbol.upper()
        self._allocations[symbol] = self._allocations.get(symbol, Decimal(0)) + amount
        logger.info(f"Funds allocated: ${amount} to {symbol}")
        return True
