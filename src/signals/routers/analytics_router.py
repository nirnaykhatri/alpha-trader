"""
Analytics Router.

Handles analytics and reporting operations:
- Performance metrics
- Trade history
- Statistics

Author: Trading Bot Team
Version: 2.0.0
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from pydantic import BaseModel, Field
from fastapi import Request, HTTPException, Header
from fastapi.responses import JSONResponse

from src.core.logging_config import get_logger
from src.constants import HTTPStatus
from src.signals.routers.base_router import BaseAdminRouter, handle_route_errors

# Analytics service import - may not exist in older installations
try:
    from src.services.analytics_service_interface import IAnalyticsService
except ImportError:
    IAnalyticsService = None  # type: ignore


logger = get_logger(__name__)


class AnalyticsRouter(BaseAdminRouter):
    """
    Router for analytics operations.
    
    Provides endpoints for:
    - GET /analytics/summary - Get trading summary
    - GET /analytics/performance - Get performance metrics
    - GET /analytics/trades - Get trade history
    - GET /analytics/pnl - Get P&L analysis
    """
    
    def __init__(
        self,
        analytics_service: Optional["IAnalyticsService"] = None,
        auth_service=None,
        bot_instance=None
    ):
        """
        Initialize analytics router.
        
        Args:
            analytics_service: Analytics service
            auth_service: Authentication service
            bot_instance: Legacy bot instance for backward compatibility
        """
        super().__init__(auth_service=auth_service, prefix="/admin", tags=["analytics"])
        
        self._analytics_service = analytics_service
        self._bot_instance = bot_instance
        
        self._setup_routes()
        logger.info("✅ AnalyticsRouter initialized")
    
    def set_analytics_service(self, analytics_service: "IAnalyticsService") -> None:
        """Set the analytics service."""
        self._analytics_service = analytics_service
        logger.info("Analytics service set for AnalyticsRouter")
    
    def set_bot_instance(self, bot_instance) -> None:
        """Set legacy bot instance for backward compatibility."""
        self._bot_instance = bot_instance
    
    async def _get_legacy_summary(self) -> Dict[str, Any]:
        """Get summary from legacy bot instance."""
        if not self._bot_instance:
            return {}
        
        return {
            "is_running": getattr(self._bot_instance, 'is_running', False),
            "positions": [],
            "pending_orders": [],
            "uptime": "0:00:00"
        }
    
    def _setup_routes(self) -> None:
        """Setup analytics routes."""
        
        @self.router.get("/analytics/summary")
        async def get_summary(
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Get trading summary."""
            await self.validate_auth(request, authorization)
            
            if self._analytics_service:
                try:
                    summary = await self._analytics_service.get_summary()
                    return JSONResponse(content={"summary": summary})
                except Exception as e:
                    logger.error(f"Analytics service error: {e}")
            
            # Fall back to legacy
            summary = await self._get_legacy_summary()
            return JSONResponse(content={"summary": summary})
        
        @self.router.get("/analytics/performance")
        @handle_route_errors(operation_name="get_performance")
        async def get_performance(
            request: Request,
            authorization: Optional[str] = Header(None),
            period: str = "7d",
            bot_id: Optional[str] = None
        ):
            """Get performance metrics."""
            await self.validate_auth(request, authorization)
            
            if not self._analytics_service:
                return JSONResponse(content={
                    "performance": {},
                    "message": "Analytics service not configured"
                })
            
            # Parse period to datetime range
            end_time = datetime.utcnow()
            period_map = {
                "1d": timedelta(days=1),
                "7d": timedelta(days=7),
                "30d": timedelta(days=30),
                "90d": timedelta(days=90),
                "1y": timedelta(days=365),
            }
            delta = period_map.get(period, timedelta(days=7))
            start_time = end_time - delta
            
            performance = await self._analytics_service.get_performance(
                start_time=start_time,
                end_time=end_time,
                bot_id=bot_id
            )
            return JSONResponse(content={"performance": performance})
        
        @self.router.get("/analytics/trades")
        @handle_route_errors(operation_name="get_trades")
        async def get_trades(
            request: Request,
            authorization: Optional[str] = Header(None),
            symbol: Optional[str] = None,
            bot_id: Optional[str] = None,
            limit: int = 100,
            offset: int = 0
        ):
            """Get trade history."""
            await self.validate_auth(request, authorization)
            
            if not self._analytics_service:
                return JSONResponse(content={
                    "trades": [],
                    "count": 0,
                    "message": "Analytics service not configured"
                })
            
            trades = await self._analytics_service.get_trade_history(
                symbol=symbol,
                bot_id=bot_id,
                limit=limit,
                offset=offset
            )
            return JSONResponse(content={
                "trades": [t.to_dict() for t in trades],
                "count": len(trades)
            })
        
        @self.router.get("/analytics/pnl")
        @handle_route_errors(operation_name="get_pnl")
        async def get_pnl(
            request: Request,
            authorization: Optional[str] = Header(None),
            period: str = "7d",
            bot_id: Optional[str] = None,
            symbol: Optional[str] = None
        ):
            """Get P&L analysis."""
            await self.validate_auth(request, authorization)
            
            if not self._analytics_service:
                return JSONResponse(content={
                    "pnl": {
                        "realized": 0,
                        "unrealized": 0,
                        "total": 0
                    },
                    "message": "Analytics service not configured"
                })
            
            # Parse period
            end_time = datetime.utcnow()
            period_map = {
                "1d": timedelta(days=1),
                "7d": timedelta(days=7),
                "30d": timedelta(days=30),
                "90d": timedelta(days=90),
            }
            delta = period_map.get(period, timedelta(days=7))
            start_time = end_time - delta
            
            pnl = await self._analytics_service.get_pnl(
                start_time=start_time,
                end_time=end_time,
                bot_id=bot_id,
                symbol=symbol
            )
            return JSONResponse(content={"pnl": pnl})
