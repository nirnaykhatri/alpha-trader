"""
Broker-specific interfaces and types.
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Optional, Dict, Any
from src.interfaces import Order, Position, OrderStatus

class BrokerType(Enum):
    """
    Supported broker types.
    
    Attributes:
        ALPACA: Alpaca Markets.
        TASTYTRADE: Tastytrade (formerly Tastyworks).
    """
    ALPACA = "alpaca"
    TASTYTRADE = "tastytrade"

class IBrokerOrderExecutor(ABC):
    """
    Interface for broker-specific order execution.
    
    Implementations of this interface handle the specifics of placing,
    cancelling, and tracking orders with a particular broker API.
    """
    
    @abstractmethod
    async def place_order(self, order: Order) -> str:
        """
        Place an order with the broker.
        
        Args:
            order: The order to place.
            
        Returns:
            str: The broker-assigned order ID.
            
        Raises:
            OrderExecutionException: If the order cannot be placed.
        """
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order with the broker.
        
        Args:
            order_id: The broker order ID to cancel.
            
        Returns:
            bool: True if cancellation request was successful.
        """
        pass
    
    @abstractmethod
    async def get_order_status(self, order_id: str) -> OrderStatus:
        """
        Get the status of an order from the broker.
        
        Args:
            order_id: The broker order ID.
            
        Returns:
            OrderStatus: The current status of the order.
        """
        pass
    
    @abstractmethod
    async def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get complete order details including fill information from the broker.
        
        This method provides full order data including filled_quantity, filled_price,
        and status, which is essential for accurate fill tracking and reconciliation.
        
        Args:
            order_id: The broker order ID.
            
        Returns:
            Optional[Order]: The complete order with fill details, or None if not found.
        """
        pass
    
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get open orders from the broker.
        
        Args:
            symbol: Optional symbol to filter orders by.
            
        Returns:
            List[Order]: List of open orders.
        """
        pass

class IBrokerAccountProvider(ABC):
    """
    Interface for broker-specific account information.
    
    Implementations of this interface handle retrieving account balances,
    buying power, and positions from a particular broker API.
    """
    
    @abstractmethod
    async def get_account_value(self) -> float:
        """
        Get total account value/equity.
        
        Returns:
            float: Total account equity (cash + positions).
        """
        pass
    
    @abstractmethod
    async def get_buying_power(self) -> float:
        """
        Get available buying power.
        
        Returns:
            float: Available buying power for new orders.
        """
        pass
    
    @abstractmethod
    async def get_cash(self) -> float:
        """
        Get available cash.
        
        Returns:
            float: Settled cash available for withdrawal or trading.
        """
        pass
        
    @abstractmethod
    async def get_positions(self) -> List[Position]:
        """
        Get all open positions from the broker.
        
        Returns:
            List[Position]: List of open positions.
        """
        pass

class IBrokerMarketDataProvider(ABC):
    """
    Interface for broker-specific market data.
    
    Implementations of this interface handle retrieving real-time and
    historical market data from a particular broker API.
    """
    
    @abstractmethod
    async def get_current_price(self, symbol: str) -> float:
        """
        Get current price for a symbol.
        
        Args:
            symbol: The symbol to get the price for.
            
        Returns:
            float: The current market price.
        """
        pass
        
    @abstractmethod
    async def get_historical_data(self, symbol: str, timeframe: str, count: int) -> List[Dict[str, Any]]:
        """
        Get historical data (if supported).
        
        Args:
            symbol: The symbol to get data for.
            timeframe: The timeframe (e.g., '1m', '1h', '1d').
            count: Number of bars to retrieve.
            
        Returns:
            List[Dict[str, Any]]: List of historical data points.
        """
        pass

class IBrokerRouter(ABC):
    """
    Interface for routing requests to the appropriate broker.
    
    The router determines which broker handles a specific symbol and provides
    access to the appropriate broker-specific services.
    """
    
    @abstractmethod
    def get_broker_for_symbol(self, symbol: str) -> BrokerType:
        """
        Determine which broker to use for a symbol.
        
        Args:
            symbol: The symbol to route.
            
        Returns:
            BrokerType: The broker type responsible for this symbol.
        """
        pass
        
    @abstractmethod
    def get_order_executor(self, broker: BrokerType) -> IBrokerOrderExecutor:
        """
        Get the order executor for a specific broker.
        
        Args:
            broker: The broker type.
            
        Returns:
            IBrokerOrderExecutor: The order executor for the specified broker.
        """
        pass
        
    @abstractmethod
    def get_account_provider(self, broker: BrokerType) -> IBrokerAccountProvider:
        """
        Get the account provider for a specific broker.
        
        Args:
            broker: The broker type.
            
        Returns:
            IBrokerAccountProvider: The account provider for the specified broker.
        """
        pass
        
    @abstractmethod
    def get_market_data_provider(self, broker: BrokerType) -> IBrokerMarketDataProvider:
        """
        Get the market data provider for a specific broker.
        
        Args:
            broker: The broker type.
            
        Returns:
            IBrokerMarketDataProvider: The market data provider for the specified broker.
        """
        pass
