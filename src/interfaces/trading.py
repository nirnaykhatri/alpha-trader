"""
Trading Interfaces.

This module defines interfaces for core trading operations including
signal processing, order management, position management, and market data.

Canonical location for:
- ISignalListener
- IOrderManager
- IPositionManager
- ISupportCalculator
- ITrailingProfitManager
- IRiskManager
- IMarketDataProvider
- IAccountProvider

Author: Trading Bot Team
Version: 1.0.0
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.interfaces.core import (
        TradingSignal,
        Order,
        Position,
        SupportLevel,
        OrderStatus,
    )


# =============================================================================
# Signal Interfaces
# =============================================================================

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
    async def process_signal(self, signal_data: Dict[str, Any]) -> "TradingSignal":
        """Process incoming signal data."""
        pass


# =============================================================================
# Order Management Interfaces
# =============================================================================

class IOrderManager(ABC):
    """Interface for managing trading orders."""
    
    @abstractmethod
    async def place_order(self, order: "Order") -> str:
        """Place a new order. Returns order ID."""
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        pass
    
    @abstractmethod
    async def get_order_status(self, order_id: str) -> "OrderStatus":
        """Get the current status of an order."""
        pass
    
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List["Order"]:
        """Get all open orders, optionally filtered by symbol."""
        pass


# =============================================================================
# Position Management Interfaces
# =============================================================================

class IPositionManager(ABC):
    """Interface for managing positions."""
    
    @abstractmethod
    async def get_position(self, symbol: str) -> Optional["Position"]:
        """Get current position for a symbol."""
        pass
    
    @abstractmethod
    async def get_all_positions(
        self, 
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List["Position"]:
        """
        Get all current positions with optional pagination.
        
        Args:
            limit: Maximum number of positions to return. None for all positions.
            offset: Number of positions to skip (for pagination). Defaults to 0.
            
        Returns:
            List of positions, optionally paginated.
        """
        pass
    
    @abstractmethod
    async def update_position(self, symbol: str, quantity: float, price: float) -> None:
        """Update position after a trade."""
        pass


# =============================================================================
# Technical Analysis Interfaces
# =============================================================================

class ISupportCalculator(ABC):
    """Interface for calculating support levels."""
    
    @abstractmethod
    async def calculate_support(self, symbol: str, timeframe: str) -> "SupportLevel":
        """Calculate support level for a symbol and timeframe."""
        pass


class ITrailingProfitManager(ABC):
    """Interface for managing trailing profit logic."""
    
    @abstractmethod
    async def should_trail(self, position: "Position", current_price: float) -> bool:
        """Determine if trailing should be activated."""
        pass
    
    @abstractmethod
    async def calculate_trailing_stop(self, position: "Position", 
                                    current_price: float) -> float:
        """Calculate trailing stop price."""
        pass
    
    @abstractmethod
    async def should_take_profit(self, position: "Position", 
                               current_price: float) -> bool:
        """Determine if profit should be taken."""
        pass


# =============================================================================
# Risk Management Interfaces
# =============================================================================

class IRiskManager(ABC):
    """Interface for risk management."""
    
    @abstractmethod
    async def validate_order(self, order: "Order") -> bool:
        """Validate order against risk parameters."""
        pass
    
    @abstractmethod
    async def calculate_position_size(self, symbol: str, signal: "TradingSignal") -> float:
        """Calculate appropriate position size."""
        pass
    
    @abstractmethod
    async def get_max_exposure(self, symbol: str) -> float:
        """Get maximum allowed exposure for a symbol."""
        pass


# =============================================================================
# Market Data Interfaces
# =============================================================================

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


# =============================================================================
# Account Interfaces
# =============================================================================

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


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "ISignalListener",
    "IOrderManager",
    "IPositionManager",
    "ISupportCalculator",
    "ITrailingProfitManager",
    "IRiskManager",
    "IMarketDataProvider",
    "IAccountProvider",
]
