"""
Endpoint Policy Dataclass

Consolidates endpoint decorator arguments into a validated configuration object.
Prevents parameter drift and provides structured policy definition.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class EndpointPolicy:
    """
    Consolidated endpoint policy configuration.
    
    Replaces scattered decorator arguments with a single validated object.
    
    Example:
        policy = EndpointPolicy(
            localhost_only=True,
            rate_limit_per_minute=60,
            require_auth=False,
            log_requests=True,
            circuit_breaker_threshold=5
        )
        
        @apply_endpoint_policy(policy)
        async def admin_endpoint():
            # ... endpoint logic
    """
    
    # Access control
    localhost_only: bool = False
    require_auth: bool = False
    allowed_ips: List[str] = field(default_factory=list)
    
    # Rate limiting
    rate_limit_per_minute: Optional[int] = None
    rate_limit_per_hour: Optional[int] = None
    
    # Circuit breaker
    circuit_breaker_enabled: bool = False
    circuit_breaker_threshold: int = 5  # failures before opening
    circuit_breaker_timeout: int = 60  # seconds before retry
    
    # Retry logic
    retry_enabled: bool = False
    max_retries: int = 3
    retry_backoff_base: float = 1.0  # seconds
    retry_jitter: bool = True
    
    # Logging & monitoring
    log_requests: bool = True
    log_responses: bool = False
    emit_metrics: bool = True
    
    # Timeouts
    request_timeout: Optional[float] = None  # seconds
    
    def __post_init__(self):
        """Validate policy configuration."""
        if self.circuit_breaker_enabled and self.circuit_breaker_threshold < 1:
            raise ValueError("circuit_breaker_threshold must be >= 1")
        
        if self.retry_enabled and self.max_retries < 1:
            raise ValueError("max_retries must be >= 1")
        
        if self.rate_limit_per_minute and self.rate_limit_per_minute < 1:
            raise ValueError("rate_limit_per_minute must be >= 1")
        
        if self.retry_backoff_base <= 0:
            raise ValueError("retry_backoff_base must be > 0")


# Predefined policies for common scenarios

ADMIN_POLICY = EndpointPolicy(
    localhost_only=True,
    log_requests=True,
    emit_metrics=True
)

PUBLIC_API_POLICY = EndpointPolicy(
    localhost_only=False,
    rate_limit_per_minute=100,
    rate_limit_per_hour=5000,
    circuit_breaker_enabled=True,
    log_requests=True,
    emit_metrics=True
)

WEBHOOK_POLICY = EndpointPolicy(
    localhost_only=False,
    require_auth=True,
    rate_limit_per_minute=300,
    log_requests=True,
    emit_metrics=True,
    request_timeout=5.0
)

INTERNAL_API_POLICY = EndpointPolicy(
    localhost_only=False,
    retry_enabled=True,
    max_retries=3,
    retry_jitter=True,
    circuit_breaker_enabled=True,
    log_requests=True,
    emit_metrics=True
)
