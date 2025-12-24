"""
Base Admin Router with shared functionality.

Contains authentication, request/response models, and common utilities
used by all specialized admin routers.

Author: Trading Bot Team
Version: 2.1.0
"""

import os
import functools
import uuid
import time
from typing import Optional, Dict, Any, List, Callable, TypeVar, Awaitable, Literal
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, validator

from fastapi import Request, HTTPException, APIRouter, Header
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.logging_config import get_logger
from src.constants import HTTPStatus, AssetClassificationConstants
from src.auth import IAuthService, TokenClaims, create_auth_service
from src.exceptions import (
    TradingBotException,
    OrderExecutionException,
    RiskManagementException,
    ConfigurationException,
    ValidationException,
    PositionNotFoundException,
    BrokerException,
)


logger = get_logger(__name__)


# =============================================================================
# Request/Response Logging Middleware
# =============================================================================

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for structured request/response logging with correlation IDs.
    
    Provides:
    - Unique correlation ID for each request (X-Correlation-ID header)
    - Request method, path, and timing metrics
    - Response status code logging
    - Excludes sensitive endpoints from body logging
    
    Usage:
        app.add_middleware(RequestLoggingMiddleware)
    
    Example log output:
        [abc123] POST /api/v1/orders - 201 Created (145ms)
    """
    
    # Paths to exclude from detailed logging (health checks, static files)
    EXCLUDED_PATHS = {"/health", "/healthz", "/ready", "/metrics", "/favicon.ico"}
    
    # Paths with sensitive data (don't log bodies)
    SENSITIVE_PATHS = {"/auth", "/login", "/token"}
    
    async def dispatch(self, request: Request, call_next):
        """Process request with correlation ID and timing."""
        # Generate or extract correlation ID
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())[:8]
        
        # Skip detailed logging for excluded paths
        if request.url.path in self.EXCLUDED_PATHS:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        
        # Start timing
        start_time = time.perf_counter()
        
        # Log incoming request
        client_ip = request.client.host if request.client else "unknown"
        logger.info(
            f"[{correlation_id}] {request.method} {request.url.path} - "
            f"Client: {client_ip}"
        )
        
        # Process request
        try:
            response = await call_next(request)
        except Exception as e:
            # Log unhandled exceptions
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"[{correlation_id}] {request.method} {request.url.path} - "
                f"EXCEPTION ({duration_ms:.0f}ms): {type(e).__name__}: {str(e)}"
            )
            raise
        
        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # Log response
        log_level = "info" if response.status_code < 400 else "warning"
        getattr(logger, log_level)(
            f"[{correlation_id}] {request.method} {request.url.path} - "
            f"{response.status_code} ({duration_ms:.0f}ms)"
        )
        
        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = correlation_id
        
        return response


# =============================================================================
# Type Variables for Generic Decorators
# =============================================================================

T = TypeVar('T')


# =============================================================================
# Reusable Error Handling Decorator
# =============================================================================

def handle_route_errors(
    operation_name: str = "operation",
    log_level: str = "error",
    include_traceback: bool = False
) -> Callable:
    """
    Decorator for standardized error handling in FastAPI route handlers.
    
    Reduces boilerplate try/except blocks across routers by providing:
    - Consistent error logging with context
    - Standardized HTTP error responses
    - Specific exception handling for domain exceptions
    - Optional traceback inclusion for debugging
    
    Usage:
        @router.get("/positions")
        @handle_route_errors(operation_name="get_positions")
        async def get_positions():
            # Route logic without try/except needed
            return {"positions": [...]}
    
    Args:
        operation_name: Name of the operation for logging context
        log_level: Logging level for errors ('error', 'warning', 'critical')
        include_traceback: Whether to include traceback in error response
        
    Returns:
        Decorated async function with error handling
        
    Example:
        @handle_route_errors("fetch_account_balance")
        async def get_balance(account_id: str):
            balance = await broker.get_balance(account_id)
            return {"balance": balance}
    """
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                # Re-raise HTTP exceptions as-is (already formatted)
                raise
            
            # Domain-specific exceptions (from src/exceptions.py)
            except ValidationException as e:
                logger.warning(f"Validation error in {operation_name}: {e.message}")
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=e.message
                )
            except PositionNotFoundException as e:
                logger.warning(f"Position not found in {operation_name}: {e.message}")
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND,
                    detail=e.message
                )
            except RiskManagementException as e:
                logger.warning(f"Risk limit exceeded in {operation_name}: {e.message}")
                raise HTTPException(
                    status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    detail=f"Risk check failed: {e.message}"
                )
            except OrderExecutionException as e:
                logger.error(f"Order execution failed in {operation_name}: {e.message}")
                raise HTTPException(
                    status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    detail=f"Order execution failed: {e.message}"
                )
            except BrokerException as e:
                logger.error(f"Broker error in {operation_name}: {e.message}")
                raise HTTPException(
                    status_code=HTTPStatus.BAD_GATEWAY,
                    detail=f"Broker error: {e.message}"
                )
            except ConfigurationException as e:
                logger.error(f"Configuration error in {operation_name}: {e.message}")
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR,
                    detail=f"Configuration error: {e.message}"
                )
            except TradingBotException as e:
                # Catch-all for other domain exceptions
                logger.error(f"Trading bot error in {operation_name}: {e.message}")
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR,
                    detail=e.message
                )
            
            # Standard Python exceptions
            except ValueError as e:
                # Client-side validation errors -> 400
                logger.warning(f"Validation error in {operation_name}: {e}")
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=str(e)
                )
            except PermissionError as e:
                # Authorization errors -> 403
                logger.warning(f"Permission denied in {operation_name}: {e}")
                raise HTTPException(
                    status_code=HTTPStatus.FORBIDDEN,
                    detail=str(e)
                )
            except KeyError as e:
                # Missing resource -> 404
                logger.warning(f"Resource not found in {operation_name}: {e}")
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND,
                    detail=f"Resource not found: {e}"
                )
            except Exception as e:
                # All other errors -> 500 (last resort)
                log_method = getattr(logger, log_level, logger.error)
                log_method(f"Unexpected error in {operation_name}: {type(e).__name__}: {e}", exc_info=include_traceback)
                
                detail = f"Internal error during {operation_name}"
                if include_traceback:
                    import traceback
                    detail = f"{detail}: {str(e)}\n{traceback.format_exc()}"
                
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR,
                    detail=detail
                )
        return wrapper
    return decorator


# =============================================================================
# Standardized API Response Envelope
# =============================================================================

from typing import Generic


class ErrorDetail(BaseModel):
    """Structured error information."""
    
    code: str = Field(..., description="Error code for client handling")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error context")


class ApiResponse(BaseModel, Generic[T]):
    """
    Standardized API response envelope.
    
    All API endpoints should return responses wrapped in this envelope
    for consistent client-side handling.
    
    Success Response:
        {
            "success": true,
            "data": { ... },
            "correlation_id": "abc123",
            "timestamp": "2024-01-15T10:30:00Z"
        }
    
    Error Response:
        {
            "success": false,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid order quantity",
                "details": { "field": "quantity", "value": -1 }
            },
            "correlation_id": "abc123",
            "timestamp": "2024-01-15T10:30:00Z"
        }
    """
    
    success: bool = Field(..., description="Whether the request succeeded")
    data: Optional[Any] = Field(None, description="Response payload (on success)")
    error: Optional[ErrorDetail] = Field(None, description="Error details (on failure)")
    correlation_id: Optional[str] = Field(None, description="Request correlation ID for tracing")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Response timestamp (ISO 8601)"
    )
    
    @classmethod
    def success_response(
        cls, 
        data: Any, 
        correlation_id: Optional[str] = None
    ) -> "ApiResponse":
        """Create a successful response."""
        return cls(
            success=True,
            data=data,
            correlation_id=correlation_id
        )
    
    @classmethod
    def error_response(
        cls,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None
    ) -> "ApiResponse":
        """Create an error response."""
        return cls(
            success=False,
            error=ErrorDetail(code=code, message=message, details=details),
            correlation_id=correlation_id
        )


# =============================================================================
# Shared Request/Response Models (DTOs)
# =============================================================================

# Type aliases for order fields
OrderSideType = Literal["buy", "sell"]
OrderTypeValue = Literal["market", "limit"]
TimeInForceType = Literal["day", "gtc", "ioc"]
FundActionType = Literal["deposit", "withdraw", "allocate"]


class OrderRequest(BaseModel):
    """Request model for placing a new order."""
    
    symbol: str = Field(..., description="Trading symbol (e.g., AAPL)", min_length=1, max_length=10)
    side: OrderSideType = Field(..., description="Order side: 'buy' or 'sell'")
    quantity: float = Field(..., description="Number of shares", gt=0)
    order_type: OrderTypeValue = Field(default="market", description="Order type: 'market' or 'limit'")
    limit_price: Optional[float] = Field(None, description="Limit price (required for limit orders)", gt=0)
    time_in_force: TimeInForceType = Field(default="day", description="Time in force: 'day', 'gtc', 'ioc'")
    
    @validator('symbol')
    def uppercase_symbol(cls, v: str) -> str:
        """Ensure symbol is uppercase."""
        return v.upper().strip()
    
    @validator('limit_price')
    def validate_limit_price(cls, v: Optional[float], values: Dict) -> Optional[float]:
        """Validate limit price is provided for limit orders."""
        if values.get('order_type') == 'limit' and v is None:
            raise ValueError("Limit price is required for limit orders")
        return v


class OrderResponse(BaseModel):
    """Response model for order operations."""
    
    status: str
    order_id: Optional[str] = None
    message: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ClosePositionRequest(BaseModel):
    """Request model for closing a position."""
    
    quantity: Optional[float] = Field(None, description="Quantity to close (None = close all)", gt=0)
    order_type: str = Field(default="market", description="Order type for closing")
    limit_price: Optional[float] = Field(None, description="Limit price if using limit order", gt=0)


class BotStateResponse(BaseModel):
    """Response model for bot state."""
    
    state: str  # 'running', 'paused', 'stopped'
    uptime_seconds: Optional[float] = None
    positions_count: int = 0
    pending_orders: int = 0
    last_signal_time: Optional[str] = None
    message: Optional[str] = None


class FundAllocationRequest(BaseModel):
    """Request model for fund allocation."""
    
    action: FundActionType = Field(..., description="Action: 'deposit', 'withdraw', 'allocate'")
    amount: float = Field(..., description="Amount in USD", gt=0)
    symbol: Optional[str] = Field(None, description="Symbol for allocation (if action='allocate')")
    notes: Optional[str] = Field(None, description="Optional notes")


class BaseAdminRouter:
    """
    Base class for admin routers with shared authentication and utilities.
    
    Provides:
    - Azure AD authentication validation
    - Localhost access for development
    - Common error handling patterns
    
    All specialized routers should inherit from this class.
    """
    
    def __init__(
        self,
        auth_service: Optional[IAuthService] = None,
        prefix: str = "/admin",
        tags: List[str] = None
    ):
        """
        Initialize base admin router.
        
        Args:
            auth_service: Authentication service for token validation
            prefix: Router URL prefix
            tags: OpenAPI tags
        """
        self._auth_service = auth_service
        self.router = APIRouter(prefix=prefix, tags=tags or ["admin"])
    
    def set_auth_service(self, auth_service: IAuthService) -> None:
        """Set the authentication service."""
        self._auth_service = auth_service
        logger.info(f"Auth service set for {self.__class__.__name__}")
    
    async def validate_auth(
        self, 
        request: Request, 
        authorization: Optional[str] = None,
        required_role: Optional[str] = None
    ) -> Optional[TokenClaims]:
        """
        Validate request authentication using Azure AD.
        
        In production (Azure): Validates Azure AD JWT token with signature,
                              issuer, audience, and expiration checks.
        In development: Allows localhost access with mock claims.
        
        Args:
            request: FastAPI request object
            authorization: Authorization header value
            required_role: Optional role requirement (Admin, Trader, Viewer)
            
        Returns:
            TokenClaims if authenticated, raises HTTPException otherwise
        """
        client_host = request.client.host if request.client else "unknown"
        
        # Check if running in Azure (stricter validation)
        is_azure = os.environ.get("WEBSITE_SITE_NAME") or os.environ.get("CONTAINER_APP_NAME")
        
        # Allow localhost in development (non-Azure)
        if not is_azure and client_host in ["127.0.0.1", "localhost", "::1"]:
            logger.debug(f"Allowing localhost request from {client_host}")
            return TokenClaims(
                user_id="localhost-dev",
                tenant_id="localhost",
                email="dev@localhost",
                name="Local Developer",
                roles=["Admin", "Trader"]
            )
        
        # In production, require valid Azure AD token
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="Missing or invalid authorization header",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        token = authorization.replace("Bearer ", "").strip()
        if not token:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="Empty token",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Validate with auth service
        if not self._auth_service:
            logger.error("Auth service not configured for production")
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_ERROR,
                detail="Authentication service not configured"
            )
        
        # Validate token
        claims = await self._auth_service.validate_token(token)
        if not claims:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer error=\"invalid_token\""}
            )
        
        # Check role if required
        if required_role:
            has_role = await self._auth_service.is_authorized(token, required_role)
            if not has_role:
                raise HTTPException(
                    status_code=HTTPStatus.FORBIDDEN,
                    detail=f"Insufficient permissions. Required role: {required_role}"
                )
        
        logger.debug(f"Authenticated user: {claims.user_id} (roles: {claims.roles})")
        return claims
    
    def _infer_asset_class(self, symbol: str) -> str:
        """
        Infer asset class from trading symbol.
        
        Uses heuristics based on configurable symbol patterns from constants.
        
        Args:
            symbol: Trading symbol (e.g., 'AAPL', 'BTC/USD', 'EUR/USD')
            
        Returns:
            Asset class string: 'stock', 'crypto', 'forex', 'etf', 'commodity', 'index'
        """
        if not symbol:
            return "stock"
        
        symbol_upper = symbol.upper()
        
        # Crypto patterns (from constants)
        crypto_bases = AssetClassificationConstants.CRYPTO_BASES
        if "/" in symbol_upper and any(c in symbol_upper for c in crypto_bases):
            return "crypto"
        if symbol_upper.endswith("USD") and any(c in symbol_upper for c in crypto_bases):
            return "crypto"
        
        # Forex patterns (from constants)
        forex_currencies = AssetClassificationConstants.FOREX_CURRENCIES
        if "/" in symbol_upper:
            parts = symbol_upper.split("/")
            if len(parts) == 2 and (parts[0] in forex_currencies or parts[1] in forex_currencies):
                return "forex"
        
        # ETF patterns (from constants)
        etf_symbols = AssetClassificationConstants.ETF_SYMBOLS
        if symbol_upper in etf_symbols:
            return "etf"
        
        # Index patterns (from constants)
        index_patterns = AssetClassificationConstants.INDEX_PATTERNS
        if any(p in symbol_upper for p in index_patterns):
            return "index"
        
        # Commodity patterns (from constants)
        commodity_symbols = AssetClassificationConstants.COMMODITY_SYMBOLS
        if symbol_upper in commodity_symbols:
            return "commodity"
        
        # Default to stock
        return "stock"
