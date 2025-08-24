"""
Broker Abstraction Interfaces - Universal interfaces for supporting multiple brokers.
Provides complete abstraction layer for trading clients, market data, and broker-specific functionality.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Union, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

# Import exchange-aware market hours
try:
    from .exchange_market_hours import (
        Exchange, ExchangeSchedule, MarketStatus, TradingSession,
        IMultiExchangeMarketHoursManager
    )
except ImportError:
    # Fallback definitions if exchange_market_hours not available
    class Exchange(Enum):
        NYSE = "NYSE"
        NASDAQ = "NASDAQ"
        LSE = "LSE"
        TSE = "TSE"
        CRYPTO = "CRYPTO"
        FOREX = "FOREX"
    
    class TradingSession(Enum):
        PREMARKET = "premarket"
        REGULAR = "regular"
        POSTMARKET = "postmarket"
        LUNCH_BREAK = "lunch_break"
        CLOSED = "closed"


class BrokerType(Enum):
    """Supported broker types."""
    ALPACA = "alpaca"
    MOCK = "mock"
    INTERACTIVE_BROKERS = "interactive_brokers"
    TD_AMERITRADE = "td_ameritrade"
    E_TRADE = "e_trade"
    SCHWAB = "schwab"
    ROBINHOOD = "robinhood"
    WEBULL = "webull"
    CUSTOM = "custom"


class OrderStatus(Enum):
    """Universal order status across all brokers."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class OrderSide(Enum):
    """Universal order side."""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Universal order types."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class TimeInForce(Enum):
    """Universal time in force options."""
    DAY = "day"
    GTC = "gtc"  # Good Till Cancelled
    IOC = "ioc"  # Immediate or Cancel
    FOK = "fok"  # Fill or Kill


@dataclass
class BrokerCredentials:
    """Universal broker credentials container."""
    broker_type: BrokerType
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    base_url: Optional[str] = None
    environment: str = "paper"  # "paper" or "live"
    additional_params: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.additional_params is None:
            self.additional_params = {}


@dataclass
class UniversalOrder:
    """Universal order representation across all brokers."""
    symbol: str
    side: OrderSide
    type: OrderType
    quantity: float
    time_in_force: TimeInForce = TimeInForce.DAY
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    extended_hours: bool = False
    client_order_id: Optional[str] = None
    
    # Broker-specific parameters
    broker_specific_params: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.broker_specific_params is None:
            self.broker_specific_params = {}


@dataclass
class OrderResponse:
    """Universal order response from brokers."""
    broker_order_id: str
    client_order_id: Optional[str]
    symbol: str
    side: OrderSide
    status: OrderStatus
    quantity: float
    filled_quantity: float = 0.0
    average_fill_price: Optional[float] = None
    submitted_at: Optional[datetime] = None
    filled_at: Optional[datetime] = None
    broker_type: Optional[BrokerType] = None
    
    # Raw broker response for debugging
    raw_response: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.raw_response is None:
            self.raw_response = {}


@dataclass
class Position:
    """Universal position representation."""
    symbol: str
    quantity: float
    average_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    broker_type: Optional[BrokerType] = None
    
    @property
    def is_long(self) -> bool:
        return self.quantity > 0
    
    @property
    def is_short(self) -> bool:
        return self.quantity < 0


@dataclass
class AccountInfo:
    """Universal account information."""
    account_id: str
    broker_type: BrokerType
    buying_power: float
    equity: float
    cash: float
    portfolio_value: float
    day_trading_buying_power: Optional[float] = None
    pattern_day_trader: bool = False
    trade_suspended_by_user: bool = False
    trading_blocked: bool = False
    
    # Raw broker account data
    raw_account_data: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.raw_account_data is None:
            self.raw_account_data = {}


@dataclass
class MarketQuote:
    """Universal market quote representation."""
    symbol: str
    bid_price: Optional[float]
    ask_price: Optional[float]
    bid_size: Optional[int]
    ask_size: Optional[int]
    last_price: Optional[float]
    last_size: Optional[int]
    timestamp: datetime
    broker_type: Optional[BrokerType] = None
    
    @property
    def spread(self) -> Optional[float]:
        if self.bid_price and self.ask_price:
            return self.ask_price - self.bid_price
        return None
    
    @property
    def mid_price(self) -> Optional[float]:
        if self.bid_price and self.ask_price:
            return (self.bid_price + self.ask_price) / 2
        return None


@dataclass
class HistoricalBar:
    """Universal historical bar representation."""
    symbol: str
    timestamp: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: int
    vwap: Optional[float] = None
    broker_type: Optional[BrokerType] = None


# ===== CORE INTERFACES =====

class ITradingClient(ABC):
    """Universal trading client interface for all brokers."""
    
    @property
    @abstractmethod
    def broker_type(self) -> BrokerType:
        """Return the broker type for this client."""
        pass
    
    @abstractmethod
    async def submit_order(self, order: UniversalOrder) -> OrderResponse:
        """Submit an order to the broker."""
        pass
    
    @abstractmethod
    async def get_order_status(self, broker_order_id: str) -> OrderResponse:
        """Get status of an existing order."""
        pass
    
    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel an existing order."""
        pass
    
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """Get all current positions."""
        pass
    
    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for a specific symbol."""
        pass
    
    @abstractmethod
    async def get_account_info(self) -> AccountInfo:
        """Get account information."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close the trading client connection."""
        pass


