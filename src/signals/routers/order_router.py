"""
Order Management Router.

Handles order-related endpoints:
- Place orders (market/limit)
- Cancel orders
- List pending orders

Author: Trading Bot Team
Version: 2.0.0
"""

from typing import Optional
from datetime import datetime
from decimal import Decimal

from fastapi import Request, HTTPException, Header
from fastapi.responses import JSONResponse

from src.core.logging_config import get_logger
from src.constants import HTTPStatus
from src.interfaces import Order, OrderSide, OrderType
from src.services.admin_interfaces import IOrderService
from src.signals.routers.base_router import (
    BaseAdminRouter,
    OrderRequest,
    OrderResponse,
    handle_route_errors,
)

logger = get_logger(__name__)


class OrderRouter(BaseAdminRouter):
    """
    Router for order management operations.
    
    Provides endpoints for:
    - POST /orders - Place a new order
    - DELETE /orders/{order_id} - Cancel an order
    - GET /orders/pending - List pending orders
    
    Thread Safety:
        Uses async operations; services handle their own locking.
    """
    
    def __init__(
        self,
        order_service: Optional[IOrderService] = None,
        auth_service=None,
        bot_instance=None  # Legacy support
    ):
        """
        Initialize order router.
        
        Args:
            order_service: Order management service
            auth_service: Authentication service
            bot_instance: Legacy bot instance (deprecated)
        """
        super().__init__(auth_service=auth_service, prefix="/admin", tags=["orders"])
        
        self._order_service = order_service
        self._bot_instance = bot_instance
        self._bot_state = "running"
        
        self._setup_routes()
        logger.info("✅ OrderRouter initialized")
    
    def set_order_service(self, order_service: IOrderService) -> None:
        """Set the order service."""
        self._order_service = order_service
        logger.info("Order service set for OrderRouter")
    
    def set_bot_instance(self, bot_instance) -> None:
        """Set bot instance (legacy support)."""
        self._bot_instance = bot_instance
    
    def set_bot_state(self, state: str) -> None:
        """Update bot state reference."""
        self._bot_state = state
    
    def _setup_routes(self) -> None:
        """Setup order management routes."""
        
        @self.router.post("/orders", response_model=OrderResponse)
        @handle_route_errors(operation_name="place_order")
        async def place_order(
            order_request: OrderRequest,
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """
            Place a new order.
            
            Supports market and limit orders for buying and selling.
            Orders are validated against risk limits before execution.
            """
            await self.validate_auth(request, authorization)
            
            if not self._order_service and not self._bot_instance:
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR,
                    detail="Order service not available"
                )
            
            if self._bot_state == "stopped":
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail="Bot is stopped. Start the bot before placing orders."
                )
            
            logger.info(f"📝 Admin order request: {order_request.side.upper()} {order_request.quantity} {order_request.symbol}")
            
            side = OrderSide.BUY if order_request.side == "buy" else OrderSide.SELL
            order_type = OrderType.MARKET if order_request.order_type == "market" else OrderType.LIMIT
            quantity = Decimal(str(order_request.quantity))
            limit_price = Decimal(str(order_request.limit_price)) if order_request.limit_price else None
            
            if self._order_service:
                order_id = await self._order_service.place_order(
                    symbol=order_request.symbol,
                    side=side,
                    quantity=quantity,
                    order_type=order_type,
                    limit_price=limit_price,
                    time_in_force=order_request.time_in_force
                )
            else:
                # Legacy approach
                order_params = {
                    "symbol": order_request.symbol,
                    "side": side,
                    "qty": quantity,
                    "order_type": order_type,
                    "time_in_force": order_request.time_in_force,
                }
                if limit_price:
                    order_params["limit_price"] = limit_price
                
                order_id = await self._bot_instance.order_manager.place_order(
                    Order(**order_params)
                )
            
            logger.info(f"✅ Admin order placed: {order_id}")
            
            return OrderResponse(
                status="success",
                order_id=order_id,
                message=f"Order placed: {order_request.side.upper()} {order_request.quantity} {order_request.symbol}"
            )
        
        @self.router.delete("/orders/{order_id}")
        @handle_route_errors(operation_name="cancel_order")
        async def cancel_order(
            order_id: str,
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Cancel an existing order."""
            await self.validate_auth(request, authorization)
            
            if not self._order_service and not self._bot_instance:
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR,
                    detail="Order service not available"
                )
            
            logger.info(f"🚫 Admin cancel request: order {order_id}")
            
            if self._order_service:
                success = await self._order_service.cancel_order(order_id)
            else:
                success = await self._bot_instance.order_manager.cancel_order(order_id)
            
            if success:
                logger.info(f"✅ Order cancelled: {order_id}")
                return JSONResponse(content={
                    "status": "success",
                    "message": f"Order {order_id} cancelled",
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND,
                    detail=f"Order {order_id} not found or already filled"
                )
        
        @self.router.get("/orders/pending")
        @handle_route_errors(operation_name="get_pending_orders")
        async def get_pending_orders(
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Get all pending (open) orders."""
            await self.validate_auth(request, authorization)
            
            if not self._bot_instance:
                return JSONResponse(content={"status": "error", "orders": []})
            
            orders = await self._bot_instance.order_manager.get_open_orders()
            orders_data = [
                {
                    "id": str(order.id),
                    "symbol": order.symbol,
                    "side": order.side.value if hasattr(order.side, 'value') else str(order.side),
                    "quantity": float(order.qty),
                    "filled_quantity": float(order.filled_qty) if hasattr(order, 'filled_qty') else 0,
                    "order_type": order.order_type.value if hasattr(order.order_type, 'value') else str(order.order_type),
                    "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
                    "created_at": order.created_at.isoformat() if hasattr(order, 'created_at') else None
                }
                for order in orders
            ]
            
            return JSONResponse(content={
                "status": "success",
                "orders": orders_data,
                "count": len(orders_data)
            })
