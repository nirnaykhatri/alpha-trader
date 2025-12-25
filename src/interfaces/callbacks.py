"""
Callback Type Aliases.

This module defines type aliases for callback functions used throughout
the trading bot system. These provide type safety and documentation
for event-driven patterns.

Author: Trading Bot Team
Version: 1.0.0
"""

from typing import Any, Awaitable, Callable, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from src.interfaces.core import TradingSignal, Order, Position


# =============================================================================
# Type Aliases for Callbacks
# =============================================================================

# Generic type for event data
EventData = Dict[str, Any]

# Sync callbacks
SignalCallback = Callable[["TradingSignal"], None]
ConfigChangeCallback = Callable[[str, Any, Any], None]  # key, old_value, new_value
OrderCallback = Callable[["Order"], None]
PositionCallback = Callable[["Position", float], Any]  # position, pnl_percent

# Async callbacks
AsyncEventCallback = Callable[[EventData], Awaitable[None]]
AsyncSignalCallback = Callable[["TradingSignal"], Awaitable[None]]
AsyncOrderCallback = Callable[["Order"], Awaitable[None]]
AsyncPositionCallback = Callable[["Position"], Awaitable[None]]
AsyncErrorCallback = Callable[[Exception], Awaitable[None]]

# Type alias for close position callback (used by trailing managers)
ClosePositionCallback = Callable[[str], Awaitable[None]]


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "EventData",
    "SignalCallback",
    "ConfigChangeCallback",
    "OrderCallback",
    "PositionCallback",
    "AsyncEventCallback",
    "AsyncSignalCallback",
    "AsyncOrderCallback",
    "AsyncPositionCallback",
    "AsyncErrorCallback",
    "ClosePositionCallback",
]
