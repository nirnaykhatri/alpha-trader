"""
Domain Error Standardization

Provides uniform error handling across all layers with typed error codes
and structured context for debugging and observability.

Automatically emits Prometheus metrics for error tracking.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

# Import metrics if available (optional dependency)
try:
    from prometheus_client import Counter
    
    domain_error_total = Counter(
        'trading_bot_domain_error_total',
        'Total domain errors raised',
        ['error_code', 'component']
    )
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False


class DomainErrorEmitter:
    """
    Service responsible for emitting metrics when domain errors occur.
    
    Separates metric emission from error construction (SRP compliance).
    """
    
    @staticmethod
    def emit(code: 'ErrorCode', component: str = 'unknown') -> None:
        """Emit error metric if metrics available."""
        if METRICS_AVAILABLE:
            domain_error_total.labels(
                error_code=code.value,
                component=component
            ).inc()


class ErrorCode(Enum):
    """Standardized domain error codes."""
    
    # Configuration errors (1xxx)
    CONFIG_INVALID = "CONFIG_INVALID"
    CONFIG_MISSING = "CONFIG_MISSING"
    CONFIG_PLACEHOLDER = "CONFIG_PLACEHOLDER"
    
    # Market data errors (2xxx)
    MARKET_DATA_UNAVAILABLE = "MARKET_DATA_UNAVAILABLE"
    MARKET_DATA_STALE = "MARKET_DATA_STALE"
    MARKET_DATA_CONSENSUS_FAILED = "MARKET_DATA_CONSENSUS_FAILED"
    PRICE_INVALID = "PRICE_INVALID"
    
    # Order errors (3xxx)
    ORDER_PLACEMENT_FAILED = "ORDER_PLACEMENT_FAILED"
    ORDER_INSUFFICIENT_FUNDS = "ORDER_INSUFFICIENT_FUNDS"
    ORDER_INVALID_QUANTITY = "ORDER_INVALID_QUANTITY"
    ORDER_BROKER_REJECTED = "ORDER_BROKER_REJECTED"
    
    # Position errors (4xxx)
    POSITION_NOT_FOUND = "POSITION_NOT_FOUND"
    POSITION_CLOSED = "POSITION_CLOSED"
    POSITION_LIFECYCLE_INVALID = "POSITION_LIFECYCLE_INVALID"
    
    # Risk errors (5xxx)
    RISK_LIMIT_EXCEEDED = "RISK_LIMIT_EXCEEDED"
    MARTINGALE_SAFETY_BLOCK = "MARTINGALE_SAFETY_BLOCK"
    CONSECUTIVE_LOSS_LIMIT = "CONSECUTIVE_LOSS_LIMIT"
    SYMBOL_LOSS_LIMIT = "SYMBOL_LOSS_LIMIT"
    INDIVIDUAL_LOSS_LIMIT = "INDIVIDUAL_LOSS_LIMIT"
    VOLATILITY_TOO_HIGH = "VOLATILITY_TOO_HIGH"
    POSITION_SIZE_LIMIT = "POSITION_SIZE_LIMIT"
    
    # DCA errors (6xxx)
    DCA_MAX_ATTEMPTS_REACHED = "DCA_MAX_ATTEMPTS_REACHED"
    DCA_NON_PROGRESSIVE = "DCA_NON_PROGRESSIVE"
    DCA_NO_SUPPORT_DATA = "DCA_NO_SUPPORT_DATA"
    DCA_NO_RESISTANCE_DATA = "DCA_NO_RESISTANCE_DATA"
    DCA_SAFETY_CHECK_FAILED = "DCA_SAFETY_CHECK_FAILED"
    
    # Strategy errors (7xxx)
    STRATEGY_DISABLED = "STRATEGY_DISABLED"
    SIGNAL_INVALID = "SIGNAL_INVALID"
    CONFIDENCE_TOO_LOW = "CONFIDENCE_TOO_LOW"
    
    # System errors (8xxx)
    SYSTEM_CONGESTED = "SYSTEM_CONGESTED"
    DATABASE_ERROR = "DATABASE_ERROR"
    EXTERNAL_API_ERROR = "EXTERNAL_API_ERROR"
    
    # Validation errors (9xxx)
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PARAMETER_INVALID = "PARAMETER_INVALID"


@dataclass
class DomainError(Exception):
    """
    Standardized domain error with typed code and structured context.
    
    Provides consistent error handling across all layers with:
    - Machine-readable error codes
    - Human-readable detail messages
    - Structured context for debugging
    - Optional parent exception for error chaining
    
    Example:
        raise DomainError(
            code=ErrorCode.MARTINGALE_SAFETY_BLOCK,
            detail="Consecutive loss limit exceeded: 5 >= 5",
            context={
                'symbol': 'AAPL',
                'attempts': 5,
                'max_attempts': 5
            }
        )
    """
    
    code: ErrorCode
    detail: str
    context: Dict[str, Any] = field(default_factory=dict)
    cause: Optional[Exception] = None
    
    def __post_init__(self):
        """Automatically emit error metric on creation."""
        component = self.context.get('component', 'unknown')
        DomainErrorEmitter.emit(self.code, component)
    
    def __str__(self) -> str:
        """Format error for logging."""
        parts = [f"[{self.code.value}] {self.detail}"]
        
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            parts.append(f"Context: {context_str}")
        
        if self.cause:
            parts.append(f"Caused by: {str(self.cause)}")
        
        return " | ".join(parts)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'code': self.code.value,
            'detail': self.detail,
            'context': self.context,
            'cause': str(self.cause) if self.cause else None
        }


# Convenience constructors for common error types

def config_error(detail: str, **context) -> DomainError:
    """Create configuration error."""
    return DomainError(
        code=ErrorCode.CONFIG_INVALID,
        detail=detail,
        context=context
    )


def market_data_error(detail: str, **context) -> DomainError:
    """Create market data error."""
    return DomainError(
        code=ErrorCode.MARKET_DATA_UNAVAILABLE,
        detail=detail,
        context=context
    )


def order_error(detail: str, code: ErrorCode = ErrorCode.ORDER_PLACEMENT_FAILED, **context) -> DomainError:
    """Create order error."""
    return DomainError(
        code=code,
        detail=detail,
        context=context
    )


def risk_error(detail: str, code: ErrorCode = ErrorCode.RISK_LIMIT_EXCEEDED, **context) -> DomainError:
    """Create risk management error."""
    return DomainError(
        code=code,
        detail=detail,
        context=context
    )


def dca_error(detail: str, code: ErrorCode = ErrorCode.DCA_SAFETY_CHECK_FAILED, **context) -> DomainError:
    """Create DCA error."""
    return DomainError(
        code=code,
        detail=detail,
        context=context
    )
