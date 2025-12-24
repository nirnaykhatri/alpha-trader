"""
Database module initialization.

This module provides database access for the trading bot, including:
- DatabaseManager: Core database operations and session management
- BotRepository: Individual bot configuration persistence
- BotRecord: SQLAlchemy model for bot storage
"""

from src.database.database_manager import DatabaseManager
from src.database.bot_repository import (
    BotRepository,
    BotRecord,
    BotHistoryRecord,
    BotOrderRecord,
)

__all__ = [
    "DatabaseManager",
    "BotRepository",
    "BotRecord",
    "BotHistoryRecord",
    "BotOrderRecord",
]
