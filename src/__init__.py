"""
Trading Bot - A scalable, configurable trading bot system.
"""

__version__ = "1.0.0"
__author__ = "Trading Bot Team"
__email__ = "support@tradingbot.com"

# Core imports for easy access
from .interfaces import (
    TradingSignal, Order, Position, SupportLevel,
    SignalType, OrderType, OrderSide, OrderStatus,
    ISignalListener, IOrderManager, IPositionManager,
    ISupportCalculator, ITrailingProfitManager, IRiskManager,
    IMarketDataProvider, IConfigurationManager
)

from .exceptions import (
    TradingBotException, SignalProcessingException,
    OrderExecutionException, MarketDataException,
    RiskManagementException, ConfigurationException,
    APIException, ValidationException,
    InsufficientFundsException, PositionNotFoundException
)

__all__ = [
    # Data models
    "TradingSignal", "Order", "Position", "SupportLevel",
    
    # Enums
    "SignalType", "OrderType", "OrderSide", "OrderStatus",
    
    # Interfaces
    "ISignalListener", "IOrderManager", "IPositionManager",
    "ISupportCalculator", "ITrailingProfitManager", "IRiskManager",
    "IMarketDataProvider", "IConfigurationManager",
    
    # Exceptions
    "TradingBotException", "SignalProcessingException",
    "OrderExecutionException", "MarketDataException",
    "RiskManagementException", "ConfigurationException",
    "APIException", "ValidationException",
    "InsufficientFundsException", "PositionNotFoundException"
]
