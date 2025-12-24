"""
Admin Service Interfaces.

Defines interfaces for admin operations following Interface Segregation Principle.
Each interface handles a specific domain of admin functionality.

Author: Trading Bot Team
Version: 1.0.0
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from src.interfaces import Order, OrderSide, OrderType


# =============================================================================
# Data Transfer Objects
# =============================================================================

@dataclass
class OrderDTO:
    """Order data transfer object."""
    
    id: str
    symbol: str
    side: str
    quantity: float
    filled_quantity: float
    order_type: str
    status: str
    limit_price: Optional[float] = None
    created_at: Optional[datetime] = None


@dataclass
class PositionDTO:
    """Position data transfer object."""
    
    symbol: str
    quantity: float
    avg_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    market_value: float
    direction: str  # 'long' or 'short'


class BotState(str, Enum):
    """Bot operational states."""
    
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass
class BotStatus:
    """Bot status information."""
    
    state: BotState
    uptime_seconds: float
    positions_count: int
    pending_orders: int
    last_signal_time: Optional[datetime] = None
    version: Optional[str] = None


# =============================================================================
# Service Interfaces
# =============================================================================

class IOrderService(ABC):
    """Interface for order management operations."""
    
    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        order_type: OrderType,
        limit_price: Optional[Decimal] = None,
        time_in_force: str = "day"
    ) -> str:
        """
        Place a new order.
        
        Args:
            symbol: Trading symbol
            side: Buy or sell
            quantity: Order quantity
            order_type: Market or limit
            limit_price: Limit price (required for limit orders)
            time_in_force: Order duration
            
        Returns:
            Order ID
            
        Raises:
            OrderException: If order placement fails
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order.
        
        Args:
            order_id: ID of order to cancel
            
        Returns:
            True if cancelled successfully
        """
        pass
    
    @abstractmethod
    async def get_pending_orders(self) -> List[OrderDTO]:
        """
        Get all pending (open) orders.
        
        Returns:
            List of pending orders
        """
        pass
    
    @abstractmethod
    async def get_order(self, order_id: str) -> Optional[OrderDTO]:
        """
        Get order by ID.
        
        Args:
            order_id: Order ID
            
        Returns:
            Order if found, None otherwise
        """
        pass


class IPositionService(ABC):
    """Interface for position management operations."""
    
    @abstractmethod
    async def get_positions(self) -> List[PositionDTO]:
        """
        Get all open positions.
        
        Returns:
            List of positions
        """
        pass
    
    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[PositionDTO]:
        """
        Get position for a specific symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Position if found, None otherwise
        """
        pass
    
    @abstractmethod
    async def close_position(
        self,
        symbol: str,
        quantity: Optional[Decimal] = None,
        order_type: OrderType = OrderType.MARKET,
        limit_price: Optional[Decimal] = None
    ) -> str:
        """
        Close a position (fully or partially).
        
        Args:
            symbol: Trading symbol
            quantity: Amount to close (None = close all)
            order_type: Market or limit
            limit_price: Limit price for limit orders
            
        Returns:
            Close order ID
            
        Raises:
            PositionException: If position not found or close fails
        """
        pass
    
    @abstractmethod
    async def close_all_positions(self, order_type: OrderType = OrderType.MARKET) -> Dict[str, str]:
        """
        Close all open positions.
        
        Args:
            order_type: Market or limit
            
        Returns:
            Dict mapping symbol to close order ID
        """
        pass


class IBotLifecycleService(ABC):
    """Interface for bot lifecycle management."""
    
    @abstractmethod
    async def get_status(self) -> BotStatus:
        """
        Get current bot status.
        
        Returns:
            Bot status information
        """
        pass
    
    @abstractmethod
    async def start(self) -> bool:
        """
        Start the bot.
        
        Returns:
            True if started successfully
        """
        pass
    
    @abstractmethod
    async def stop(self) -> bool:
        """
        Stop the bot gracefully.
        
        Returns:
            True if stopped successfully
        """
        pass
    
    @abstractmethod
    async def pause(self) -> bool:
        """
        Pause trading (no new positions, manage existing).
        
        Returns:
            True if paused successfully
        """
        pass
    
    @abstractmethod
    async def resume(self) -> bool:
        """
        Resume trading from paused state.
        
        Returns:
            True if resumed successfully
        """
        pass


class IConfigService(ABC):
    """Interface for configuration management."""
    
    @abstractmethod
    async def get_config(self, section: Optional[str] = None) -> Dict[str, Any]:
        """
        Get configuration values.
        
        Args:
            section: Optional section to get (e.g., 'dca', 'risk')
            
        Returns:
            Configuration dictionary
        """
        pass
    
    @abstractmethod
    async def update_config(self, section: str, settings: Dict[str, Any]) -> bool:
        """
        Update configuration values.
        
        Args:
            section: Configuration section
            settings: Settings to update
            
        Returns:
            True if updated successfully
        """
        pass
    
    @abstractmethod
    async def reload_config(self) -> bool:
        """
        Reload configuration from sources.
        
        Returns:
            True if reloaded successfully
        """
        pass


class IRiskValidationService(ABC):
    """Interface for order risk validation."""
    
    @abstractmethod
    async def validate_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        price: Optional[Decimal] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Validate order against risk parameters.
        
        Args:
            symbol: Trading symbol
            side: Buy or sell
            quantity: Order quantity
            price: Expected price (for limit orders)
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        pass
    
    @abstractmethod
    async def get_risk_limits(self) -> Dict[str, Any]:
        """
        Get current risk limits.
        
        Returns:
            Risk limits configuration
        """
        pass


class IFundService(ABC):
    """Interface for fund management operations."""
    
    @abstractmethod
    async def get_account_summary(self) -> Dict[str, Any]:
        """
        Get account summary.
        
        Returns:
            Account summary with equity, cash, buying power
        """
        pass
    
    @abstractmethod
    async def record_deposit(self, amount: Decimal, notes: Optional[str] = None) -> str:
        """
        Record a deposit.
        
        Args:
            amount: Deposit amount
            notes: Optional notes
            
        Returns:
            Transaction ID
        """
        pass
    
    @abstractmethod
    async def record_withdrawal(self, amount: Decimal, notes: Optional[str] = None) -> str:
        """
        Record a withdrawal.
        
        Args:
            amount: Withdrawal amount
            notes: Optional notes
            
        Returns:
            Transaction ID
        """
        pass
    
    @abstractmethod
    async def allocate_funds(self, symbol: str, amount: Decimal) -> bool:
        """
        Allocate funds to a symbol.
        
        Args:
            symbol: Trading symbol
            amount: Amount to allocate
            
        Returns:
            True if allocated successfully
        """
        pass
