"""
Utility modules for the trading bot.

This package provides common utilities used across the trading bot:
- Error handling decorators and context managers
- Logging wrapper with trading-specific methods
- Async utilities and bounded concurrency
"""

from src.utils.asyncio_utils import run_blocking
from src.utils.bounded_gather import (
    bounded_gather,
    fetch_prices_bounded,
    BoundedFetcher,
)
from src.utils.trading_utils import get_order_type
from src.utils.error_handler import (
    handle_errors,
    async_handle_errors,
    safe_execute,
    sync_safe_execute,
    error_boundary,
    async_error_boundary,
    log_and_continue,
    async_log_and_continue,
    ErrorContext,
)
from src.utils.bot_logger import (
    BotLogger,
    get_logger,
    configure_root_logger,
    LogEmoji,
)

__all__ = [
    # Async utilities
    'run_blocking',
    'bounded_gather',
    'fetch_prices_bounded',
    'BoundedFetcher',
    # Trading utilities
    'get_order_type',
    # Error handling
    'handle_errors',
    'async_handle_errors',
    'safe_execute',
    'sync_safe_execute',
    'error_boundary',
    'async_error_boundary',
    'log_and_continue',
    'async_log_and_continue',
    'ErrorContext',
    # Logging
    'BotLogger',
    'get_logger',
    'configure_root_logger',
    'LogEmoji',
]
