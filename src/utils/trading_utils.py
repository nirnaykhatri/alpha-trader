"""
Trading utility functions.

This module provides common trading-related utility functions that are shared
across multiple strategy components to eliminate code duplication.
"""

from src.interfaces import OrderType


def get_order_type(order_type_str: str) -> OrderType:
    """
    Convert order type string to OrderType enum.
    
    This is a centralized utility function used across the codebase
    to convert configuration strings to proper OrderType enums.
    
    Args:
        order_type_str: Order type as string (e.g., 'market', 'limit', 'stop', 'stop_limit').
                       Case-insensitive.
    
    Returns:
        OrderType: The corresponding OrderType enum value.
                  Defaults to OrderType.MARKET if unrecognized.
    
    Examples:
        >>> get_order_type('limit')
        OrderType.LIMIT
        >>> get_order_type('MARKET')
        OrderType.MARKET
        >>> get_order_type('invalid')
        OrderType.MARKET  # Default fallback
    """
    order_type_map = {
        'market': OrderType.MARKET,
        'limit': OrderType.LIMIT,
        'stop': OrderType.STOP,
        'stop_limit': OrderType.STOP_LIMIT
    }
    return order_type_map.get(order_type_str.lower(), OrderType.MARKET)
