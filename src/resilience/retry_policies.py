"""
Centralized Retry Policies for Broker API Operations

This module provides reusable retry decorators and policies for handling
transient API failures when communicating with broker APIs.

Key Features:
- Configurable retry attempts, delays, and backoff strategies
- Exception filtering for transient vs permanent failures
- Async-compatible decorators
- Logging integration for retry visibility

Usage:
    from src.resilience.retry_policies import retry_on_transient_api_error

    @retry_on_transient_api_error(max_attempts=3, base_delay=1.0)
    async def fetch_account_data() -> AccountData:
        return await broker_client.get_account()

Thread-Safety: Decorators are stateless and safe for concurrent use.
"""

import asyncio
import functools
import logging
from typing import (
    Any,
    Callable,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Type variable for decorated function return type
T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    """
    Immutable configuration for retry behavior.
    
    Attributes:
        max_attempts: Maximum number of attempts (including initial try)
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        exponential_backoff: Whether to use exponential backoff
        backoff_multiplier: Multiplier for exponential backoff (default 2.0)
        jitter: Whether to add randomness to delays (reduces thundering herd)
    """
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_backoff: bool = True
    backoff_multiplier: float = 2.0
    jitter: bool = True


# Default policies for common scenarios
DEFAULT_API_POLICY = RetryPolicy(
    max_attempts=3,
    base_delay=1.0,
    max_delay=10.0,
    exponential_backoff=True,
)

AGGRESSIVE_API_POLICY = RetryPolicy(
    max_attempts=5,
    base_delay=0.5,
    max_delay=30.0,
    exponential_backoff=True,
)

CONSERVATIVE_API_POLICY = RetryPolicy(
    max_attempts=2,
    base_delay=2.0,
    max_delay=5.0,
    exponential_backoff=False,
)


# Common transient exception patterns
TRANSIENT_ERROR_KEYWORDS = frozenset([
    "timeout",
    "timed out",
    "connection reset",
    "connection refused",
    "connection error",
    "temporarily unavailable",
    "service unavailable",
    "rate limit",
    "throttl",
    "too many requests",
    "429",
    "500",
    "502",
    "503",
    "504",
    "retry",
    "network",
])


def is_transient_error(exception: Exception) -> bool:
    """
    Determine if an exception represents a transient, retryable error.
    
    Args:
        exception: The exception to analyze
        
    Returns:
        True if the error is likely transient and retryable
    """
    error_str = str(exception).lower()
    error_type = type(exception).__name__.lower()
    
    # Check error message for transient patterns
    for keyword in TRANSIENT_ERROR_KEYWORDS:
        if keyword in error_str or keyword in error_type:
            return True
    
    # Check for common network exception types
    transient_types = (
        "timeout",
        "connection",
        "network",
        "temporary",
        "unavailable",
    )
    for t in transient_types:
        if t in error_type:
            return True
    
    return False


def calculate_delay(
    attempt: int,
    policy: RetryPolicy,
) -> float:
    """
    Calculate delay before next retry attempt.
    
    Args:
        attempt: Current attempt number (1-based)
        policy: Retry policy configuration
        
    Returns:
        Delay in seconds before next retry
    """
    if policy.exponential_backoff:
        delay = policy.base_delay * (policy.backoff_multiplier ** (attempt - 1))
    else:
        delay = policy.base_delay
    
    delay = min(delay, policy.max_delay)
    
    if policy.jitter:
        import random
        # Add ±25% jitter
        jitter_factor = 0.75 + (random.random() * 0.5)
        delay = delay * jitter_factor
    
    return delay


def retry_on_transient_api_error(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 10.0,
    exponential_backoff: bool = True,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying async functions on transient API errors.
    
    This decorator automatically retries the decorated function when it
    raises exceptions that appear to be transient (network issues, rate
    limits, temporary unavailability).
    
    Args:
        max_attempts: Maximum number of attempts (including initial)
        base_delay: Initial delay between retries in seconds
        max_delay: Maximum delay cap in seconds
        exponential_backoff: Whether to increase delay exponentially
        retryable_exceptions: Optional tuple of exception types to retry on.
                            If None, uses is_transient_error() heuristic.
        on_retry: Optional callback called on each retry with (exception, attempt)
    
    Returns:
        Decorated async function with retry behavior
    
    Example:
        @retry_on_transient_api_error(max_attempts=3)
        async def get_account_balance() -> float:
            return await api.get_balance()
    """
    policy = RetryPolicy(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        exponential_backoff=exponential_backoff,
    )
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception: Optional[Exception] = None
            
            for attempt in range(1, policy.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except Exception as e:
                    last_exception = e
                    
                    # Determine if this error is retryable
                    should_retry = False
                    if retryable_exceptions is not None:
                        should_retry = isinstance(e, retryable_exceptions)
                    else:
                        should_retry = is_transient_error(e)
                    
                    # If not retryable or last attempt, re-raise
                    if not should_retry or attempt >= policy.max_attempts:
                        logger.warning(
                            f"[{func.__name__}] Failed after {attempt} attempt(s): {e}"
                        )
                        raise
                    
                    # Calculate delay and log retry
                    delay = calculate_delay(attempt, policy)
                    logger.info(
                        f"[{func.__name__}] Attempt {attempt}/{policy.max_attempts} failed "
                        f"with transient error: {e}. Retrying in {delay:.2f}s..."
                    )
                    
                    # Call optional retry callback
                    if on_retry:
                        on_retry(e, attempt)
                    
                    await asyncio.sleep(delay)
            
            # Should not reach here, but satisfy type checker
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry loop exit")
        
        return wrapper
    
    return decorator


def retry_with_policy(
    policy: RetryPolicy,
    retryable_exceptions: Optional[Tuple[Type[Exception], ...]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator using a predefined RetryPolicy object.
    
    Args:
        policy: RetryPolicy configuration
        retryable_exceptions: Optional tuple of exception types to retry on
    
    Returns:
        Decorator function
    
    Example:
        @retry_with_policy(AGGRESSIVE_API_POLICY)
        async def fetch_market_data(symbol: str) -> MarketData:
            return await api.get_quote(symbol)
    """
    return retry_on_transient_api_error(
        max_attempts=policy.max_attempts,
        base_delay=policy.base_delay,
        max_delay=policy.max_delay,
        exponential_backoff=policy.exponential_backoff,
        retryable_exceptions=retryable_exceptions,
    )
