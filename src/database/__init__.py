"""
Database Module - Cosmos DB Implementation.

This module provides database access for the trading bot using Azure Cosmos DB.
All persistence operations are performed against Cosmos DB NoSQL containers.

Lazy Loading:
    Heavy Azure SDK dependencies are imported lazily to allow tests and
    utilities to import this module without requiring the full Azure SDK.
    Only importing interfaces/constants is safe without Azure SDK.

Components:
    - CosmosDBManager: Core database operations (positions, orders, trades, signals)
    - CosmosBotRepository: Bot management (bots, bot_orders, bot_history)
    - CosmosConnectionPool: Shared connection pool for efficiency
    - CosmosBaseRepository: Abstract base for custom repositories
    - IBotRepository: Interface for bot repository implementations

Usage:
    # Direct Cosmos access (recommended)
    from src.database import CosmosDBManager
    cosmos = CosmosDBManager(config)
    await cosmos.initialize()
    await cosmos.save_position(position)
    
    # Bot management with interface
    from src.database import IBotRepository, CosmosBotRepository
    repo: IBotRepository = CosmosBotRepository(cosmos_endpoint, "trading-bot")
    await repo.initialize()
    await repo.create_bot(bot)

Architecture:
    All repositories use CosmosConnectionPool for shared connection management.
    New code should use CosmosBotRepository (implements IBotRepository).
"""

from typing import TYPE_CHECKING

# These are safe to import at module level (no Azure SDK dependency)
from src.database.database_interface import (
    IBotRepository,
    IDatabaseManager,
)

# Lightweight constant - no Azure SDK needed
COSMOS_SYSTEM_PROPERTIES = frozenset([
    '_rid', '_self', '_etag', '_attachments', '_ts', '_type'
])

# Lazy imports for heavy Azure SDK dependencies
# These will be imported when first accessed via __getattr__

_lazy_imports = {
    "CosmosConnectionPool": "src.database.cosmos_base",
    "CosmosBaseRepository": "src.database.cosmos_base",
    "CosmosDBManager": "src.database.cosmos_manager",
    "CosmosBotRepository": "src.database.cosmos_bot_repository",
    "CosmosBrokerRepository": "src.database.cosmos_broker_repository",
    "BrokerConnectionDocument": "src.database.cosmos_broker_repository",
    "IBrokerRepository": "src.database.cosmos_broker_repository",
    "Bot": "src.database.cosmos_bot_repository",
    "BotOrder": "src.database.cosmos_bot_repository",
    "BotHistory": "src.database.cosmos_bot_repository",
    "BotPerformance": "src.database.cosmos_bot_repository",
    "BotState": "src.database.cosmos_bot_repository",
    "BotType": "src.database.cosmos_bot_repository",
    "OrderSide": "src.database.cosmos_bot_repository",
    "OrderStatus": "src.database.cosmos_bot_repository",
    "OperationalPhase": "src.database.cosmos_bot_repository",
    "FeeDetails": "src.database.cosmos_bot_repository",
    "DCAConfig": "src.database.cosmos_bot_repository",
    "GridConfig": "src.database.cosmos_bot_repository",
}

_loaded_modules = {}


def __getattr__(name: str):
    """Lazy import mechanism for heavy dependencies."""
    if name in _lazy_imports:
        module_path = _lazy_imports[name]
        if module_path not in _loaded_modules:
            import importlib
            _loaded_modules[module_path] = importlib.import_module(module_path)
        return getattr(_loaded_modules[module_path], name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Infrastructure (lazy loaded)
    "CosmosConnectionPool",
    "CosmosBaseRepository",
    "COSMOS_SYSTEM_PROPERTIES",
    # Interfaces (safe to import)
    "IBotRepository",
    "IBrokerRepository",
    "IDatabaseManager",
    # Core managers (lazy loaded)
    "CosmosDBManager",
    "CosmosBotRepository",
    "CosmosBrokerRepository",
    "BrokerConnectionDocument",
    # Bot models (lazy loaded)
    "Bot",
    "BotOrder",
    "BotHistory",
    "BotPerformance",
    "FeeDetails",
    "DCAConfig",
    "GridConfig",
    # Enums (lazy loaded)
    "BotState",
    "BotType",
    "OrderSide",
    "OrderStatus",
    "OperationalPhase",
]
