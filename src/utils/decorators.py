"""
Reusable decorators for the trading bot application.

This module provides common decorators to reduce code duplication and
improve consistency across the application.
"""

import asyncio
import functools
import random
import time
from typing import Callable, Any, Optional
from fastapi import Request, HTTPException
from src.constants import HTTPStatus, SecurityConstants, APIConstants, ErrorMessages
import structlog

logger = structlog.get_logger(__name__)


def localhost_only(func: Callable) -> Callable:
    """
    Decorator to restrict FastAPI endpoints to localhost access only.
    
    This decorator checks the client host and raises an HTTP 403 error
    if the request originates from a non-localhost address.
    
    Args:
        func: The async function to wrap (FastAPI route handler)
        
    Returns:
        Wrapped function that enforces localhost-only access
        
    Raises:
        HTTPException: 403 Forbidden if accessed from non-localhost
        
    Example:
        @app.get("/admin/status")
        @localhost_only
        async def get_admin_status(request: Request):
            return {"status": "ok"}
    """
    @functools.wraps(func)
    async def wrapper(request: Request, *args, **kwargs):
        client_host = request.client.host if request.client else "unknown"
        
        if client_host not in SecurityConstants.LOCALHOST_IPS:
            logger.warning(
                "unauthorized_access_attempt",
                endpoint=request.url.path,
                client_host=client_host,
                function=func.__name__
            )
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail=ErrorMessages.FORBIDDEN_ACCESS
            )
        
        return await func(request, *args, **kwargs)
    
    return wrapper


def handle_api_errors(
    retryable: bool = True,
    max_retries: int = APIConstants.MAX_RETRY_ATTEMPTS,
    backoff_base: float = APIConstants.RETRY_BACKOFF_BASE,
    is_retryable: Optional[Callable[[Exception], bool]] = None
) -> Callable:
    """
    Decorator to implement consistent error handling with retry logic.
    
    This decorator provides exponential backoff retry logic with jitter for API calls
    and standardized error logging.
    
    Args:
        retryable: Whether to retry on failure
        max_retries: Maximum number of retry attempts
        backoff_base: Base for exponential backoff calculation
        is_retryable: Optional predicate to determine if exception is retryable.
                     If provided, only retryable exceptions will be retried.
        
    Returns:
        Decorator function
        
    Example:
        # Simple retry
        @handle_api_errors(retryable=True, max_retries=3)
        async def fetch_data(symbol: str):
            return await api_client.get_data(symbol)
        
        # With custom retryable predicate
        def is_transient_error(e: Exception) -> bool:
            return isinstance(e, (TimeoutError, ConnectionError))
        
        @handle_api_errors(retryable=True, is_retryable=is_transient_error)
        async def fetch_with_classification(symbol: str):
            return await api_client.get_data(symbol)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception: Optional[Exception] = None
            
            attempts = max_retries if retryable else 1
            
            for attempt in range(1, attempts + 1):
                try:
                    return await func(*args, **kwargs)
                    
                except Exception as e:
                    last_exception = e
                    
                    # Check if exception is retryable (if predicate provided)
                    if is_retryable and not is_retryable(e):
                        logger.error(
                            "non_retryable_error",
                            function=func.__name__,
                            error=str(e),
                            error_type=type(e).__name__
                        )
                        raise  # Non-retryable error, raise immediately
                    
                    logger.warning(
                        "api_call_failed",
                        function=func.__name__,
                        attempt=attempt,
                        max_attempts=attempts,
                        error=str(e),
                        error_type=type(e).__name__
                    )
                    
                    # Don't retry if this is the last attempt
                    if attempt >= attempts:
                        break
                    
                    # Calculate backoff delay with jitter (Issue #6)
                    base_delay = min(
                        backoff_base ** attempt,
                        APIConstants.RETRY_BACKOFF_MAX
                    )
                    jitter = random.uniform(0.8, 1.2)  # ±20% jitter
                    delay = base_delay * jitter
                    
                    logger.info(
                        "retrying_api_call",
                        function=func.__name__,
                        delay_seconds=delay,
                        next_attempt=attempt + 1
                    )
                    
                    await asyncio.sleep(delay)
            
            # All retries exhausted
            logger.error(
                "api_call_failed_all_retries",
                function=func.__name__,
                total_attempts=attempts,
                error=str(last_exception)
            )
            
            raise last_exception
        
        return wrapper
    
    return decorator


def rate_limit(calls_per_minute: int = SecurityConstants.MAX_REQUESTS_PER_MINUTE) -> Callable:
    """
    Decorator to implement rate limiting for functions.
    
    Args:
        calls_per_minute: Maximum number of calls allowed per minute
        
    Returns:
        Decorator function
        
    Example:
        @rate_limit(calls_per_minute=30)
        async def expensive_operation():
            pass
    """
    min_interval = 60.0 / calls_per_minute
    last_called = {}
    
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            func_key = func.__name__
            current_time = time.time()
            
            if func_key in last_called:
                elapsed = current_time - last_called[func_key]
                if elapsed < min_interval:
                    wait_time = min_interval - elapsed
                    logger.debug(
                        "rate_limit_triggered",
                        function=func.__name__,
                        wait_seconds=wait_time
                    )
                    await asyncio.sleep(wait_time)
            
            last_called[func_key] = time.time()
            return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator


def log_execution_time(func: Callable) -> Callable:
    """
    Decorator to log execution time of async functions.
    
    Useful for performance monitoring and identifying bottlenecks.
    
    Example:
        @log_execution_time
        async def complex_calculation():
            pass
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        start_time = time.time()
        
        try:
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            logger.info(
                "function_execution_completed",
                function=func.__name__,
                execution_time_seconds=round(execution_time, 3),
                success=True
            )
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            
            logger.error(
                "function_execution_failed",
                function=func.__name__,
                execution_time_seconds=round(execution_time, 3),
                error=str(e),
                success=False
            )
            
            raise
    
    return wrapper


