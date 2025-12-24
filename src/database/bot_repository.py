"""
Bot Repository for Database Persistence.

Provides database storage for individual bot configurations, allowing each bot
to have its own customized settings independent of global TOML configuration.

This module implements the Repository pattern for clean separation between
domain models and persistence layer.

Supports multiple bot types:
- DCA (Dollar Cost Averaging)
- COMBO (Combined Long/Short)
- GRID (Grid Trading)
- LOOP (Spot Loop for Sideways Markets)
- BTD (Buy The Dip)
- Futures variants (DCA, COMBO)

Author: Trading Bot Team
Version: 1.0.0
"""

from sqlalchemy import Column, String, Float, Integer, DateTime, Text, Boolean, JSON, Enum as SQLEnum
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, update
from datetime import datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal
import json
import uuid

from src.database.base import Base
from src.domain.bot_models import (
    Bot, BotConfiguration, BotState, BotType, BotAction,
    DCAConfig, PositionMode, MarginMode, BotPerformance,
    BotStartSettings, AveragingOrdersConfig, TakeProfitConfig,
    StopLossConfig, RiskManagementConfig, BotOperationalPhase,
    BotHistoryEntry,
)
from src.core.logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# Database Models
# =============================================================================

class BotRecord(Base):
    """
    Database record for trading bot persistence.
    
    Stores complete bot configuration and state, enabling:
    - Individual bot customization (overrides TOML defaults)
    - Bot lifecycle management
    - Performance tracking
    - Historical analysis
    """
    __tablename__ = 'bots'
    
    # Primary Key
    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Ownership & Identification
    user_id = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    
    # Asset Configuration
    symbol = Column(String(20), nullable=False, index=True)
    exchange = Column(String(50), nullable=False, index=True)
    asset_class = Column(String(20), nullable=False, default='stock')  # stock, crypto, forex, commodity, etf
    
    # Bot Type & Strategy
    bot_type = Column(String(20), nullable=False, index=True)  # dca, combo, grid, loop, btd, futures_dca, futures_combo
    position_mode = Column(String(10), nullable=False, default='long')  # long, short, both
    
    # Investment Configuration
    investment_amount = Column(Float, nullable=False)
    leverage = Column(Integer, nullable=False, default=1)
    margin_mode = Column(String(20), nullable=True)  # isolated, cross (for futures)
    
    # Strategy Configuration (JSON for flexibility)
    # Stores DCAConfig, GridConfig, ComboConfig, etc.
    strategy_config = Column(JSON, nullable=False)
    
    # Bot State
    state = Column(String(20), nullable=False, default='created', index=True)
    is_active = Column(Boolean, nullable=False, default=False)
    
    # Operational Phase Tracking (detailed state within running bot)
    operational_phase = Column(String(30), nullable=False, default='idle', index=True)
    # Signal tracking for indicator-based bots
    last_signal_match_at = Column(DateTime, nullable=True)  # When indicator conditions matched
    signal_indicators_status = Column(JSON, nullable=True)  # Current indicator values/status
    # Price range tracking for Grid/Loop/Combo bots
    price_range_status = Column(String(20), nullable=True)  # in_range, above_range, below_range
    grid_lower_bound = Column(Float, nullable=True)  # Grid lower price boundary
    grid_upper_bound = Column(Float, nullable=True)  # Grid upper price boundary
    # Cooldown tracking
    cooldown_until = Column(DateTime, nullable=True)  # When cooldown expires
    last_order_at = Column(DateTime, nullable=True)  # Last order placement time
    # Deal/Cycle tracking
    current_deal_id = Column(String(50), nullable=True)  # Current active deal/cycle ID
    completed_deals = Column(Integer, nullable=False, default=0)  # Total completed cycles
    
    # Performance Metrics (updated in real-time)
    total_invested = Column(Float, nullable=False, default=0.0)
    current_value = Column(Float, nullable=False, default=0.0)
    total_pnl = Column(Float, nullable=False, default=0.0)
    total_pnl_percent = Column(Float, nullable=False, default=0.0)
    bot_profit = Column(Float, nullable=False, default=0.0)
    total_trades = Column(Integer, nullable=False, default=0)
    winning_trades = Column(Integer, nullable=False, default=0)
    losing_trades = Column(Integer, nullable=False, default=0)
    
    # Position State (for active bots)
    current_position_size = Column(Float, nullable=True)
    avg_entry_price = Column(Float, nullable=True)
    current_price = Column(Float, nullable=True)
    dca_layers_used = Column(Integer, nullable=False, default=0)
    pending_orders_count = Column(Integer, nullable=False, default=0)
    
    # Account Mode
    account_mode = Column(String(10), nullable=False, default='demo')  # demo, live
    
    # Tags for organization
    tags = Column(JSON, nullable=True)  # List of string tags
    
    # Error tracking
    last_error = Column(Text, nullable=True)
    error_count = Column(Integer, nullable=False, default=0)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    stopped_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_domain_model(self) -> Bot:
        """Convert database record to domain model."""
        from src.domain.bot_models import Bot, BotConfiguration, BotPerformance
        
        # Parse strategy config
        config_data = self.strategy_config or {}
        dca_config = DCAConfig.from_dict(config_data.get('dca_config', {})) if config_data.get('dca_config') else DCAConfig()
        
        configuration = BotConfiguration(
            symbol=self.symbol,
            exchange=self.exchange,
            asset_class=self.asset_class,
            position_mode=PositionMode(self.position_mode),
            investment_amount=Decimal(str(self.investment_amount)),
            leverage=self.leverage,
            margin_mode=MarginMode(self.margin_mode) if self.margin_mode else MarginMode.ISOLATED,
            bot_type=BotType(self.bot_type),
            dca_config=dca_config,
        )
        
        # Calculate trading time
        trading_time_seconds = 0
        if self.started_at:
            end_time = self.stopped_at or datetime.utcnow()
            trading_time_seconds = int((end_time - self.started_at).total_seconds())
        
        performance = BotPerformance(
            total_invested=Decimal(str(self.total_invested)),
            current_value=Decimal(str(self.current_value)),
            total_pnl=Decimal(str(self.total_pnl)),
            total_pnl_percent=Decimal(str(self.total_pnl_percent)),
            bot_profit=Decimal(str(self.bot_profit)),
            bot_profit_percent=Decimal(str((self.bot_profit / self.total_invested * 100) if self.total_invested > 0 else 0)),
            total_trades=self.total_trades,
            winning_trades=self.winning_trades,
            losing_trades=self.losing_trades,
            win_rate=Decimal(str((self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0)),
            trading_time_seconds=trading_time_seconds,
            dca_layers_used=self.dca_layers_used,
            position_size=Decimal(str(self.current_position_size)) if self.current_position_size else None,
            avg_entry_price=Decimal(str(self.avg_entry_price)) if self.avg_entry_price else None,
            current_price=Decimal(str(self.current_price)) if self.current_price else None,
            pending_orders_count=self.pending_orders_count,
        )
        
        return Bot(
            id=self.id,
            user_id=self.user_id,
            name=self.name,
            description=self.description,
            state=BotState(self.state),
            configuration=configuration,
            performance=performance,
            created_at=self.created_at,
            started_at=self.started_at,
            stopped_at=self.stopped_at,
            updated_at=self.updated_at,
            tags=self.tags or [],
            error_message=self.last_error,
            # Operational Phase Tracking
            operational_phase=BotOperationalPhase(self.operational_phase) if self.operational_phase else BotOperationalPhase.IDLE,
            last_signal_match_at=self.last_signal_match_at,
            signal_indicators_status=self.signal_indicators_status,
            # Price Range Tracking (Grid/Loop/Combo bots)
            price_range_status=self.price_range_status,
            grid_lower_bound=Decimal(str(self.grid_lower_bound)) if self.grid_lower_bound else None,
            grid_upper_bound=Decimal(str(self.grid_upper_bound)) if self.grid_upper_bound else None,
            # Cooldown Tracking
            cooldown_until=self.cooldown_until,
            last_order_at=self.last_order_at,
            # Deal/Cycle Tracking
            current_deal_id=self.current_deal_id,
            completed_deals=self.completed_deals or 0,
        )
    
    @classmethod
    def from_domain_model(cls, bot: Bot) -> "BotRecord":
        """Create database record from domain model."""
        strategy_config = {
            'dca_config': bot.configuration.dca_config.to_dict() if bot.configuration.dca_config else None,
            # Add other strategy configs here (grid_config, combo_config, etc.)
        }
        
        return cls(
            id=bot.id,
            user_id=bot.user_id,
            name=bot.name,
            description=bot.description,
            symbol=bot.configuration.symbol,
            exchange=bot.configuration.exchange,
            asset_class=bot.configuration.asset_class,
            bot_type=bot.configuration.bot_type.value,
            position_mode=bot.configuration.position_mode.value,
            investment_amount=float(bot.configuration.investment_amount),
            leverage=bot.configuration.leverage,
            margin_mode=bot.configuration.margin_mode.value if bot.configuration.margin_mode else None,
            strategy_config=strategy_config,
            state=bot.state.value,
            is_active=bot.is_active,
            total_invested=float(bot.performance.total_invested) if bot.performance else 0.0,
            current_value=float(bot.performance.current_value) if bot.performance else 0.0,
            total_pnl=float(bot.performance.total_pnl) if bot.performance else 0.0,
            total_pnl_percent=float(bot.performance.total_pnl_percent) if bot.performance else 0.0,
            bot_profit=float(bot.performance.bot_profit) if bot.performance else 0.0,
            total_trades=bot.performance.total_trades if bot.performance else 0,
            winning_trades=bot.performance.winning_trades if bot.performance else 0,
            losing_trades=bot.performance.losing_trades if bot.performance else 0,
            dca_layers_used=bot.performance.dca_layers_used if bot.performance else 0,
            tags=bot.tags,
            created_at=bot.created_at,
            started_at=bot.started_at,
            stopped_at=bot.stopped_at,
            updated_at=bot.updated_at,
            # Operational Phase Tracking
            operational_phase=bot.operational_phase.value if bot.operational_phase else 'idle',
            last_signal_match_at=bot.last_signal_match_at,
            signal_indicators_status=bot.signal_indicators_status,
            # Price Range Tracking (Grid/Loop/Combo bots)
            price_range_status=bot.price_range_status,
            grid_lower_bound=float(bot.grid_lower_bound) if bot.grid_lower_bound else None,
            grid_upper_bound=float(bot.grid_upper_bound) if bot.grid_upper_bound else None,
            # Cooldown Tracking
            cooldown_until=bot.cooldown_until,
            last_order_at=bot.last_order_at,
            # Deal/Cycle Tracking
            current_deal_id=bot.current_deal_id,
            completed_deals=bot.completed_deals or 0,
        )


class BotHistoryRecord(Base):
    """
    Historical record of completed/stopped bots for analytics.
    Created when a bot is stopped or completes.
    """
    __tablename__ = 'bot_history'
    
    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    bot_id = Column(String(50), nullable=False, index=True)
    user_id = Column(String(50), nullable=False, index=True)
    
    # Bot identification
    name = Column(String(100), nullable=False)
    symbol = Column(String(20), nullable=False)
    exchange = Column(String(50), nullable=False)
    bot_type = Column(String(20), nullable=False)
    
    # Final state
    final_state = Column(String(20), nullable=False)
    
    # Performance summary
    total_invested = Column(Float, nullable=False)
    total_profit = Column(Float, nullable=False)
    total_profit_percent = Column(Float, nullable=False)
    total_trades = Column(Integer, nullable=False)
    win_rate = Column(Float, nullable=False)
    
    # Duration
    started_at = Column(DateTime, nullable=False)
    stopped_at = Column(DateTime, nullable=False)
    trading_duration_seconds = Column(Integer, nullable=False)
    
    # Metadata
    account_mode = Column(String(10), nullable=False, default='demo')
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class BotOrderRecord(Base):
    """
    Orders placed by bots for detailed tracking.
    Links orders to specific bots for analysis.
    """
    __tablename__ = 'bot_orders'
    
    id = Column(String(50), primary_key=True, default=lambda: str(uuid.uuid4()))
    bot_id = Column(String(50), nullable=False, index=True)
    broker_order_id = Column(String(50), nullable=False, index=True)
    
    # Order details
    symbol = Column(String(20), nullable=False)
    side = Column(String(10), nullable=False)  # buy, sell
    order_type = Column(String(20), nullable=False)  # market, limit
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=True)  # Limit price
    
    # Execution
    status = Column(String(20), nullable=False, default='pending')
    filled_quantity = Column(Float, nullable=False, default=0.0)
    filled_price = Column(Float, nullable=True)
    
    # DCA metadata
    layer_number = Column(Integer, nullable=True)  # 0 = base order, 1+ = safety orders
    is_take_profit = Column(Boolean, nullable=False, default=False)
    is_stop_loss = Column(Boolean, nullable=False, default=False)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    filled_at = Column(DateTime, nullable=True)
    cancelled_at = Column(DateTime, nullable=True)
    cancel_reason = Column(String(100), nullable=True)


