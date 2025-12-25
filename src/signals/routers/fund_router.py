"""
Fund Management Router.

Handles fund allocation operations:
- Allocate funds to strategies
- Get current allocations
- Rebalance allocations

Author: Trading Bot Team
Version: 2.0.0
"""

from typing import Optional, List, Dict, Any
from decimal import Decimal

from pydantic import BaseModel, Field, validator
from fastapi import Request, HTTPException, Header
from fastapi.responses import JSONResponse

from src.core.logging_config import get_logger
from src.constants import HTTPStatus
from src.signals.routers.base_router import BaseAdminRouter, handle_route_errors

# Fund service import - may not exist in older installations
try:
    from src.services.fund_service_interface import IFundService
    _FUND_SERVICE_AVAILABLE = True
except ImportError:
    IFundService = None  # type: ignore
    _FUND_SERVICE_AVAILABLE = False


logger = get_logger(__name__)

# Log import warnings after logger is initialized
if not _FUND_SERVICE_AVAILABLE:
    logger.warning("IFundService interface not found - fund management features may be limited")


# =============================================================================
# Fund Management Request/Response Models
# =============================================================================

class FundAllocationRequest(BaseModel):
    """Request model for fund allocation."""
    strategy_id: str = Field(..., min_length=1, max_length=100)
    amount: float = Field(..., gt=0)
    allocation_type: str = Field(default="fixed", pattern="^(fixed|percentage)$")
    
    @validator('strategy_id')
    def validate_strategy_id(cls, v: str) -> str:
        return v.strip()


class BulkFundAllocationRequest(BaseModel):
    """Request model for bulk fund allocation."""
    allocations: List[FundAllocationRequest] = Field(..., min_items=1)
    
    @validator('allocations')
    def validate_total_percentage(cls, v: List[FundAllocationRequest]) -> List[FundAllocationRequest]:
        percentage_allocations = [a for a in v if a.allocation_type == "percentage"]
        if percentage_allocations:
            total = sum(a.amount for a in percentage_allocations)
            if total > 100:
                raise ValueError(f"Total percentage allocations exceed 100%: {total}%")
        return v


class RebalanceRequest(BaseModel):
    """Request model for fund rebalancing."""
    target_allocations: Dict[str, float] = Field(...)
    threshold_percent: float = Field(default=5.0, ge=0, le=50)
    
    @validator('target_allocations')
    def validate_allocations(cls, v: Dict[str, float]) -> Dict[str, float]:
        total = sum(v.values())
        if not (99 <= total <= 101):  # Allow for rounding
            raise ValueError(f"Target allocations must sum to 100%, got {total}%")
        return v


