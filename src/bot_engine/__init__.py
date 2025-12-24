"""
Bot Engine Module - Multi-Bot Async Execution Architecture.

This module provides the infrastructure for running hundreds of trading bots
efficiently in a single process using Python's asyncio.

Architecture Overview:
- BotEngineManager: Central orchestrator managing all bot instances
- BotRunner: Lightweight async wrapper executing individual bot strategies
- MarketDataHub: Shared market data streams with symbol-based deduplication
- SignalRouter: Routes webhooks/signals to specific bot instances
- BrokerConnectionPool: Shared broker connections across all bots
- BotEngineRouter: FastAPI router for REST API integration

Key Benefits:
- Memory efficient: ~10KB per bot (vs ~50MB for separate processes)
- Shared resources: One WebSocket per symbol, not per bot
- Instant start/stop: No process spawn overhead
- Real-time status: Sub-millisecond status updates

Author: Trading Bot Team
Version: 1.0.0
"""

from src.bot_engine.interfaces import (
    IBotRunner,
    IBotEngineManager,
    IMarketDataHub,
    ISignalRouter,
    IBrokerConnectionPool,
    BotStatus,
    BotEngineConfig,
    MarketDataSubscription,
    SignalSubscription,
)
from src.bot_engine.exceptions import (
    BotEngineException,
    BotAlreadyRunningError,
    BotNotRunningError,
    BotNotFoundError,
    ResourceLimitError,
    BotStartupError,
    BotShutdownError,
    SignalRoutingError,
    MarketDataError,
    BrokerConnectionError,
)
from src.bot_engine.bot_runner import BotRunner, BotRunnerContext
from src.bot_engine.bot_engine_manager import BotEngineManager
from src.bot_engine.market_data_hub import MarketDataHub
from src.bot_engine.signal_router import SignalRouter
from src.bot_engine.broker_connection_pool import BrokerConnectionPool, BrokerType
from src.bot_engine.bot_engine_router import BotEngineRouter

# Extracted components from TradingBotOrchestrator (SRP refactoring)
from src.bot_engine.component_initializer import ComponentInitializer, InitializedComponents
from src.bot_engine.shutdown_coordinator import ShutdownCoordinator
from src.bot_engine.signal_processor import SignalProcessor

__all__ = [
    # Interfaces
    "IBotRunner",
    "IBotEngineManager",
    "IMarketDataHub",
    "ISignalRouter",
    "IBrokerConnectionPool",
    # Data classes
    "BotStatus",
    "BotEngineConfig",
    "MarketDataSubscription",
    "SignalSubscription",
    "BotRunnerContext",
    # Exceptions
    "BotEngineException",
    "BotAlreadyRunningError",
    "BotNotRunningError",
    "BotNotFoundError",
    "ResourceLimitError",
    "BotStartupError",
    "BotShutdownError",
    "SignalRoutingError",
    "MarketDataError",
    "BrokerConnectionError",
    # Implementations
    "BotRunner",
    "BotEngineManager",
    "MarketDataHub",
    "SignalRouter",
    "BrokerConnectionPool",
    "BrokerType",
    # API Router
    "BotEngineRouter",
    # Extracted Components (SRP refactoring)
    "ComponentInitializer",
    "InitializedComponents",
    "ShutdownCoordinator",
    "SignalProcessor",
]
