"""
Database management implementation using SQLAlchemy.
Handles persistence of positions, orders, and trading history.
"""

import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool
import json
from ..interfaces import IConfigurationManager
from ..exceptions import TradingBotException
from ..core.logging_config import get_logger
from .. import Position, Order, OrderStatus, OrderType


logger = get_logger(__name__)

Base = declarative_base()


class PositionRecord(Base):
    """Database model for positions."""
    __tablename__ = 'positions'
    
    symbol = Column(String(10), primary_key=True)
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
    Database manager for persisting trading data.
    Supports SQLite for development and PostgreSQL for production.
    """
    
    def __init__(self, config: IConfigurationManager):
        """
        Initialize database manager.
        
        Args:
            config: Configuration manager instance
        """
        self._config = config
        self._engine = None
        self._session_factory = None
        
        # Database configuration
        self._db_url = config.get_config("database.url", "sqlite:///data/trading_bot.db")
        self._echo = config.get_config("database.echo", False)
        self._pool_size = config.get_config("database.pool_size", 5)
        self._max_overflow = config.get_config("database.max_overflow", 10)
        
        logger.info(f"DatabaseManager initialized with URL: {self._db_url}")
    
    async def initialize(self) -> None:
        """Initialize database connection and create tables."""
        try:
            logger.info("Initializing database...")
            
            # Create engine
            if self._db_url.startswith("sqlite"):
                # SQLite configuration
                self._engine = create_engine(
                    self._db_url,
                    echo=self._echo,
                    poolclass=StaticPool,
                    connect_args={"check_same_thread": False}
                )
            else:
                # PostgreSQL or other database configuration
                self._engine = create_engine(
                    self._db_url,
                    echo=self._echo,
                    pool_size=self._pool_size,
                    max_overflow=self._max_overflow
                )
            
            # Create session factory
            self._session_factory = sessionmaker(bind=self._engine)
            
            # Create tables
            Base.metadata.create_all(self._engine)
            
            logger.info("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {str(e)}")
            raise TradingBotException(f"Database initialization failed: {str(e)}")
    
    async def close(self) -> None:
        """Close database connections."""
        try:
            if self._engine:
                self._engine.dispose()
                logger.info("Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database: {str(e)}")
    
    async def save_position(self, position: Position) -> None:
        """
        Save or update a position in the database.
        
        Args:
            position: Position to save
        """
        try:
            session = self._session_factory()
            
            try:
                # Check if position exists
                existing = session.query(PositionRecord).filter_by(symbol=position.symbol).first()
                
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
                        quantity=position.quantity,
                        avg_price=position.avg_price,
                        current_price=position.current_price,
                        unrealized_pnl=position.unrealized_pnl,
                        realized_pnl=position.realized_pnl,
                        created_at=position.created_at,
                        updated_at=datetime.utcnow()
                    )
                    session.add(new_position)
                
                session.commit()
                logger.debug(f"Position saved: {position.symbol}")
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error saving position {position.symbol}: {str(e)}")
            raise
    
    async def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get a position from the database.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Position if found, None otherwise
        """
        try:
            session = self._session_factory()
            
            try:
                record = session.query(PositionRecord).filter_by(symbol=symbol).first()
                
                if record:
                    return Position(
                        symbol=record.symbol,
                        quantity=record.quantity,
                        avg_price=record.avg_price,
                        current_price=record.current_price,
                        unrealized_pnl=record.unrealized_pnl,
                        realized_pnl=record.realized_pnl,
                        created_at=record.created_at
                    )
                
                return None
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error getting position {symbol}: {str(e)}")
            return None
    
    async def get_all_positions(self) -> List[Position]:
        """
        Get all positions from the database.
        
        Returns:
            List of all positions
        """
        try:
            session = self._session_factory()
            
            try:
                records = session.query(PositionRecord).all()
                
                positions = []
                for record in records:
                    position = Position(
                        symbol=record.symbol,
                        quantity=record.quantity,
                        avg_price=record.avg_price,
                        current_price=record.current_price,
                        unrealized_pnl=record.unrealized_pnl,
                        realized_pnl=record.realized_pnl,
                        created_at=record.created_at
                    )
                    positions.append(position)
                
                return positions
                
            finally:
                session.close()
                
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
            session = self._session_factory()
            
            try:
                # Check if order exists
                existing = session.query(OrderRecord).filter_by(order_id=str(order.order_id)).first()  # Convert UUID to string
                
                if existing:
                    # Update existing order
                    existing.status = order.status.value
                    existing.filled_at = order.filled_at
                    existing.filled_price = order.filled_price
                    existing.filled_quantity = order.filled_quantity
                else:
                    # Create new order
                    new_order = OrderRecord(
                        order_id=str(order.order_id),  # Convert UUID to string
                        symbol=order.symbol,
                        quantity=order.quantity,
                        order_type=order.order_type.value,
                        side=order.side.value if hasattr(order.side, 'value') else str(order.side),  # Handle OrderSide enum
                        price=order.price,
                        stop_price=order.stop_price,
                        status=order.status.value,
                        created_at=order.created_at,
                        filled_at=order.filled_at,
                        filled_price=order.filled_price,
                        filled_quantity=order.filled_quantity
                    )
                    session.add(new_order)
                
                session.commit()
                logger.debug(f"Order saved: {order.order_id}")
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error saving order {order.order_id}: {str(e)}")
            raise
    
    async def get_orders(self, symbol: Optional[str] = None, 
                        status: Optional[OrderStatus] = None) -> List[Order]:
        """
        Get orders from the database with optional filtering.
        
        Args:
            symbol: Optional symbol filter
            status: Optional status filter
            
        Returns:
            List of orders matching criteria
        """
        try:
            session = self._session_factory()
            
            try:
                query = session.query(OrderRecord)
                
                if symbol:
                    query = query.filter_by(symbol=symbol)
                
                if status:
                    query = query.filter_by(status=status.value)
                
                records = query.all()
                
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
                        filled_quantity=record.filled_quantity
                    )
                    orders.append(order)
                
                return orders
                
            finally:
                session.close()
                
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
            session = self._session_factory()
            
            try:
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
                session.commit()
                
                logger.debug(f"Signal saved: {signal.signal_id}")
                
            finally:
                session.close()
                
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
            session = self._session_factory()
            
            try:
                # Calculate date range
                end_date = datetime.utcnow()
                start_date = end_date - timedelta(days=days)
                
                # Query orders in date range
                query = session.query(OrderRecord).filter(
                    OrderRecord.created_at >= start_date,
                    OrderRecord.created_at <= end_date
                )
                
                if symbol:
                    query = query.filter_by(symbol=symbol)
                
                orders = query.all()
                
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
                
            finally:
                session.close()
                
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
            session = self._session_factory()
            
            try:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                
                # Delete old filled/canceled orders (SAFE - never deletes open orders)
                deleted_orders = session.query(OrderRecord).filter(
                    OrderRecord.created_at < cutoff_date,
                    OrderRecord.status.in_([OrderStatus.FILLED.value, OrderStatus.CANCELED.value])
                ).delete()
                
                # Delete old signals
                deleted_signals = session.query(TradingSignalRecord).filter(
                    TradingSignalRecord.timestamp < cutoff_date
                ).delete()
                
                session.commit()
                logger.info(f"Cleaned up {deleted_orders} old orders and {deleted_signals} old signals (older than {days} days)")
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error cleaning up old data: {str(e)}")
    
    async def cleanup_closed_positions(self, days: int = 30) -> None:
        """
        Clean up closed positions (quantity = 0) older than specified days.
        SAFE: Only deletes positions that are completely closed.
        
        Args:
            days: Number of days to keep closed positions for historical reference
        """
        try:
            session = self._session_factory()
            
            try:
                cutoff_date = datetime.utcnow() - timedelta(days=days)
                
                # Only delete positions with zero quantity that are old
                deleted_positions = session.query(PositionRecord).filter(
                    PositionRecord.quantity == 0,  # CRITICAL: Only zero quantity positions
                    PositionRecord.updated_at < cutoff_date
                ).delete()
                
                session.commit()
                logger.info(f"Cleaned up {deleted_positions} closed positions (older than {days} days)")
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error cleaning up closed positions: {str(e)}")
    
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
            
            # Extract database path from URL
            if self._db_url.startswith("sqlite:///"):
                source_db = self._db_url.replace("sqlite:///", "")
                
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
            
            # Extract database path from URL
            if self._db_url.startswith("sqlite:///"):
                target_db = self._db_url.replace("sqlite:///", "")
                
                # Close existing connections
                if self._engine:
                    self._engine.dispose()
                
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
            session = self._session_factory()
            
            try:
                stats = {}
                
                # Count records in each table
                stats["positions_total"] = session.query(PositionRecord).count()
                stats["positions_open"] = session.query(PositionRecord).filter(
                    PositionRecord.quantity != 0
                ).count()
                stats["positions_closed"] = session.query(PositionRecord).filter(
                    PositionRecord.quantity == 0
                ).count()
                
                stats["orders_total"] = session.query(OrderRecord).count()
                stats["orders_filled"] = session.query(OrderRecord).filter(
                    OrderRecord.status == OrderStatus.FILLED.value
                ).count()
                
                stats["signals_total"] = session.query(TradingSignalRecord).count()
                
                # Get date ranges
                oldest_position = session.query(PositionRecord.created_at).order_by(
                    PositionRecord.created_at.asc()
                ).first()
                newest_position = session.query(PositionRecord.updated_at).order_by(
                    PositionRecord.updated_at.desc()
                ).first()
                
                if oldest_position:
                    stats["oldest_position_date"] = oldest_position[0]
                if newest_position:
                    stats["newest_position_date"] = newest_position[0]
                
                # Database file size (SQLite only)
                if self._db_url.startswith("sqlite:///"):
                    from pathlib import Path
                    db_file = self._db_url.replace("sqlite:///", "")
                    if Path(db_file).exists():
                        stats["database_size_bytes"] = Path(db_file).stat().st_size
                        stats["database_size_mb"] = stats["database_size_bytes"] / (1024 * 1024)
                
                return stats
                
            finally:
                session.close()
                
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
            session = self._session_factory()
            
            try:
                trade_id = f"{symbol}_{str(entry_order.order_id)}"
                
                trade = TradeRecord(
                    trade_id=trade_id,
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
                session.commit()
                
                logger.info(f"Trade entry created: {trade_id} - {symbol} {entry_order.side} "
                           f"{trade.entry_quantity} @ ${trade.entry_price:.4f}")
                
                return trade_id
                
            finally:
                session.close()
                
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
            session = self._session_factory()
            
            try:
                trade = session.query(TradeRecord).filter_by(trade_id=trade_id).first()
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
                
                session.commit()
                
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
                
                logger.info(f"Trade completed: {trade_id} - {trade.symbol} "
                           f"P&L: ${trade.realized_pnl:.2f} ({trade.profit_percentage:.2f}%) "
                           f"Reason: {exit_reason}")
                
                return trade_summary
                
            finally:
                session.close()
                
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
            session = self._session_factory()
            
            try:
                trade = session.query(TradeRecord).filter_by(trade_id=trade_id).first()
                if trade:
                    if activation_price is not None:
                        trade.trailing_started_at = activation_price
                    if peak_price is not None:
                        trade.trailing_peak_price = peak_price
                    
                    session.commit()
                    logger.debug(f"Updated trailing info for {trade_id}")
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error updating trade trailing info: {str(e)}")
    
    async def get_open_trades(self, symbol: str = None) -> List[Dict[str, Any]]:
        """
        Get all open trades (not yet completed).
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of open trade dictionaries
        """
        try:
            session = self._session_factory()
            
            try:
                query = session.query(TradeRecord).filter(TradeRecord.completed_at.is_(None))
                
                if symbol:
                    query = query.filter(TradeRecord.symbol == symbol)
                
                trades = query.all()
                
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
                
            finally:
                session.close()
                
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
            session = self._session_factory()
            
            try:
                query = session.query(TradeRecord).filter(TradeRecord.completed_at.isnot(None))
                
                if symbol:
                    query = query.filter(TradeRecord.symbol == symbol)
                
                trades = query.order_by(TradeRecord.completed_at.desc()).limit(limit).all()
                
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
                
            finally:
                session.close()
                
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
            session = self._session_factory()
            
            try:
                # Get or create position tracking record
                tracking = session.query(PositionTrackingRecord).filter_by(symbol=symbol).first()
                
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
                
                session.commit()
                
            finally:
                session.close()
                
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
            session = self._session_factory()
            
            try:
                tracking = session.query(PositionTrackingRecord).filter_by(symbol=symbol).first()
                
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
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"Error getting position tracking: {str(e)}")
            return None
