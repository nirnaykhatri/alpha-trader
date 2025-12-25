"""
Monitoring endpoints for bot status, positions, orders, and analytics.
Provides comprehensive monitoring and analytics capabilities.

Includes health and readiness endpoints for Azure Container Apps:
- /health: Liveness probe - checks if app is running
- /ready: Readiness probe - checks if app can handle traffic
"""

from typing import Optional, Dict, Any
from datetime import datetime
from fastapi import Request, HTTPException, APIRouter
from fastapi.responses import JSONResponse

from src.core.logging_config import get_logger
from src.utils.decorators import localhost_only


logger = get_logger(__name__)


class MonitoringRouter:
    """
    Provides monitoring and analytics endpoints for the trading bot.
    
    Access Control Model:
        - Public endpoints (no auth): /health, /ready, / (root)
          These are required for Azure Container Apps health probes.
        - Protected endpoints (@localhost_only): /status, /positions, /orders, etc.
          Admin/analytics endpoints are restricted to localhost for security.
          If remote dashboard access is needed, implement proper authentication
          and remove localhost-only restriction for authenticated requests.
    
    Container Apps Health Probes:
        - /health: Liveness probe - returns 200 if app is running
        - /ready: Readiness probe - returns 200 if all dependencies ready
    """
    
    def __init__(self, bot_instance=None):
        """
        Initialize monitoring router.
        
        Args:
            bot_instance: Reference to the trading bot instance
        """
        self._bot_instance = bot_instance
        self._dependency_checks: Dict[str, Any] = {}
        
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
    
    def register_dependency_check(self, name: str, check_func) -> None:
        """
        Register a dependency health check function for readiness probe.
        
        Args:
            name: Name of the dependency (e.g., 'database', 'key_vault')
            check_func: Async function that returns dict with 'healthy' bool
        """
        self._dependency_checks[name] = check_func
        logger.info(f"Registered dependency check: {name}")
    
    async def _check_all_dependencies(self) -> Dict[str, Any]:
        """
        Check all registered dependencies for readiness probe.
        
        Returns:
            Dict with overall status and individual dependency results
        """
        results = {}
        all_healthy = True
        
        for name, check_func in self._dependency_checks.items():
            try:
                result = await check_func()
                results[name] = result
                if not result.get('healthy', False):
                    all_healthy = False
            except Exception as e:
                logger.error(f"Dependency check failed for {name}: {str(e)}")
                results[name] = {'healthy': False, 'error': str(e)}
                all_healthy = False
        
        return {
            'all_healthy': all_healthy,
            'dependencies': results
        }
    
    def _setup_routes(self) -> None:
        """Setup all monitoring routes."""
        
        @self.router.get("/health", tags=["health"])
        async def health_check():
            """
            Liveness probe endpoint for Container Apps.
            
            Returns 200 if the application is running.
            This is a lightweight check - does not verify dependencies.
            
            Returns:
                Health status with timestamp and version
            """
            return {
                "status": "healthy", 
                "timestamp": datetime.utcnow().isoformat(),
                "version": "1.0.0"
            }
        
        @self.router.get("/ready", tags=["health"])
        async def readiness_check():
            """
            Readiness probe endpoint for Container Apps.
            
            Checks all registered dependencies (database, key vault, etc.)
            and returns 200 only if ALL dependencies are healthy.
            
            Container Apps will not route traffic until this returns 200.
            
            Returns:
                200 with status if ready, 503 if not ready
            """
            try:
                # Check all registered dependencies
                result = await self._check_all_dependencies()
                
                response_data = {
                    "status": "ready" if result['all_healthy'] else "not_ready",
                    "timestamp": datetime.utcnow().isoformat(),
                    "version": "1.0.0",
                    "dependencies": result['dependencies']
                }
                
                if result['all_healthy']:
                    return JSONResponse(
                        content=response_data,
                        status_code=200
                    )
                else:
                    return JSONResponse(
                        content=response_data,
                        status_code=503
                    )
            except Exception as e:
                logger.error(f"Readiness check failed: {str(e)}")
                return JSONResponse(
                    content={
                        "status": "not_ready",
                        "error": str(e),
                        "timestamp": datetime.utcnow().isoformat()
                    },
                    status_code=503
                )
        
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
                
                # Get positions from bot instance
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
                
                # Get position detail from bot instance (Cosmos DB)
                # TODO: Implement Cosmos-based position detail lookup
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
                
                # DCA orders from Cosmos DB
                # TODO: Implement Cosmos-based DCA order retrieval
                return JSONResponse(content={
                    "status": "success",
                    "data": {
                        "dca_orders": [],
                        "note": "DCA order tracking via Cosmos DB - implementation pending"
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
                
                # Get portfolio summary from bot positions
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
