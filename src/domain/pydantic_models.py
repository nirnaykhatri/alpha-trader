"""
Pydantic-based Domain Models.

These models provide validated versions of the core trading domain objects.
They can be used at API boundaries for request/response validation while
the internal dataclass versions remain unchanged for compatibility.

Author: Trading Bot Team
Version: 2.0.0
"""

from typing import Optional, Dict, Any, List, Self
from datetime import datetime
from enum import Enum
import uuid

from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


# =============================================================================
# Enums (Shared with dataclass versions)
# =============================================================================

class SignalType(str, Enum):
    """Types of trading signals."""
    BUY = "buy"
    SELL = "sell"
    CLOSE = "close"


class OrderType(str, Enum):
    """Types of orders."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    """Order status values."""
    PENDING = "pending"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    PARTIAL_FILL = "partial_fill"


class OrderSide(str, Enum):
    """Order side values."""
    BUY = "buy"
    SELL = "sell"


# =============================================================================
# Validated Pydantic Models
# =============================================================================

class TradingSignalModel(BaseModel):
    """
    Validated trading signal model.
    
    Use for API request validation and external data ingestion.
    """
    model_config = ConfigDict(use_enum_values=True)
    
    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = Field(..., min_length=1, max_length=20)
    signal_type: SignalType
    price: float = Field(..., gt=0)
    quantity: Optional[float] = Field(None, gt=0)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @field_validator('symbol')
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        """Normalize symbol to uppercase."""
        return v.upper().strip()
    
    @field_validator('price')
    @classmethod
    def validate_price(cls, v: float) -> float:
        """Ensure price is positive and reasonable."""
        if v <= 0:
            raise ValueError("Price must be positive")
        if v > 1_000_000:
            raise ValueError("Price seems unreasonably high")
        return round(v, 4)
    
    def to_dataclass(self):
        """Convert to dataclass version for internal use."""
        from src.interfaces import TradingSignal, SignalType as DCSignalType
        return TradingSignal(
            signal_id=self.signal_id,
            symbol=self.symbol,
            signal_type=DCSignalType(self.signal_type),
            price=self.price,
            quantity=self.quantity,
            timestamp=self.timestamp,
            metadata=self.metadata
        )


class OrderModel(BaseModel):
    """
    Validated order model.
    
    Use for API request validation and order creation.
    """
    model_config = ConfigDict(use_enum_values=True)
    
    order_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = Field(..., min_length=1, max_length=20)
    quantity: float = Field(..., gt=0)
    order_type: OrderType
    side: OrderSide
    price: Optional[float] = Field(None, gt=0)
    stop_price: Optional[float] = Field(None, gt=0)
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None
    filled_price: Optional[float] = Field(None, gt=0)
    filled_quantity: Optional[float] = Field(None, ge=0)
    broker: Optional[str] = None
    broker_order_id: Optional[str] = None
    is_dca_order: bool = False
    is_closing: bool = False
    
    @field_validator('symbol')
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        """Normalize symbol to uppercase."""
        return v.upper().strip()
    
    @model_validator(mode='after')
    def validate_order_type_price(self) -> Self:
        """Validate price requirements based on order type."""
        if self.order_type == OrderType.LIMIT and self.price is None:
            raise ValueError("Limit orders require a price")
        
        if self.order_type == OrderType.STOP and self.stop_price is None:
            raise ValueError("Stop orders require a stop price")
        
        if self.order_type == OrderType.STOP_LIMIT:
            if self.price is None or self.stop_price is None:
                raise ValueError("Stop-limit orders require both price and stop price")
        
        # Validate filled consistency
        if self.status == OrderStatus.FILLED:
            if self.filled_price is None or self.filled_quantity is None:
                raise ValueError("Filled orders must have filled_price and filled_quantity")
        
        # Auto-set filled_at if filled_price is set
        if self.filled_price is not None and self.filled_at is None:
            object.__setattr__(self, 'filled_at', datetime.utcnow())
        
        return self
    
    def to_dataclass(self):
        """Convert to dataclass version for internal use."""
        from src.interfaces import Order, OrderType as DCOrderType, OrderSide as DCOrderSide, OrderStatus as DCOrderStatus
        return Order(
            order_id=self.order_id,
            symbol=self.symbol,
            quantity=self.quantity,
            order_type=DCOrderType(self.order_type),
            side=DCOrderSide(self.side),
            price=self.price,
            stop_price=self.stop_price,
            status=DCOrderStatus(self.status),
            created_at=self.created_at,
            filled_at=self.filled_at,
            filled_price=self.filled_price,
            filled_quantity=self.filled_quantity,
            broker=self.broker,
            broker_order_id=self.broker_order_id,
            is_dca_order=self.is_dca_order,
            is_closing=self.is_closing
        )


class PositionModel(BaseModel):
    """
    Validated position model.
    
    Use for API responses and position tracking.
    """
    model_config = ConfigDict(use_enum_values=True)
    
    symbol: str = Field(..., min_length=1, max_length=20)
    quantity: float
    avg_price: float = Field(..., gt=0)
    current_price: float = Field(..., gt=0)
    unrealized_pnl: float
    realized_pnl: float = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    broker: Optional[str] = None
    
    @field_validator('symbol')
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        """Normalize symbol to uppercase."""
        return v.upper().strip()
    
    @model_validator(mode='after')
    def calculate_pnl_if_missing(self) -> Self:
        """Validate/calculate unrealized PnL."""
        if self.quantity != 0 and self.avg_price > 0 and self.current_price > 0:
            expected_pnl = (self.current_price - self.avg_price) * self.quantity
            if self.unrealized_pnl == 0 and expected_pnl != 0:
                object.__setattr__(self, 'unrealized_pnl', round(expected_pnl, 2))
        return self
    
    @property
    def pnl_percent(self) -> float:
        """Calculate P&L as percentage."""
        if self.avg_price <= 0 or self.quantity == 0:
            return 0.0
        return ((self.current_price - self.avg_price) / self.avg_price) * 100
    
    @property
    def market_value(self) -> float:
        """Calculate current market value."""
        return abs(self.quantity * self.current_price)
    
    @property
    def cost_basis(self) -> float:
        """Calculate cost basis."""
        return abs(self.quantity * self.avg_price)
    
    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.quantity > 0
    
    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.quantity < 0
    
    def to_dataclass(self):
        """Convert to dataclass version for internal use."""
        from src.interfaces import Position
        return Position(
            symbol=self.symbol,
            quantity=self.quantity,
            avg_price=self.avg_price,
            current_price=self.current_price,
            unrealized_pnl=self.unrealized_pnl,
            realized_pnl=self.realized_pnl,
            created_at=self.created_at,
            broker=self.broker
        )


class SupportLevelModel(BaseModel):
    """
    Validated support/resistance level model.
    """
    price: float = Field(..., gt=0)
    confidence: float = Field(..., ge=0, le=1)
    method: str = Field(..., min_length=1)
    touches: int = Field(default=0, ge=0)
    last_touch: datetime = Field(default_factory=datetime.utcnow)
    calculated_at: datetime = Field(default_factory=datetime.utcnow)


class SupportLevelDataModel(BaseModel):
    """
    Validated support level data container.
    """
    symbol: str = Field(..., min_length=1, max_length=20)
    timeframe: str = Field(..., min_length=1)
    levels: List[SupportLevelModel] = Field(default_factory=list)
    calculated_at: datetime = Field(default_factory=datetime.utcnow)
    confidence: float = Field(..., ge=0, le=1)
    
    @field_validator('symbol')
    @classmethod
    def uppercase_symbol(cls, v: str) -> str:
        """Normalize symbol to uppercase."""
        return v.upper().strip()
    
    def get_nearest_support(self, current_price: float) -> Optional[SupportLevelModel]:
        """Get the nearest support level below current price."""
        support_levels = [level for level in self.levels if level.price < current_price]
        return max(support_levels, key=lambda x: x.price) if support_levels else None
    
    def get_nearest_resistance(self, current_price: float) -> Optional[SupportLevelModel]:
        """Get the nearest resistance level above current price."""
        resistance_levels = [level for level in self.levels if level.price > current_price]
        return min(resistance_levels, key=lambda x: x.price) if resistance_levels else None


# =============================================================================
# Factory Functions
# =============================================================================

def from_dataclass_signal(signal) -> TradingSignalModel:
    """Create TradingSignalModel from dataclass TradingSignal."""
    return TradingSignalModel(
        signal_id=signal.signal_id,
        symbol=signal.symbol,
        signal_type=signal.signal_type.value,
        price=signal.price,
        quantity=signal.quantity,
        timestamp=signal.timestamp,
        metadata=signal.metadata or {}
    )


def from_dataclass_order(order) -> OrderModel:
    """Create OrderModel from dataclass Order."""
    return OrderModel(
        order_id=order.order_id,
        symbol=order.symbol,
        quantity=order.quantity,
        order_type=order.order_type.value,
        side=order.side.value,
        price=order.price,
        stop_price=order.stop_price,
        status=order.status.value,
        created_at=order.created_at,
        filled_at=order.filled_at,
        filled_price=order.filled_price,
        filled_quantity=order.filled_quantity,
        broker=order.broker,
        broker_order_id=order.broker_order_id,
        is_dca_order=order.is_dca_order,
        is_closing=order.is_closing
    )


def from_dataclass_position(position) -> PositionModel:
    """Create PositionModel from dataclass Position."""
    return PositionModel(
        symbol=position.symbol,
        quantity=position.quantity,
        avg_price=position.avg_price,
        current_price=position.current_price,
        unrealized_pnl=position.unrealized_pnl,
        realized_pnl=position.realized_pnl,
        created_at=position.created_at,
        broker=position.broker
    )