class FundRouter(BaseAdminRouter):
    """
    Router for fund management operations.
    
    Provides endpoints for:
    - GET /funds/balance - Get account balance
    - GET /funds/allocations - Get current allocations
    - POST /funds/allocate - Allocate funds
    - POST /funds/allocate/bulk - Bulk allocation
    - POST /funds/rebalance - Rebalance allocations
    - GET /funds/history - Get allocation history
    """
    
    def __init__(
        self,
        fund_service: Optional["IFundService"] = None,
        auth_service=None,
        bot_instance=None
    ):
        """
        Initialize fund management router.
        
        Args:
            fund_service: Fund management service
            auth_service: Authentication service
            bot_instance: Legacy bot instance for backward compatibility
        """
        super().__init__(auth_service=auth_service, prefix="/admin", tags=["funds"])
        
        self._fund_service = fund_service
        self._bot_instance = bot_instance
        
        self._setup_routes()
        logger.info("✅ FundRouter initialized")
    
    def set_fund_service(self, fund_service: "IFundService") -> None:
        """Set the fund service."""
        self._fund_service = fund_service
        logger.info("Fund service set for FundRouter")
    
    def set_bot_instance(self, bot_instance) -> None:
        """Set legacy bot instance for backward compatibility."""
        self._bot_instance = bot_instance
    
    async def _get_legacy_balance(self) -> Dict[str, Any]:
        """Get balance from legacy bot instance."""
        if not self._bot_instance:
            return {"cash": 0, "buying_power": 0}
        
        trading_client = getattr(self._bot_instance, 'trading_client', None)
        if not trading_client:
            return {"cash": 0, "buying_power": 0}
        
        try:
            account = await trading_client.get_account()
            return {
                "cash": float(getattr(account, 'cash', 0)),
                "buying_power": float(getattr(account, 'buying_power', 0)),
                "portfolio_value": float(getattr(account, 'portfolio_value', 0)),
                "equity": float(getattr(account, 'equity', 0))
            }
        except Exception as e:
            logger.error(f"Failed to get account balance: {e}")
            return {"cash": 0, "buying_power": 0, "error": str(e)}
    
    def _setup_routes(self) -> None:
        """Setup fund management routes."""
        
        @self.router.get("/funds/balance")
        async def get_balance(
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Get current account balance."""
            await self.validate_auth(request, authorization)
            
            if self._fund_service:
                try:
                    balance = await self._fund_service.get_balance()
                    return JSONResponse(content={"balance": balance})
                except Exception as e:
                    logger.error(f"Fund service error: {e}")
            
            # Fall back to legacy
            balance = await self._get_legacy_balance()
            return JSONResponse(content={"balance": balance})
        
        @self.router.get("/funds/allocations")
        @handle_route_errors(operation_name="get_allocations")
        async def get_allocations(
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Get current fund allocations."""
            await self.validate_auth(request, authorization)
            
            if not self._fund_service:
                return JSONResponse(content={
                    "allocations": [],
                    "message": "Fund service not configured"
                })
            
            allocations = await self._fund_service.get_allocations()
            return JSONResponse(content={
                "allocations": [a.to_dict() for a in allocations]
            })
        
        @self.router.post("/funds/allocate")
        @handle_route_errors(operation_name="allocate_funds")
        async def allocate_funds(
            allocation_request: FundAllocationRequest,
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Allocate funds to a strategy."""
            claims = await self.validate_auth(request, authorization)
            user_id = claims.user_id if claims else "anonymous"
            
            if not self._fund_service:
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR,
                    detail="Fund service not configured"
                )
            
            allocation = await self._fund_service.allocate(
                strategy_id=allocation_request.strategy_id,
                amount=Decimal(str(allocation_request.amount)),
                allocation_type=allocation_request.allocation_type,
                user_id=user_id
            )
            
            logger.info(
                f"Funds allocated: {allocation_request.amount} "
                f"to {allocation_request.strategy_id} by {user_id}"
            )
            
            return JSONResponse(content={
                "status": "allocated",
                "allocation": allocation.to_dict()
            })
        
        @self.router.post("/funds/allocate/bulk")
        @handle_route_errors(operation_name="bulk_allocate_funds")
        async def bulk_allocate_funds(
            bulk_request: BulkFundAllocationRequest,
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Bulk allocate funds to multiple strategies."""
            claims = await self.validate_auth(request, authorization)
            user_id = claims.user_id if claims else "anonymous"
            
            if not self._fund_service:
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR,
                    detail="Fund service not configured"
                )
            
            results = []
            for alloc_req in bulk_request.allocations:
                allocation = await self._fund_service.allocate(
                    strategy_id=alloc_req.strategy_id,
                    amount=Decimal(str(alloc_req.amount)),
                    allocation_type=alloc_req.allocation_type,
                    user_id=user_id
                )
                results.append(allocation.to_dict())
            
            logger.info(f"Bulk fund allocation: {len(results)} strategies by {user_id}")
            
            return JSONResponse(content={
                "status": "allocated",
                "allocations": results
            })
        
        @self.router.post("/funds/rebalance")
        @handle_route_errors(operation_name="rebalance_funds")
        async def rebalance_funds(
            rebalance_request: RebalanceRequest,
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Rebalance fund allocations to target percentages."""
            claims = await self.validate_auth(request, authorization)
            user_id = claims.user_id if claims else "anonymous"
            
            if not self._fund_service:
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR,
                    detail="Fund service not configured"
                )
            
            rebalance_result = await self._fund_service.rebalance(
                target_allocations=rebalance_request.target_allocations,
                threshold_percent=Decimal(str(rebalance_request.threshold_percent)),
                user_id=user_id
            )
            
            logger.info(f"Funds rebalanced by {user_id}")
            
            return JSONResponse(content={
                "status": "rebalanced",
                "result": rebalance_result
            })
        
        @self.router.get("/funds/history")
        @handle_route_errors(operation_name="get_allocation_history")
        async def get_allocation_history(
            request: Request,
            authorization: Optional[str] = Header(None),
            strategy_id: Optional[str] = None,
            limit: int = 50
        ):
            """Get fund allocation history."""
            await self.validate_auth(request, authorization)
            
            if not self._fund_service:
                return JSONResponse(content={
                    "history": [],
                    "message": "Fund service not configured"
                })
            
            history = await self._fund_service.get_allocation_history(
                strategy_id=strategy_id,
                limit=limit
            )
            return JSONResponse(content={
                "history": [h.to_dict() for h in history]
            })
