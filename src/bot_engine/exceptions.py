"""
Bot Engine Exceptions.

Custom exceptions for the multi-bot execution architecture.
Provides specific error types for better error handling
and user feedback.

Author: Trading Bot Team
Version: 1.0.0
"""

from src.exceptions import TradingBotException


class BotEngineException(TradingBotException):
    """Base exception for all bot engine errors."""
    pass


class BotAlreadyRunningError(BotEngineException):
    """Raised when attempting to start a bot that is already running."""
    
    def __init__(self, bot_id: str, message: str = None):
        self.bot_id = bot_id
        super().__init__(message or f"Bot {bot_id} is already running")


class BotNotRunningError(BotEngineException):
    """Raised when attempting to operate on a bot that is not running."""
    
    def __init__(self, bot_id: str, message: str = None):
        self.bot_id = bot_id
        super().__init__(message or f"Bot {bot_id} is not running")


class BotNotFoundError(BotEngineException):
    """Raised when a bot configuration cannot be found."""
    
    def __init__(self, bot_id: str, message: str = None):
        self.bot_id = bot_id
        super().__init__(message or f"Bot {bot_id} not found")


class ResourceLimitError(BotEngineException):
    """Raised when resource limits are exceeded."""
    
    def __init__(self, resource_type: str, limit: int, message: str = None):
        self.resource_type = resource_type
        self.limit = limit
        super().__init__(
            message or f"Resource limit exceeded: {resource_type} (limit: {limit})"
        )


class BotStartupError(BotEngineException):
    """Raised when a bot fails to start."""
    
    def __init__(self, bot_id: str, reason: str, message: str = None):
        self.bot_id = bot_id
        self.reason = reason
        super().__init__(message or f"Bot {bot_id} failed to start: {reason}")


class BotShutdownError(BotEngineException):
    """Raised when a bot fails to shutdown cleanly."""
    
    def __init__(self, bot_id: str, reason: str, message: str = None):
        self.bot_id = bot_id
        self.reason = reason
        super().__init__(message or f"Bot {bot_id} failed to shutdown: {reason}")


class SignalRoutingError(BotEngineException):
    """Raised when signal routing fails."""
    
    def __init__(self, signal_id: str, reason: str, message: str = None):
        self.signal_id = signal_id
        self.reason = reason
        super().__init__(message or f"Failed to route signal {signal_id}: {reason}")


class MarketDataError(BotEngineException):
    """Raised when market data operations fail."""
    
    def __init__(self, symbol: str, reason: str, message: str = None):
        self.symbol = symbol
        self.reason = reason
        super().__init__(message or f"Market data error for {symbol}: {reason}")


class BrokerConnectionError(BotEngineException):
    """Raised when broker connection operations fail."""
    
    def __init__(self, broker: str, reason: str, message: str = None):
        self.broker = broker
        self.reason = reason
        super().__init__(message or f"Broker connection error ({broker}): {reason}")
