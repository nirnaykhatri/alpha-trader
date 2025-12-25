"""
Test fakes and stubs for heavy dependencies.

Provides lightweight in-memory implementations that can be used in unit tests
without requiring actual Azure SDK, FastAPI, or broker packages.

These fakes follow the same interfaces as the real implementations but are
completely self-contained with no external dependencies.

Usage:
    from tests.fixtures.fakes import (
        FakeCosmosDBManager,
        FakeOrderManager,
        FakeMarketDataProvider,
    )
    
    # In tests
    db = FakeCosmosDBManager()
    await db.save_position(position)
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from unittest.mock import AsyncMock, Mock
import uuid


# ============================================================================
# Lightweight Data Models (no Pydantic required)
# ============================================================================

class FakeSignalType(Enum):
    """Signal type enum for testing."""
    BUY = "buy"
    SELL = "sell"
    CLOSE = "close"


class FakeOrderSide(Enum):
    """Order side enum for testing."""
    BUY = "buy"
    SELL = "sell"


class FakeOrderType(Enum):
    """Order type enum for testing."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class FakeOrderStatus(Enum):
    """Order status enum for testing."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class FakeTradingSignal:
    """Lightweight trading signal for testing."""
    signal_id: str
    symbol: str
    signal_type: FakeSignalType
    price: float
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FakePosition:
    """Lightweight position for testing."""
    symbol: str
    quantity: float
    avg_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    broker: str = "fake"
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FakeOrder:
    """Lightweight order for testing."""
    order_id: str
    symbol: str
    quantity: float
    side: FakeOrderSide
    order_type: FakeOrderType = FakeOrderType.LIMIT
    price: Optional[float] = None
    status: FakeOrderStatus = FakeOrderStatus.PENDING
    filled_quantity: float = 0.0
    filled_price: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


# ============================================================================
# Fake Database Manager
# ============================================================================

class FakeCosmosDBManager:
    """
    In-memory fake of CosmosDBManager for unit testing.
    
    Stores all data in memory dictionaries. Thread-safe for concurrent access.
    No Azure SDK required.
    """
    
    def __init__(self):
        self._positions: Dict[str, FakePosition] = {}
        self._orders: Dict[str, FakeOrder] = {}
        self._signals: Dict[str, FakeTradingSignal] = {}
        self._trades: List[Dict[str, Any]] = []
        self._initialized = False
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize the fake database (no-op)."""
        self._initialized = True
    
    async def close(self) -> None:
        """Close the fake database (clears data)."""
        async with self._lock:
            self._positions.clear()
            self._orders.clear()
            self._signals.clear()
            self._trades.clear()
            self._initialized = False
    
    async def save_position(self, position: FakePosition) -> str:
        """Save a position to the fake database."""
        async with self._lock:
            self._positions[position.symbol] = position
            return position.symbol
    
    async def get_position(self, symbol: str) -> Optional[FakePosition]:
        """Get a position by symbol."""
        return self._positions.get(symbol)
    
    async def get_all_positions(
        self,
        max_items: int = 100,
        continuation_token: Optional[str] = None,
        exclude_zero_quantity: bool = False,
    ) -> List[FakePosition]:
        """Get all positions with optional filtering."""
        positions = list(self._positions.values())
        if exclude_zero_quantity:
            positions = [p for p in positions if p.quantity != 0]
        return positions[:max_items]
    
    async def save_order(self, order: FakeOrder) -> str:
        """Save an order to the fake database."""
        async with self._lock:
            self._orders[order.order_id] = order
            return order.order_id
    
    async def get_order(self, order_id: str) -> Optional[FakeOrder]:
        """Get an order by ID."""
        return self._orders.get(order_id)
    
    async def get_orders(self, symbol: Optional[str] = None) -> List[FakeOrder]:
        """Get orders, optionally filtered by symbol."""
        orders = list(self._orders.values())
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders
    
    async def save_signal(self, signal: FakeTradingSignal) -> str:
        """Save a signal to the fake database."""
        async with self._lock:
            self._signals[signal.signal_id] = signal
            return signal.signal_id
    
    async def get_signals(self, limit: int = 100) -> List[FakeTradingSignal]:
        """Get recent signals."""
        return list(self._signals.values())[:limit]
    
    async def record_trade(self, trade_data: Dict[str, Any]) -> str:
        """Record a trade."""
        async with self._lock:
            trade_id = str(uuid.uuid4())
            trade_data["id"] = trade_id
            self._trades.append(trade_data)
            return trade_id
    
    def reset(self) -> None:
        """Reset all data (for test cleanup)."""
        self._positions.clear()
        self._orders.clear()
        self._signals.clear()
        self._trades.clear()


