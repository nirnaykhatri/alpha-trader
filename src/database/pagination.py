"""
Cosmos DB Pagination Helpers.

Provides reusable pagination patterns for Cosmos DB queries to prevent
unbounded scans and memory issues. Implements continuation token support
and efficient query patterns.

Key Features:
    - Continuation token support for cursor-based pagination
    - Field projection to reduce RU consumption
    - Active-only filters to reduce result sets
    - Bounded result sets with configurable limits

Usage:
    from src.database.pagination import (
        PaginatedResult,
        PaginationOptions,
        build_paginated_query,
        POSITION_FIELDS,
    )
    
    # Create pagination options
    options = PaginationOptions(
        max_items=100,
        continuation_token=None,
        fields=POSITION_FIELDS
    )
    
    # Execute paginated query
    result = await execute_paginated_query(container, query, options)

Author: Trading Bot Team
Version: 1.0.0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TypeVar, Generic, Callable
from enum import Enum

from src.core.logging_config import get_logger

logger = get_logger(__name__)


# Default limits to prevent unbounded queries
DEFAULT_MAX_ITEMS = 100
ABSOLUTE_MAX_ITEMS = 1000  # Hard cap to prevent abuse


class QueryProjection(Enum):
    """
    Predefined field projections for common entity types.
    
    Using projections instead of SELECT * reduces:
    - RU consumption (less data transferred)
    - Memory usage
    - Network latency
    """
    POSITION_MINIMAL = "position_minimal"
    POSITION_FULL = "position_full"
    ORDER_MINIMAL = "order_minimal"
    ORDER_FULL = "order_full"
    TRADE_SUMMARY = "trade_summary"
    TRADE_FULL = "trade_full"


# Field projections for different use cases
POSITION_FIELDS_MINIMAL = [
    "id", "symbol", "broker", "quantity", "avg_price", "current_price"
]

POSITION_FIELDS_FULL = [
    "id", "symbol", "broker", "quantity", "avg_price", "current_price",
    "unrealized_pnl", "realized_pnl", "created_at", "updated_at", "type"
]

ORDER_FIELDS_MINIMAL = [
    "id", "symbol", "broker", "quantity", "order_type", "side", 
    "price", "status", "created_at"
]

ORDER_FIELDS_FULL = [
    "id", "symbol", "broker", "quantity", "order_type", "side",
    "price", "stop_price", "status", "created_at", "filled_at",
    "filled_price", "filled_quantity", "broker_order_id",
    "is_dca_order", "is_closing", "type"
]

TRADE_FIELDS_SUMMARY = [
    "id", "symbol", "broker", "entry_price", "exit_price",
    "realized_pnl", "profit_percentage", "completed_at"
]

TRADE_FIELDS_FULL = [
    "id", "symbol", "broker", "entry_order_id", "entry_price",
    "entry_quantity", "entry_time", "entry_side", "exit_order_id",
    "exit_price", "exit_quantity", "exit_time", "exit_side",
    "exit_reason", "realized_pnl", "profit_percentage",
    "strategy_used", "created_at", "completed_at", "type"
]

# Mapping from enum to field lists
PROJECTION_FIELDS: Dict[QueryProjection, List[str]] = {
    QueryProjection.POSITION_MINIMAL: POSITION_FIELDS_MINIMAL,
    QueryProjection.POSITION_FULL: POSITION_FIELDS_FULL,
    QueryProjection.ORDER_MINIMAL: ORDER_FIELDS_MINIMAL,
    QueryProjection.ORDER_FULL: ORDER_FIELDS_FULL,
    QueryProjection.TRADE_SUMMARY: TRADE_FIELDS_SUMMARY,
    QueryProjection.TRADE_FULL: TRADE_FIELDS_FULL,
}


@dataclass
class PaginationOptions:
    """
    Options for paginated Cosmos DB queries.
    
    Attributes:
        max_items: Maximum number of items to return per page.
                   Capped at ABSOLUTE_MAX_ITEMS for safety.
        continuation_token: Token from previous query for cursor-based pagination.
        projection: Optional field projection to reduce data transfer.
        partition_key: Optional partition key for single-partition queries (more efficient).
    """
    max_items: int = DEFAULT_MAX_ITEMS
    continuation_token: Optional[str] = None
    projection: Optional[QueryProjection] = None
    partition_key: Optional[str] = None
    
    def __post_init__(self):
        """Validate and cap max_items."""
        if self.max_items > ABSOLUTE_MAX_ITEMS:
            logger.warning(
                f"max_items {self.max_items} exceeds limit, capping to {ABSOLUTE_MAX_ITEMS}"
            )
            self.max_items = ABSOLUTE_MAX_ITEMS
        if self.max_items < 1:
            self.max_items = DEFAULT_MAX_ITEMS
    
    def get_fields(self) -> Optional[List[str]]:
        """Get field list for projection, or None for SELECT *."""
        if self.projection:
            return PROJECTION_FIELDS.get(self.projection)
        return None


T = TypeVar('T')


@dataclass
class PaginatedResult(Generic[T]):
    """
    Result of a paginated query with continuation support.
    
    Attributes:
        items: List of items in this page
        continuation_token: Token for fetching next page, None if no more pages
        has_more: Whether more pages exist
        total_fetched: Number of items fetched in this request
        request_charge: RU consumed by this query (if available)
    """
    items: List[T] = field(default_factory=list)
    continuation_token: Optional[str] = None
    has_more: bool = False
    total_fetched: int = 0
    request_charge: Optional[float] = None
    
    @property
    def count(self) -> int:
        """Number of items in this page."""
        return len(self.items)
    
    def is_empty(self) -> bool:
        """Check if result is empty."""
        return len(self.items) == 0


def build_select_clause(
    fields: Optional[List[str]] = None,
    limit: Optional[int] = None,
    alias: str = "c"
) -> str:
    """
    Build SELECT clause with optional projection and limit.
    
    Args:
        fields: List of fields to project, None for all fields
        limit: Optional TOP clause limit
        alias: Query alias (default 'c')
    
    Returns:
        SELECT clause string
        
    Examples:
        >>> build_select_clause(None, 100)
        'SELECT TOP 100 *'
        >>> build_select_clause(['id', 'symbol'], None)
        'SELECT c.id, c.symbol'
        >>> build_select_clause(['id', 'symbol'], 50)
        'SELECT TOP 50 c.id, c.symbol'
    """
    if fields:
        field_list = ", ".join(f"{alias}.{f}" for f in fields)
        if limit:
            return f"SELECT TOP {limit} {field_list}"
        return f"SELECT {field_list}"
    else:
        if limit:
            return f"SELECT TOP {limit} *"
        return "SELECT *"


def build_where_clause(
    conditions: Optional[List[str]] = None,
    alias: str = "c"
) -> str:
    """
    Build WHERE clause from conditions.
    
    Args:
        conditions: List of condition strings (e.g., ["c.quantity != 0"])
        alias: Query alias (default 'c')
    
    Returns:
        WHERE clause string or empty string if no conditions
        
    Examples:
        >>> build_where_clause(None)
        ''
        >>> build_where_clause(["c.quantity != 0", "c.broker = @broker"])
        'WHERE c.quantity != 0 AND c.broker = @broker'
    """
    if not conditions:
        return ""
    return f"WHERE {' AND '.join(conditions)}"


def build_order_by_clause(
    order_by: Optional[str] = None,
    descending: bool = True,
    alias: str = "c"
) -> str:
    """
    Build ORDER BY clause.
    
    Args:
        order_by: Field to order by
        descending: If True, order DESC; otherwise ASC
        alias: Query alias (default 'c')
    
    Returns:
        ORDER BY clause string or empty string if no ordering
        
    Examples:
        >>> build_order_by_clause("created_at")
        'ORDER BY c.created_at DESC'
        >>> build_order_by_clause("created_at", descending=False)
        'ORDER BY c.created_at ASC'
    """
    if not order_by:
        return ""
    direction = "DESC" if descending else "ASC"
    return f"ORDER BY {alias}.{order_by} {direction}"


def build_paginated_query(
    container_alias: str = "c",
    fields: Optional[List[str]] = None,
    conditions: Optional[List[str]] = None,
    order_by: Optional[str] = None,
    descending: bool = True,
    limit: Optional[int] = None
) -> str:
    """
    Build a complete paginated query string.
    
    Args:
        container_alias: Alias for the container (default 'c')
        fields: List of fields to project, None for all fields
        conditions: List of WHERE conditions
        order_by: Field to order by
        descending: If True, order DESC
        limit: Optional TOP clause limit
    
    Returns:
        Complete query string
        
    Examples:
        >>> build_paginated_query(
        ...     fields=['id', 'symbol', 'quantity'],
        ...     conditions=['c.quantity != 0'],
        ...     order_by='created_at',
        ...     limit=100
        ... )
        'SELECT TOP 100 c.id, c.symbol, c.quantity FROM c WHERE c.quantity != 0 ORDER BY c.created_at DESC'
    """
    select = build_select_clause(fields, limit, container_alias)
    where = build_where_clause(conditions, container_alias)
    order = build_order_by_clause(order_by, descending, container_alias)
    
    query_parts = [select, f"FROM {container_alias}"]
    if where:
        query_parts.append(where)
    if order:
        query_parts.append(order)
    
    return " ".join(query_parts)


class ActiveOnlyFilter:
    """
    Common active-only filter conditions for different entity types.
    
    Using these filters reduces result sets and RU consumption by
    excluding inactive/closed records at the query level.
    """
    
    # Position filters
    POSITION_HAS_QUANTITY = "c.quantity != 0"
    POSITION_IS_LONG = "c.quantity > 0"
    POSITION_IS_SHORT = "c.quantity < 0"
    
    # Trade filters
    TRADE_IS_OPEN = "c.completed_at = null"
    TRADE_IS_COMPLETED = "c.completed_at != null"
    
    # Order filters
    ORDER_IS_OPEN = "c.status IN ('new', 'pending', 'accepted', 'partially_filled')"
    ORDER_IS_FILLED = "c.status = 'filled'"
    
    @staticmethod
    def broker_filter(broker: str) -> str:
        """Generate broker filter condition (use with parameterized query)."""
        return "c.broker = @broker"
    
    @staticmethod
    def symbol_filter(symbol: str) -> str:
        """Generate symbol filter condition (use with parameterized query)."""
        return "c.symbol = @symbol"
    
    @staticmethod
    def date_cutoff_filter(field: str = "created_at") -> str:
        """Generate date cutoff filter (use with parameterized query)."""
        return f"c.{field} >= @cutoff"


# Export all public symbols
__all__ = [
    "PaginationOptions",
    "PaginatedResult",
    "QueryProjection",
    "ActiveOnlyFilter",
    "build_paginated_query",
    "build_select_clause",
    "build_where_clause",
    "build_order_by_clause",
    "POSITION_FIELDS_MINIMAL",
    "POSITION_FIELDS_FULL",
    "ORDER_FIELDS_MINIMAL",
    "ORDER_FIELDS_FULL",
    "TRADE_FIELDS_SUMMARY",
    "TRADE_FIELDS_FULL",
    "DEFAULT_MAX_ITEMS",
    "ABSOLUTE_MAX_ITEMS",
]
