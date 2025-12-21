"""
Database management implementation using SQLAlchemy with async support.
Handles persistence of positions, orders, and trading history.
"""

import asyncio
from typing import List, Optional, Dict, Any, AsyncGenerator
from datetime import datetime, timedelta
from contextlib import asynccontextmanager

# Async SQLAlchemy imports
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine
)
from sqlalchemy import Column, String, Float, Integer, DateTime, Text, select, delete
import json

from src.interfaces import IConfigurationManager
from src.exceptions import TradingBotException
from src.core.logging_config import get_logger
from src import Position, Order, OrderStatus, OrderType
from src.constants import DatabaseConstants
from src.database.base import Base

# Import other schema modules to register their models with the shared Base
# This ensures all tables are created when Base.metadata.create_all() is called
import src.database.enhanced_schema  # noqa: F401
import src.database.dca_metadata_manager  # noqa: F401


logger = get_logger(__name__)


class PositionRecord(Base):
    """Database model for positions."""
    __tablename__ = 'positions'
    
    symbol = Column(String(10), primary_key=True)
    broker = Column(String(20), primary_key=True, default='alpaca')  # Added broker to PK
    quantity = Column(Float, nullable=False)
    avg_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, nullable=False, default=0)
    realized_pnl = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class OrderRecord(Base):
    """Database model for orders."""
    __tablename__ = 'orders'
    
    order_id = Column(String(50), primary_key=True)
    broker = Column(String(20), nullable=True, default='alpaca')  # Added broker
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
    """Database model for completed trades (pairs of buy/sell orders)."""
    __tablename__ = 'trades'
    
    trade_id = Column(String(50), primary_key=True)
    broker = Column(String(20), nullable=True, default='alpaca')  # Added broker
    symbol = Column(String(10), nullable=False)
    
    # Entry details
    entry_order_id = Column(String(50), nullable=False)
    entry_price = Column(Float, nullable=False)
    entry_quantity = Column(Float, nullable=False)
    entry_time = Column(DateTime, nullable=False)
    entry_side = Column(String(10), nullable=False)  # 'buy' or 'sell'
    
    # Exit details
    exit_order_id = Column(String(50), nullable=True)
    exit_price = Column(Float, nullable=True)
    exit_quantity = Column(Float, nullable=True)
    exit_time = Column(DateTime, nullable=True)
    exit_side = Column(String(10), nullable=True)  # 'sell' or 'buy'
    exit_reason = Column(String(50), nullable=True)  # 'profit_taking', 'stop_loss', 'trailing_stop', 'manual'
    
    # P&L details
    realized_pnl = Column(Float, nullable=True)
    profit_percentage = Column(Float, nullable=True)
    
    # Strategy details
    strategy_used = Column(String(50), nullable=True)
    trailing_started_at = Column(Float, nullable=True)  # Price at which trailing started
    trailing_peak_price = Column(Float, nullable=True)  # Peak price during trailing
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class PositionTrackingRecord(Base):
    """Enhanced position tracking with detailed fill history."""
    __tablename__ = 'position_tracking'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), nullable=False)
    
    # Current position summary
    total_quantity = Column(Float, nullable=False, default=0)
    avg_entry_price = Column(Float, nullable=False, default=0)
    total_cost_basis = Column(Float, nullable=False, default=0)
    
    # Trailing information
    is_trailing = Column(String(10), nullable=False, default='false')  # 'true'/'false'
    trailing_activation_price = Column(Float, nullable=True)
    trailing_peak_price = Column(Float, nullable=True)
    trailing_stop_price = Column(Float, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class TradingSignalRecord(Base):
    """Database model for trading signals."""
    __tablename__ = 'trading_signals'
    
    signal_id = Column(String(50), primary_key=True)
    symbol = Column(String(10), nullable=False)
    signal_type = Column(String(10), nullable=False)
    price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=True)
    timestamp = Column(DateTime, nullable=False)
    signal_metadata = Column(Text, nullable=True)
    processed_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class DatabaseManager:
    """
    Async database manager for persisting trading data.
    Uses async SQLAlchemy for non-blocking database operations.
    Supports SQLite (with aiosqlite) for development and PostgreSQL (with asyncpg) for production.
    """
    
    def __init__(self, config: IConfigurationManager):
        """
        Initialize database manager.
        
        Args:
            config: Configuration manager instance
        """
        self._config = config
        self._engine: Optional[AsyncEngine] = None
        self._async_session_factory = None
        
        # Database configuration with defaults from constants
        db_url = config.get_config("database.url", "sqlite:///data/trading_bot.db")
        
        # Convert sync URL to async URL
        if db_url.startswith("sqlite://"):
            self._db_url = db_url.replace("sqlite://", "sqlite+aiosqlite://")
        elif db_url.startswith("postgresql://"):
            self._db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
        else:
            self._db_url = db_url  # Assume already async-compatible
        
        self._echo = config.get_config("database.echo", False)
        self._pool_size = config.get_config("database.pool_size", DatabaseConstants.POOL_SIZE)
        self._max_overflow = config.get_config("database.max_overflow", DatabaseConstants.POOL_MAX_OVERFLOW)
        self._pool_timeout = config.get_config("database.pool_timeout", DatabaseConstants.POOL_TIMEOUT)
        self._pool_recycle = config.get_config("database.pool_recycle", DatabaseConstants.POOL_RECYCLE)
        
        logger.info(f"DatabaseManager initialized with async URL: {self._db_url}")
    
    async def initialize(self) -> None:
        """
        Initialize async database connection and create tables with proper connection pooling.
        
        This method sets up the SQLAlchemy async engine with connection pooling parameters
        configured in the application settings. It handles both SQLite (using aiosqlite)
        and PostgreSQL (using asyncpg) dialects.
        
        For SQLite, it configures the engine to allow access from multiple threads/tasks.
        For PostgreSQL, it sets up a connection pool with configurable size, overflow,
        timeout, and recycle settings to ensure efficient resource usage under load.
        
        Finally, it creates all defined database tables if they do not exist.
        
        Raises:
            TradingBotException: If initialization fails due to configuration or connection errors.
        """
        try:
            logger.info("Initializing async database with connection pooling...")
            
            # Create async engine with appropriate settings
            if "sqlite" in self._db_url:
                # SQLite async configuration
                logger.info("Using async SQLite with aiosqlite")
                self._engine = create_async_engine(
                    self._db_url,
                    echo=self._echo,
                    connect_args={"check_same_thread": False}
                )
            else:
                # PostgreSQL or other database with connection pooling
                logger.info(f"Using async engine with pool_size={self._pool_size}, max_overflow={self._max_overflow}")
                self._engine = create_async_engine(
                    self._db_url,
                    echo=self._echo,
                    pool_size=self._pool_size,
                    max_overflow=self._max_overflow,
                    pool_timeout=self._pool_timeout,
                    pool_recycle=self._pool_recycle,
                    pool_pre_ping=True  # Verify connections before using
                )
            
            # Create async session factory
            self._async_session_factory = async_sessionmaker(
                self._engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Create tables asynchronously
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            
            logger.info("Async database initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize async database: {str(e)}")
            raise TradingBotException(f"Async database initialization failed: {str(e)}")
    
    async def close(self) -> None:
        """Close async database connections."""
        try:
            if self._engine:
                await self._engine.dispose()
                logger.info("Async database connections closed")
        except Exception as e:
            logger.error(f"Error closing async database: {str(e)}")
    
    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Context manager for providing async database sessions.
        
        This method yields an AsyncSession that is automatically committed on success
        or rolled back on exception. It ensures that the session is properly closed
        regardless of the outcome.
        
        The session is created from the configured session factory and is thread-safe
        (or task-safe in asyncio context).
        
        Usage:
            async with db_manager.get_session() as session:
                # Perform database operations
                await session.execute(...)
                # Commit happens automatically at the end of the block
        
        Yields:
            AsyncSession: An active async database session.
            
        Raises:
            TradingBotException: If the database has not been initialized.
            Exception: Re-raises any exception that occurs within the context block
                      after rolling back the transaction.
        """
        if not self._async_session_factory:
            raise TradingBotException("Database not initialized. Call initialize() first.")
        
        session = self._async_session_factory()
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.warning(f"Database session rolled back due to: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()
    
    async def save_position(self, position: Position) -> None:
        """
        Save or update a position in the database with proper async transaction boundaries.
        
        Args:
            position: Position to save
            
        Raises:
            TradingBotException: If save operation fails
        """
        try:
            async with self.get_session() as session:
                # Check if position exists for this symbol AND broker
                broker = position.broker or 'alpaca'
                stmt = select(PositionRecord).where(
                    PositionRecord.symbol == position.symbol,
                    PositionRecord.broker == broker
                )
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if existing:
                    # Update existing position
                    existing.quantity = position.quantity
                    existing.avg_price = position.avg_price
                    existing.current_price = position.current_price
                    existing.unrealized_pnl = position.unrealized_pnl
                    existing.realized_pnl = position.realized_pnl
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new position
                    new_position = PositionRecord(
                        symbol=position.symbol,
                        broker=broker,
                        quantity=position.quantity,
                        avg_price=position.avg_price,
                        current_price=position.current_price,
                        unrealized_pnl=position.unrealized_pnl,
                        realized_pnl=position.realized_pnl,
                        created_at=position.created_at,
                        updated_at=datetime.utcnow()
                    )
                    session.add(new_position)
            # Transaction auto-commits on success via context manager, auto-rolls back on exception
            
            logger.debug(f"Position saved successfully: {position.symbol} ({broker})")
            
        except Exception as e:
            logger.error(f"Error saving position {position.symbol}: {str(e)}")
            raise TradingBotException(f"Failed to save position: {str(e)}")
    
    async def get_position(self, symbol: str, broker: str = None) -> Optional[Position]:
        """
        Get a position from the database.
        
        Args:
            symbol: Trading symbol
            broker: Optional broker name. If None, returns first found (legacy behavior) or prefers default.
            
        Returns:
            Position if found, None otherwise
        """
        try:
            async with self.get_session() as session:
                stmt = select(PositionRecord).where(PositionRecord.symbol == symbol)
                if broker:
                    stmt = stmt.where(PositionRecord.broker == broker)
                
                result = await session.execute(stmt)
                # If broker not specified, this might return multiple. For now, take first.
                # Ideally, caller should specify broker.
                record = result.scalars().first()
                
                if record:
                    return Position(
                        symbol=record.symbol,
                        quantity=record.quantity,
                        avg_price=record.avg_price,
                        current_price=record.current_price,
                        unrealized_pnl=record.unrealized_pnl,
                        realized_pnl=record.realized_pnl,
                        created_at=record.created_at,
                        broker=record.broker
                    )
                
                return None
                
        except Exception as e:
            logger.error(f"Error getting position {symbol}: {str(e)}")
            return None
    
    async def get_all_positions(self, broker: str = None) -> List[Position]:
        """
        Get all positions from the database.
        
        Args:
            broker: Optional broker filter
            
        Returns:
            List of all positions
        """
        try:
            async with self.get_session() as session:
                stmt = select(PositionRecord)
                if broker:
                    stmt = stmt.where(PositionRecord.broker == broker)
                    
                result = await session.execute(stmt)
                records = result.scalars().all()
                
                positions = []
                for record in records:
                    positions.append(Position(
                        symbol=record.symbol,
                        quantity=record.quantity,
                        avg_price=record.avg_price,
                        current_price=record.current_price,
                        unrealized_pnl=record.unrealized_pnl,
                        realized_pnl=record.realized_pnl,
                        created_at=record.created_at,
                        broker=record.broker
                    ))
                
                return positions
                
        except Exception as e:
            logger.error(f"Error getting all positions: {str(e)}")
            return []
    
    async def save_order(self, order: Order) -> None:
        """
        Save or update an order in the database.
        
        Args:
            order: Order to save
        """
        try:
            async with self.get_session() as session:
                # Check if order exists
                stmt = select(OrderRecord).where(OrderRecord.order_id == str(order.order_id))
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()
                
                if existing:
                    # Update existing order
                    existing.status = order.status.value
                    existing.filled_at = order.filled_at
                    existing.filled_price = order.filled_price
                    existing.filled_quantity = order.filled_quantity
                    # Ensure broker is set if missing
                    if not existing.broker and order.broker:
                        existing.broker = order.broker
                else:
                    # Create new order
                    new_order = OrderRecord(
                        order_id=str(order.order_id),  # Convert UUID to string
                        broker=order.broker or 'alpaca',
                        symbol=order.symbol,
                        quantity=order.quantity,
                        order_type=order.order_type.value,
                        side=order.side.value if hasattr(order.side, 'value') else str(order.side),
                        price=order.price,
                        stop_price=order.stop_price,
                        status=order.status.value,
                        created_at=order.created_at,
                        filled_at=order.filled_at,
                        filled_price=order.filled_price,
                        filled_quantity=order.filled_quantity
                    )
                    session.add(new_order)
            # Transaction auto-commits on success via context manager
            
            logger.debug(f"Order saved successfully: {order.order_id}")
                
        except Exception as e:
            logger.error(f"Error saving order {order.order_id}: {str(e)}")
            raise TradingBotException(f"Failed to save order: {str(e)}")
    
    async def get_orders(self, symbol: Optional[str] = None, 
                        status: Optional[OrderStatus] = None,
                        broker: Optional[str] = None) -> List[Order]:
        """
        Get orders from the database with optional filtering.
        
        Args:
            symbol: Optional symbol filter
            status: Optional status filter
            broker: Optional broker filter
            
        Returns:
            List of orders matching criteria
        """
        try:
            async with self.get_session() as session:
                # Build query with filters
                stmt = select(OrderRecord)
                
                if symbol:
                    stmt = stmt.where(OrderRecord.symbol == symbol)
                
                if status:
                    stmt = stmt.where(OrderRecord.status == status.value)
                
                if broker:
                    stmt = stmt.where(OrderRecord.broker == broker)
                
                result = await session.execute(stmt)
                records = result.scalars().all()
                
                orders = []
                for record in records:
                    order = Order(
                        order_id=record.order_id,
                        symbol=record.symbol,
                        quantity=record.quantity,
                        order_type=OrderType(record.order_type),
                        side=record.side,
                        price=record.price,
                        stop_price=record.stop_price,
                        status=OrderStatus(record.status),
                        created_at=record.created_at,
                        filled_at=record.filled_at,
                        filled_price=record.filled_price,
                        filled_quantity=record.filled_quantity,
                        broker=record.broker
                    )
                    orders.append(order)
                
                return orders
                
        except Exception as e:
            logger.error(f"Error getting orders: {str(e)}")
            return []
    
    async def save_signal(self, signal) -> None:
        """
        Save a trading signal to the database.
        
        Args:
            signal: Trading signal to save
        """
        try:
            async with self.get_session() as session:
                new_signal = TradingSignalRecord(
                    signal_id=signal.signal_id,
                    symbol=signal.symbol,
                    signal_type=signal.signal_type.value,
                    price=signal.price,
                    quantity=signal.quantity,
                    timestamp=signal.timestamp,
                    signal_metadata=json.dumps(signal.metadata) if signal.metadata else None
                )
                
                session.add(new_signal)
            # Auto-commit via context manager
            
            logger.debug(f"Signal saved: {signal.signal_id}")
                
        except Exception as e:
            logger.error(f"Error saving signal {signal.signal_id}: {str(e)}")
            raise
    
    async def get_trading_history(self, symbol: Optional[str] = None, 
                                days: int = 30) -> Dict[str, Any]:
        """
        Get trading history for analysis.
        
        Args:
            symbol: Optional symbol filter
            days: Number of days to look back
            
        Returns:
            Dictionary with trading statistics
        """
        try:
            async with self.get_session() as session:
                # Calculate date range
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=days)
                
                # Build query with filters
                stmt = select(OrderRecord).where(
                    OrderRecord.created_at >= start_date,
                    OrderRecord.created_at <= end_date
                )
                
                if symbol:
                    stmt = stmt.where(OrderRecord.symbol == symbol)
                
                result = await session.execute(stmt)
                orders = result.scalars().all()
                
                # Calculate statistics
                total_trades = len([o for o in orders if o.status == OrderStatus.FILLED.value])
                buy_trades = len([o for o in orders if o.side == "buy" and o.status == OrderStatus.FILLED.value])
                sell_trades = len([o for o in orders if o.side == "sell" and o.status == OrderStatus.FILLED.value])
                
                return {
                    "total_trades": total_trades,
                    "buy_trades": buy_trades,
                    "sell_trades": sell_trades,
                    "success_rate": (sell_trades / buy_trades * 100) if buy_trades > 0 else 0,
                    "period_days": days,
                    "symbol": symbol
                }
                
        except Exception as e:
            logger.error(f"Error getting trading history: {str(e)}")
            return {}
    
    async def cleanup_old_data(self, days: int = 90) -> None:
        """
        Clean up old data from the database.
        SAFE: Only deletes old orders and signals, never open positions.
        
        Args:
            days: Number of days of data to keep
        """
        try:
            async with self.get_session() as session:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                
                # Delete old filled/canceled orders (SAFE - never deletes open orders)
                stmt_orders = delete(OrderRecord).where(
                    OrderRecord.created_at < cutoff_date,
                    OrderRecord.status.in_([OrderStatus.FILLED.value, OrderStatus.CANCELED.value])
                )
                result_orders = await session.execute(stmt_orders)
                deleted_orders = result_orders.rowcount
                
                # Delete old signals
                stmt_signals = delete(TradingSignalRecord).where(
                    TradingSignalRecord.timestamp < cutoff_date
                )
                result_signals = await session.execute(stmt_signals)
                deleted_signals = result_signals.rowcount
                
                logger.info(f"Cleaned up {deleted_orders} old orders and {deleted_signals} old signals (older than {days} days)")
                
        except Exception as e:
            logger.error(f"Error cleaning up old data: {str(e)}")
    
    async def backup_database(self, backup_path: str = None) -> str:
        """
        Create a backup of the current database.
        
        Args:
            backup_path: Optional custom backup path
            
        Returns:
            Path to the created backup file
        """
        try:
            import shutil
            from pathlib import Path
            
            if backup_path is None:
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                backup_path = f"data/backup_trading_bot_{timestamp}.db"
            
            # Ensure backup directory exists
            Path(backup_path).parent.mkdir(parents=True, exist_ok=True)
            
            # Extract database path from async URL
            if "sqlite" in self._db_url:
                # Remove async prefix for file path
                source_db = self._db_url.replace("sqlite+aiosqlite:///", "")
                source_db = source_db.replace("sqlite:///", "")
                
                if Path(source_db).exists():
                    shutil.copy2(source_db, backup_path)
                    logger.info(f"Database backed up to: {backup_path}")
                    return backup_path
                else:
                    raise FileNotFoundError(f"Source database not found: {source_db}")
            else:
                raise NotImplementedError("Backup only supported for SQLite databases")
                
        except Exception as e:
            logger.error(f"Database backup failed: {str(e)}")
            raise

    async def restore_database(self, backup_path: str) -> None:
        """
        Restore database from a backup file.
        
        Args:
            backup_path: Path to backup file to restore
        """
        try:
            import shutil
            from pathlib import Path
            
            if not Path(backup_path).exists():
                raise FileNotFoundError(f"Backup file not found: {backup_path}")
            
            # Extract database path from async URL
            if "sqlite" in self._db_url:
                # Remove async prefix for file path
                target_db = self._db_url.replace("sqlite+aiosqlite:///", "")
                target_db = target_db.replace("sqlite:///", "")
                
                # Close existing connections
                if self._engine:
                    await self._engine.dispose()
                
                # Restore backup
                shutil.copy2(backup_path, target_db)
                
                # Reinitialize database
                await self.initialize()
                
                logger.info(f"Database restored from: {backup_path}")
            else:
                raise NotImplementedError("Restore only supported for SQLite databases")
                
        except Exception as e:
            logger.error(f"Database restore failed: {str(e)}")
            raise

    async def get_database_stats(self) -> Dict[str, Any]:
        """
        Get database statistics for health monitoring.
        
        Returns:
            Dictionary with database statistics
        """
        try:
            async with self.get_session() as session:
                stats = {}
                
                # Count records in each table
                result = await session.execute(select(PositionRecord))
                stats["positions_total"] = len(result.scalars().all())
                
                result = await session.execute(select(PositionRecord).where(PositionRecord.quantity != 0))
                stats["positions_open"] = len(result.scalars().all())
                
                result = await session.execute(select(PositionRecord).where(PositionRecord.quantity == 0))
                stats["positions_closed"] = len(result.scalars().all())
                
                result = await session.execute(select(OrderRecord))
                stats["orders_total"] = len(result.scalars().all())
                
                result = await session.execute(select(OrderRecord).where(OrderRecord.status == OrderStatus.FILLED.value))
                stats["orders_filled"] = len(result.scalars().all())
                
                result = await session.execute(select(TradingSignalRecord))
                stats["signals_total"] = len(result.scalars().all())
                
                # Get date ranges
                result = await session.execute(select(PositionRecord.created_at).order_by(PositionRecord.created_at.asc()).limit(1))
                oldest_position = result.scalar_one_or_none()
                
                result = await session.execute(select(PositionRecord.updated_at).order_by(PositionRecord.updated_at.desc()).limit(1))
                newest_position = result.scalar_one_or_none()
                
                if oldest_position:
                    stats["oldest_position_date"] = oldest_position
                if newest_position:
                    stats["newest_position_date"] = newest_position
                
                # Database file size (SQLite only)
                if "sqlite" in self._db_url:
                    from pathlib import Path
                    db_file = self._db_url.replace("sqlite+aiosqlite:///", "")
                    db_file = db_file.replace("sqlite:///", "")
                    if Path(db_file).exists():
                        stats["database_size_bytes"] = Path(db_file).stat().st_size
                        stats["database_size_mb"] = stats["database_size_bytes"] / (1024 * 1024)
                
                return stats
                
        except Exception as e:
            logger.error(f"Error getting database stats: {str(e)}")
            return {}

    # ==================== TRADE TRACKING METHODS ====================
    
    async def create_trade_entry(self, symbol: str, entry_order: Order, strategy_used: str = None) -> str:
        """
        Create a new trade record when an entry order is filled.
        
        Args:
            symbol: Trading symbol
            entry_order: The filled entry order
            strategy_used: Strategy that initiated the trade
            
        Returns:
            trade_id: Unique identifier for the trade
        """
        try:
            async with self.get_session() as session:
                trade_id = f"{symbol}_{str(entry_order.order_id)}"
                
                trade = TradeRecord(
                    trade_id=trade_id,
                    broker=entry_order.broker or 'alpaca',
                    symbol=symbol,
                    entry_order_id=str(entry_order.order_id),  # Convert UUID to string
                    entry_price=entry_order.filled_price or entry_order.price,
                    entry_quantity=entry_order.filled_quantity or entry_order.quantity,
                    entry_time=entry_order.filled_at or entry_order.created_at,
                    entry_side=entry_order.side.value if hasattr(entry_order.side, 'value') else str(entry_order.side),
                    strategy_used=strategy_used,
                    created_at=datetime.utcnow()
                )
                
                session.add(trade)
            # Auto-commit via context manager
            
            logger.info(f"Trade entry created: {trade_id} - {symbol} {entry_order.side} "
                       f"{trade.entry_quantity} @ ${trade.entry_price:.4f}")
            
            return trade_id
                
        except Exception as e:
            logger.error(f"Error creating trade entry: {str(e)}")
            raise TradingBotException(f"Failed to create trade entry: {str(e)}")
    
    async def complete_trade(self, trade_id: str, exit_order: Order, exit_reason: str) -> Dict[str, Any]:
        """
        Complete a trade by adding exit information and calculating P&L.
        
        Args:
            trade_id: Trade identifier
            exit_order: The filled exit order
            exit_reason: Reason for exit ('profit_taking', 'stop_loss', 'trailing_stop', 'manual')
            
        Returns:
            Trade summary with P&L information
        """
        try:
            async with self.get_session() as session:
                stmt = select(TradeRecord).where(TradeRecord.trade_id == trade_id)
                result = await session.execute(stmt)
                trade = result.scalar_one_or_none()
                
                if not trade:
                    raise TradingBotException(f"Trade {trade_id} not found")
                
                # Update exit information
                trade.exit_order_id = str(exit_order.order_id)  # Convert UUID to string
                trade.exit_price = exit_order.filled_price or exit_order.price
                trade.exit_quantity = exit_order.filled_quantity or exit_order.quantity
                trade.exit_time = exit_order.filled_at or exit_order.created_at
                trade.exit_side = exit_order.side.value if hasattr(exit_order.side, 'value') else str(exit_order.side)
                trade.exit_reason = exit_reason
                trade.completed_at = datetime.utcnow()
                
                # Calculate P&L
                if trade.entry_side.lower() == 'buy':
                    # Long position: profit = (exit_price - entry_price) * quantity
                    trade.realized_pnl = (trade.exit_price - trade.entry_price) * trade.exit_quantity
                    trade.profit_percentage = ((trade.exit_price - trade.entry_price) / trade.entry_price) * 100
                else:
                    # Short position: profit = (entry_price - exit_price) * quantity
                    trade.realized_pnl = (trade.entry_price - trade.exit_price) * trade.exit_quantity
                    trade.profit_percentage = ((trade.entry_price - trade.exit_price) / trade.entry_price) * 100
                
                # Create summary
                trade_summary = {
                    'trade_id': trade_id,
                    'symbol': trade.symbol,
                    'entry_price': trade.entry_price,
                    'exit_price': trade.exit_price,
                    'quantity': trade.exit_quantity,
                    'realized_pnl': trade.realized_pnl,
                    'profit_percentage': trade.profit_percentage,
                    'exit_reason': exit_reason,
                    'duration_minutes': (trade.exit_time - trade.entry_time).total_seconds() / 60
                }
            # Auto-commit via context manager
            
            logger.info(f"Trade completed: {trade_id} - {trade.symbol} "
                       f"P&L: ${trade.realized_pnl:.2f} ({trade.profit_percentage:.2f}%) "
                       f"Reason: {exit_reason}")
            
            return trade_summary
                
        except Exception as e:
            logger.error(f"Error completing trade: {str(e)}")
            raise TradingBotException(f"Failed to complete trade: {str(e)}")
    
    async def update_trade_trailing_info(self, trade_id: str, activation_price: float = None, 
                                       peak_price: float = None) -> None:
        """
        Update trailing stop information for a trade.
        
        Args:
            trade_id: Trade identifier
            activation_price: Price at which trailing was activated
            peak_price: Peak price reached during trailing
        """
        try:
            async with self.get_session() as session:
                stmt = select(TradeRecord).where(TradeRecord.trade_id == trade_id)
                result = await session.execute(stmt)
                trade = result.scalar_one_or_none()
                
                if trade:
                    if activation_price is not None:
                        trade.trailing_started_at = activation_price
                    if peak_price is not None:
                        trade.trailing_peak_price = peak_price
                    
                    logger.debug(f"Updated trailing info for {trade_id}")
                
        except Exception as e:
            logger.error(f"Error updating trade trailing info: {str(e)}")
    
    async def get_trade_by_exit_order_id(self, exit_order_id: str) -> Optional[Dict[str, Any]]:
        """
        Find a trade by its exit order ID (deterministic lookup).
        
        This method provides deterministic trade lookup for externally closed
        positions by directly querying the exit_order_id foreign key.
        
        Args:
            exit_order_id: Exit order ID to search for
            
        Returns:
            Trade dictionary if found, None otherwise
            
        Example:
            ```python
            trade = await db.get_trade_by_exit_order_id("abc-123-def-456")
            if trade:
                print(f"Found trade {trade['trade_id']} for exit order")
            ```
        """
        try:
            async with self.get_session() as session:
                stmt = select(TradeRecord).where(TradeRecord.exit_order_id == str(exit_order_id))
                result = await session.execute(stmt)
                trade = result.scalar_one_or_none()
                
                if not trade:
                    return None
                
                return {
                    'trade_id': trade.trade_id,
                    'symbol': trade.symbol,
                    'entry_price': trade.entry_price,
                    'entry_quantity': trade.entry_quantity,
                    'entry_time': trade.entry_time,
                    'entry_side': trade.entry_side,
                    'exit_order_id': trade.exit_order_id,
                    'exit_price': trade.exit_price,
                    'exit_quantity': trade.exit_quantity,
                    'exit_time': trade.exit_time,
                    'exit_side': trade.exit_side,
                    'exit_reason': trade.exit_reason,
                    'realized_pnl': trade.realized_pnl,
                    'profit_percentage': trade.profit_percentage,
                    'strategy_used': trade.strategy_used
                }
                
        except Exception as e:
            logger.error(f"Error finding trade by exit order ID {exit_order_id}: {str(e)}")
            return None

    async def get_open_trades(self, symbol: str = None) -> List[Dict[str, Any]]:
        """
        Get all open trades (not yet completed).
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of open trade dictionaries
        """
        try:
            async with self.get_session() as session:
                stmt = select(TradeRecord).where(TradeRecord.completed_at.is_(None))
                
                if symbol:
                    stmt = stmt.where(TradeRecord.symbol == symbol)
                
                result = await session.execute(stmt)
                trades = result.scalars().all()
                
                open_trades = []
                for trade in trades:
                    open_trades.append({
                        'trade_id': trade.trade_id,
                        'symbol': trade.symbol,
                        'entry_price': trade.entry_price,
                        'entry_quantity': trade.entry_quantity,
                        'entry_time': trade.entry_time,
                        'entry_side': trade.entry_side,
                        'strategy_used': trade.strategy_used,
                        'trailing_started_at': trade.trailing_started_at,
                        'trailing_peak_price': trade.trailing_peak_price
                    })
                
                return open_trades
                
        except Exception as e:
            logger.error(f"Error getting open trades: {str(e)}")
            return []
    
    async def get_completed_trades(self, symbol: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get completed trades with P&L information.
        
        Args:
            symbol: Optional symbol filter
            limit: Maximum number of trades to return
            
        Returns:
            List of completed trade dictionaries
        """
        try:
            async with self.get_session() as session:
                stmt = select(TradeRecord).where(TradeRecord.completed_at.isnot(None))
                
                if symbol:
                    stmt = stmt.where(TradeRecord.symbol == symbol)
                
                stmt = stmt.order_by(TradeRecord.completed_at.desc()).limit(limit)
                result = await session.execute(stmt)
                trades = result.scalars().all()
                
                completed_trades = []
                for trade in trades:
                    completed_trades.append({
                        'trade_id': trade.trade_id,
                        'symbol': trade.symbol,
                        'entry_price': trade.entry_price,
                        'exit_price': trade.exit_price,
                        'quantity': trade.exit_quantity,
                        'entry_time': trade.entry_time,
                        'exit_time': trade.exit_time,
                        'realized_pnl': trade.realized_pnl,
                        'profit_percentage': trade.profit_percentage,
                        'exit_reason': trade.exit_reason,
                        'strategy_used': trade.strategy_used,
                        'trailing_started_at': trade.trailing_started_at,
                        'trailing_peak_price': trade.trailing_peak_price
                    })
                
                return completed_trades
                
        except Exception as e:
            logger.error(f"Error getting completed trades: {str(e)}")
            return []
    
    async def save_position_tracking(self, symbol: str, quantity: float, avg_price: float, 
                                   cost_basis: float, is_trailing: bool = False,
                                   activation_price: float = None, peak_price: float = None,
                                   stop_price: float = None) -> None:
        """
        Save or update enhanced position tracking information.
        
        Args:
            symbol: Trading symbol
            quantity: Current position quantity
            avg_price: Average entry price
            cost_basis: Total cost basis
            is_trailing: Whether position is currently trailing
            activation_price: Price at which trailing was activated
            peak_price: Peak price reached
            stop_price: Current trailing stop price
        """
        try:
            async with self.get_session() as session:
                # Get or create position tracking record
                stmt = select(PositionTrackingRecord).where(PositionTrackingRecord.symbol == symbol)
                result = await session.execute(stmt)
                tracking = result.scalar_one_or_none()
                
                if tracking:
                    # Update existing
                    tracking.total_quantity = quantity
                    tracking.avg_entry_price = avg_price
                    tracking.total_cost_basis = cost_basis
                    tracking.is_trailing = 'true' if is_trailing else 'false'
                    tracking.trailing_activation_price = activation_price
                    tracking.trailing_peak_price = peak_price
                    tracking.trailing_stop_price = stop_price
                    tracking.updated_at = datetime.utcnow()
                else:
                    # Create new
                    tracking = PositionTrackingRecord(
                        symbol=symbol,
                        total_quantity=quantity,
                        avg_entry_price=avg_price,
                        total_cost_basis=cost_basis,
                        is_trailing='true' if is_trailing else 'false',
                        trailing_activation_price=activation_price,
                        trailing_peak_price=peak_price,
                        trailing_stop_price=stop_price
                    )
                    session.add(tracking)
            # Auto-commit via context manager
                
        except Exception as e:
            logger.error(f"Error saving position tracking: {str(e)}")
    
    async def get_position_tracking(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get enhanced position tracking information.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Position tracking dictionary or None
        """
        try:
            async with self.get_session() as session:
                stmt = select(PositionTrackingRecord).where(PositionTrackingRecord.symbol == symbol)
                result = await session.execute(stmt)
                tracking = result.scalar_one_or_none()
                
                if tracking:
                    return {
                        'symbol': tracking.symbol,
                        'total_quantity': tracking.total_quantity,
                        'avg_entry_price': tracking.avg_entry_price,
                        'total_cost_basis': tracking.total_cost_basis,
                        'is_trailing': tracking.is_trailing == 'true',
                        'trailing_activation_price': tracking.trailing_activation_price,
                        'trailing_peak_price': tracking.trailing_peak_price,
                        'trailing_stop_price': tracking.trailing_stop_price,
                        'created_at': tracking.created_at,
                        'updated_at': tracking.updated_at
                    }
                
                return None
                
        except Exception as e:
            logger.error(f"Error getting position tracking: {str(e)}")
            return None
