"""
Cosmos DB Bot Repository - Complete Bot Persistence Layer.

This module provides comprehensive bot management using Azure Cosmos DB.
It stores bots, their orders, order history, and closed bot history with
complete trading performance tracking including fees, PnL, and analytics.

Architecture:
- Container: 'bots' - Active bot configurations and state
- Container: 'bot_history' - Closed/deleted bots for analytics
- Container: 'bot_orders' - All orders associated with bots

Partition Strategy:
- bots: /user_id (enables efficient per-user queries)
- bot_history: /user_id (historical analytics per user)
- bot_orders: /bot_id (all orders for a bot together)

Model Integration:
    This module uses domain models from src.domain as the single source of truth:
    - Bot, BotPerformance, BotOrder from src.domain.bot_state
    - BotState, BotType, BotOperationalPhase from src.domain.bot_enums
    - BotConfiguration, DCAConfig from src.domain.bot_config
    
    Mapper functions convert between domain models and Cosmos DB documents.

Lazy Loading:
    Azure SDK imports are deferred until initialize() is called.
    This allows tests to import this module without Azure SDK installed.

Note:
    This module uses CosmosBaseRepository for shared connection pool
    and common utilities. See cosmos_base.py for details.

Author: Trading Bot Team
Version: 3.2.0
"""

from __future__ import annotations

import uuid
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING
from dataclasses import dataclass, field, asdict
from enum import Enum

# Lazy imports for Azure SDK - only loaded when actually initializing
if TYPE_CHECKING:
    from azure.cosmos import exceptions as cosmos_exceptions
    from azure.identity.aio import DefaultAzureCredential

from src.core.logging_config import get_logger
from src.database.cosmos_base import (
    CosmosBaseRepository,
    CosmosConnectionPool,
    COSMOS_SYSTEM_PROPERTIES
)
from src.database.database_interface import IBotRepository
# Import domain models as single source of truth
from src.domain.bot_enums import (
    BotState,
    BotType,
    BotOperationalPhase,
)
from src.domain.bot_config import BotConfiguration, DCAConfig
from src.domain.bot_state import Bot, BotPerformance, BotOrder as DomainBotOrder


logger = get_logger(__name__)


# =============================================================================
# Enums - Imported from Domain (Single Source of Truth)
# =============================================================================
# BotState, BotType, BotOperationalPhase are imported from src.domain.bot_enums
# This ensures consistency between domain layer and persistence layer.

