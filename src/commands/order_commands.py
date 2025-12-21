"""
Concrete command implementations for trading operations.
"""

from typing import Any, Dict, Optional
from datetime import datetime

from src.commands.base_command import TradingCommand, CommandResult, CommandStatus
from src.interfaces import IOrderManager, IRiskManager
from src import Order, OrderType, OrderSide
from src.core.logging_config import get_logger


logger = get_logger(__name__)


class PlaceOrderCommand(TradingCommand):
    """Command to place a trading order."""
    
    def __init__(
        self,
        order_manager: IOrderManager,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        is_dca_order: bool = False,
        position_lifecycle_id: Optional[str] = None,
        command_id: Optional[str] = None
    ):
        """
        Initialize place order command.
        
        Args:
            order_manager: Order manager instance
            symbol: Trading symbol
            side: Order side (buy/sell)
            quantity: Order quantity
            order_type: Type of order
            price: Limit price (for limit orders)
            stop_price: Stop price (for stop orders)
            is_dca_order: Flag indicating DCA order
            position_lifecycle_id: Position lifecycle ID
            command_id: Optional command ID
        """
        super().__init__(command_id)
        self.order_manager = order_manager
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.order_type = order_type
        self.price = price
        self.stop_price = stop_price
        self.is_dca_order = is_dca_order
        self.position_lifecycle_id = position_lifecycle_id
        self.placed_order: Optional[Order] = None
    
    async def execute(self) -> CommandResult:
        """Execute order placement."""
        try:
            logger.info(
                f"Placing {self.side.value} order: {self.symbol} "
                f"qty={self.quantity} type={self.order_type.value}"
            )
            
            # Place order through order manager
            order = await self.order_manager.place_order(
                symbol=self.symbol,
                side=self.side,
                quantity=self.quantity,
                order_type=self.order_type,
                price=self.price,
                stop_price=self.stop_price
            )
            
            self.placed_order = order
            
            return CommandResult(
                success=True,
                command_id=self.command_id,
                status=CommandStatus.COMPLETED,
                data={
                    "order_id": order.order_id,
                    "symbol": self.symbol,
                    "side": self.side.value,
                    "quantity": self.quantity,
                    "order_type": self.order_type.value,
                    "is_dca_order": self.is_dca_order
                },
                rollback_data={
                    "order_id": order.order_id,
                    "symbol": self.symbol
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to place order for {self.symbol}: {str(e)}")
            return CommandResult(
                success=False,
                command_id=self.command_id,
                status=CommandStatus.FAILED,
                error=str(e)
            )
    
    async def undo(self) -> bool:
        """Undo order placement by canceling the order."""
        if not self.can_undo() or not self.placed_order:
            logger.warning(f"Cannot undo command {self.command_id}")
            return False
        
        try:
            logger.info(f"Undoing order placement: {self.placed_order.order_id}")
            
            # Cancel the order
            await self.order_manager.cancel_order(self.placed_order.order_id)
            
            self.status = CommandStatus.ROLLED_BACK
            logger.info(f"Successfully rolled back order {self.placed_order.order_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to rollback order {self.placed_order.order_id}: {str(e)}")
            return False


class CancelOrderCommand(TradingCommand):
    """Command to cancel an existing order."""
    
    def __init__(
        self,
        order_manager: IOrderManager,
        order_id: str,
        command_id: Optional[str] = None
    ):
        """
        Initialize cancel order command.
        
        Args:
            order_manager: Order manager instance
            order_id: ID of order to cancel
            command_id: Optional command ID
        """
        super().__init__(command_id)
        self.order_manager = order_manager
        self.order_id = order_id
        self.canceled_order: Optional[Order] = None
    
    async def execute(self) -> CommandResult:
        """Execute order cancellation."""
        try:
            logger.info(f"Canceling order: {self.order_id}")
            
            # Get order details before canceling (for potential undo)
            order = await self.order_manager.get_order(self.order_id)
            self.canceled_order = order
            
            # Cancel the order
            await self.order_manager.cancel_order(self.order_id)
            
            return CommandResult(
                success=True,
                command_id=self.command_id,
                status=CommandStatus.COMPLETED,
                data={
                    "order_id": self.order_id,
                    "canceled_at": datetime.utcnow().isoformat()
                },
                rollback_data={
                    "order": order  # Store order details for potential re-creation
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to cancel order {self.order_id}: {str(e)}")
            return CommandResult(
                success=False,
                command_id=self.command_id,
                status=CommandStatus.FAILED,
                error=str(e)
            )
    
    async def undo(self) -> bool:
        """
        Undo order cancellation by re-placing the order.
        Note: This may not restore exact order state (fills, etc.)
        """
        if not self.can_undo() or not self.canceled_order:
            logger.warning(f"Cannot undo command {self.command_id}")
            return False
        
        try:
            logger.info(f"Undoing order cancellation: {self.order_id}")
            
            # Re-place the order (best effort)
            await self.order_manager.place_order(
                symbol=self.canceled_order.symbol,
                side=self.canceled_order.side,
                quantity=self.canceled_order.quantity,
                order_type=self.canceled_order.order_type,
                price=getattr(self.canceled_order, 'limit_price', None)
            )
            
            self.status = CommandStatus.ROLLED_BACK
            logger.info(f"Successfully re-placed canceled order {self.order_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to undo cancellation for {self.order_id}: {str(e)}")
            return False


class ModifyPositionCommand(TradingCommand):
    """Command to modify an existing position."""
    
    def __init__(
        self,
        position_manager,
        symbol: str,
        modification: Dict[str, Any],
        command_id: Optional[str] = None
    ):
        """
        Initialize modify position command.
        
        Args:
            position_manager: Position manager instance
            symbol: Trading symbol
            modification: Dictionary of modifications to apply
            command_id: Optional command ID
        """
        super().__init__(command_id)
        self.position_manager = position_manager
        self.symbol = symbol
        self.modification = modification
        self.previous_state: Optional[Dict[str, Any]] = None
    
    async def execute(self) -> CommandResult:
        """Execute position modification."""
        try:
            logger.info(f"Modifying position: {self.symbol}")
            
            # Get current position state (for rollback)
            position = await self.position_manager.get_position(self.symbol)
            if position:
                self.previous_state = {
                    "symbol": position.symbol,
                    "quantity": position.quantity,
                    "avg_price": position.avg_price
                }
            
            # Apply modifications
            await self.position_manager.update_position(self.symbol, self.modification)
            
            return CommandResult(
                success=True,
                command_id=self.command_id,
                status=CommandStatus.COMPLETED,
                data={
                    "symbol": self.symbol,
                    "modifications": self.modification
                },
                rollback_data={
                    "previous_state": self.previous_state
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to modify position {self.symbol}: {str(e)}")
            return CommandResult(
                success=False,
                command_id=self.command_id,
                status=CommandStatus.FAILED,
                error=str(e)
            )
    
    async def undo(self) -> bool:
        """Undo position modification by restoring previous state."""
        if not self.can_undo() or not self.previous_state:
            logger.warning(f"Cannot undo command {self.command_id}")
            return False
        
        try:
            logger.info(f"Undoing position modification: {self.symbol}")
            
            # Restore previous state
            await self.position_manager.update_position(self.symbol, self.previous_state)
            
            self.status = CommandStatus.ROLLED_BACK
            logger.info(f"Successfully restored position {self.symbol}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to undo position modification for {self.symbol}: {str(e)}")
            return False


class ExecuteDCACommand(TradingCommand):
    """Command to execute DCA (Dollar Cost Averaging) order."""
    
    def __init__(
        self,
        order_manager: IOrderManager,
        risk_manager: IRiskManager,
        symbol: str,
        current_price: float,
        support_level: float,
        base_quantity: float,
        multiplier: float,
        position_lifecycle_id: str,
        command_id: Optional[str] = None
    ):
        """
        Initialize DCA execution command.
        
        Args:
            order_manager: Order manager instance
            risk_manager: Risk manager instance
            symbol: Trading symbol
            current_price: Current market price
            support_level: Support level for DCA
            base_quantity: Base position quantity
            multiplier: DCA size multiplier
            position_lifecycle_id: Position lifecycle ID
            command_id: Optional command ID
        """
        super().__init__(command_id)
        self.order_manager = order_manager
        self.risk_manager = risk_manager
        self.symbol = symbol
        self.current_price = current_price
        self.support_level = support_level
        self.base_quantity = base_quantity
        self.multiplier = multiplier
        self.position_lifecycle_id = position_lifecycle_id
        self.dca_order: Optional[Order] = None
    
    async def execute(self) -> CommandResult:
        """Execute DCA order placement."""
        try:
            logger.info(
                f"Executing DCA for {self.symbol} at support {self.support_level:.2f} "
                f"(current: {self.current_price:.2f})"
            )
            
            # Calculate DCA quantity
            dca_quantity = self.base_quantity * self.multiplier
            
            # Validate with risk manager
            if hasattr(self.risk_manager, 'validate_position_size'):
                is_valid, validated_qty = await self.risk_manager.validate_position_size(
                    self.symbol,
                    dca_quantity,
                    self.current_price
                )
                
                if not is_valid:
                    return CommandResult(
                        success=False,
                        command_id=self.command_id,
                        status=CommandStatus.FAILED,
                        error="DCA order rejected by risk manager"
                    )
                
                dca_quantity = validated_qty
            
            # Place DCA order
            order = await self.order_manager.place_order(
                symbol=self.symbol,
                side=OrderSide.BUY,
                quantity=dca_quantity,
                order_type=OrderType.LIMIT,
                price=self.support_level
            )
            
            self.dca_order = order
            
            return CommandResult(
                success=True,
                command_id=self.command_id,
                status=CommandStatus.COMPLETED,
                data={
                    "order_id": order.order_id,
                    "symbol": self.symbol,
                    "quantity": dca_quantity,
                    "support_level": self.support_level,
                    "position_lifecycle_id": self.position_lifecycle_id
                },
                rollback_data={
                    "order_id": order.order_id
                }
            )
            
        except Exception as e:
            logger.error(f"Failed to execute DCA for {self.symbol}: {str(e)}")
            return CommandResult(
                success=False,
                command_id=self.command_id,
                status=CommandStatus.FAILED,
                error=str(e)
            )
    
    async def undo(self) -> bool:
        """Undo DCA order by canceling it."""
        if not self.can_undo() or not self.dca_order:
            logger.warning(f"Cannot undo command {self.command_id}")
            return False
        
        try:
            logger.info(f"Undoing DCA order: {self.dca_order.order_id}")
            
            await self.order_manager.cancel_order(self.dca_order.order_id)
            
            self.status = CommandStatus.ROLLED_BACK
            logger.info(f"Successfully rolled back DCA order {self.dca_order.order_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to rollback DCA order {self.dca_order.order_id}: {str(e)}")
            return False
