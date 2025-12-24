"""
Database Models for Trading Bot

SQLAlchemy ORM models for positions, orders, trades, and signals.
Extracted from database_manager.py for improved separation of concerns.

Author: Trading Bot Team
Version: 1.0.0
"""

from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, Text, Boolean

from src.database.base import Base


class PositionRecord(Base):
    """
    Database model for positions.
    
    Tracks current holdings with broker support for multi-broker scenarios.
    
    Attributes:
        symbol: Trading symbol (primary key component)
        broker: Broker identifier (primary key component)
        quantity: Number of shares/contracts held
        avg_price: Average entry price
        current_price: Most recent price
        unrealized_pnl: Current unrealized profit/loss
        realized_pnl: Cumulative realized profit/loss
        created_at: Position creation timestamp
        updated_at: Last update timestamp
    """
    __tablename__ = 'positions'
    
    symbol = Column(String(10), primary_key=True)
    broker = Column(String(20), primary_key=True, default='alpaca')
    quantity = Column(Float, nullable=False)
    avg_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, nullable=False, default=0)
    realized_pnl = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class OrderRecord(Base):
    """
    Database model for orders.
    
    Stores order details including fill information.
    
    Attributes:
        order_id: Unique order identifier (primary key)
        broker: Broker where order was placed
        symbol: Trading symbol
        quantity: Order quantity
        order_type: Type of order (market, limit, etc.)
        side: Order side (buy/sell)
        price: Limit price if applicable
        stop_price: Stop price if applicable
        status: Current order status
        created_at: Order creation timestamp
        filled_at: Fill timestamp if filled
        filled_price: Average fill price
        filled_quantity: Quantity filled
    """
    __tablename__ = 'orders'
    
    order_id = Column(String(50), primary_key=True)
    broker = Column(String(20), nullable=True, default='alpaca')
    symbol = Column(String(10), nullable=False)
    quantity = Column(Float, nullable=False)
    order_type = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)
    price = Column(Float, nullable=True)
    stop_price = Column(Float, nullable=True)
    status = Column(String(20), nullable=False)
    created_at = Column(DateTime, nullable=False)
    filled_at = Column(DateTime, nullable=True)
    filled_price = Column(Float, nullable=True)
    filled_quantity = Column(Float, nullable=True)


class TradeRecord(Base):
    """
    Database model for completed trades (pairs of buy/sell orders).
    
    Tracks complete round-trip trades with entry/exit details and P&L.
    
    Attributes:
        trade_id: Unique trade identifier (primary key)
        broker: Broker where trade was executed
        symbol: Trading symbol
        entry_*: Entry order details
        exit_*: Exit order details
        realized_pnl: Final profit/loss
        profit_percentage: P&L as percentage
        strategy_used: Strategy that generated the trade
        trailing_*: Trailing stop details if applicable
    """
    __tablename__ = 'trades'
    
    trade_id = Column(String(50), primary_key=True)
    broker = Column(String(20), nullable=True, default='alpaca')
    symbol = Column(String(10), nullable=False)
    
    # Entry details
    entry_order_id = Column(String(50), nullable=False)
    entry_price = Column(Float, nullable=False)
    entry_quantity = Column(Float, nullable=False)
    entry_time = Column(DateTime, nullable=False)
    entry_side = Column(String(10), nullable=False)
    
    # Exit details
    exit_order_id = Column(String(50), nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_quantity = Column(Float, nullable=True)
    exit_time = Column(DateTime, nullable=True)
    exit_side = Column(String(10), nullable=True)
    exit_reason = Column(String(50), nullable=True)
    
    # P&L details
    realized_pnl = Column(Float, nullable=True)
    profit_percentage = Column(Float, nullable=True)
    
    # Strategy details
    strategy_used = Column(String(50), nullable=True)
    trailing_started_at = Column(Float, nullable=True)
    trailing_peak_price = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class PositionTrackingRecord(Base):
    """
    Enhanced position tracking with detailed fill history.
    
    Provides additional tracking beyond basic positions, including
    trailing stop information.
    
    Attributes:
        id: Auto-increment primary key
        symbol: Trading symbol
        total_quantity: Current position size
        avg_entry_price: Weighted average entry price
        total_cost_basis: Total cost of position
        is_trailing: Whether trailing stop is active
        trailing_*: Trailing stop price levels
    """
    __tablename__ = 'position_tracking'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False)
    
    # Current position summary
    total_quantity = Column(Float, nullable=False, default=0)
    avg_entry_price = Column(Float, nullable=False, default=0)
    total_cost_basis = Column(Float, nullable=False, default=0)
    
    # Trailing information
    is_trailing = Column(Boolean, nullable=False, default=False)
    trailing_activation_price = Column(Float, nullable=True)
    trailing_peak_price = Column(Float, nullable=True)
    trailing_stop_price = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class TradingSignalRecord(Base):
    """
    Database model for trading signals.
    
    Stores incoming trading signals for auditing and analysis.
    
    Attributes:
        signal_id: Unique signal identifier (primary key)
        symbol: Trading symbol
        signal_type: Type of signal (buy/sell/close)
        price: Price at signal time
        quantity: Suggested quantity if any
        timestamp: When signal was generated
        signal_metadata: JSON metadata about the signal
        processed_at: When signal was processed
    """
    __tablename__ = 'trading_signals'
    
    signal_id = Column(String(50), primary_key=True)
    symbol = Column(String(10), nullable=False)
    signal_type = Column(String(10), nullable=False)
    price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=True)
    timestamp = Column(DateTime, nullable=False)
    signal_metadata = Column(Text, nullable=True)
    processed_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# Re-export all models for convenient imports
__all__ = [
    'PositionRecord',
    'OrderRecord',
    'TradeRecord',
    'PositionTrackingRecord',
    'TradingSignalRecord',
]