# Database-specific enums (not in domain layer)
class OrderSide(str, Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """Order execution status."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


# =============================================================================
# Database-Specific Data Models (Cosmos Documents)
# =============================================================================
# These models are specific to the persistence layer and include fields
# needed for Cosmos DB storage that aren't part of the domain models.

@dataclass
class FeeDetails:
    """Trading fee breakdown for order tracking."""
    commission: float = 0.0
    exchange_fee: float = 0.0
    regulatory_fee: float = 0.0
    slippage: float = 0.0
    total: float = 0.0
    currency: str = "USD"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for Cosmos storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeeDetails":
        """Create from dictionary."""
        if not data:
            return cls()
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class OrderFill:
    """Individual order fill information."""
    fill_id: str = ""
    quantity: float = 0.0
    price: float = 0.0
    timestamp: str = ""
    fees: FeeDetails = field(default_factory=FeeDetails)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = asdict(self)
        result['fees'] = self.fees.to_dict()
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OrderFill":
        """Create from dictionary."""
        if not data:
            return cls()
        fees = FeeDetails.from_dict(data.pop('fees', {}))
        return cls(fees=fees, **{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class CosmosBotOrder:
    """
    Complete order record for Cosmos DB storage.
    
    This is the persistence-layer order model with full tracking including
    fees, fills, and DCA metadata. Different from domain BotOrder which
    is a simpler runtime model.
    """
    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    bot_id: str = ""  # Partition key
    order_id: str = ""  # Broker order ID
    
    # Order Details
    symbol: str = ""
    side: str = OrderSide.BUY.value
    order_type: str = "limit"
    quantity: float = 0.0
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    
    # Execution
    status: str = OrderStatus.PENDING.value
    filled_quantity: float = 0.0
    average_fill_price: float = 0.0
    fills: List[Dict[str, Any]] = field(default_factory=list)
    
    # Fees & Costs
    fees: FeeDetails = field(default_factory=FeeDetails)
    total_cost: float = 0.0  # quantity * price + fees
    net_amount: float = 0.0  # For sells: proceeds - fees
    
    # DCA/Strategy Metadata
    is_dca_order: bool = False
    dca_layer: int = 0
    strategy_signal: str = ""
    
    # Timestamps
    created_at: str = ""
    submitted_at: Optional[str] = None
    filled_at: Optional[str] = None
    canceled_at: Optional[str] = None
    updated_at: str = ""
    
    # Metadata
    broker: str = "alpaca"
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Set timestamps if not provided."""
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        if not self.id:
            self.id = str(uuid.uuid4())
    
    def to_cosmos_doc(self) -> Dict[str, Any]:
        """Convert to Cosmos DB document."""
        doc = asdict(self)
        doc['fees'] = self.fees.to_dict()
        doc['fills'] = [f if isinstance(f, dict) else f.to_dict() for f in self.fills]
        doc['_type'] = 'bot_order'
        return doc
    
    @classmethod
    def from_cosmos_doc(cls, doc: Dict[str, Any]) -> "CosmosBotOrder":
        """Create from Cosmos DB document."""
        if not doc:
            return None
        
        # Remove Cosmos metadata
        doc.pop('_type', None)
        doc.pop('_rid', None)
        doc.pop('_self', None)
        doc.pop('_etag', None)
        doc.pop('_attachments', None)
        doc.pop('_ts', None)
        
        fees = FeeDetails.from_dict(doc.pop('fees', {}))
        fills = [OrderFill.from_dict(f) if isinstance(f, dict) else f for f in doc.pop('fills', [])]
        
        return cls(
            fees=fees,
            fills=fills,
            **{k: v for k, v in doc.items() if k in cls.__dataclass_fields__}
        )


# =============================================================================
# Domain Model ↔ Cosmos Document Mappers
# =============================================================================
# These functions convert between domain models (src.domain) and Cosmos DB documents.
# Domain models are the single source of truth; Cosmos documents are storage format.

def _decimal_to_float(value: Any) -> float:
    """Convert Decimal to float for JSON serialization."""
    if isinstance(value, Decimal):
        return float(value)
    return value


def bot_to_cosmos_doc(bot: Bot) -> Dict[str, Any]:
    """
    Convert domain Bot to Cosmos DB document.
    
    Maps the rich domain Bot model to a flat document structure
    suitable for Cosmos DB storage. Handles nested configurations
    and converts Decimals to floats.
    
    Args:
        bot: Domain Bot instance
        
    Returns:
        Dictionary ready for Cosmos DB storage
    """
    # Start with the bot's to_dict() which handles nested objects
    doc = bot.to_dict()
    
    # Convert camelCase keys back to snake_case for storage consistency
    cosmos_doc = {
        "id": bot.id,
        "user_id": bot.user_id,
        "name": bot.name,
        "description": bot.description,
        "symbol": bot.symbol,
        "exchange": bot.exchange,
        "bot_type": bot.bot_type.value,
        "state": bot.state.value,
        "is_active": bot.is_active,
        "error_message": bot.error_message,
        "operational_phase": bot.operational_phase.value,
        # Configuration stored as nested dict
        "configuration": bot.configuration.to_dict(),
        # Performance metrics  
        "performance": _performance_to_cosmos(bot.performance),
        # Timestamps (ISO format strings)
        "created_at": bot.created_at.isoformat() if bot.created_at else None,
        "started_at": bot.started_at.isoformat() if bot.started_at else None,
        "stopped_at": bot.stopped_at.isoformat() if bot.stopped_at else None,
        "last_activity_at": bot.last_activity_at.isoformat() if bot.last_activity_at else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        # Operational tracking
        "last_signal_match_at": bot.last_signal_match_at.isoformat() if bot.last_signal_match_at else None,
        "signal_indicators_status": bot.signal_indicators_status,
        "price_range_status": bot.price_range_status,
        "grid_lower_bound": _decimal_to_float(bot.grid_lower_bound) if bot.grid_lower_bound else None,
        "grid_upper_bound": _decimal_to_float(bot.grid_upper_bound) if bot.grid_upper_bound else None,
        "cooldown_until": bot.cooldown_until.isoformat() if bot.cooldown_until else None,
        "last_order_at": bot.last_order_at.isoformat() if bot.last_order_at else None,
        "current_deal_id": bot.current_deal_id,
        "completed_deals": bot.completed_deals,
        # Metadata
        "tags": bot.tags,
        "_type": "bot"
    }
    
    return cosmos_doc


def cosmos_doc_to_bot(doc: Dict[str, Any]) -> Optional[Bot]:
    """
    Convert Cosmos DB document to domain Bot.
    
    Maps stored document back to the rich domain Bot model,
    reconstructing nested configurations and handling type conversions.
    
    Args:
        doc: Cosmos DB document dictionary
        
    Returns:
        Domain Bot instance, or None if doc is empty
    """
    if not doc:
        return None
    
    # Remove Cosmos system properties
    for key in COSMOS_SYSTEM_PROPERTIES:
        doc.pop(key, None)
    doc.pop('_type', None)
    
    # Parse configuration
    config_data = doc.get('configuration', {})
    configuration = BotConfiguration.from_dict(config_data) if config_data else BotConfiguration(
        symbol=doc.get('symbol', ''),
        exchange=doc.get('exchange', 'alpaca')
    )
    
    # Parse performance
    perf_data = doc.get('performance', {})
    performance = _cosmos_to_performance(perf_data)
    
    # Parse timestamps
    created_at = _parse_datetime(doc.get('created_at'))
    started_at = _parse_datetime(doc.get('started_at'))
    stopped_at = _parse_datetime(doc.get('stopped_at'))
    last_activity_at = _parse_datetime(doc.get('last_activity_at'))
    last_signal_match_at = _parse_datetime(doc.get('last_signal_match_at'))
    cooldown_until = _parse_datetime(doc.get('cooldown_until'))
    last_order_at = _parse_datetime(doc.get('last_order_at'))
    
    # Parse enums with fallback defaults
    state_str = doc.get('state', 'created')
    try:
        state = BotState(state_str)
    except ValueError:
        state = BotState.CREATED
    
    phase_str = doc.get('operational_phase', 'idle')
    try:
        operational_phase = BotOperationalPhase(phase_str)
    except ValueError:
        operational_phase = BotOperationalPhase.IDLE
    
    # Construct the domain Bot
    bot = Bot(
        id=doc.get('id', str(uuid.uuid4())),
        user_id=doc.get('user_id', ''),
        name=doc.get('name', ''),
        description=doc.get('description', ''),
        configuration=configuration,
        state=state,
        error_message=doc.get('error_message'),
        operational_phase=operational_phase,
        last_signal_match_at=last_signal_match_at,
        signal_indicators_status=doc.get('signal_indicators_status'),
        price_range_status=doc.get('price_range_status'),
        grid_lower_bound=Decimal(str(doc['grid_lower_bound'])) if doc.get('grid_lower_bound') else None,
        grid_upper_bound=Decimal(str(doc['grid_upper_bound'])) if doc.get('grid_upper_bound') else None,
        cooldown_until=cooldown_until,
        last_order_at=last_order_at,
        current_deal_id=doc.get('current_deal_id'),
        completed_deals=doc.get('completed_deals', 0),
        performance=performance,
        created_at=created_at or datetime.now(timezone.utc),
        started_at=started_at,
        stopped_at=stopped_at,
        last_activity_at=last_activity_at,
        tags=doc.get('tags', [])
    )
    
    return bot


def _performance_to_cosmos(perf: BotPerformance) -> Dict[str, Any]:
    """Convert domain BotPerformance to Cosmos storage format."""
    return {
        "total_invested": _decimal_to_float(perf.total_invested),
        "current_value": _decimal_to_float(perf.current_value),
        "total_pnl": _decimal_to_float(perf.total_pnl),
        "total_pnl_percent": _decimal_to_float(perf.total_pnl_percent),
        "bot_profit": _decimal_to_float(perf.bot_profit),
        "bot_profit_percent": _decimal_to_float(perf.bot_profit_percent),
        "position_pnl": _decimal_to_float(perf.position_pnl),
        "position_pnl_percent": _decimal_to_float(perf.position_pnl_percent),
        "avg_daily_profit": _decimal_to_float(perf.avg_daily_profit),
        "avg_daily_profit_percent": _decimal_to_float(perf.avg_daily_profit_percent),
        "position_size": _decimal_to_float(perf.position_size),
        "avg_entry_price": _decimal_to_float(perf.avg_entry_price),
        "current_price": _decimal_to_float(perf.current_price),
        "dca_layers_used": perf.dca_layers_used,
        "pending_orders_count": perf.pending_orders_count,
        "pending_orders_value": _decimal_to_float(perf.pending_orders_value),
        "total_trades": perf.total_trades,
        "winning_trades": perf.winning_trades,
        "losing_trades": perf.losing_trades,
        "win_rate": _decimal_to_float(perf.win_rate),
        "trading_time_seconds": perf.trading_time_seconds
    }


def _cosmos_to_performance(data: Dict[str, Any]) -> BotPerformance:
    """Convert Cosmos storage format to domain BotPerformance."""
    if not data:
        return BotPerformance()
    
    return BotPerformance(
        total_invested=Decimal(str(data.get('total_invested', 0))),
        current_value=Decimal(str(data.get('current_value', 0))),
        total_pnl=Decimal(str(data.get('total_pnl', 0))),
        total_pnl_percent=Decimal(str(data.get('total_pnl_percent', 0))),
        bot_profit=Decimal(str(data.get('bot_profit', 0))),
        bot_profit_percent=Decimal(str(data.get('bot_profit_percent', 0))),
        position_pnl=Decimal(str(data.get('position_pnl', 0))),
        position_pnl_percent=Decimal(str(data.get('position_pnl_percent', 0))),
        avg_daily_profit=Decimal(str(data.get('avg_daily_profit', 0))),
        avg_daily_profit_percent=Decimal(str(data.get('avg_daily_profit_percent', 0))),
        position_size=Decimal(str(data.get('position_size', 0))),
        avg_entry_price=Decimal(str(data.get('avg_entry_price', 0))),
        current_price=Decimal(str(data.get('current_price', 0))),
        dca_layers_used=data.get('dca_layers_used', 0),
        pending_orders_count=data.get('pending_orders_count', 0),
        pending_orders_value=Decimal(str(data.get('pending_orders_value', 0))),
        total_trades=data.get('total_trades', 0),
        winning_trades=data.get('winning_trades', 0),
        losing_trades=data.get('losing_trades', 0),
        win_rate=Decimal(str(data.get('win_rate', 0))),
        trading_time_seconds=data.get('trading_time_seconds', 0)
    )


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO datetime string to datetime object."""
    if not value:
        return None
    try:
        # Handle both with and without timezone
        if value.endswith('Z'):
            value = value[:-1] + '+00:00'
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


@dataclass
class CosmosBotHistory:
    """
    Historical record of a closed/deleted bot for Cosmos DB storage.
    
    Preserves complete bot state and performance at time of closure.
    This is a persistence-layer model, storing snapshots of domain data.
    """
    # Identity
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""  # Partition key
    original_bot_id: str = ""
    name: str = ""
    
    # Configuration Snapshot
    symbol: str = ""
    exchange: str = ""
    bot_type: str = ""
    investment_amount: float = 0.0
    
    # Final State
    final_state: str = "stopped"
    close_reason: str = ""
    
    # Final Performance (snapshot as dict)
    final_performance: Dict[str, Any] = field(default_factory=dict)
    
    # Summary Stats
    total_invested: float = 0.0
    total_withdrawn: float = 0.0
    final_pnl: float = 0.0
    final_pnl_percent: float = 0.0
    total_fees_paid: float = 0.0
    
    # Lifecycle
    bot_created_at: str = ""
    bot_started_at: Optional[str] = None
    closed_at: str = ""
    duration_days: float = 0.0
    
    # Full Config Backup
    full_config_snapshot: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize timestamps."""
        if not self.closed_at:
            self.closed_at = datetime.now(timezone.utc).isoformat()
        if not self.id:
            self.id = str(uuid.uuid4())
    
    def to_cosmos_doc(self) -> Dict[str, Any]:
        """Convert to Cosmos DB document."""
        doc = asdict(self)
        doc['_type'] = 'bot_history'
        return doc
    
    @classmethod
    def from_cosmos_doc(cls, doc: Dict[str, Any]) -> "CosmosBotHistory":
        """Create from Cosmos DB document."""
        if not doc:
            return None
        
        for key in COSMOS_SYSTEM_PROPERTIES:
            doc.pop(key, None)
        doc.pop('_type', None)
        
        return cls(**{k: v for k, v in doc.items() if k in cls.__dataclass_fields__})
    
    @classmethod
    def from_bot(cls, bot: Bot, close_reason: str) -> "CosmosBotHistory":
        """Create history record from a domain Bot."""
        now = datetime.now(timezone.utc)
        duration = 0.0
        if bot.started_at and bot.stopped_at:
            duration = (bot.stopped_at - bot.started_at).days
        elif bot.started_at:
            duration = (now - bot.started_at).days
        
        return cls(
            user_id=bot.user_id,
            original_bot_id=bot.id,
            name=bot.name,
            symbol=bot.symbol,
            exchange=bot.exchange,
            bot_type=bot.bot_type.value,
            investment_amount=float(bot.configuration.investment_amount),
            final_state=bot.state.value,
            close_reason=close_reason,
            final_performance=_performance_to_cosmos(bot.performance),
            total_invested=float(bot.performance.total_invested),
            final_pnl=float(bot.performance.total_pnl),
            final_pnl_percent=float(bot.performance.total_pnl_percent),
            bot_created_at=bot.created_at.isoformat() if bot.created_at else "",
            bot_started_at=bot.started_at.isoformat() if bot.started_at else None,
            duration_days=duration,
            full_config_snapshot=bot_to_cosmos_doc(bot)
        )


# =============================================================================
# Cosmos DB Bot Repository
# =============================================================================

class CosmosBotRepository(CosmosBaseRepository, IBotRepository):
    """
    Cosmos DB repository for bot management.
    
    Implements IBotRepository interface using Azure Cosmos DB as the backend.
    Provides complete CRUD operations for bots, orders, and history
    with support for performance tracking, fee management, and analytics.
    
    Inherits from CosmosBaseRepository for shared connection pooling
    and utility methods. Uses the shared CosmosConnectionPool singleton
    to avoid duplicate connections.
    
    Architecture:
        - Implements IBotRepository for clean dependency injection
        - Uses shared CosmosConnectionPool (via CosmosBaseRepository)
        - Partition strategy optimized for multi-tenant scenarios
        - Automatic retry and error handling
    
    Usage:
        ```python
        repo: IBotRepository = CosmosBotRepository(
            cosmos_endpoint="https://myaccount.documents.azure.com:443/",
            database_name="trading-bot"
        )
        await repo.initialize()
        
        # Create a bot
        bot = Bot(
            user_id="user123",
            name="AAPL DCA Bot",
            symbol="AAPL",
            investment_amount=10000.0
        )
        await repo.create_bot(bot)
        
        # Add an order
        order = BotOrder(
            bot_id=bot.id,
            symbol="AAPL",
            side="buy",
            quantity=10,
            limit_price=150.00
        )
        await repo.create_order(order)
        ```
    """
    
    def __init__(
        self,
        cosmos_endpoint: str,
        database_name: str = "trading-bot",
        credential: Optional[DefaultAzureCredential] = None
    ):
        """
        Initialize the bot repository.
        
        Args:
            cosmos_endpoint: Cosmos DB account endpoint URL
            database_name: Name of the database to use
            credential: Optional Azure credential (defaults to DefaultAzureCredential)
        """
        super().__init__(cosmos_endpoint, database_name, credential)
        
        self._bots_container = None
        self._orders_container = None
        self._history_container = None
        # Lazy-loaded Azure exceptions module
        self._cosmos_exceptions = None
        
        logger.info(f"CosmosBotRepository created for {cosmos_endpoint}")
    
    async def initialize(self) -> None:
        """
        Initialize Cosmos DB connection and create containers if needed.
        
        Creates three containers:
        - bots: Active bot configurations (partition: /user_id)
        - bot_orders: All orders for bots (partition: /bot_id)
        - bot_history: Closed bot records (partition: /user_id)
        """
        if self._initialized:
            return
        
        try:
            # Lazy import Azure SDK exceptions
            from azure.cosmos import exceptions as cosmos_exceptions
            self._cosmos_exceptions = cosmos_exceptions
            
            # Initialize base connection (uses shared pool)
            await self._initialize_base()
            
            # Create containers with optimal partition keys
            self._bots_container = await self._create_container(
                "bots", "/user_id", offer_throughput=400
            )
            
            self._orders_container = await self._create_container(
                "bot_orders", "/bot_id", offer_throughput=400
            )
            
            self._history_container = await self._create_container(
                "bot_history", "/user_id", offer_throughput=400
            )
            
            self._initialized = True
            logger.info(f"CosmosBotRepository initialized - database: {self._database_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize CosmosBotRepository: {e}")
            raise
    
    async def close(self) -> None:
        """Close local resources (connection pool is managed separately)."""
        self._bots_container = None
        self._orders_container = None
        self._history_container = None
        self._initialized = False
        logger.info("CosmosBotRepository resources released")
    
    # =========================================================================
    # Bot CRUD Operations
    # =========================================================================
    
    async def create_bot(self, bot: Bot) -> Bot:
        """
        Create a new bot.
        
        Args:
            bot: Domain Bot instance to create
            
        Returns:
            Created bot with ID
            
        Raises:
            ValueError: If bot with same ID already exists
        """
        await self._ensure_initialized()
        
        try:
            doc = bot_to_cosmos_doc(bot)
            result = await self._bots_container.create_item(body=doc)
            logger.info(f"Bot created: {bot.id} - {bot.name} ({bot.symbol})")
            return cosmos_doc_to_bot(result)
        except self._cosmos_exceptions.CosmosResourceExistsError:
            raise ValueError(f"Bot with ID {bot.id} already exists")
        except Exception as e:
            logger.error(f"Failed to create bot: {e}")
            raise
    
    async def get_bot(self, bot_id: str, user_id: str) -> Optional[Bot]:
        """
        Get a bot by ID.
        
        Args:
            bot_id: Bot ID
            user_id: User ID (partition key)
            
        Returns:
            Domain Bot if found, None otherwise
        """
        await self._ensure_initialized()
        
        try:
            result = await self._bots_container.read_item(
                item=bot_id,
                partition_key=user_id
            )
            return cosmos_doc_to_bot(result)
        except self._cosmos_exceptions.CosmosResourceNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Failed to get bot {bot_id}: {e}")
            return None
    
    async def list_bots(
        self,
        user_id: str,
        state: Optional[BotState] = None,
        symbol: Optional[str] = None,
        is_active: Optional[bool] = None,
        limit: int = 100
    ) -> List[Bot]:
        """
        List bots for a user with optional filters.
        
        Args:
            user_id: User ID to filter by
            state: Optional state filter (domain BotState enum)
            symbol: Optional symbol filter
            is_active: Optional active status filter
            limit: Maximum number of bots to return
            
        Returns:
            List of domain Bot instances matching criteria
        """
        await self._ensure_initialized()
        
        try:
            # Build query
            conditions = ["c.user_id = @user_id"]
            parameters = [{"name": "@user_id", "value": user_id}]
            
            if state:
                conditions.append("c.state = @state")
                parameters.append({"name": "@state", "value": state.value})
            
            if symbol:
                conditions.append("c.symbol = @symbol")
                parameters.append({"name": "@symbol", "value": symbol})
            
            if is_active is not None:
                conditions.append("c.is_active = @is_active")
                parameters.append({"name": "@is_active", "value": is_active})
            
            query = f"SELECT * FROM c WHERE {' AND '.join(conditions)} ORDER BY c.created_at DESC"
            
            items = []
            async for item in self._bots_container.query_items(
                query=query,
                parameters=parameters,
                max_item_count=limit
            ):
                bot = cosmos_doc_to_bot(item)
                if bot:
                    items.append(bot)
            
            return items
            
        except Exception as e:
            logger.error(f"Failed to list bots: {e}")
            return []
    
    async def update_bot(self, bot: Bot) -> Bot:
        """
        Update an existing bot.
        
        Args:
            bot: Domain Bot with updated fields
            
        Returns:
            Updated domain Bot
        """
        await self._ensure_initialized()
        
        try:
            bot.updated_at = datetime.now(timezone.utc)
            doc = bot_to_cosmos_doc(bot)
            result = await self._bots_container.replace_item(
                item=bot.id,
                body=doc
            )
            logger.debug(f"Bot updated: {bot.id}")
            return cosmos_doc_to_bot(result)
        except Exception as e:
            logger.error(f"Failed to update bot {bot.id}: {e}")
            raise
    
    async def delete_bot(
        self,
        bot_id: str,
        user_id: str,
        close_reason: str = "user_deleted",
        archive: bool = True
    ) -> bool:
        """
        Delete a bot, optionally archiving to history.
        
        Args:
            bot_id: Bot ID to delete
            user_id: User ID (partition key)
            close_reason: Reason for closure
            archive: If True, move to history before deleting
            
        Returns:
            True if deleted successfully
        """
        await self._ensure_initialized()
        
        try:
            # Get bot first
            bot = await self.get_bot(bot_id, user_id)
            if not bot:
                logger.warning(f"Bot {bot_id} not found for deletion")
                return False
            
            # Archive to history if requested
            if archive:
                history = CosmosBotHistory.from_bot(bot, close_reason)
                await self.create_history(history)
                logger.info(f"Bot {bot_id} archived to history")
            
            # Delete the bot
            await self._bots_container.delete_item(
                item=bot_id,
                partition_key=user_id
            )
            
            logger.info(f"Bot deleted: {bot_id} (archived: {archive})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete bot {bot_id}: {e}")
            return False
    
    # =========================================================================
    # Bot State Management
    # =========================================================================
    
    async def update_bot_state(
        self,
        bot_id: str,
        user_id: str,
        state: BotState,
        operational_phase: Optional[BotOperationalPhase] = None
    ) -> Optional[Bot]:
        """
        Update bot state and optionally operational phase.
        
        Args:
            bot_id: Bot ID
            user_id: User ID
            state: New state (domain BotState enum)
            operational_phase: Optional new operational phase (domain enum)
            
        Returns:
            Updated domain Bot or None if not found
        """
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            return None
        
        bot.state = state
        
        if operational_phase:
            bot.operational_phase = operational_phase
        
        if state == BotState.RUNNING and not bot.started_at:
            bot.started_at = datetime.now(timezone.utc)
        
        return await self.update_bot(bot)
    
    async def update_bot_position(
        self,
        bot_id: str,
        user_id: str,
        position_size: Decimal,
        avg_price: Decimal,
        current_price: Decimal,
        cost_basis: Decimal
    ) -> Optional[Bot]:
        """
        Update bot position information.
        
        Args:
            bot_id: Bot ID
            user_id: User ID
            position_size: Current position size
            avg_price: Average entry price
            current_price: Current market price
            cost_basis: Total cost basis
            
        Returns:
            Updated domain Bot or None if not found
        """
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            return None
        
        # Update performance metrics with position data
        bot.performance.position_size = position_size
        bot.performance.avg_entry_price = avg_price
        bot.performance.current_price = current_price
        bot.performance.current_value = position_size * current_price
        
        # Calculate unrealized P&L
        if position_size != Decimal("0"):
            bot.performance.position_pnl = (current_price - avg_price) * position_size
            if cost_basis != Decimal("0"):
                bot.performance.position_pnl_percent = (bot.performance.position_pnl / cost_basis) * Decimal("100")
        
        return await self.update_bot(bot)
    
    async def update_bot_performance(
        self,
        bot_id: str,
        user_id: str,
        trade_pnl: Decimal,
        fees: Decimal,
        is_winner: bool
    ) -> Optional[Bot]:
        """
        Update bot performance after a completed trade.
        
        Args:
            bot_id: Bot ID
            user_id: User ID
            trade_pnl: P&L from the trade
            fees: Total fees paid
            is_winner: Whether trade was profitable
            
        Returns:
            Updated domain Bot or None if not found
        """
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            return None
        
        bot.performance.total_trades += 1
        bot.performance.bot_profit = bot.performance.bot_profit + trade_pnl
        
        if is_winner:
            bot.performance.winning_trades += 1
        else:
            bot.performance.losing_trades += 1
        
        # Recalculate win rate
        if bot.performance.total_trades > 0:
            bot.performance.win_rate = Decimal(str(bot.performance.winning_trades)) / Decimal(str(bot.performance.total_trades)) * Decimal("100")
        
        bot.last_activity_at = datetime.now(timezone.utc)
        
        return await self.update_bot(bot)
    
    # =========================================================================
    # Order Operations
    # =========================================================================
    
    async def create_order(self, order: CosmosBotOrder) -> CosmosBotOrder:
        """
        Create a new order for a bot.
        
        Args:
            order: CosmosBotOrder to create
            
        Returns:
            Created order
        """
        await self._ensure_initialized()
        
        try:
            doc = order.to_cosmos_doc()
            result = await self._orders_container.create_item(body=doc)
            logger.info(f"Order created: {order.id} for bot {order.bot_id}")
            return CosmosBotOrder.from_cosmos_doc(result)
        except Exception as e:
            logger.error(f"Failed to create order: {e}")
            raise
    
    async def get_order(self, order_id: str, bot_id: str) -> Optional[CosmosBotOrder]:
        """
        Get an order by ID.
        
        Args:
            order_id: Order ID
            bot_id: Bot ID (partition key)
            
        Returns:
            CosmosBotOrder if found, None otherwise
        """
        await self._ensure_initialized()
        
        try:
            result = await self._orders_container.read_item(
                item=order_id,
                partition_key=bot_id
            )
            return CosmosBotOrder.from_cosmos_doc(result)
        except self._cosmos_exceptions.CosmosResourceNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None
    
    async def list_orders(
        self,
        bot_id: str,
        status: Optional[OrderStatus] = None,
        side: Optional[OrderSide] = None,
        is_dca: Optional[bool] = None,
        limit: int = 100
    ) -> List[CosmosBotOrder]:
        """
        List orders for a bot with optional filters.
        
        Args:
            bot_id: Bot ID
            status: Optional status filter
            side: Optional side filter (buy/sell)
            is_dca: Optional DCA order filter
            limit: Maximum number of orders to return
            
        Returns:
            List of CosmosBotOrder instances matching criteria
        """
        await self._ensure_initialized()
        
        try:
            conditions = ["c.bot_id = @bot_id"]
            parameters = [{"name": "@bot_id", "value": bot_id}]
            
            if status:
                conditions.append("c.status = @status")
                parameters.append({"name": "@status", "value": status.value})
            
            if side:
                conditions.append("c.side = @side")
                parameters.append({"name": "@side", "value": side.value})
            
            if is_dca is not None:
                conditions.append("c.is_dca_order = @is_dca")
                parameters.append({"name": "@is_dca", "value": is_dca})
            
            query = f"SELECT * FROM c WHERE {' AND '.join(conditions)} ORDER BY c.created_at DESC"
            
            items = []
            async for item in self._orders_container.query_items(
                query=query,
                parameters=parameters,
                max_item_count=limit
            ):
                order = CosmosBotOrder.from_cosmos_doc(item)
                if order:
                    items.append(order)
            
            return items
            
        except Exception as e:
            logger.error(f"Failed to list orders for bot {bot_id}: {e}")
            return []
    
    async def get_open_orders(self, bot_id: str) -> List[CosmosBotOrder]:
        """
        Get all open (unfilled) orders for a bot.
        
        Args:
            bot_id: Bot ID
            
        Returns:
            List of open orders
        """
        open_statuses = [OrderStatus.PENDING, OrderStatus.SUBMITTED, OrderStatus.PARTIAL]
        
        all_open = []
        for status in open_statuses:
            orders = await self.list_orders(bot_id, status=status)
            all_open.extend(orders)
        
        return all_open
    
    async def update_order(self, order: CosmosBotOrder) -> CosmosBotOrder:
        """
        Update an existing order.
        
        Args:
            order: CosmosBotOrder with updated fields
            
        Returns:
            Updated order
        """
        await self._ensure_initialized()
        
        try:
            order.updated_at = datetime.now(timezone.utc).isoformat()
            doc = order.to_cosmos_doc()
            result = await self._orders_container.replace_item(
                item=order.id,
                body=doc
            )
            logger.debug(f"Order updated: {order.id}")
            return CosmosBotOrder.from_cosmos_doc(result)
        except Exception as e:
            logger.error(f"Failed to update order {order.id}: {e}")
            raise
    
    async def update_order_fill(
        self,
        order_id: str,
        bot_id: str,
        fill_quantity: float,
        fill_price: float,
        fees: FeeDetails,
        is_complete: bool = False
    ) -> Optional[CosmosBotOrder]:
        """
        Update order with fill information.
        
        Args:
            order_id: Order ID
            bot_id: Bot ID
            fill_quantity: Quantity filled in this fill
            fill_price: Price of fill
            fees: Fee details for this fill
            is_complete: Whether order is completely filled
            
        Returns:
            Updated order or None if not found
        """
        order = await self.get_order(order_id, bot_id)
        if not order:
            return None
        
        # Add fill record
        fill = OrderFill(
            fill_id=str(uuid.uuid4()),
            quantity=fill_quantity,
            price=fill_price,
            timestamp=datetime.now(timezone.utc).isoformat(),
            fees=fees
        )
        order.fills.append(fill.to_dict())
        
        # Update order totals
        order.filled_quantity += fill_quantity
        
        # Recalculate average fill price
        total_cost = sum(f.get('price', 0) * f.get('quantity', 0) for f in order.fills)
        if order.filled_quantity > 0:
            order.average_fill_price = total_cost / order.filled_quantity
        
        # Update fees
        order.fees.total += fees.total
        order.fees.commission += fees.commission
        order.fees.exchange_fee += fees.exchange_fee
        order.fees.slippage += fees.slippage
        
        # Calculate total cost / net amount
        if order.side == OrderSide.BUY.value:
            order.total_cost = (order.filled_quantity * order.average_fill_price) + order.fees.total
        else:
            order.net_amount = (order.filled_quantity * order.average_fill_price) - order.fees.total
        
        # Update status
        if is_complete or order.filled_quantity >= order.quantity:
            order.status = OrderStatus.FILLED.value
            order.filled_at = datetime.now(timezone.utc).isoformat()
        else:
            order.status = OrderStatus.PARTIAL.value
        
        return await self.update_order(order)
    
    # =========================================================================
    # History Operations
    # =========================================================================
    
    async def create_history(self, history: CosmosBotHistory) -> CosmosBotHistory:
        """
        Create a bot history record.
        
        Args:
            history: CosmosBotHistory record to create
            
        Returns:
            Created history record
        """
        await self._ensure_initialized()
        
        try:
            doc = history.to_cosmos_doc()
            result = await self._history_container.create_item(body=doc)
            logger.info(f"Bot history created: {history.id} (bot: {history.original_bot_id})")
            return CosmosBotHistory.from_cosmos_doc(result)
        except Exception as e:
            logger.error(f"Failed to create history: {e}")
            raise
    
    async def get_history(self, history_id: str, user_id: str) -> Optional[CosmosBotHistory]:
        """
        Get a history record by ID.
        
        Args:
            history_id: History record ID
            user_id: User ID (partition key)
            
        Returns:
            CosmosBotHistory record if found, None otherwise
        """
        await self._ensure_initialized()
        
        try:
            result = await self._history_container.read_item(
                item=history_id,
                partition_key=user_id
            )
            return CosmosBotHistory.from_cosmos_doc(result)
        except self._cosmos_exceptions.CosmosResourceNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Failed to get history {history_id}: {e}")
            return None
    
    async def list_history(
        self,
        user_id: str,
        symbol: Optional[str] = None,
        close_reason: Optional[str] = None,
        limit: int = 100
    ) -> List[CosmosBotHistory]:
        """
        List bot history for a user.
        
        Args:
            user_id: User ID
            symbol: Optional symbol filter
            close_reason: Optional close reason filter
            limit: Maximum records to return
            
        Returns:
            List of history records
        """
        await self._ensure_initialized()
        
        try:
            conditions = ["c.user_id = @user_id"]
            parameters = [{"name": "@user_id", "value": user_id}]
            
            if symbol:
                conditions.append("c.symbol = @symbol")
                parameters.append({"name": "@symbol", "value": symbol})
            
            if close_reason:
                conditions.append("c.close_reason = @reason")
                parameters.append({"name": "@reason", "value": close_reason})
            
            query = f"SELECT * FROM c WHERE {' AND '.join(conditions)} ORDER BY c.closed_at DESC"
            
            items = []
            async for item in self._history_container.query_items(
                query=query,
                parameters=parameters,
                max_item_count=limit
            ):
                history_item = CosmosBotHistory.from_cosmos_doc(item)
                if history_item:
                    items.append(history_item)
            
            return items
            
        except Exception as e:
            logger.error(f"Failed to list history: {e}")
            return []
    
    async def get_history_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get aggregate statistics from bot history.
        
        Args:
            user_id: User ID
            
        Returns:
            Dictionary of aggregate statistics
        """
        await self._ensure_initialized()
        
        try:
            history = await self.list_history(user_id, limit=1000)
            
            if not history:
                return {
                    "total_bots": 0,
                    "total_pnl": 0.0,
                    "total_fees": 0.0,
                    "average_pnl_percent": 0.0,
                    "winning_bots": 0,
                    "losing_bots": 0
                }
            
            total_pnl = sum(h.final_pnl for h in history)
            total_fees = sum(h.total_fees_paid for h in history)
            winning = len([h for h in history if h.final_pnl > 0])
            losing = len([h for h in history if h.final_pnl < 0])
            avg_pnl_pct = sum(h.final_pnl_percent for h in history) / len(history) if history else 0
            
            return {
                "total_bots": len(history),
                "total_pnl": total_pnl,
                "total_fees": total_fees,
                "average_pnl_percent": avg_pnl_pct,
                "winning_bots": winning,
                "losing_bots": losing,
                "win_rate": (winning / len(history) * 100) if history else 0
            }
            
        except Exception as e:
            logger.error(f"Failed to get history stats: {e}")
            return {}
    
    # =========================================================================
    # Analytics Queries
    # =========================================================================
    
    async def get_bot_pnl_summary(self, bot_id: str, user_id: str) -> Dict[str, Any]:
        """
        Get detailed P&L summary for a bot.
        
        Args:
            bot_id: Bot ID
            user_id: User ID
            
        Returns:
            Detailed P&L breakdown
        """
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            return {}
        
        orders = await self.list_orders(bot_id, status=OrderStatus.FILLED)
        
        buy_orders = [o for o in orders if o.side == OrderSide.BUY.value]
        sell_orders = [o for o in orders if o.side == OrderSide.SELL.value]
        
        total_bought = sum(o.filled_quantity * o.average_fill_price for o in buy_orders)
        total_sold = sum(o.filled_quantity * o.average_fill_price for o in sell_orders)
        total_fees = sum(o.fees.total for o in orders)
        
        # Use domain Bot properties and performance
        return {
            "bot_id": bot_id,
            "symbol": bot.symbol,
            "investment": float(bot.configuration.investment_amount),
            "current_position": float(bot.performance.position_size),
            "avg_entry_price": float(bot.performance.avg_entry_price),
            "current_price": float(bot.performance.current_price),
            "cost_basis": float(bot.performance.total_invested),
            "market_value": float(bot.performance.current_value),
            "unrealized_pnl": float(bot.performance.position_pnl),
            "unrealized_pnl_percent": float(bot.performance.position_pnl_percent),
            "realized_pnl": float(bot.performance.bot_profit),
            "total_pnl": float(bot.performance.total_pnl),
            "total_fees": total_fees,
            "total_bought": total_bought,
            "total_sold": total_sold,
            "total_trades": bot.performance.total_trades,
            "win_rate": float(bot.performance.win_rate),
            "buy_orders": len(buy_orders),
            "sell_orders": len(sell_orders),
            "dca_layers_used": bot.performance.dca_layers_used
        }
    
    async def get_fee_report(self, user_id: str) -> Dict[str, Any]:
        """
        Get fee report across all bots for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            Fee breakdown by bot and total
        """
        bots = await self.list_bots(user_id)
        
        report = {
            "user_id": user_id,
            "total_fees": 0.0,
            "total_commission": 0.0,
            "total_slippage": 0.0,
            "bots": []
        }
        
        for bot in bots:
            orders = await self.list_orders(bot.id, status=OrderStatus.FILLED)
            
            bot_fees = {
                "bot_id": bot.id,
                "symbol": bot.symbol,
                "total_fees": sum(o.fees.total for o in orders),
                "commission": sum(o.fees.commission for o in orders),
                "slippage": sum(o.fees.slippage for o in orders),
                "order_count": len(orders)
            }
            
            report["bots"].append(bot_fees)
            report["total_fees"] += bot_fees["total_fees"]
            report["total_commission"] += bot_fees["commission"]
            report["total_slippage"] += bot_fees["slippage"]
        
        return report
    
    # =========================================================================
    # Internal Helpers
    # =========================================================================
    
    async def _ensure_initialized(self) -> None:
        """Ensure repository is initialized."""
        if not self._initialized:
            await self.initialize()


# =============================================================================
# Exports
# =============================================================================
# Domain models are imported and re-exported for convenience
# Database-specific models are defined here

__all__ = [
    # Repository
    'CosmosBotRepository',
    # Domain models (re-exported from src.domain)
    'Bot',
    'BotPerformance',
    'BotState',
    'BotType',
    'BotOperationalPhase',
    'BotConfiguration',
    'DCAConfig',
    # Database-specific models
    'CosmosBotOrder',
    'CosmosBotHistory',
    'OrderSide',
    'OrderStatus',
    'FeeDetails',
    'OrderFill',
    # Mapper functions
    'bot_to_cosmos_doc',
    'cosmos_doc_to_bot',
]
