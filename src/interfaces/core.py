"""
Core Trading Data Models and Enums.

This module contains the fundamental data structures and enumerations
used throughout the trading bot system. These are domain-agnostic
primitives that other modules depend on.

Canonical location for:
- TradingSignal, Order, Position, SupportLevel, SupportLevelData
- SignalType, OrderType, OrderStatus, OrderSide enums

Author: Trading Bot Team
Version: 1.0.0
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


# =============================================================================
# Enumerations
# =============================================================================

class SignalType(Enum):
    """Types of trading signals."""
    BUY = "buy"
    SELL = "sell"
    CLOSE = "close"


class OrderType(Enum):
    """Types of orders."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    """Order status values."""
    PENDING = "pending"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    PARTIAL_FILL = "partial_fill"


class OrderSide(Enum):
    """Order side values."""
    BUY = "buy"
    SELL = "sell"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class TradingSignal:
    """Represents a trading signal from TradingView or other sources."""
    signal_id: str
    symbol: str
    signal_type: SignalType
    price: float
    quantity: Optional[float] = None
    timestamp: datetime = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.metadata is None:
            self.metadata = {}
        if self.signal_id is None:
            self.signal_id = str(uuid.uuid4())


@dataclass
class Order:
    """Represents a trading order."""
    order_id: str
    symbol: str
    quantity: float
    order_type: OrderType
    side: OrderSide  # Buy or sell
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = None
    filled_at: Optional[datetime] = None
    filled_price: Optional[float] = None
    filled_quantity: Optional[float] = None
    broker: Optional[str] = None
    broker_order_id: Optional[str] = None
    is_dca_order: bool = False  # Indicates if this is a DCA (Dollar Cost Averaging) order
    is_closing: bool = False  # Indicates if this order is closing a position
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.order_id is None:
            self.order_id = str(uuid.uuid4())


@dataclass
class Position:
    """Represents a current position."""
    symbol: str
    quantity: float
    avg_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    created_at: datetime = None
    broker: Optional[str] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


@dataclass
class SupportLevel:
    """Represents a calculated support or resistance level."""
    price: float
    confidence: float  # 0.0 to 1.0
    method: str  # Calculation method used
    touches: int = 0  # Number of times price touched this level
    last_touch: datetime = None
    calculated_at: datetime = None
    
    def __post_init__(self):
        if self.calculated_at is None:
            self.calculated_at = datetime.utcnow()
        if self.last_touch is None:
            self.last_touch = datetime.utcnow()


@dataclass
class SupportLevelData:
    """Contains comprehensive support/resistance level data."""
    symbol: str
    timeframe: str
    levels: List[SupportLevel]
    calculated_at: datetime
    confidence: float  # Overall confidence of the analysis
    
    def get_nearest_level(self, current_price: float, level_type: str = "support") -> Optional[SupportLevel]:
        """Get the nearest support or resistance level to current price."""
        if not self.levels:
            return None
        
        if level_type == "support":
            # Find highest support below current price
            support_levels = [level for level in self.levels if level.price < current_price]
            return max(support_levels, key=lambda x: x.price) if support_levels else None
        else:
            # Find lowest resistance above current price
            resistance_levels = [level for level in self.levels if level.price > current_price]
            return min(resistance_levels, key=lambda x: x.price) if resistance_levels else None


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Enums
    "SignalType",
    "OrderType",
    "OrderStatus",
    "OrderSide",
    # Data classes
    "TradingSignal",
    "Order",
    "Position",
    "SupportLevel",
    "SupportLevelData",
]
