"""
Centralized Error Handling Utilities

This module provides standardized error handling patterns to reduce code duplication
across the codebase. It includes decorators, context managers, and utility functions
for consistent error handling with proper logging.

Usage:
    from src.utils.error_handler import handle_errors, async_handle_errors, safe_execute

    @handle_errors(logger=my_logger, default_return=None)
    def my_function():
        ...

    @async_handle_errors(logger=my_logger)
    async def my_async_function():
        ...

    result = await safe_execute(risky_operation, default=default_value, logger=logger)
"""

from functools import wraps
from typing import TypeVar, Callable, Any, Optional, Union, Type
from contextlib import contextmanager, asynccontextmanager
import logging
import asyncio

from src.domain.errors import DomainError

# Type variables for generic typing
T = TypeVar('T')
R = TypeVar('R')


class ErrorContext:
    """
    Context information for error handling.
    
    Provides structured error information for logging and error responses.
    """
    
    def __init__(
        self,
        operation: str,
        component: str,
        symbol: Optional[str] = None,
        details: Optional[dict] = None
    ):
        """
        Initialize error context.
        
        Args:
            operation: The operation being performed (e.g., 'create_order')
            component: The component/module name (e.g., 'OrderManager')
            symbol: Optional trading symbol for trade-related operations
            details: Optional additional context details
        """
        self.operation = operation
        self.component = component
        self.symbol = symbol
        self.details = details or {}
    
    def to_log_message(self) -> str:
        """Format context as a log message prefix."""
        parts = [f"[{self.component}]", f"op={self.operation}"]
        if self.symbol:
            parts.append(f"symbol={self.symbol}")
        return " ".join(parts)
    
    def to_dict(self) -> dict:
        """Convert context to dictionary for structured logging."""
        result = {
            "operation": self.operation,
            "component": self.component,
        }
        if self.symbol:
            result["symbol"] = self.symbol
        if self.details:
            result.update(self.details)
        return result


def handle_errors(
    logger: Optional[logging.Logger] = None,
    default_return: T = None,
    error_message: Optional[str] = None,
    reraise: bool = False,
    reraise_types: Optional[tuple[Type[Exception], ...]] = None,
    context: Optional[ErrorContext] = None,
) -> Callable[[Callable[..., R]], Callable[..., Union[R, T]]]:
    """
    Decorator for synchronous functions with standardized error handling.
    
    Catches exceptions, logs them appropriately, and optionally returns
    a default value or re-raises the exception.
    
    Args:
        logger: Logger instance for error logging. Uses print if None.
        default_return: Value to return if an exception occurs.
        error_message: Custom error message prefix.
        reraise: If True, re-raise the exception after logging.
        reraise_types: Tuple of exception types to always re-raise.
        context: ErrorContext for structured logging.
    
    Returns:
        Decorated function with error handling.
    
    Example:
        @handle_errors(logger=logger, default_return=[], error_message="Failed to fetch orders")
        def fetch_orders() -> List[Order]:
            ...
    """
    def decorator(func: Callable[..., R]) -> Callable[..., Union[R, T]]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Union[R, T]:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Always re-raise specific exception types
                if reraise_types and isinstance(e, reraise_types):
                    raise
                
                # Format error message
                msg_prefix = error_message or f"Error in {func.__name__}"
                if context:
                    msg_prefix = f"{context.to_log_message()} {msg_prefix}"
                
                full_message = f"{msg_prefix}: {e}"
                
                # Log the error
                if logger:
                    if isinstance(e, DomainError):
                        logger.warning(full_message)
                    else:
                        logger.error(full_message, exc_info=True)
                else:
                    print(f"❌ {full_message}")
                
                # Re-raise if requested
                if reraise:
                    raise
                
                return default_return
        
        return wrapper
    return decorator


