"""
DCA Preview Router.

Provides API endpoints for DCA order preview calculation.
This allows the frontend to get server-side previews that match
the backend execution logic exactly.

Author: Trading Bot Team
Version: 1.0.0
"""

from typing import Optional, List
from decimal import Decimal

from pydantic import BaseModel, Field
from fastapi import Request
from fastapi.responses import JSONResponse

from src.core.logging_config import get_logger
from src.constants import HTTPStatus
from src.signals.routers.base_router import BaseAdminRouter, handle_route_errors
from src.domain.dca_order_preview import (
    DCAOrderPreviewService,
    DCAOrderPreviewRequest,
    AssetClass,
    Strategy,
)


logger = get_logger(__name__)


# =============================================================================
# Request/Response Models
# =============================================================================

class DCAPreviewRequest(BaseModel):
    """
    Request model for DCA order preview calculation.
    
    Unit Convention:
    - Crypto/Forex LONG: amounts are in quote currency (USD/USDT)
    - Crypto/Forex SHORT: amounts are in base units (BTC, ETH, etc.)
    - Stocks/ETF LONG: amounts are in USD
    - Stocks/ETF SHORT: amounts are in shares (whole numbers)
    """
    
    symbol: str = Field(..., description="Trading symbol (e.g., 'AAPL', 'BTC/USD')")
    asset_class: str = Field(
        ..., 
        description="Asset class: crypto, forex, stock, etf, commodity, index"
    )
    strategy: str = Field(..., description="Strategy: long or short")
    current_price: float = Field(..., gt=0, description="Current market price")
    
    base_order_amount: float = Field(
        ..., 
        gt=0, 
        description="Base order amount (USD for long, units for short)"
    )
    averaging_orders_amount: float = Field(
        ..., 
        ge=0, 
        description="Total amount for all safety orders"
    )
    orders_count: int = Field(
        ..., 
        ge=1, 
        le=100, 
        description="Number of safety orders"
    )
    step_percent: float = Field(
        ..., 
        gt=0, 
        le=100, 
        description="Price step percentage between orders"
    )
    
    amount_multiplier: float = Field(
        default=1.0, 
        ge=1.0, 
        le=10.0,
        description="Multiplier for order sizing (geometric)"
    )
    amount_multiplier_enabled: bool = Field(
        default=False, 
        description="Whether to apply amount multiplier"
    )
    step_multiplier: float = Field(
        default=1.0, 
        ge=1.0, 
        le=10.0,
        description="Multiplier for step sizes (geometric)"
    )
    step_multiplier_enabled: bool = Field(
        default=False, 
        description="Whether to apply step multiplier"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "symbol": "AAPL",
                "asset_class": "stock",
                "strategy": "long",
                "current_price": 150.00,
                "base_order_amount": 500.00,
                "averaging_orders_amount": 2000.00,
                "orders_count": 5,
                "step_percent": 2.0,
                "amount_multiplier": 1.3,
                "amount_multiplier_enabled": True,
                "step_multiplier": 1.2,
                "step_multiplier_enabled": True,
            }
        }


class OrderPreviewRowResponse(BaseModel):
    """Single order in the preview ladder."""
    order_number: int
    order_label: str
    amount: float
    adjusted_amount: float
    units: float
    target_price: float
    price_deviation_pct: float
    cumulative_amount: float
    cumulative_units: float
    average_price: float
    is_invalid: bool
    was_adjusted: bool
    has_insufficient_shares: bool


class ValidationIssueResponse(BaseModel):
    """Validation issue detected in configuration."""
    code: str
    message: str
    severity: str
    affected_order: Optional[int] = None


class SuggestedFixResponse(BaseModel):
    """Suggested fix for invalid configuration."""
    orders_count: int
    step_percent: Optional[float] = None
    description: str


class TotalsResponse(BaseModel):
    """Totals summary for all orders."""
    total_investment: float
    total_units: float
    final_average_price: float
    max_deviation_pct: float


class ValidationResponse(BaseModel):
    """Validation result."""
    is_valid: bool
    issues: List[ValidationIssueResponse]
    suggested_fix: Optional[SuggestedFixResponse] = None


class DCAPreviewResponse(BaseModel):
    """
    Complete DCA order preview response.
    
    Contains the order ladder, totals, and validation results.
    """
    orders: List[OrderPreviewRowResponse]
    totals: TotalsResponse
    validation: ValidationResponse


# =============================================================================
# Router
# =============================================================================