# ============================================================================
# Fake Order Manager
# ============================================================================

class FakeOrderManager:
    """
    In-memory fake of OrderManager for unit testing.
    
    Simulates order placement and fills without any broker connection.
    """
    
    def __init__(self, auto_fill: bool = True, fill_delay: float = 0.0):
        self._orders: Dict[str, FakeOrder] = {}
        self._auto_fill = auto_fill
        self._fill_delay = fill_delay
        self._fill_price_offset = 0.0  # Can simulate slippage
    
    async def place_order(
        self,
        symbol: str,
        quantity: float,
        side: FakeOrderSide,
        order_type: FakeOrderType = FakeOrderType.LIMIT,
        price: Optional[float] = None,
    ) -> FakeOrder:
        """Place a fake order."""
        order_id = str(uuid.uuid4())
        order = FakeOrder(
            order_id=order_id,
            symbol=symbol,
            quantity=quantity,
            side=side,
            order_type=order_type,
            price=price,
            status=FakeOrderStatus.SUBMITTED,
        )
        self._orders[order_id] = order
        
        if self._auto_fill:
            if self._fill_delay > 0:
                await asyncio.sleep(self._fill_delay)
            await self._fill_order(order_id, price or 100.0)
        
        return order
    
    async def _fill_order(self, order_id: str, fill_price: float) -> None:
        """Simulate filling an order."""
        if order_id in self._orders:
            order = self._orders[order_id]
            order.status = FakeOrderStatus.FILLED
            order.filled_quantity = order.quantity
            order.filled_price = fill_price + self._fill_price_offset
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        if order_id in self._orders:
            order = self._orders[order_id]
            if order.status in (FakeOrderStatus.PENDING, FakeOrderStatus.SUBMITTED):
                order.status = FakeOrderStatus.CANCELLED
                return True
        return False
    
    async def get_order_status(self, order_id: str) -> Optional[FakeOrderStatus]:
        """Get order status."""
        order = self._orders.get(order_id)
        return order.status if order else None
    
    async def get_active_orders(self, symbol: Optional[str] = None) -> List[FakeOrder]:
        """Get active (unfilled) orders."""
        active_statuses = (FakeOrderStatus.PENDING, FakeOrderStatus.SUBMITTED)
        orders = [o for o in self._orders.values() if o.status in active_statuses]
        if symbol:
            orders = [o for o in orders if o.symbol == symbol]
        return orders


# ============================================================================
# Fake Market Data Provider
# ============================================================================

class FakeMarketDataProvider:
    """
    In-memory fake of MarketDataProvider for unit testing.
    
    Returns configurable prices for symbols.
    """
    
    def __init__(self, default_price: float = 100.0):
        self._prices: Dict[str, float] = {}
        self._quotes: Dict[str, Dict[str, float]] = {}
        self._default_price = default_price
    
    def set_price(self, symbol: str, price: float) -> None:
        """Set the price for a symbol."""
        self._prices[symbol] = price
    
    def set_quote(
        self,
        symbol: str,
        bid: float,
        ask: float,
        bid_size: int = 100,
        ask_size: int = 100,
    ) -> None:
        """Set the quote for a symbol."""
        self._quotes[symbol] = {
            "bid": bid,
            "ask": ask,
            "bid_size": bid_size,
            "ask_size": ask_size,
        }
    
    async def get_current_price(self, symbol: str) -> float:
        """Get current price for a symbol."""
        return self._prices.get(symbol, self._default_price)
    
    async def get_latest_quote(self, symbol: str) -> Dict[str, Any]:
        """Get latest quote for a symbol."""
        if symbol in self._quotes:
            return self._quotes[symbol]
        price = self._prices.get(symbol, self._default_price)
        return {
            "bid": price - 0.01,
            "ask": price + 0.01,
            "bid_size": 100,
            "ask_size": 100,
        }
    
    async def get_historical_data(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        timeframe: str = "1d",
    ) -> List[Dict[str, Any]]:
        """Get historical data (returns empty list in fake)."""
        return []


# ============================================================================
# Fake Risk Manager
# ============================================================================

