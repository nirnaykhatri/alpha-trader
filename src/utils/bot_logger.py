"""
Centralized Logger Wrapper for Trading Bot

This module provides a standardized logging interface with:
- Consistent formatting across all modules
- Trading-specific log methods with emojis for visual scanning
- Structured logging support for log aggregation
- Context-aware logging for symbol/bot tracking

Usage:
    from src.utils.bot_logger import BotLogger, get_logger

    # Get a logger for a module
    logger = get_logger(__name__)
    
    # Use trading-specific methods
    logger.trade_opened("AAPL", "buy", 100.50, 10)
    logger.dca_executed("AAPL", 2, 98.25, 15)
    logger.position_closed("AAPL", profit=150.00, pnl_pct=3.5)
"""

import logging
import sys
from typing import Optional, Any, Dict
from functools import lru_cache
from datetime import datetime

# Default log format
DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Trading-specific emojis for visual scanning
class LogEmoji:
    """Emojis for visual log scanning."""
    SUCCESS = "✅"
    ERROR = "❌"
    WARNING = "⚠️"
    INFO = "ℹ️"
    DEBUG = "🔍"
    
    # Trading specific
    BUY = "📈"
    SELL = "📉"
    DCA = "🔄"
    CLOSE = "🏁"
    PROFIT = "💰"
    LOSS = "💸"
    POSITION = "📊"
    ORDER = "📝"
    SIGNAL = "📡"
    
    # System
    START = "🚀"
    STOP = "🛑"
    PAUSE = "⏸️"
    RESUME = "▶️"
    CONFIG = "⚙️"
    DATABASE = "🗄️"
    CACHE = "💾"
    API = "🌐"


