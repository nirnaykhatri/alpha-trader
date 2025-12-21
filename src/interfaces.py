"""
Core interfaces and abstract base classes for the trading bot system.
This module defines the contracts that all implementations must follow.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid


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


class ISignalListener(ABC):
    """Interface for receiving trading signals."""
    
    @abstractmethod
    async def start_listening(self) -> None:
        """Start listening for signals."""
        pass
    
    @abstractmethod
    async def stop_listening(self) -> None:
        """Stop listening for signals."""
        pass
    
    @abstractmethod
    async def process_signal(self, signal_data: Dict[str, Any]) -> TradingSignal:
        """Process incoming signal data."""
        pass


class IOrderManager(ABC):
    """Interface for managing trading orders."""
    
    @abstractmethod
    async def place_order(self, order: Order) -> str:
        """Place a new order. Returns order ID."""
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        pass
    
    @abstractmethod
    async def get_order_status(self, order_id: str) -> OrderStatus:
        """Get the current status of an order."""
        pass
    
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all open orders, optionally filtered by symbol."""
        pass


class IPositionManager(ABC):
    """Interface for managing positions."""
    
    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get current position for a symbol."""
        pass
    
    @abstractmethod
    async def get_all_positions(self) -> List[Position]:
        """Get all current positions."""
        pass
    
    @abstractmethod
    async def update_position(self, symbol: str, quantity: float, price: float) -> None:
        """Update position after a trade."""
        pass


class ISupportCalculator(ABC):
    """Interface for calculating support levels."""
    
    @abstractmethod
    async def calculate_support(self, symbol: str, timeframe: str) -> SupportLevel:
        """Calculate support level for a symbol and timeframe."""
        pass


class ITrailingProfitManager(ABC):
    """Interface for managing trailing profit logic."""
    
    @abstractmethod
    async def should_trail(self, position: Position, current_price: float) -> bool:
        """Determine if trailing should be activated."""
        pass
    
    @abstractmethod
    async def calculate_trailing_stop(self, position: Position, 
                                    current_price: float) -> float:
        """Calculate trailing stop price."""
        pass
    
    @abstractmethod
    async def should_take_profit(self, position: Position, 
                               current_price: float) -> bool:
        """Determine if profit should be taken."""
        pass


class IRiskManager(ABC):
    """Interface for risk management."""
    
    @abstractmethod
    async def validate_order(self, order: Order) -> bool:
        """Validate order against risk parameters."""
        pass
    
    @abstractmethod
    async def calculate_position_size(self, symbol: str, signal: TradingSignal) -> float:
        """Calculate appropriate position size."""
        pass
    
    @abstractmethod
    async def get_max_exposure(self, symbol: str) -> float:
        """Get maximum allowed exposure for a symbol."""
        pass


class IMarketDataProvider(ABC):
    """Interface for market data access."""
    
    @abstractmethod
    async def get_current_price(self, symbol: str) -> float:
        """Get current market price for a symbol."""
        pass
    
    @abstractmethod
    async def get_historical_data(self, symbol: str, timeframe: str, 
                                count: int) -> List[Dict[str, Any]]:
        """Get historical market data."""
        pass


class IConfigurationManager(ABC):
    """Interface for configuration management."""
    
    @abstractmethod
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        pass
    
    @abstractmethod
    def set_config(self, key: str, value: Any) -> None:
        """Set configuration value."""
        pass
    
    @abstractmethod
    def reload_config(self) -> None:
        """Reload configuration from source."""
        pass


class IAccountProvider(ABC):
    """Interface for accessing account information."""
    
    @abstractmethod
    async def get_account_value(self) -> float:
        """Get current account value/equity."""
        pass
    
    @abstractmethod
    async def get_buying_power(self) -> float:
        """Get available buying power."""
        pass
    
    @abstractmethod
    async def get_portfolio_value(self) -> float:
        """Get total portfolio value including positions."""
        pass
    
    @abstractmethod
    async def get_cash(self) -> float:
        """Get available cash (not including margin)."""
        pass


class IAsyncContextManager(ABC):
    """Interface for components requiring async lifecycle management."""
    
    @abstractmethod
    async def start(self) -> None:
        """Start the component."""
        pass
        
    @abstractmethod
    async def stop(self) -> None:
        """Stop the component and cleanup resources."""
        pass
