"""
Provider Circuit Breaker

Implements circuit breaker pattern for market data providers to prevent
cascading failures and improve system resilience.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker state."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failures exceeded threshold, provider disabled
    HALF_OPEN = "half_open"  # Testing if provider has recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5        # Consecutive failures before opening
    reset_timeout: int = 60          # Seconds before attempting reset
    half_open_max_calls: int = 3     # Test calls in half-open state
    success_threshold: int = 2       # Successes needed to close from half-open


@dataclass
class ProviderCircuitStats:
    """Statistics for a provider's circuit breaker."""
    state: CircuitState = CircuitState.CLOSED
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: datetime = field(default_factory=datetime.utcnow)
    opened_at: datetime | None = None
    half_open_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0


class ProviderCircuitBreaker:
    """
    Circuit breaker for market data providers.
    
    Tracks provider failures and automatically disables providers
    that consistently fail, allowing periodic recovery attempts.
    
    Example:
        breaker = ProviderCircuitBreaker(failure_threshold=5, reset_timeout=60)
        
        # Record failure
        breaker.record_failure('alpaca')
        
        # Check if provider is available
        if not breaker.is_disabled('alpaca'):
            data = await provider.fetch()
            breaker.record_success('alpaca')
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        reset_timeout: int = 60,
        half_open_max_calls: int = 3,
        success_threshold: int = 2
    ):
        """
        Initialize circuit breaker.
        
        Args:
            failure_threshold: Consecutive failures before opening circuit
            reset_timeout: Seconds before attempting reset from open state
            half_open_max_calls: Maximum test calls in half-open state
            success_threshold: Successes needed to close from half-open
        """
        self.config = CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            reset_timeout=reset_timeout,
            half_open_max_calls=half_open_max_calls,
            success_threshold=success_threshold
        )
        
        # Provider statistics
        self.providers: Dict[str, ProviderCircuitStats] = {}
        
        logger.info(
            f"ProviderCircuitBreaker initialized: "
            f"failure_threshold={failure_threshold}, "
            f"reset_timeout={reset_timeout}s"
        )
    
    def record_failure(self, provider: str) -> None:
        """
        Record a provider failure.
        
        Updates failure count and potentially opens the circuit.
        
        Args:
            provider: Provider name
        """
        if provider not in self.providers:
            self.providers[provider] = ProviderCircuitStats()
        
        stats = self.providers[provider]
        stats.consecutive_failures += 1
        stats.consecutive_successes = 0
        stats.total_failures += 1
        stats.last_failure_time = datetime.utcnow()
        
        # Check if we should open the circuit
        if stats.state == CircuitState.CLOSED:
            if stats.consecutive_failures >= self.config.failure_threshold:
                self._open_circuit(provider)
        
        elif stats.state == CircuitState.HALF_OPEN:
            # Failure in half-open state reopens circuit
            logger.warning(
                f"🔴 Circuit REOPENED for {provider} - "
                f"failed during recovery test"
            )
            self._open_circuit(provider)
        
        logger.debug(
            f"Failure recorded for {provider}: "
            f"consecutive={stats.consecutive_failures}, "
            f"state={stats.state.value}"
        )
    
    def record_success(self, provider: str) -> None:
        """
        Record a provider success.
        
        Resets failure count and potentially closes the circuit.
        
        Args:
            provider: Provider name
        """
        if provider not in self.providers:
            self.providers[provider] = ProviderCircuitStats()
        
        stats = self.providers[provider]
        stats.consecutive_successes += 1
        stats.consecutive_failures = 0
        stats.total_successes += 1
        
        # Check if we should close the circuit
        if stats.state == CircuitState.HALF_OPEN:
            stats.half_open_calls += 1
            
            if stats.consecutive_successes >= self.config.success_threshold:
                self._close_circuit(provider)
            elif stats.half_open_calls >= self.config.half_open_max_calls:
                # Exhausted test calls without enough successes
                logger.warning(
                    f"🟡 Circuit remains OPEN for {provider} - "
                    f"insufficient successes ({stats.consecutive_successes}/{self.config.success_threshold}) "
                    f"during recovery test"
                )
                self._open_circuit(provider)
        
        elif stats.state == CircuitState.OPEN:
            # Success while open shouldn't happen (disabled), but reset if it does
            logger.info(
                f"🟢 Unexpected success for OPEN circuit {provider}, "
                f"transitioning to HALF_OPEN"
            )
            self._transition_to_half_open(provider)
        
        logger.debug(
            f"Success recorded for {provider}: "
            f"consecutive={stats.consecutive_successes}, "
            f"state={stats.state.value}"
        )
    
    def is_disabled(self, provider: str) -> bool:
        """
        Check if a provider is disabled (circuit open).
        
        Automatically attempts reset if timeout has passed.
        
        Args:
            provider: Provider name
            
        Returns:
            True if provider should not be used
        """
        if provider not in self.providers:
            return False
        
        stats = self.providers[provider]
        
        # Closed circuit = provider available
        if stats.state == CircuitState.CLOSED:
            return False
        
        # Half-open = allow limited testing
        if stats.state == CircuitState.HALF_OPEN:
            if stats.half_open_calls >= self.config.half_open_max_calls:
                # Exhausted test calls, reopen
                logger.debug(
                    f"Half-open test calls exhausted for {provider}, "
                    f"reopening circuit"
                )
                self._open_circuit(provider)
                return True
            return False
        
        # Open circuit - check if we should attempt reset
        if stats.opened_at:
            elapsed = (datetime.utcnow() - stats.opened_at).total_seconds()
            if elapsed >= self.config.reset_timeout:
                logger.info(
                    f"🔄 Circuit reset timeout reached for {provider} "
                    f"({elapsed:.0f}s >= {self.config.reset_timeout}s), "
                    f"transitioning to HALF_OPEN for testing"
                )
                self._transition_to_half_open(provider)
                return False
        
        return True
    
    def get_state(self, provider: str) -> CircuitState:
        """
        Get current circuit state for provider.
        
        Args:
            provider: Provider name
            
        Returns:
            Current circuit state
        """
        if provider not in self.providers:
            return CircuitState.CLOSED
        
        return self.providers[provider].state
    
    def get_statistics(self, provider: str) -> Dict[str, any]:
        """
        Get circuit breaker statistics for provider.
        
        Args:
            provider: Provider name
            
        Returns:
            Statistics dictionary
        """
        if provider not in self.providers:
            return {
                'state': CircuitState.CLOSED.value,
                'consecutive_failures': 0,
                'consecutive_successes': 0,
                'total_failures': 0,
                'total_successes': 0,
                'success_rate': 1.0
            }
        
        stats = self.providers[provider]
        total = stats.total_successes + stats.total_failures
        success_rate = stats.total_successes / total if total > 0 else 1.0
        
        return {
            'state': stats.state.value,
            'consecutive_failures': stats.consecutive_failures,
            'consecutive_successes': stats.consecutive_successes,
            'total_failures': stats.total_failures,
            'total_successes': stats.total_successes,
            'success_rate': success_rate,
            'opened_at': stats.opened_at.isoformat() if stats.opened_at else None,
            'half_open_calls': stats.half_open_calls
        }
    
    def reset_provider(self, provider: str) -> None:
        """
        Manually reset circuit for a provider.
        
        Args:
            provider: Provider name
        """
        if provider in self.providers:
            logger.info(f"🔄 Manually resetting circuit for {provider}")
            self._close_circuit(provider)
    
    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        logger.info("🔄 Resetting all circuit breakers")
        for provider in list(self.providers.keys()):
            self._close_circuit(provider)
    
    def _open_circuit(self, provider: str) -> None:
        """Open circuit for provider."""
        stats = self.providers[provider]
        stats.state = CircuitState.OPEN
        stats.opened_at = datetime.utcnow()
        stats.half_open_calls = 0
        
        logger.warning(
            f"🔴 Circuit OPENED for {provider} - "
            f"{stats.consecutive_failures} consecutive failures "
            f"(threshold: {self.config.failure_threshold}). "
            f"Provider disabled for {self.config.reset_timeout}s"
        )
    
    def _close_circuit(self, provider: str) -> None:
        """Close circuit for provider."""
        stats = self.providers[provider]
        previous_state = stats.state
        
        stats.state = CircuitState.CLOSED
        stats.consecutive_failures = 0
        stats.consecutive_successes = 0
        stats.opened_at = None
        stats.half_open_calls = 0
        
        if previous_state != CircuitState.CLOSED:
            logger.info(
                f"🟢 Circuit CLOSED for {provider} - "
                f"provider recovered and re-enabled"
            )
    
    def _transition_to_half_open(self, provider: str) -> None:
        """Transition circuit to half-open state for testing."""
        stats = self.providers[provider]
        stats.state = CircuitState.HALF_OPEN
        stats.consecutive_failures = 0
        stats.consecutive_successes = 0
        stats.half_open_calls = 0
        
        logger.info(
            f"🟡 Circuit HALF_OPEN for {provider} - "
            f"testing recovery (max {self.config.half_open_max_calls} calls, "
            f"need {self.config.success_threshold} successes)"
        )