class DCAPreviewRouter(BaseAdminRouter):
    """
    Router for DCA order preview endpoints.
    
    Provides server-side calculation of DCA order previews
    that match the backend execution logic exactly.
    """
    
    def __init__(self):
        """Initialize the DCA preview router."""
        super().__init__()
        self._preview_service = DCAOrderPreviewService()
        self._register_routes()
        logger.info("DCAPreviewRouter initialized")
    
    def _register_routes(self):
        """Register API routes."""
        
        @self.router.post(
            "/dca/preview",
            response_model=DCAPreviewResponse,
            summary="Calculate DCA Order Preview",
            description=(
                "Calculate a complete DCA order preview including target prices, "
                "order sizes, running average price, and configuration validation. "
                "This uses the same logic as the backend execution engine."
            ),
            tags=["DCA"],
        )
        @handle_route_errors
        async def calculate_preview(request: DCAPreviewRequest) -> DCAPreviewResponse:
            """
            Calculate DCA order preview.
            
            Returns a complete order ladder with:
            - Target prices for each order
            - Units/shares per order
            - Running average price after each fill
            - Total investment and units
            - Configuration validation with suggested fixes
            """
            logger.debug(
                f"Calculating DCA preview for {request.symbol} "
                f"({request.asset_class}/{request.strategy})"
            )
            
            # Validate asset class
            try:
                asset_class = AssetClass(request.asset_class.lower())
            except ValueError:
                raise ValueError(
                    f"Invalid asset_class: {request.asset_class}. "
                    f"Must be one of: {[e.value for e in AssetClass]}"
                )
            
            # Validate strategy
            try:
                strategy = Strategy(request.strategy.lower())
            except ValueError:
                raise ValueError(
                    f"Invalid strategy: {request.strategy}. "
                    "Must be 'long' or 'short'"
                )
            
            # Build domain request
            domain_request = DCAOrderPreviewRequest(
                symbol=request.symbol,
                asset_class=asset_class,
                strategy=strategy,
                current_price=Decimal(str(request.current_price)),
                base_order_amount=Decimal(str(request.base_order_amount)),
                averaging_orders_amount=Decimal(str(request.averaging_orders_amount)),
                orders_count=request.orders_count,
                step_percent=Decimal(str(request.step_percent)),
                amount_multiplier=Decimal(str(request.amount_multiplier)),
                amount_multiplier_enabled=request.amount_multiplier_enabled,
                step_multiplier=Decimal(str(request.step_multiplier)),
                step_multiplier_enabled=request.step_multiplier_enabled,
            )
            
            # Calculate preview
            result = self._preview_service.calculate(domain_request)
            
            # Convert to response model
            orders = [
                OrderPreviewRowResponse(
                    order_number=o.order_number,
                    order_label=o.order_label,
                    amount=float(o.amount),
                    adjusted_amount=float(o.adjusted_amount),
                    units=float(o.units),
                    target_price=float(o.target_price),
                    price_deviation_pct=float(o.price_deviation_pct),
                    cumulative_amount=float(o.cumulative_amount),
                    cumulative_units=float(o.cumulative_units),
                    average_price=float(o.average_price),
                    is_invalid=o.is_invalid,
                    was_adjusted=o.was_adjusted,
                    has_insufficient_shares=o.has_insufficient_shares,
                )
                for o in result.orders
            ]
            
            issues = [
                ValidationIssueResponse(
                    code=i.code,
                    message=i.message,
                    severity=i.severity,
                    affected_order=i.affected_order,
                )
                for i in result.issues
            ]
            
            suggested_fix = None
            if result.suggested_fix:
                suggested_fix = SuggestedFixResponse(
                    orders_count=result.suggested_fix.orders_count,
                    step_percent=(
                        float(result.suggested_fix.step_percent) 
                        if result.suggested_fix.step_percent 
                        else None
                    ),
                    description=result.suggested_fix.description,
                )
            
            return DCAPreviewResponse(
                orders=orders,
                totals=TotalsResponse(
                    total_investment=float(result.total_investment),
                    total_units=float(result.total_units),
                    final_average_price=float(result.final_average_price),
                    max_deviation_pct=float(result.max_deviation_pct),
                ),
                validation=ValidationResponse(
                    is_valid=result.is_valid,
                    issues=issues,
                    suggested_fix=suggested_fix,
                ),
            )


# =============================================================================
# Module-level router instance
# =============================================================================

# Create router instance for import
dca_preview_router = DCAPreviewRouter()