def validate_symbol(func: Callable) -> Callable:
    """
    Decorator to validate trading symbol format before execution.
    
    Ensures symbol is a non-empty string with valid characters.
    
    Example:
        @validate_symbol
        async def get_price(symbol: str):
            pass
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        # Try to find symbol in args or kwargs
        symbol = None
        
        # Check positional args
        if args and len(args) > 0 and isinstance(args[0], str):
            symbol = args[0]
        # Check kwargs
        elif 'symbol' in kwargs:
            symbol = kwargs['symbol']
        
        if symbol:
            if not symbol or not isinstance(symbol, str):
                raise ValueError(ErrorMessages.INVALID_SYMBOL)
            
            # Basic validation - alphanumeric and some special chars
            if not symbol.replace('.', '').replace('-', '').isalnum():
                raise ValueError(f"{ErrorMessages.INVALID_SYMBOL}: {symbol}")
        
        return await func(*args, **kwargs)
    
    return wrapper


def endpoint_policy(
    localhost: bool = False,
    rate_limit_config: Optional[tuple[int, int]] = None,  # (max_calls, period_seconds)
    retries: int = 0,
    log_time: bool = False
) -> Callable:
    """
    Composite decorator for endpoint policies.
    
    Combines multiple decorators into a single, readable policy declaration.
    Replaces decorator stacking for improved readability.
    
    Args:
        localhost: Restrict to localhost access only
        rate_limit_config: Tuple of (max_calls, period_seconds) for rate limiting
        retries: Number of retry attempts for retryable operations
        log_time: Whether to log execution time
        
    Returns:
        Composite decorator function
        
    Example:
        @endpoint_policy(localhost=True, rate_limit_config=(10, 60), retries=3)
        async def admin_operation(request: Request):
            pass
            
        # Replaces:
        # @localhost_only
        # @rate_limit(calls_per_minute=10)
        # @handle_api_errors(retryable=True, max_retries=3)
        # @log_execution_time
    """
    def decorator(func: Callable) -> Callable:
        wrapped = func
        
        # Apply decorators in reverse order (innermost first)
        
        # 1. Logging (innermost - measures actual execution)
        if log_time:
            wrapped = log_execution_time(wrapped)
        
        # 2. Retry logic
        if retries > 0:
            wrapped = handle_api_errors(
                retryable=True,
                max_retries=retries
            )(wrapped)
        
        # 3. Rate limiting
        if rate_limit_config:
            max_calls, period_seconds = rate_limit_config
            calls_per_minute = int((max_calls / period_seconds) * 60)
            wrapped = rate_limit(calls_per_minute=calls_per_minute)(wrapped)
        
        # 4. Access control (outermost - first check)
        if localhost:
            wrapped = localhost_only(wrapped)
        
        return wrapped
    
    return decorator