def async_handle_errors(
    logger: Optional[logging.Logger] = None,
    default_return: T = None,
    error_message: Optional[str] = None,
    reraise: bool = False,
    reraise_types: Optional[tuple[Type[Exception], ...]] = None,
    context: Optional[ErrorContext] = None,
) -> Callable[[Callable[..., R]], Callable[..., Union[R, T]]]:
    """
    Decorator for async functions with standardized error handling.
    
    Async equivalent of handle_errors decorator.
    
    Args:
        logger: Logger instance for error logging. Uses print if None.
        default_return: Value to return if an exception occurs.
        error_message: Custom error message prefix.
        reraise: If True, re-raise the exception after logging.
        reraise_types: Tuple of exception types to always re-raise.
        context: ErrorContext for structured logging.
    
    Returns:
        Decorated async function with error handling.
    
    Example:
        @async_handle_errors(logger=logger, default_return=False)
        async def place_order() -> bool:
            ...
    """
    def decorator(func: Callable[..., R]) -> Callable[..., Union[R, T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Union[R, T]:
            try:
                return await func(*args, **kwargs)
            except asyncio.CancelledError:
                # Always re-raise cancellation
                raise
            except Exception as e:
                # Always re-raise specific exception types
                if reraise_types and isinstance(e, reraise_types):
                    raise
                
                # Format error message
                msg_prefix = error_message or f"Error in {func.__name__}"
                if context:
                    msg_prefix = f"{context.to_log_message()} {msg_prefix}"
                
                full_message = f"{msg_prefix}: {e}"
                
                # Log the error
                if logger:
                    if isinstance(e, DomainError):
                        logger.warning(full_message)
                    else:
                        logger.error(full_message, exc_info=True)
                else:
                    print(f"❌ {full_message}")
                
                # Re-raise if requested
                if reraise:
                    raise
                
                return default_return
        
        return wrapper
    return decorator


async def safe_execute(
    coro: Any,
    default: T = None,
    logger: Optional[logging.Logger] = None,
    error_message: Optional[str] = None,
    context: Optional[ErrorContext] = None,
) -> Union[Any, T]:
    """
    Safely execute an async operation with error handling.
    
    Use for one-off operations where a decorator isn't practical.
    
    Args:
        coro: Coroutine to execute
        default: Default value to return on error
        logger: Logger instance for error logging
        error_message: Custom error message
        context: ErrorContext for structured logging
    
    Returns:
        Result of the coroutine or default value on error.
    
    Example:
        result = await safe_execute(
            risky_database_operation(),
            default=[],
            logger=logger,
            error_message="Database query failed"
        )
    """
    try:
        return await coro
    except asyncio.CancelledError:
        raise
    except Exception as e:
        msg = error_message or "Operation failed"
        if context:
            msg = f"{context.to_log_message()} {msg}"
        
        full_message = f"{msg}: {e}"
        
        if logger:
            logger.error(full_message, exc_info=True)
        else:
            print(f"❌ {full_message}")
        
        return default


def sync_safe_execute(
    func: Callable[..., R],
    *args: Any,
    default: T = None,
    logger: Optional[logging.Logger] = None,
    error_message: Optional[str] = None,
    **kwargs: Any,
) -> Union[R, T]:
    """
    Safely execute a synchronous function with error handling.
    
    Args:
        func: Function to execute
        *args: Positional arguments for the function
        default: Default value to return on error
        logger: Logger instance for error logging
        error_message: Custom error message
        **kwargs: Keyword arguments for the function
    
    Returns:
        Result of the function or default value on error.
    
    Example:
        result = sync_safe_execute(
            parse_config,
            config_path,
            default={},
            logger=logger,
            error_message="Config parsing failed"
        )
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        msg = error_message or f"Error in {func.__name__}"
        full_message = f"{msg}: {e}"
        
        if logger:
            logger.error(full_message, exc_info=True)
        else:
            print(f"❌ {full_message}")
        
        return default


@contextmanager
def error_boundary(
    operation: str,
    logger: Optional[logging.Logger] = None,
    reraise: bool = True,
    component: Optional[str] = None,
):
    """
    Context manager for error handling with structured logging.
    
    Args:
        operation: Description of the operation being performed
        logger: Logger instance for error logging
        reraise: If True, re-raise the exception after logging
        component: Component/module name for context
    
    Yields:
        None
    
    Example:
        with error_boundary("database query", logger=logger, component="OrderManager"):
            result = execute_query()
    """
    context = ErrorContext(operation=operation, component=component or "Unknown")
    try:
        yield
    except Exception as e:
        full_message = f"{context.to_log_message()}: {e}"
        
        if logger:
            logger.error(full_message, exc_info=True)
        else:
            print(f"❌ {full_message}")
        
        if reraise:
            raise


@asynccontextmanager
async def async_error_boundary(
    operation: str,
    logger: Optional[logging.Logger] = None,
    reraise: bool = True,
    component: Optional[str] = None,
):
    """
    Async context manager for error handling with structured logging.
    
    Args:
        operation: Description of the operation being performed
        logger: Logger instance for error logging
        reraise: If True, re-raise the exception after logging
        component: Component/module name for context
    
    Yields:
        None
    
    Example:
        async with async_error_boundary("API call", logger=logger, component="AlpacaClient"):
            result = await api.get_positions()
    """
    context = ErrorContext(operation=operation, component=component or "Unknown")
    try:
        yield
    except asyncio.CancelledError:
        raise
    except Exception as e:
        full_message = f"{context.to_log_message()}: {e}"
        
        if logger:
            logger.error(full_message, exc_info=True)
        else:
            print(f"❌ {full_message}")
        
        if reraise:
            raise


def log_and_continue(
    logger: logging.Logger,
    level: int = logging.WARNING,
) -> Callable[[Callable[..., R]], Callable[..., Optional[R]]]:
    """
    Decorator that logs exceptions and continues execution (returns None).
    
    Useful for non-critical operations where failures should be logged
    but not interrupt the main flow.
    
    Args:
        logger: Logger instance
        level: Logging level for the error message
    
    Returns:
        Decorated function that returns None on error.
    
    Example:
        @log_and_continue(logger, level=logging.DEBUG)
        def optional_cleanup():
            ...
    """
    def decorator(func: Callable[..., R]) -> Callable[..., Optional[R]]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Optional[R]:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.log(level, f"Non-critical error in {func.__name__}: {e}")
                return None
        return wrapper
    return decorator


def async_log_and_continue(
    logger: logging.Logger,
    level: int = logging.WARNING,
) -> Callable[[Callable[..., R]], Callable[..., Optional[R]]]:
    """
    Async version of log_and_continue decorator.
    
    Args:
        logger: Logger instance
        level: Logging level for the error message
    
    Returns:
        Decorated async function that returns None on error.
    """
    def decorator(func: Callable[..., R]) -> Callable[..., Optional[R]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Optional[R]:
            try:
                return await func(*args, **kwargs)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.log(level, f"Non-critical error in {func.__name__}: {e}")
                return None
        return wrapper
    return decorator
