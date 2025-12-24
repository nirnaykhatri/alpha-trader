"""
Position Management Router.

Handles position-related endpoints:
- Close specific position
- Close all positions
- Get positions

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
from src.services.admin_interfaces import IPositionService
from src.signals.routers.base_router import (
    BaseAdminRouter,
    ClosePositionRequest,
    handle_route_errors,
)

logger = get_logger(__name__)


class PositionRouter(BaseAdminRouter):
    """
    Router for position management operations.
    
    Provides endpoints for:
    - POST /positions/{symbol}/close - Close a specific position
    - POST /positions/close-all - Close all positions
    - GET /positions - List all positions
    """
    
    def __init__(
        self,
        position_service: Optional[IPositionService] = None,
        auth_service=None,
        bot_instance=None  # Legacy support
    ):
        """
        Initialize position router.
        
        Args:
            position_service: Position management service
            auth_service: Authentication service
            bot_instance: Legacy bot instance (deprecated)
        """
        super().__init__(auth_service=auth_service, prefix="/admin", tags=["positions"])
        
        self._position_service = position_service
        self._bot_instance = bot_instance
        
        self._setup_routes()
        logger.info("✅ PositionRouter initialized")
    
    def set_position_service(self, position_service: IPositionService) -> None:
        """Set the position service."""
        self._position_service = position_service
        logger.info("Position service set for PositionRouter")
    
    def set_bot_instance(self, bot_instance) -> None:
        """Set bot instance (legacy support)."""
        self._bot_instance = bot_instance
    
    def _setup_routes(self) -> None:
        """Setup position management routes."""
        
        @self.router.post("/positions/{symbol}/close")
        @handle_route_errors(operation_name="close_position")
        async def close_position(
            symbol: str,
            close_request: ClosePositionRequest,
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Close a position (fully or partially)."""
            await self.validate_auth(request, authorization)
            
            if not self._bot_instance:
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR,
                    detail="Bot instance not available"
                )
            
            symbol = symbol.upper().strip()
            
            logger.info(f"📤 Admin close position request: {symbol}")
            
            positions = await self._bot_instance.get_positions()
            position = next((p for p in positions if p.symbol == symbol), None)
            
            if not position:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND,
                    detail=f"No active position found for {symbol}"
                )
            
            qty_to_close = close_request.quantity or abs(position.quantity)
            
            if qty_to_close > abs(position.quantity):
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=f"Cannot close {qty_to_close} shares. Position has {abs(position.quantity)} shares."
                )
            
            close_side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
            order_type = OrderType.MARKET if close_request.order_type == "market" else OrderType.LIMIT
            
            order_params = {
                "symbol": symbol,
                "side": close_side,
                "qty": Decimal(str(qty_to_close)),
                "order_type": order_type,
                "time_in_force": "day",
            }
            
            if close_request.limit_price:
                order_params["limit_price"] = Decimal(str(close_request.limit_price))
            
            order_id = await self._bot_instance.order_manager.place_order(
                Order(**order_params)
            )
            
            action = "fully closed" if qty_to_close == abs(position.quantity) else f"partially closed ({qty_to_close} shares)"
            logger.info(f"✅ Position {action}: {symbol}, order {order_id}")
            
            return JSONResponse(content={
                "status": "success",
                "order_id": order_id,
                "symbol": symbol,
                "quantity_closed": qty_to_close,
                "action": action,
                "timestamp": datetime.utcnow().isoformat()
            })
        
        @self.router.post("/positions/close-all")
        @handle_route_errors(operation_name="close_all_positions")
        async def close_all_positions(
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Close all open positions (emergency liquidation)."""
            await self.validate_auth(request, authorization)
            
            if not self._bot_instance:
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR,
                    detail="Bot instance not available"
                )
            
            logger.warning("🚨 Admin close ALL positions request")
            
            positions = await self._bot_instance.get_positions()
            
            if not positions:
                return JSONResponse(content={
                    "status": "success",
                    "message": "No open positions to close",
                    "closed_count": 0
                })
            
            closed = []
            errors = []
            
            for position in positions:
                try:
                    close_side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
                    
                    order_id = await self._bot_instance.order_manager.place_order(
                        Order(
                            symbol=position.symbol,
                            side=close_side,
                            qty=Decimal(str(abs(position.quantity))),
                            order_type=OrderType.MARKET,
                            time_in_force="day"
                        )
                    )
                    
                    closed.append({
                        "symbol": position.symbol,
                        "quantity": abs(position.quantity),
                        "order_id": order_id
                    })
                    
                except Exception as e:
                    errors.append({
                        "symbol": position.symbol,
                        "error": str(e)
                    })
            
            logger.info(f"✅ Closed {len(closed)} positions, {len(errors)} errors")
            
            return JSONResponse(content={
                "status": "success" if not errors else "partial",
                "closed_count": len(closed),
                "closed_positions": closed,
                "errors": errors,
                "timestamp": datetime.utcnow().isoformat()
            })
        
        @self.router.get("/positions")
        @handle_route_errors(operation_name="get_positions")
        async def get_positions(
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Get all current positions."""
            await self.validate_auth(request, authorization)
            
            if not self._bot_instance:
                return JSONResponse(content={"status": "success", "positions": []})
            
            positions = await self._bot_instance.get_positions()
            positions_data = [
                {
                    "symbol": p.symbol,
                    "quantity": float(p.quantity),
                    "avg_price": float(p.avg_price),
                    "current_price": float(p.current_price) if hasattr(p, 'current_price') else None,
                    "unrealized_pnl": float(p.unrealized_pnl) if hasattr(p, 'unrealized_pnl') else None,
                    "side": "long" if p.quantity > 0 else "short"
                }
                for p in positions
            ]
            
            return JSONResponse(content={
                "status": "success",
                "positions": positions_data,
                "count": len(positions_data)
            })
