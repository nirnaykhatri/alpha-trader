"""
Position State Model
Shared data structures for position tracking across strategy components.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class PositionDirection(Enum):
    """Position direction enumeration."""
    LONG = "long"
    SHORT = "short"


class TradePhase(Enum):
    """Trading phase enumeration."""
    ENTRY = "entry"
    PROFIT_TRAILING = "profit_trailing"
    SUPPORT_AVERAGING = "support_averaging"
    RESISTANCE_AVERAGING = "resistance_averaging"
    EXIT = "exit"


@dataclass
class PositionState:
    """Represents the current state of a position."""
    symbol: str
    direction: PositionDirection
    phase: TradePhase
    quantity: float
    average_price: float
    current_price: float
    entry_time: datetime
    
    # Trailing data
    peak_price: Optional[float] = None
    trail_price: Optional[float] = None
    profit_percentage: float = 0.0
    
    # Support/Resistance data
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None
    averaging_attempts: int = 0
    
    # DCA Price Tracking for Progressive Enforcement
    last_dca_price: Optional[float] = None  # Price of last DCA order for progressive validation
    dca_order_prices: List[float] = field(default_factory=list)  # History of all DCA order prices
    position_lifecycle_id: Optional[str] = None  # Unique ID for this position lifecycle
    
    # Orders
    active_orders: List[str] = field(default_factory=list)
