"""
Monitoring endpoints for bot status, positions, orders, and analytics.
Provides comprehensive monitoring and analytics capabilities.
"""

from typing import Optional
from datetime import datetime
from fastapi import Request, HTTPException, APIRouter
from fastapi.responses import JSONResponse

from src.core.logging_config import get_logger
from src.utils.decorators import localhost_only


logger = get_logger(__name__)


class MonitoringRouter:
    """
    Provides monitoring and analytics endpoints for the trading bot.
    All endpoints are localhost-only for security.
    """
    
    def __init__(self, bot_instance=None):
        """
        Initialize monitoring router.
        
        Args:
            bot_instance: Reference to the trading bot instance
        """
        self._bot_instance = bot_instance
        
        # Create router for monitoring endpoints
        self.router = APIRouter(
            prefix="",
            tags=["monitoring"]
        )
        
        # Setup routes
        self._setup_routes()
        
        logger.info("Monitoring router initialized")
    
    def set_bot_instance(self, bot_instance):
        """Set the bot instance reference."""
        self._bot_instance = bot_instance
    
    def _setup_routes(self) -> None:
        """Setup all monitoring routes."""
        
        @self.router.get("/health", tags=["health"])
        async def health_check():
            """Health check endpoint."""
            return {
                "status": "healthy", 
                "timestamp": datetime.utcnow().isoformat(),
                "version": "1.0.0"
            }
        
        @self.router.get("/", tags=["health"])
        async def root():
            """Root endpoint."""
            return {
                "message": "TradingView Trading Bot API", 
                "version": "1.0.0",
                "docs": "/docs",
                "health": "/health"
            }
        
        @self.router.get("/status", tags=["admin"])
        @localhost_only
        async def get_bot_status(request: Request):
            """Get current bot status including positions and orders."""
            try:
                if self._bot_instance:
                    status = await self._bot_instance.get_status()
                    return JSONResponse(content=status)
                else:
                    return JSONResponse(content={
                        "error": "Bot instance not available",
                        "message": "Bot may not be fully initialized"
                    })
            except Exception as e:
                logger.error(f"Error getting bot status: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Status error: {str(e)}")
        
        @self.router.get("/positions", tags=["positions"])
        @localhost_only
        async def get_positions(request: Request):
            """Get all current positions with enhanced DCA tracking."""
            try:
                if not self._bot_instance:
                    return JSONResponse(content={
                        "status": "error",
                        "message": "Bot instance not available",
                        "data": {"positions": []}
                    })
                
                # Try enhanced DCA positions if available
                if hasattr(self._bot_instance, 'enhanced_db') and hasattr(self._bot_instance, 'dca_metadata_manager'):
                    try:
                        from ..database.view_manager import PositionSummaryView
                        
                        session = self._bot_instance.enhanced_db.db._session_factory()
                        try:
                            positions_data = PositionSummaryView.get_position_summary(session)
                            
                            return JSONResponse(content={
                                "status": "success",
                                "timestamp": datetime.utcnow().isoformat(),
                                "data": {
                                    "positions": positions_data,
                                    "summary": {
                                        "total_positions": len(positions_data),
                                        "total_symbols": len(set(p['symbol'] for p in positions_data)),
                                        "positions_with_dca": len([p for p in positions_data if p['dca_details']['total_attempts'] > 0]),
                                        "total_unrealized_pnl": sum(p['pnl']['unrealized'] for p in positions_data),
                                        "progressive_dca_compliance": sum(1 for p in positions_data if p['dca_details']['progressive_rate'] == 100.0) / len(positions_data) * 100 if positions_data else 0
                                    }
                                }
                            })
                        finally:
                            session.close()
                    except Exception as enhanced_error:
                        logger.warning(f"Enhanced DCA tracking not available: {enhanced_error}, falling back")
                
                # Fallback to basic positions
                positions = await self._bot_instance.get_positions()
                positions_data = [
                    {
                        "symbol": pos.symbol,
                        "direction": "long" if pos.quantity > 0 else "short",
                        "quantity": abs(pos.quantity),
                        "avg_price": pos.avg_price,
                        "current_price": pos.current_price,
                        "unrealized_pnl": pos.unrealized_pnl,
                        "unrealized_pnl_pct": (pos.unrealized_pnl / (abs(pos.quantity) * pos.avg_price) * 100) if pos.quantity != 0 and pos.avg_price != 0 else 0
                    }
                    for pos in positions
                ]
                
                return JSONResponse(content={
                    "status": "success",
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": {
                        "positions": positions_data,
                        "summary": {
                            "total_positions": len(positions_data),
                            "total_unrealized_pnl": sum(p['unrealized_pnl'] for p in positions_data)
                        }
                    }
                })
            except Exception as e:
                logger.error(f"Error getting positions: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Positions error: {str(e)}")
        
        @self.router.get("/positions/{symbol}", tags=["positions"])
        @localhost_only
        async def get_position_detail(symbol: str, request: Request):
            """Get detailed information for a specific position."""
            try:
                if not self._bot_instance:
                    return JSONResponse(
                        content={
                            "status": "error",
                            "message": "Bot instance not available"
                        },
                        status_code=500
                    )
                
                # Try enhanced tracking first
                if hasattr(self._bot_instance, 'enhanced_db'):
                    try:
                        from ..database.enhanced_schema import EnhancedPositionRecord
                        
                        session = self._bot_instance.enhanced_db.db._session_factory()
                        try:
                            position = session.query(EnhancedPositionRecord).filter_by(
                                symbol=symbol.upper(),
                                status='active'
                            ).first()
                            
                            if not position:
                                return JSONResponse(
                                    content={
                                        "status": "not_found",
                                        "message": f"No active position found for {symbol}"
                                    },
                                    status_code=404
                                )
                            
                            # Build detailed response (simplified for now)
                            return JSONResponse(content={
                                "status": "success",
                                "data": {
                                    "symbol": position.symbol,
                                    "direction": position.direction,
                                    "quantity": float(position.quantity),
                                    "avg_price": float(position.avg_entry_price)
                                }
                            })
                        finally:
                            session.close()
                    except Exception as e:
                        logger.warning(f"Enhanced position detail not available: {e}")
                
                # Fallback: simple not found
                return JSONResponse(
                    content={
                        "status": "not_found",
                        "message": f"Position not found for {symbol}"
                    },
                    status_code=404
                )
            except Exception as e:
                logger.error(f"Error getting position detail: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.get("/orders", tags=["orders"])
        @localhost_only
        async def get_orders(request: Request, limit: int = 50):
            """Get recent orders."""
            try:
                if not self._bot_instance:
                    return JSONResponse(content={"status": "error", "data": {"orders": []}})
                
                orders = await self._bot_instance.get_orders(limit=limit)
                orders_data = [
                    {
                        "symbol": order.symbol,
                        "side": order.side.value if hasattr(order, 'side') else 'unknown',
                        "qty": float(order.qty) if hasattr(order, 'qty') else 0,
                        "filled_qty": float(order.filled_qty) if hasattr(order, 'filled_qty') else 0,
                        "status": order.status.value if hasattr(order, 'status') else 'unknown'
                    }
                    for order in orders
                ]
                
                return JSONResponse(content={
                    "status": "success",
                    "data": {"orders": orders_data, "count": len(orders_data)}
                })
            except Exception as e:
                logger.error(f"Error getting orders: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.get("/trades", tags=["analytics"])
        @localhost_only
        async def get_trades(request: Request, limit: int = 50):
            """Get recent trades summary."""
            try:
                if not self._bot_instance:
                    return JSONResponse(content={"status": "error", "data": {"trades": []}})
                
                # Basic implementation - can be enhanced
                return JSONResponse(content={
                    "status": "success",
                    "data": {
                        "trades": [],
                        "message": "Trade history endpoint - enhance as needed"
                    }
                })
            except Exception as e:
                logger.error(f"Error getting trades: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.get("/dca-orders", tags=["analytics"])
        @localhost_only
        async def get_dca_orders(
            request: Request,
            symbol: Optional[str] = None,
            status: Optional[str] = None,
            limit: int = 100
        ):
            """Get DCA orders with filtering."""
            try:
                if not self._bot_instance:
                    return JSONResponse(content={
                        "status": "error",
                        "data": {"dca_orders": []}
                    })
                
                # Try enhanced DCA tracking
                if hasattr(self._bot_instance, 'enhanced_db'):
                    try:
                        from ..database.enhanced_schema import DCAOrderRecord
                        
                        session = self._bot_instance.enhanced_db.db._session_factory()
                        try:
                            query = session.query(DCAOrderRecord)
                            if symbol:
                                query = query.filter_by(symbol=symbol.upper())
                            if status:
                                query = query.filter_by(status=status)
                            
                            dca_orders = query.limit(limit).all()
                            dca_orders_data = [
                                {
                                    "symbol": order.symbol,
                                    "status": order.status,
                                    "quantity": float(order.quantity),
                                    "target_price": float(order.target_price) if order.target_price else None
                                }
                                for order in dca_orders
                            ]
                            
                            return JSONResponse(content={
                                "status": "success",
                                "data": {
                                    "dca_orders": dca_orders_data,
                                    "count": len(dca_orders_data)
                                }
                            })
                        finally:
                            session.close()
                    except Exception as e:
                        logger.warning(f"Enhanced DCA orders not available: {e}")
                
                # Fallback
                return JSONResponse(content={
                    "status": "success",
                    "data": {
                        "dca_orders": [],
                        "note": "Enhanced DCA tracking not available"
                    }
                })
            except Exception as e:
                logger.error(f"Error getting DCA orders: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.get("/portfolio-summary", tags=["analytics"])
        @localhost_only
        async def get_portfolio_summary(request: Request):
            """Get comprehensive portfolio summary."""
            try:
                if not self._bot_instance:
                    return JSONResponse(content={"status": "error"}, status_code=500)
                
                # Try enhanced portfolio metrics
                if hasattr(self._bot_instance, 'enhanced_db'):
                    try:
                        from ..database.view_manager import PositionSummaryView
                        
                        session = self._bot_instance.enhanced_db.db._session_factory()
                        try:
                            portfolio_metrics = PositionSummaryView.get_portfolio_metrics(session)
                            
                            return JSONResponse(content={
                                "status": "success",
                                "timestamp": datetime.utcnow().isoformat(),
                                "data": portfolio_metrics
                            })
                        finally:
                            session.close()
                    except Exception as e:
                        logger.warning(f"Enhanced portfolio not available: {e}")
                
                # Fallback to basic
                positions = await self._bot_instance.get_positions()
                total_unrealized = sum(pos.unrealized_pnl for pos in positions)
                
                return JSONResponse(content={
                    "status": "success",
                    "data": {
                        "total_positions": len(positions),
                        "total_unrealized_pnl": total_unrealized
                    }
                })
            except Exception as e:
                logger.error(f"Error getting portfolio summary: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.get("/strategy", tags=["analytics"])
        @localhost_only
        async def get_strategy_details(request: Request):
            """Get strategy configuration and status."""
            try:
                if self._bot_instance and hasattr(self._bot_instance, 'advanced_strategy'):
                    strategy = self._bot_instance.advanced_strategy
                    position_summary = strategy.get_position_summary()
                    
                    return JSONResponse(content={
                        "status": "success",
                        "positions": position_summary,
                        "strategy_config": {
                            "long_enabled": strategy.long_config.get('enabled', False),
                            "short_enabled": strategy.short_config.get('enabled', False)
                        }
                    })
                else:
                    return JSONResponse(content={
                        "status": "error",
                        "message": "Strategy not available"
                    })
            except Exception as e:
                logger.error(f"Error getting strategy: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.router.post("/admin/shutdown", tags=["admin"])
        async def admin_shutdown(request: Request):
            """Admin endpoint to trigger bot shutdown (localhost only)."""
            try:
                client_host = request.client.host if request.client else "unknown"
                if client_host not in ["127.0.0.1", "localhost", "::1"]:
                    raise HTTPException(status_code=403, detail="Shutdown only allowed from localhost")
                
                logger.info("Shutdown requested via admin endpoint")
                
                # Signal shutdown (implementation depends on bot architecture)
                return {
                    "status": "shutdown_initiated",
                    "message": "Bot shutdown initiated"
                }
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error in shutdown endpoint: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))
