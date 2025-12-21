"""
Risk Decision Types and Enums

Typed risk decision objects replacing hard-coded strings.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional


class RiskDecisionStatus(Enum):
    """Risk validation decision status."""
    SAFE = "safe"
    CONSECUTIVE_LOSS_LIMIT = "consecutive_loss_limit_exceeded"
    SYMBOL_LOSS_LIMIT = "symbol_loss_limit_exceeded"
    INDIVIDUAL_LOSS_LIMIT = "individual_loss_limit_exceeded"
    EMERGENCY_STOP = "emergency_stop_triggered"
    DAILY_LOSS_LIMIT = "daily_loss_limit_exceeded"
    WEEKLY_LOSS_LIMIT = "weekly_loss_limit_exceeded"
    INSUFFICIENT_MARGIN = "insufficient_margin"
    POSITION_SIZE_LIMIT = "position_size_limit_exceeded"
    VOLATILITY_TOO_HIGH = "volatility_exceeds_threshold"
    CORRELATION_STOP = "cross_symbol_correlation_stop"
    SYMBOL_CONCENTRATION_EXCEEDED = "symbol_concentration_exceeded"
    CORRELATED_EXPOSURE_EXCEEDED = "correlated_exposure_exceeded"


@dataclass(frozen=True)
class RiskDecision:
    """
    Immutable risk decision result.
    
    Attributes:
        status: Decision status enum
        safe: Whether operation is safe to proceed
        reason: Human-readable explanation
        details: Additional context and metrics
        recommended_size: Recommended position size (if applicable)
    """
    status: RiskDecisionStatus
    safe: bool
    reason: str
    details: Dict[str, Any]
    recommended_size: Optional[float] = None
    
    @classmethod
    def allow(cls, reason: str = "All risk checks passed", details: Dict[str, Any] = None) -> 'RiskDecision':
        """Create a SAFE decision."""
        return cls(
            status=RiskDecisionStatus.SAFE,
            safe=True,
            reason=reason,
            details=details or {}
        )
    
    @classmethod
    def deny(cls, status: RiskDecisionStatus, reason: str, details: Dict[str, Any] = None) -> 'RiskDecision':
        """Create a denial decision."""
        return cls(
            status=status,
            safe=False,
            reason=reason,
            details=details or {}
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            'status': self.status.value,
            'safe': self.safe,
            'reason': self.reason,
            'details': self.details,
            'recommended_size': self.recommended_size
        }


@dataclass(frozen=True)
class RiskEnvelope:
    """
    Composite risk assessment envelope.
    
    Consolidates multiple risk validators into single decision.
    
    Attributes:
        max_position_size: Maximum allowed position size
        dynamic_ceiling: Dynamically adjusted size ceiling
        reason_codes: List of risk decision statuses
        safe: Overall safety decision
        primary_constraint: Most restrictive constraint
        details: Aggregated details from all validators
    """
    max_position_size: float
    dynamic_ceiling: float
    reason_codes: tuple[RiskDecisionStatus, ...]
    safe: bool
    primary_constraint: RiskDecisionStatus
    details: Dict[str, Any]
    
    @property
    def effective_limit(self) -> float:
        """Get the most restrictive size limit."""
        return min(self.max_position_size, self.dynamic_ceiling)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            'max_position_size': self.max_position_size,
            'dynamic_ceiling': self.dynamic_ceiling,
            'effective_limit': self.effective_limit,
            'safe': self.safe,
            'primary_constraint': self.primary_constraint.value,
            'reason_codes': [status.value for status in self.reason_codes],
            'details': self.details
        }