class FakeRiskManager:
    """
    Fake risk manager for unit testing.
    
    Can be configured to approve or reject trades.
    """
    
    def __init__(self, approve_all: bool = True):
        self._approve_all = approve_all
        self._rejected_symbols: set = set()
        self._max_position_size = 10000.0
    
    def reject_symbol(self, symbol: str) -> None:
        """Configure to reject orders for a specific symbol."""
        self._rejected_symbols.add(symbol)
    
    async def validate_trade(
        self,
        symbol: str,
        quantity: float,
        side: str,
        price: float,
    ) -> bool:
        """Validate if a trade is allowed."""
        if symbol in self._rejected_symbols:
            return False
        if quantity * price > self._max_position_size:
            return False
        return self._approve_all
    
    async def calculate_position_size(
        self,
        symbol: str,
        price: float,
        risk_amount: Optional[float] = None,
    ) -> float:
        """Calculate position size based on risk parameters."""
        return min(100.0, self._max_position_size / price)
    
    async def check_portfolio_risk(self) -> bool:
        """Check if portfolio risk is within limits."""
        return self._approve_all
    
    async def get_risk_metrics(self) -> Dict[str, Any]:
        """Get current risk metrics."""
        return {
            "total_exposure": 0.0,
            "max_drawdown": 0.0,
            "risk_score": 0.5,
        }


# ============================================================================
# Fake Configuration Manager
# ============================================================================

class FakeConfigurationManager:
    """
    Fake configuration manager for unit testing.
    
    In-memory configuration that doesn't require file or Azure access.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self._config = config or self._default_config()
        self._secrets: Dict[str, str] = {}
    
    @staticmethod
    def _default_config() -> Dict[str, Any]:
        """Return default configuration for testing."""
        return {
            "api": {
                "alpaca": {
                    "api_key": "fake-api-key",
                    "secret_key": "fake-secret-key",
                    "base_url": "https://paper-api.alpaca.markets",
                },
                "webhook": {
                    "host": "0.0.0.0",
                    "port": 8080,
                },
            },
            "trading": {
                "default_quantity": 100,
                "max_position_size": 1000,
                "order_type": "limit",
            },
            "database": {
                "url": "fake://localhost/testdb",
            },
            "logging": {
                "level": "DEBUG",
            },
        }
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by dot-notation key."""
        parts = key.split(".")
        value = self._config
        try:
            for part in parts:
                value = value[part]
            return value
        except (KeyError, TypeError):
            return default
    
    def set_config(self, key: str, value: Any) -> None:
        """Set a configuration value."""
        parts = key.split(".")
        config = self._config
        for part in parts[:-1]:
            if part not in config:
                config[part] = {}
            config = config[part]
        config[parts[-1]] = value
    
    def get_secret(self, key: str, default: str = "") -> str:
        """Get a secret value."""
        return self._secrets.get(key, default)
    
    def set_secret(self, key: str, value: str) -> None:
        """Set a secret value (for testing)."""
        self._secrets[key] = value
    
    def is_azure_deployment(self) -> bool:
        """Check if running in Azure (always False for fake)."""
        return False
    
    @property
    def current_environment(self) -> str:
        """Get current environment."""
        return "test"


# ============================================================================
# Factory Functions for Common Test Setups
# ============================================================================

def create_test_signal(
    symbol: str = "AAPL",
    signal_type: FakeSignalType = FakeSignalType.BUY,
    price: float = 150.0,
) -> FakeTradingSignal:
    """Create a test trading signal with defaults."""
    return FakeTradingSignal(
        signal_id=str(uuid.uuid4()),
        symbol=symbol,
        signal_type=signal_type,
        price=price,
    )


def create_test_position(
    symbol: str = "AAPL",
    quantity: float = 100,
    avg_price: float = 150.0,
) -> FakePosition:
    """Create a test position with defaults."""
    return FakePosition(
        symbol=symbol,
        quantity=quantity,
        avg_price=avg_price,
        current_price=avg_price,
    )


def create_test_order(
    symbol: str = "AAPL",
    quantity: float = 100,
    side: FakeOrderSide = FakeOrderSide.BUY,
    price: float = 150.0,
) -> FakeOrder:
    """Create a test order with defaults."""
    return FakeOrder(
        order_id=str(uuid.uuid4()),
        symbol=symbol,
        quantity=quantity,
        side=side,
        price=price,
    )


# ============================================================================
# Export all fakes and utilities
# ============================================================================

__all__ = [
    # Enums
    "FakeSignalType",
    "FakeOrderSide",
    "FakeOrderType",
    "FakeOrderStatus",
    # Data models
    "FakeTradingSignal",
    "FakePosition",
    "FakeOrder",
    # Fakes
    "FakeCosmosDBManager",
    "FakeOrderManager",
    "FakeMarketDataProvider",
    "FakeRiskManager",
    "FakeConfigurationManager",
    # Factory functions
    "create_test_signal",
    "create_test_position",
    "create_test_order",
]
