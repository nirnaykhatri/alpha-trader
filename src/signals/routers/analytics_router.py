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
    _ANALYTICS_SERVICE_AVAILABLE = True
except ImportError:
    IAnalyticsService = None  # type: ignore
    _ANALYTICS_SERVICE_AVAILABLE = False


logger = get_logger(__name__)

# Log import warnings after logger is initialized
if not _ANALYTICS_SERVICE_AVAILABLE:
    logger.warning("IAnalyticsService interface not found - analytics features may be limited")


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
        
        @self.router.get("/portfolio")
        @handle_route_errors(operation_name="get_portfolio")
        async def get_portfolio(
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """
            Get comprehensive portfolio data including positions, allocations, and summary.
            
            Fetches positions directly from the connected broker (e.g., Alpaca) rather than
            the bot's internal position manager. This shows ALL positions in the broker account,
            not just those managed by the DCA strategy.
            
            Returns data matching the frontend PortfolioData interface:
            - positions: List of asset positions with full details
            - allocations: Asset allocations by category
            - summary: Portfolio value, P&L, and buying power
            """
            await self.validate_auth(request, authorization)
            
            positions_data = []
            total_value = 0.0
            total_unrealized_pnl = 0.0
            total_cost = 0.0
            buying_power = 0.0
            equity = 0.0
            
            if self._bot_instance:
                try:
                    # Fetch positions directly from broker subsystem's account providers
                    # This gets ALL positions from the broker (e.g., Alpaca), not just bot-managed ones
                    broker_subsystem = getattr(self._bot_instance, 'broker_subsystem', None)
                    
                    if broker_subsystem and hasattr(broker_subsystem, 'account_providers'):
                        # Get positions from all connected brokers
                        for broker_type, account_provider in broker_subsystem.account_providers.items():
                            if hasattr(account_provider, 'get_positions'):
                                broker_positions = await account_provider.get_positions()
                                logger.info(f"📊 Fetched {len(broker_positions)} positions from {broker_type.value}")
                                
                                for p in broker_positions:
                                    qty = float(p.quantity)
                                    avg_price = float(p.avg_price)
                                    current_price = float(p.current_price) if hasattr(p, 'current_price') else avg_price
                                    market_value = abs(qty) * current_price
                                    cost_basis = abs(qty) * avg_price
                                    unrealized_pnl = float(p.unrealized_pnl) if hasattr(p, 'unrealized_pnl') else 0.0
                                    pnl_percent = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0.0
                                    
                                    positions_data.append({
                                        "symbol": p.symbol,
                                        "quantity": abs(qty),  # Always absolute, use side for direction
                                        "avgPrice": avg_price,
                                        "currentPrice": current_price,
                                        "marketValue": market_value,
                                        "costBasis": cost_basis,
                                        "unrealizedPnL": unrealized_pnl,
                                        "unrealizedPnLPercent": pnl_percent,
                                        "dayPnL": 0.0,  # Would need historical data
                                        "dayPnLPercent": 0.0,
                                        "side": "long" if qty > 0 else "short",
                                        "assetClass": "stock",  # Default, could be enhanced
                                        "broker": broker_type.value if hasattr(broker_type, 'value') else str(broker_type),
                                    })
                                    
                                    total_value += market_value
                                    total_unrealized_pnl += unrealized_pnl
                                    total_cost += cost_basis
                    
                        # Get account info for buying power and equity from primary account provider
                        if broker_subsystem.primary_account_provider:
                            try:
                                buying_power = await broker_subsystem.primary_account_provider.get_buying_power()
                                equity = await broker_subsystem.primary_account_provider.get_account_value()
                                logger.info(f"📊 Account: equity=${equity:,.2f}, buying_power=${buying_power:,.2f}")
                            except Exception as e:
                                logger.warning(f"Could not fetch account info: {e}")
                        
                except Exception as e:
                    logger.error(f"Error fetching portfolio from broker: {e}")
            
            # Calculate allocations by asset class (simple grouping)
            allocations = []
            if positions_data:
                # Group by asset class
                by_class: Dict[str, float] = {}
                for pos in positions_data:
                    asset_class = pos.get("assetClass", "stock")
                    by_class[asset_class] = by_class.get(asset_class, 0) + pos["marketValue"]
                
                for asset_class, value in by_class.items():
                    allocations.append({
                        "assetClass": asset_class,
                        "value": value,
                        "percentage": (value / total_value * 100) if total_value > 0 else 0
                    })
            
            # Calculate summary
            total_pnl_percent = (total_unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0
            
            return JSONResponse(content={
                "status": "success",
                "data": {
                    "positions": positions_data,
                    "allocations": allocations,
                    "summary": {
                        "totalValue": total_value or equity,
                        "totalPnL": total_unrealized_pnl,
                        "totalPnLPercent": total_pnl_percent,
                        "dayPnL": 0.0,  # Would need historical data
                        "dayPnLPercent": 0.0,
                        "buyingPower": buying_power
                    }
                }
            })