class IMarketDataProvider(ABC):
    """Universal market data provider interface."""
    
    @property
    @abstractmethod
    def broker_type(self) -> BrokerType:
        """Return the broker type for this provider."""
        pass
    
    @abstractmethod
    async def get_current_price(self, symbol: str) -> float:
        """Get current market price for a symbol."""
        pass
    
    @abstractmethod
    async def get_quote(self, symbol: str) -> MarketQuote:
        """Get current quote for a symbol."""
        pass
    
    @abstractmethod
    async def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[HistoricalBar]:
        """Get historical price data."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close the market data provider connection."""
        pass


class IBrokerProvider(ABC):
    """Universal broker provider interface - combines trading and market data."""
    
    @property
    @abstractmethod
    def broker_type(self) -> BrokerType:
        """Return the broker type."""
        pass
    
    @property
    @abstractmethod
    def trading_client(self) -> ITradingClient:
        """Get the trading client."""
        pass
    
    @property
    @abstractmethod
    def market_data_provider(self) -> IMarketDataProvider:
        """Get the market data provider."""
        pass
    
    @abstractmethod
    async def initialize(self, credentials: BrokerCredentials) -> None:
        """Initialize the broker provider with credentials."""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if broker connection is healthy."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close all broker connections."""
        pass
    
    @abstractmethod
    def supports_extended_hours(self) -> bool:
        """Check if broker supports extended hours trading."""
        pass
    
    @abstractmethod
    def supports_symbol(self, symbol: str) -> bool:
        """Check if broker supports trading this symbol."""
        pass
    
    @abstractmethod
    def get_supported_order_types(self) -> List[OrderType]:
        """Get list of supported order types."""
        pass
    
    @abstractmethod
    def get_supported_time_in_force(self) -> List[TimeInForce]:
        """Get list of supported time in force options."""
        pass
    
    @abstractmethod
    def get_supported_exchanges(self) -> List[Exchange]:
        """Get list of exchanges supported by this broker."""
        pass
    
    @abstractmethod
    def supports_exchange(self, exchange: Exchange) -> bool:
        """Check if broker supports trading on this exchange."""
        pass
    
    @abstractmethod
    async def get_symbol_exchange(self, symbol: str) -> Optional[Exchange]:
        """Get the exchange where this symbol is traded by this broker."""
        pass


class IMarketStatusProvider(ABC):
    """Universal market status provider interface - now exchange-aware."""
    
    @abstractmethod
    async def is_market_open(self, exchange: Optional[Exchange] = None) -> bool:
        """Check if market is currently open for the exchange."""
        pass
    
    @abstractmethod
    async def get_market_hours(self, exchange: Optional[Exchange] = None, date: Optional[datetime] = None) -> Dict[str, Any]:
        """Get market hours for a specific exchange and date."""
        pass
    
    @abstractmethod
    async def is_trading_day(self, exchange: Optional[Exchange] = None, date: Optional[datetime] = None) -> bool:
        """Check if given date is a trading day for the exchange."""
        pass
    
    @abstractmethod
    async def get_market_status(self, exchange: Optional[Exchange] = None) -> MarketStatus:
        """Get detailed market status for the exchange."""
        pass


# ===== BROKER ROUTING INTERFACES =====

@dataclass
class SymbolBrokerMapping:
    """Maps symbols to specific brokers."""
    symbol: str
    broker_type: BrokerType
    priority: int = 1  # Higher priority = preferred broker for this symbol
    is_primary: bool = True
    
    # Symbol-specific broker settings
    extended_hours_enabled: bool = False
    max_position_size: Optional[float] = None
    broker_specific_settings: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.broker_specific_settings is None:
            self.broker_specific_settings = {}


class IBrokerRouter(ABC):
    """Interface for routing trading decisions to appropriate brokers."""
    
    @abstractmethod
    async def get_broker_for_symbol(self, symbol: str) -> BrokerType:
        """Get the appropriate broker for a symbol."""
        pass
    
    @abstractmethod
    async def get_trading_client_for_symbol(self, symbol: str) -> ITradingClient:
        """Get trading client for a specific symbol."""
        pass
    
    @abstractmethod
    async def get_market_data_provider_for_symbol(self, symbol: str) -> IMarketDataProvider:
        """Get market data provider for a specific symbol."""
        pass
    
    @abstractmethod
    def add_symbol_mapping(self, mapping: SymbolBrokerMapping) -> None:
        """Add or update symbol-to-broker mapping."""
        pass
    
    @abstractmethod
    def remove_symbol_mapping(self, symbol: str) -> None:
        """Remove symbol-to-broker mapping."""
        pass
    
    @abstractmethod
    def get_all_mappings(self) -> List[SymbolBrokerMapping]:
        """Get all symbol-to-broker mappings."""
        pass


class IBrokerFactory(ABC):
    """Factory interface for creating broker providers."""
    
    @abstractmethod
    def create_broker_provider(
        self, 
        broker_type: BrokerType, 
        credentials: BrokerCredentials
    ) -> IBrokerProvider:
        """Create a broker provider instance."""
        pass
    
    @abstractmethod
    def get_supported_broker_types(self) -> List[BrokerType]:
        """Get list of supported broker types."""
        pass
    
    @abstractmethod
    def is_broker_supported(self, broker_type: BrokerType) -> bool:
        """Check if a broker type is supported."""
        pass