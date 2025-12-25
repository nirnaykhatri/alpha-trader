"""
Trading Bot Interfaces Package.

This package provides all core interfaces, data models, and type aliases
for the trading bot system. It is organized by domain for clarity:

- core.py: Data models and enums (TradingSignal, Order, Position, etc.)
- callbacks.py: Callback type aliases for event-driven patterns
- trading.py: Trading operation interfaces (IOrderManager, IPositionManager, etc.)
- config.py: Configuration interfaces (IConfigurationManager, etc.)
- lifecycle.py: Lifecycle interfaces (IAsyncContextManager, IAsyncResource)
- strategy.py: Strategy interfaces (ITradingStrategy, IDCAPlanner, etc.)

CANONICAL INTERFACE LOCATIONS:
==============================
- Database interfaces: src/database/database_interface.py
  - IDatabaseManager (database operations)
  - IBotRepository (bot persistence)
  
- Broker interfaces: src/broker/interfaces.py
  - IBrokerOrderExecutor, IBrokerAccountProvider, IBrokerMarketDataProvider
  - IBrokerRouter, BrokerType
  
- Bot Engine interfaces: src/bot_engine/interfaces.py
  - IBotRunner, IBotEngineManager, IMarketDataHub
  - ISignalRouter, IBrokerConnectionPool

IMPORTANT:
==========
Do NOT import database interfaces (IDatabaseManager, IBotRepository) from this
module. Use the canonical location: `from src.database.database_interface import ...`

This ensures clear ownership and prevents interface/implementation drift.

Author: Trading Bot Team
Version: 2.0.0 - Reorganized by domain
"""

# =============================================================================
# Core Data Models and Enums
# =============================================================================
from src.interfaces.core import (
    # Enums
    SignalType,
    OrderType,
    OrderStatus,
    OrderSide,
    # Data classes
    TradingSignal,
    Order,
    Position,
    SupportLevel,
    SupportLevelData,
)

# =============================================================================
# Callback Type Aliases
# =============================================================================
from src.interfaces.callbacks import (
    EventData,
    SignalCallback,
    ConfigChangeCallback,
    OrderCallback,
    PositionCallback,
    AsyncEventCallback,
    AsyncSignalCallback,
    AsyncOrderCallback,
    AsyncPositionCallback,
    AsyncErrorCallback,
    ClosePositionCallback,
)

# =============================================================================
# Trading Interfaces
# =============================================================================
from src.interfaces.trading import (
    ISignalListener,
    IOrderManager,
    IPositionManager,
    ISupportCalculator,
    ITrailingProfitManager,
    IRiskManager,
    IMarketDataProvider,
    IAccountProvider,
)

# =============================================================================
# Configuration Interfaces
# =============================================================================
from src.interfaces.config import (
    IConfigurationManager,
    IAsyncConfigurationManager,
)

# =============================================================================
# Lifecycle Interfaces
# =============================================================================
from src.interfaces.lifecycle import (
    IAsyncContextManager,
    IAsyncResource,
)

# =============================================================================
# Strategy Interfaces
# =============================================================================
from src.interfaces.strategy import (
    # Data classes
    StrategyEvaluation,
    DCADecision,
    # Type aliases
    PositionStateType,
    # Interfaces
    ITradingStrategy,
    IDCAPlanner,
    ITrailingManager,
)

# =============================================================================
# Exports (Public API)
# =============================================================================
__all__ = [
    # === Core Data Models ===
    "TradingSignal",
    "Order",
    "Position",
    "SupportLevel",
    "SupportLevelData",
    
    # === Enums ===
    "SignalType",
    "OrderType",
    "OrderStatus",
    "OrderSide",
    
    # === Callback Type Aliases ===
    "EventData",
    "SignalCallback",
    "ConfigChangeCallback",
    "OrderCallback",
    "PositionCallback",
    "AsyncEventCallback",
    "AsyncSignalCallback",
    "AsyncOrderCallback",
    "AsyncPositionCallback",
    "AsyncErrorCallback",
    "ClosePositionCallback",
    
    # === Trading Interfaces ===
    "ISignalListener",
    "IOrderManager",
    "IPositionManager",
    "ISupportCalculator",
    "ITrailingProfitManager",
    "IRiskManager",
    "IMarketDataProvider",
    "IAccountProvider",
    
    # === Configuration Interfaces ===
    "IConfigurationManager",
    "IAsyncConfigurationManager",
    
    # === Lifecycle Interfaces ===
    "IAsyncContextManager",
    "IAsyncResource",
    
    # === Strategy Interfaces ===
    "StrategyEvaluation",
    "DCADecision",
    "PositionStateType",
    "ITradingStrategy",
    "IDCAPlanner",
    "ITrailingManager",
]