class BotLogger:
    """
    Enhanced logger wrapper with trading-specific logging methods.
    
    Provides consistent logging across the trading bot with:
    - Standard Python logging interface
    - Trading-specific convenience methods
    - Context tracking for symbols and bots
    - Structured data support
    
    Attributes:
        name: Logger name (usually module name)
        logger: Underlying Python logger
        context: Optional persistent context (symbol, bot_id, etc.)
    """
    
    def __init__(
        self, 
        name: str, 
        level: int = logging.INFO,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize BotLogger.
        
        Args:
            name: Logger name (typically __name__)
            level: Logging level (default: INFO)
            context: Optional persistent context for all log messages
        """
        self.name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        self.context = context or {}
        
        # Add handler if none exists
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(logging.Formatter(DEFAULT_FORMAT, DEFAULT_DATE_FORMAT))
            self.logger.addHandler(handler)
    
    # =========================================================================
    # Standard Logging Methods
    # =========================================================================
    
    def debug(self, message: str, **kwargs: Any) -> None:
        """Log debug message."""
        self.logger.debug(self._format_message(message, **kwargs))
    
    def info(self, message: str, **kwargs: Any) -> None:
        """Log info message."""
        self.logger.info(self._format_message(message, **kwargs))
    
    def warning(self, message: str, **kwargs: Any) -> None:
        """Log warning message."""
        self.logger.warning(self._format_message(message, **kwargs))
    
    def error(self, message: str, exc_info: bool = False, **kwargs: Any) -> None:
        """Log error message."""
        self.logger.error(self._format_message(message, **kwargs), exc_info=exc_info)
    
    def exception(self, message: str, **kwargs: Any) -> None:
        """Log exception with traceback."""
        self.logger.exception(self._format_message(message, **kwargs))
    
    def critical(self, message: str, **kwargs: Any) -> None:
        """Log critical message."""
        self.logger.critical(self._format_message(message, **kwargs))
    
    # =========================================================================
    # Trading-Specific Methods
    # =========================================================================
    
    def trade_opened(
        self, 
        symbol: str, 
        side: str, 
        price: float, 
        quantity: float,
        order_id: Optional[str] = None
    ) -> None:
        """
        Log a trade opening.
        
        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            price: Entry price
            quantity: Number of shares/contracts
            order_id: Optional order ID
        """
        emoji = LogEmoji.BUY if side.lower() == 'buy' else LogEmoji.SELL
        msg = (
            f"{emoji} TRADE OPENED: {symbol} {side.upper()} "
            f"{quantity} @ ${price:.2f}"
        )
        if order_id:
            msg += f" (Order: {order_id[:8]}...)"
        self.info(msg, symbol=symbol, side=side, price=price, quantity=quantity)
    
    def trade_closed(
        self,
        symbol: str,
        quantity: float,
        entry_price: float,
        exit_price: float,
        profit: Optional[float] = None,
        pnl_pct: Optional[float] = None
    ) -> None:
        """
        Log a trade closing.
        
        Args:
            symbol: Trading symbol
            quantity: Number of shares/contracts closed
            entry_price: Original entry price
            exit_price: Exit price
            profit: Optional profit/loss amount
            pnl_pct: Optional P/L percentage
        """
        if profit is not None:
            emoji = LogEmoji.PROFIT if profit >= 0 else LogEmoji.LOSS
            profit_str = f"${profit:+.2f}"
        else:
            emoji = LogEmoji.CLOSE
            profit_str = ""
        
        pnl_str = f" ({pnl_pct:+.2f}%)" if pnl_pct is not None else ""
        
        msg = (
            f"{emoji} TRADE CLOSED: {symbol} {quantity} @ ${exit_price:.2f} "
            f"(entry: ${entry_price:.2f})"
        )
        if profit_str:
            msg += f" P/L: {profit_str}{pnl_str}"
        
        self.info(msg, symbol=symbol, quantity=quantity, profit=profit, pnl_pct=pnl_pct)
    
    def dca_executed(
        self,
        symbol: str,
        dca_level: int,
        price: float,
        new_quantity: float,
        new_avg_price: Optional[float] = None
    ) -> None:
        """
        Log a DCA order execution.
        
        Args:
            symbol: Trading symbol
            dca_level: DCA level/attempt number
            price: DCA entry price
            new_quantity: Quantity added
            new_avg_price: New average entry price after DCA
        """
        msg = (
            f"{LogEmoji.DCA} DCA EXECUTED: {symbol} Level {dca_level} - "
            f"Added {new_quantity} @ ${price:.2f}"
        )
        if new_avg_price is not None:
            msg += f" (New avg: ${new_avg_price:.2f})"
        
        self.info(msg, symbol=symbol, dca_level=dca_level, price=price)
    
    def position_closed(
        self,
        symbol: str,
        profit: float,
        pnl_pct: float,
        hold_time: Optional[str] = None
    ) -> None:
        """
        Log a position fully closed.
        
        Args:
            symbol: Trading symbol
            profit: Total profit/loss
            pnl_pct: P/L percentage
            hold_time: Optional hold duration string
        """
        emoji = LogEmoji.PROFIT if profit >= 0 else LogEmoji.LOSS
        msg = (
            f"{emoji} POSITION CLOSED: {symbol} - "
            f"P/L: ${profit:+.2f} ({pnl_pct:+.2f}%)"
        )
        if hold_time:
            msg += f" - Held: {hold_time}"
        
        self.info(msg, symbol=symbol, profit=profit, pnl_pct=pnl_pct)
    
    def signal_received(
        self,
        symbol: str,
        signal_type: str,
        source: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log a trading signal received.
        
        Args:
            symbol: Trading symbol
            signal_type: Type of signal (entry, exit, dca, etc.)
            source: Signal source (TradingView, internal, etc.)
            details: Optional additional signal details
        """
        msg = (
            f"{LogEmoji.SIGNAL} SIGNAL: {symbol} {signal_type.upper()} "
            f"from {source}"
        )
        if details:
            msg += f" | {details}"
        
        self.info(msg, symbol=symbol, signal_type=signal_type, source=source)
    
    def order_placed(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        order_id: str,
        price: Optional[float] = None
    ) -> None:
        """
        Log an order placement.
        
        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            order_type: Order type (market, limit, etc.)
            quantity: Order quantity
            order_id: Broker order ID
            price: Optional limit price
        """
        price_str = f" @ ${price:.2f}" if price else " (market)"
        msg = (
            f"{LogEmoji.ORDER} ORDER PLACED: {symbol} {side.upper()} {order_type} "
            f"{quantity}{price_str} (ID: {order_id[:8]}...)"
        )
        self.info(msg, symbol=symbol, side=side, order_type=order_type, order_id=order_id)
    
    def order_filled(
        self,
        symbol: str,
        side: str,
        quantity: float,
        fill_price: float,
        order_id: str
    ) -> None:
        """
        Log an order fill.
        
        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            quantity: Filled quantity
            fill_price: Fill price
            order_id: Broker order ID
        """
        emoji = LogEmoji.BUY if side.lower() == 'buy' else LogEmoji.SELL
        msg = (
            f"{emoji} ORDER FILLED: {symbol} {side.upper()} "
            f"{quantity} @ ${fill_price:.2f} (ID: {order_id[:8]}...)"
        )
        self.info(msg, symbol=symbol, side=side, fill_price=fill_price, order_id=order_id)
    
    # =========================================================================
    # System Methods
    # =========================================================================
    
    def bot_started(self, bot_id: str, bot_name: str, symbol: str) -> None:
        """Log bot startup."""
        self.info(
            f"{LogEmoji.START} BOT STARTED: {bot_name} ({bot_id[:8]}...) - {symbol}",
            bot_id=bot_id, bot_name=bot_name, symbol=symbol
        )
    
    def bot_stopped(self, bot_id: str, bot_name: str, reason: Optional[str] = None) -> None:
        """Log bot shutdown."""
        msg = f"{LogEmoji.STOP} BOT STOPPED: {bot_name} ({bot_id[:8]}...)"
        if reason:
            msg += f" - Reason: {reason}"
        self.info(msg, bot_id=bot_id, bot_name=bot_name)
    
    def bot_paused(self, bot_id: str, bot_name: str) -> None:
        """Log bot pause."""
        self.info(
            f"{LogEmoji.PAUSE} BOT PAUSED: {bot_name} ({bot_id[:8]}...)",
            bot_id=bot_id, bot_name=bot_name
        )
    
    def bot_resumed(self, bot_id: str, bot_name: str) -> None:
        """Log bot resume."""
        self.info(
            f"{LogEmoji.RESUME} BOT RESUMED: {bot_name} ({bot_id[:8]}...)",
            bot_id=bot_id, bot_name=bot_name
        )
    
    def api_call(
        self, 
        endpoint: str, 
        method: str = "GET",
        status: Optional[int] = None,
        duration_ms: Optional[float] = None
    ) -> None:
        """Log an API call."""
        msg = f"{LogEmoji.API} API: {method} {endpoint}"
        if status:
            msg += f" -> {status}"
        if duration_ms:
            msg += f" ({duration_ms:.0f}ms)"
        self.debug(msg)
    
    def cache_hit(self, key: str) -> None:
        """Log a cache hit."""
        self.debug(f"{LogEmoji.CACHE} Cache HIT: {key}")
    
    def cache_miss(self, key: str) -> None:
        """Log a cache miss."""
        self.debug(f"{LogEmoji.CACHE} Cache MISS: {key}")
    
    def database_operation(
        self, 
        operation: str, 
        table: str,
        duration_ms: Optional[float] = None
    ) -> None:
        """Log a database operation."""
        msg = f"{LogEmoji.DATABASE} DB: {operation} on {table}"
        if duration_ms:
            msg += f" ({duration_ms:.0f}ms)"
        self.debug(msg)
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _format_message(self, message: str, **kwargs: Any) -> str:
        """
        Format message with context.
        
        Merges persistent context with per-message kwargs.
        """
        # Merge context
        full_context = {**self.context, **kwargs}
        
        # For now, just return the message
        # In production, could add structured data suffix
        return message
    
    def with_context(self, **context: Any) -> 'BotLogger':
        """
        Create a child logger with additional context.
        
        Args:
            **context: Context key-value pairs
        
        Returns:
            New BotLogger with merged context
        
        Example:
            symbol_logger = logger.with_context(symbol="AAPL", bot_id="abc123")
            symbol_logger.info("Processing signal")  # Includes symbol context
        """
        merged_context = {**self.context, **context}
        return BotLogger(
            name=self.name,
            level=self.logger.level,
            context=merged_context
        )


@lru_cache(maxsize=128)
def get_logger(name: str, level: int = logging.INFO) -> BotLogger:
    """
    Get or create a BotLogger instance.
    
    Uses LRU cache to reuse logger instances for the same name.
    
    Args:
        name: Logger name (typically __name__)
        level: Logging level
    
    Returns:
        BotLogger instance
    
    Example:
        logger = get_logger(__name__)
        logger.info("Starting operation")
    """
    return BotLogger(name=name, level=level)


def configure_root_logger(
    level: int = logging.INFO,
    format_str: str = DEFAULT_FORMAT,
    date_format: str = DEFAULT_DATE_FORMAT,
) -> None:
    """
    Configure the root logger for the application.
    
    Should be called once at application startup.
    
    Args:
        level: Logging level
        format_str: Log format string
        date_format: Date format string
    """
    logging.basicConfig(
        level=level,
        format=format_str,
        datefmt=date_format,
        handlers=[logging.StreamHandler(sys.stdout)]
    )