# =============================================================================
# Repository Implementation
# =============================================================================

class BotRepository:
    """
    Repository for bot persistence operations.
    
    Provides async CRUD operations for bots with proper
    transaction management and error handling.
    """
    
    def __init__(self, session_factory):
        """
        Initialize repository with async session factory.
        
        Args:
            session_factory: Async sessionmaker for database connections
        """
        self._session_factory = session_factory
    
    async def create(self, bot: Bot) -> Bot:
        """
        Create a new bot in the database.
        
        Args:
            bot: Bot domain model to persist
            
        Returns:
            Created bot with generated ID
        """
        async with self._session_factory() as session:
            record = BotRecord.from_domain_model(bot)
            session.add(record)
            await session.commit()
            await session.refresh(record)
            logger.info(f"Created bot {record.id} for symbol {record.symbol}")
            return record.to_domain_model()
    
    async def get_by_id(self, bot_id: str, account_mode: str = 'demo') -> Optional[Bot]:
        """
        Get a bot by ID.
        
        Args:
            bot_id: Bot unique identifier
            account_mode: Account mode filter (demo/live)
            
        Returns:
            Bot if found, None otherwise
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(BotRecord).where(
                    BotRecord.id == bot_id,
                    BotRecord.account_mode == account_mode
                )
            )
            record = result.scalar_one_or_none()
            return record.to_domain_model() if record else None
    
    async def list_bots(
        self,
        user_id: Optional[str] = None,
        account_mode: str = 'demo',
        state: Optional[str] = None,
        symbol: Optional[str] = None,
        exchange: Optional[str] = None,
        bot_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Bot]:
        """
        List bots with optional filtering.
        
        Args:
            user_id: Filter by user
            account_mode: Filter by account mode
            state: Filter by state (comma-separated for multiple)
            symbol: Filter by symbol (partial match)
            exchange: Filter by exchange
            bot_type: Filter by bot type
            is_active: Filter by active status
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of matching bots
        """
        async with self._session_factory() as session:
            query = select(BotRecord).where(BotRecord.account_mode == account_mode)
            
            if user_id:
                query = query.where(BotRecord.user_id == user_id)
            
            if state:
                states = [s.strip() for s in state.split(',')]
                query = query.where(BotRecord.state.in_(states))
            
            if symbol:
                query = query.where(BotRecord.symbol.ilike(f'%{symbol}%'))
            
            if exchange:
                query = query.where(BotRecord.exchange == exchange)
            
            if bot_type:
                query = query.where(BotRecord.bot_type == bot_type)
            
            if is_active is not None:
                query = query.where(BotRecord.is_active == is_active)
            
            query = query.order_by(BotRecord.updated_at.desc())
            query = query.limit(limit).offset(offset)
            
            result = await session.execute(query)
            records = result.scalars().all()
            
            return [record.to_domain_model() for record in records]
    
    async def update(self, bot: Bot) -> Bot:
        """
        Update an existing bot.
        
        Args:
            bot: Bot with updated fields
            
        Returns:
            Updated bot
        """
        async with self._session_factory() as session:
            result = await session.execute(
                select(BotRecord).where(BotRecord.id == bot.id)
            )
            record = result.scalar_one_or_none()
            
            if not record:
                raise ValueError(f"Bot {bot.id} not found")
            
            # Update fields
            record.name = bot.name
            record.description = bot.description
            record.state = bot.state.value
            record.is_active = bot.is_active
            record.tags = bot.tags
            record.last_error = bot.error
            record.started_at = bot.started_at
            record.stopped_at = bot.stopped_at
            record.updated_at = datetime.utcnow()
            
            # Update strategy config
            record.strategy_config = {
                'dca_config': bot.configuration.dca_config.to_dict() if bot.configuration.dca_config else None,
            }
            
            # Update performance
            if bot.performance:
                record.total_invested = float(bot.performance.total_invested)
                record.current_value = float(bot.performance.current_value)
                record.total_pnl = float(bot.performance.total_pnl)
                record.total_pnl_percent = float(bot.performance.total_pnl_percent)
                record.bot_profit = float(bot.performance.bot_profit)
                record.total_trades = bot.performance.total_trades
                record.winning_trades = bot.performance.winning_trades
                record.losing_trades = bot.performance.losing_trades
                record.dca_layers_used = bot.performance.dca_layers_used
                if bot.performance.position_size:
                    record.current_position_size = float(bot.performance.position_size)
                if bot.performance.avg_entry_price:
                    record.avg_entry_price = float(bot.performance.avg_entry_price)
                if bot.performance.current_price:
                    record.current_price = float(bot.performance.current_price)
                record.pending_orders_count = bot.performance.pending_orders_count or 0
            
            await session.commit()
            await session.refresh(record)
            
            logger.info(f"Updated bot {record.id}")
            return record.to_domain_model()
    
    async def delete(self, bot_id: str, hard_delete: bool = False) -> bool:
        """
        Delete a bot.
        
        Args:
            bot_id: Bot ID to delete
            hard_delete: If True, permanently removes. If False, soft delete.
            
        Returns:
            True if deleted, False if not found
        """
        async with self._session_factory() as session:
            if hard_delete:
                result = await session.execute(
                    delete(BotRecord).where(BotRecord.id == bot_id)
                )
                await session.commit()
                deleted = result.rowcount > 0
            else:
                # Move to history and delete
                result = await session.execute(
                    select(BotRecord).where(BotRecord.id == bot_id)
                )
                record = result.scalar_one_or_none()
                
                if record:
                    # Create history record
                    history = BotHistoryRecord(
                        bot_id=record.id,
                        user_id=record.user_id,
                        name=record.name,
                        symbol=record.symbol,
                        exchange=record.exchange,
                        bot_type=record.bot_type,
                        final_state=record.state,
                        total_invested=record.total_invested,
                        total_profit=record.bot_profit,
                        total_profit_percent=float((record.bot_profit / record.total_invested * 100) if record.total_invested > 0 else 0),
                        total_trades=record.total_trades,
                        win_rate=float((record.winning_trades / record.total_trades * 100) if record.total_trades > 0 else 0),
                        started_at=record.started_at or record.created_at,
                        stopped_at=record.stopped_at or datetime.utcnow(),
                        trading_duration_seconds=int((datetime.utcnow() - (record.started_at or record.created_at)).total_seconds()),
                        account_mode=record.account_mode,
                    )
                    session.add(history)
                    
                    # Delete bot record
                    await session.delete(record)
                    await session.commit()
                    deleted = True
                else:
                    deleted = False
            
            if deleted:
                logger.info(f"Deleted bot {bot_id}")
            return deleted
    
    async def update_performance(
        self,
        bot_id: str,
        total_pnl: float,
        current_value: float,
        position_size: Optional[float] = None,
        avg_entry_price: Optional[float] = None,
        current_price: Optional[float] = None,
        dca_layers_used: Optional[int] = None,
    ) -> bool:
        """
        Update bot performance metrics (optimized for frequent updates).
        
        Args:
            bot_id: Bot ID
            total_pnl: Current total PnL
            current_value: Current position value
            position_size: Current position size
            avg_entry_price: Current average entry price
            current_price: Current market price
            dca_layers_used: Number of DCA layers used
            
        Returns:
            True if updated
        """
        async with self._session_factory() as session:
            values = {
                'total_pnl': total_pnl,
                'current_value': current_value,
                'updated_at': datetime.utcnow(),
            }
            
            if position_size is not None:
                values['current_position_size'] = position_size
            if avg_entry_price is not None:
                values['avg_entry_price'] = avg_entry_price
            if current_price is not None:
                values['current_price'] = current_price
            if dca_layers_used is not None:
                values['dca_layers_used'] = dca_layers_used
            
            result = await session.execute(
                update(BotRecord)
                .where(BotRecord.id == bot_id)
                .values(**values)
            )
            await session.commit()
            
            return result.rowcount > 0
    
    # =========================================================================
    # Bot History Operations
    # =========================================================================
    
    async def get_history(
        self,
        user_id: str,
        symbol_filter: Optional[str] = None,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> List[BotHistoryEntry]:
        """
        Get bot history records for a user.
        
        Args:
            user_id: User ID to query history for
            symbol_filter: Optional symbol filter
            include_deleted: Include soft-deleted records
            limit: Maximum records to return
            offset: Pagination offset
            
        Returns:
            List of BotHistoryEntry domain objects
        """
        async with self._session_factory() as session:
            query = select(BotHistoryRecord).where(
                BotHistoryRecord.user_id == user_id
            )
            
            if symbol_filter:
                query = query.where(BotHistoryRecord.symbol == symbol_filter)
            
            if not include_deleted:
                query = query.where(BotHistoryRecord.is_deleted == False)
            
            query = query.order_by(BotHistoryRecord.stopped_at.desc())
            query = query.offset(offset).limit(limit)
            
            result = await session.execute(query)
            records = result.scalars().all()
            
            return [self._record_to_history_entry(r) for r in records]
    
    async def delete_history_entry(
        self,
        history_id: str,
        user_id: str,
        hard_delete: bool = False,
    ) -> bool:
        """
        Delete a history entry.
        
        Args:
            history_id: History entry ID
            user_id: User ID (for authorization)
            hard_delete: If True, permanently delete
            
        Returns:
            True if deleted
        """
        async with self._session_factory() as session:
            if hard_delete:
                result = await session.execute(
                    delete(BotHistoryRecord).where(
                        BotHistoryRecord.id == history_id,
                        BotHistoryRecord.user_id == user_id
                    )
                )
            else:
                result = await session.execute(
                    update(BotHistoryRecord)
                    .where(
                        BotHistoryRecord.id == history_id,
                        BotHistoryRecord.user_id == user_id
                    )
                    .values(
                        is_deleted=True,
                        deleted_at=datetime.utcnow()
                    )
                )
            await session.commit()
            return result.rowcount > 0
    
    async def get_history_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get aggregate statistics from bot history.
        
        Args:
            user_id: User ID
            
        Returns:
            Dictionary with aggregate stats
        """
        from sqlalchemy import func
        
        async with self._session_factory() as session:
            # Get aggregate stats
            query = select(
                func.count(BotHistoryRecord.id).label('total_bots'),
                func.sum(BotHistoryRecord.total_profit).label('total_profit'),
                func.avg(BotHistoryRecord.total_profit_percent).label('avg_profit_pct'),
                func.avg(BotHistoryRecord.win_rate).label('avg_win_rate'),
            ).where(
                BotHistoryRecord.user_id == user_id,
                BotHistoryRecord.is_deleted == False
            )
            
            result = await session.execute(query)
            row = result.first()
            
            if not row or row.total_bots == 0:
                return {
                    "total_bots_run": 0,
                    "total_profit": 0.0,
                    "average_profit_percent": 0.0,
                    "win_rate": 0.0,
                    "best_performer": None,
                    "worst_performer": None,
                }
            
            # Get best performer
            best_query = select(BotHistoryRecord).where(
                BotHistoryRecord.user_id == user_id,
                BotHistoryRecord.is_deleted == False
            ).order_by(BotHistoryRecord.total_profit_percent.desc()).limit(1)
            
            best_result = await session.execute(best_query)
            best = best_result.scalar_one_or_none()
            
            # Get worst performer
            worst_query = select(BotHistoryRecord).where(
                BotHistoryRecord.user_id == user_id,
                BotHistoryRecord.is_deleted == False
            ).order_by(BotHistoryRecord.total_profit_percent.asc()).limit(1)
            
            worst_result = await session.execute(worst_query)
            worst = worst_result.scalar_one_or_none()
            
            return {
                "total_bots_run": row.total_bots or 0,
                "total_profit": float(row.total_profit or 0.0),
                "average_profit_percent": float(row.avg_profit_pct or 0.0),
                "win_rate": float(row.avg_win_rate or 0.0),
                "best_performer": best.name if best else None,
                "worst_performer": worst.name if worst else None,
            }
    
    def _record_to_history_entry(self, record: BotHistoryRecord) -> BotHistoryEntry:
        """Convert database record to domain model."""
        return BotHistoryEntry(
            id=record.id,
            bot_id=record.bot_id,
            name=record.name,
            symbol=record.symbol,
            final_state=record.final_state,
            total_profit=Decimal(str(record.total_profit)),
            total_profit_percent=Decimal(str(record.total_profit_percent)),
            started_at=record.started_at,
            stopped_at=record.stopped_at,
        )


# =============================================================================
# Strategy Configuration Models (for different bot types)
# =============================================================================

# These will be expanded as we add more bot types

class GridConfig:
    """Configuration for Grid trading bots (placeholder for future)."""
    pass


class ComboConfig:
    """Configuration for COMBO bots (placeholder for future)."""
    pass


class LoopConfig:
    """Configuration for Spot Loop bots (placeholder for future)."""
    pass


class BuyTheDipConfig:
    """Configuration for Buy The Dip bots (placeholder for future)."""
    pass
