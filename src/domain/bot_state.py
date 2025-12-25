"""
Bot State and Entity Models.

Defines the runtime state models for bots including:
- Bot entity (main bot model with state and performance)
- BotPerformance (real-time metrics)
- BotOrder (order tracking)
- BotHistoryEntry (historical records)

These models represent the current state of running bots
and their performance metrics.

Author: Trading Bot Team
Version: 1.0.0
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from uuid import uuid4

from .bot_enums import BotType, BotState, BotOperationalPhase, BotAction
from .bot_config import BotConfiguration


# =============================================================================
# Bot Performance Models
# =============================================================================

@dataclass
class BotPerformance:
    """Real-time performance metrics for a bot."""
    
    # Investment
    total_invested: Decimal = Decimal("0")
    current_value: Decimal = Decimal("0")
    
    # Profit/Loss
    total_pnl: Decimal = Decimal("0")
    total_pnl_percent: Decimal = Decimal("0")
    bot_profit: Decimal = Decimal("0")          # Realized profit from closed deals
    bot_profit_percent: Decimal = Decimal("0")
    position_pnl: Decimal = Decimal("0")        # Unrealized P&L from open position
    position_pnl_percent: Decimal = Decimal("0")
    
    # Daily Stats
    avg_daily_profit: Decimal = Decimal("0")
    avg_daily_profit_percent: Decimal = Decimal("0")
    
    # Position Info
    position_size: Decimal = Decimal("0")
    avg_entry_price: Decimal = Decimal("0")
    current_price: Decimal = Decimal("0")
    dca_layers_used: int = 0
    
    # Orders
    pending_orders_count: int = 0
    pending_orders_value: Decimal = Decimal("0")
    
    # Trading Stats
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: Decimal = Decimal("0")
    
    # Time
    trading_time_seconds: int = 0
    
    @staticmethod
    def empty() -> "BotPerformance":
        """
        Create an empty BotPerformance with zeroed metrics.
        
        Use this when initializing a new bot or when performance
        data is not yet available.
        
        Returns:
            BotPerformance with all metrics set to zero/default.
        """
        return BotPerformance()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "totalInvested": str(self.total_invested),
            "currentValue": str(self.current_value),
            "totalPnL": str(self.total_pnl),
            "totalPnLPercent": str(self.total_pnl_percent),
            "botProfit": str(self.bot_profit),
            "botProfitPercent": str(self.bot_profit_percent),
            "positionPnL": str(self.position_pnl),
            "positionPnLPercent": str(self.position_pnl_percent),
            "avgDailyProfit": str(self.avg_daily_profit),
            "avgDailyProfitPercent": str(self.avg_daily_profit_percent),
            "positionSize": str(self.position_size),
            "avgEntryPrice": str(self.avg_entry_price),
            "currentPrice": str(self.current_price),
            "dcaLayersUsed": self.dca_layers_used,
            "pendingOrdersCount": self.pending_orders_count,
            "pendingOrdersValue": str(self.pending_orders_value),
            "totalTrades": self.total_trades,
            "winningTrades": self.winning_trades,
            "losingTrades": self.losing_trades,
            "winRate": str(self.win_rate),
            "tradingTimeSeconds": self.trading_time_seconds
        }


@dataclass
class BotOrder:
    """Represents an order placed by a bot."""
    
    id: str
    bot_id: str
    order_type: str                       # market, limit
    side: str                             # buy, sell
    quantity: Decimal
    price: Optional[Decimal]              # Limit price
    filled_quantity: Decimal = Decimal("0")
    filled_price: Optional[Decimal] = None
    status: str = "pending"               # pending, filled, cancelled, failed
    created_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "botId": self.bot_id,
            "orderType": self.order_type,
            "side": self.side,
            "quantity": str(self.quantity),
            "price": str(self.price) if self.price else None,
            "filledQuantity": str(self.filled_quantity),
            "filledPrice": str(self.filled_price) if self.filled_price else None,
            "status": self.status,
            "createdAt": self.created_at.isoformat(),
            "filledAt": self.filled_at.isoformat() if self.filled_at else None
        }


# =============================================================================
# Main Bot Model
# =============================================================================

@dataclass
class Bot:
    """
    Main bot entity representing a configured trading bot instance.
    
    Contains:
    - Unique identifier and user assignment
    - Configuration settings
    - Current state and performance
    - Operational phase tracking (detailed state)
    - Lifecycle timestamps
    
    Thread Safety:
        Bot instances are not thread-safe. Use appropriate locking
        when accessing from multiple threads.
    
    Example:
        >>> config = BotConfiguration(symbol="AAPL", exchange="alpaca")
        >>> bot = Bot(
        ...     user_id="user-123",
        ...     name="My DCA Bot",
        ...     configuration=config
        ... )
        >>> bot.start()
    """
    
    # Identity
    id: str = field(default_factory=lambda: str(uuid4()))
    user_id: str = ""
    name: str = ""
    description: str = ""
    
    # Configuration
    configuration: BotConfiguration = field(default_factory=BotConfiguration)
    
    # State (lifecycle)
    state: BotState = BotState.CREATED
    error_message: Optional[str] = None
    
    # Operational Phase (detailed state within running bot)
    operational_phase: BotOperationalPhase = BotOperationalPhase.IDLE
    last_signal_match_at: Optional[datetime] = None  # When indicator conditions matched
    signal_indicators_status: Optional[Dict[str, Any]] = None  # Current indicator values
    
    # Price Range Tracking (for Grid/Loop/Combo bots)
    price_range_status: Optional[str] = None  # in_range, above_range, below_range
    grid_lower_bound: Optional[Decimal] = None  # Grid lower price boundary
    grid_upper_bound: Optional[Decimal] = None  # Grid upper price boundary
    
    # Cooldown Tracking
    cooldown_until: Optional[datetime] = None  # When cooldown expires
    last_order_at: Optional[datetime] = None  # Last order placement time
    
    # Deal/Cycle Tracking
    current_deal_id: Optional[str] = None  # Current active deal/cycle ID
    completed_deals: int = 0  # Total completed cycles
    
    # Performance (populated at runtime)
    performance: BotPerformance = field(default_factory=BotPerformance)
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    # Tags for organization
    tags: List[str] = field(default_factory=list)
    
    @property
    def symbol(self) -> str:
        """Get trading symbol from configuration."""
        return self.configuration.symbol
    
    @property
    def exchange(self) -> str:
        """Get exchange from configuration."""
        return self.configuration.exchange
    
    @property
    def bot_type(self) -> BotType:
        """Get bot type from configuration."""
        return self.configuration.bot_type
    
    @property
    def is_active(self) -> bool:
        """Check if bot is actively trading."""
        return self.state.is_active
    
    @property
    def trading_time_display(self) -> str:
        """Get human-readable trading time."""
        if not self.started_at:
            return "Not started"
        
        end_time = self.stopped_at or datetime.utcnow()
        delta = end_time - self.started_at
        
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"
    
    def can_perform_action(self, action: BotAction) -> bool:
        """Check if an action can be performed on this bot."""
        action_state_requirements = {
            BotAction.START: self.state.can_start,
            BotAction.STOP: self.state.can_stop,
            BotAction.PAUSE: self.state == BotState.RUNNING,
            BotAction.RESUME: self.state == BotState.PAUSED,
            BotAction.MODIFY: self.state in (BotState.CREATED, BotState.PAUSED, BotState.STOPPED),
            BotAction.MANUAL_AVERAGE: self.state == BotState.RUNNING,
            BotAction.ADJUST_MARGIN: self.state == BotState.RUNNING and self.configuration.leverage > 1,
            BotAction.CLOSE_POSITION: self.state == BotState.RUNNING,
            BotAction.VIEW_DETAILS: True,
            BotAction.DELETE: self.state in (BotState.CREATED, BotState.STOPPED, BotState.COMPLETED, BotState.ERROR),
        }
        return action_state_requirements.get(action, False)
    
    def get_available_actions(self) -> List[BotAction]:
        """Get list of actions available for current state."""
        return [action for action in BotAction if self.can_perform_action(action)]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "userId": self.user_id,
            "name": self.name,
            "description": self.description,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "botType": self.bot_type.value,
            "botTypeDisplay": self.bot_type.display_name,
            "state": self.state.value,
            "isActive": self.is_active,
            "errorMessage": self.error_message,
            "configuration": self.configuration.to_dict(),
            "performance": self.performance.to_dict(),
            "createdAt": self.created_at.isoformat(),
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "stoppedAt": self.stopped_at.isoformat() if self.stopped_at else None,
            "lastActivityAt": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "tradingTimeDisplay": self.trading_time_display,
            "tags": self.tags,
            "availableActions": [a.value for a in self.get_available_actions()],
            # Operational Phase Tracking
            "operationalPhase": self.operational_phase.value,
            "lastSignalMatchAt": self.last_signal_match_at.isoformat() if self.last_signal_match_at else None,
            "signalIndicatorsStatus": self.signal_indicators_status,
            # Price Range Tracking (Grid/Loop/Combo bots)
            "priceRangeStatus": self.price_range_status,
            "gridLowerBound": str(self.grid_lower_bound) if self.grid_lower_bound else None,
            "gridUpperBound": str(self.grid_upper_bound) if self.grid_upper_bound else None,
            # Cooldown Tracking
            "cooldownUntil": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "lastOrderAt": self.last_order_at.isoformat() if self.last_order_at else None,
            # Deal/Cycle Tracking
            "currentDealId": self.current_deal_id,
            "completedDeals": self.completed_deals,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Bot":
        """Create Bot from dictionary."""
        bot = cls(
            id=data.get("id", str(uuid4())),
            user_id=data.get("userId", data.get("user_id", "")),
            name=data.get("name", ""),
            description=data.get("description", ""),
            configuration=BotConfiguration.from_dict(data.get("configuration", {})),
            state=BotState(data.get("state", "created")),
            error_message=data.get("errorMessage"),
            tags=data.get("tags", [])
        )
        
        # Parse timestamps
        if data.get("createdAt"):
            bot.created_at = datetime.fromisoformat(data["createdAt"].replace("Z", "+00:00"))
        if data.get("startedAt"):
            bot.started_at = datetime.fromisoformat(data["startedAt"].replace("Z", "+00:00"))
        if data.get("stoppedAt"):
            bot.stopped_at = datetime.fromisoformat(data["stoppedAt"].replace("Z", "+00:00"))
        
        # Parse operational phase
        if data.get("operationalPhase"):
            bot.operational_phase = BotOperationalPhase(data["operationalPhase"])
        if data.get("lastSignalMatchAt"):
            bot.last_signal_match_at = datetime.fromisoformat(data["lastSignalMatchAt"].replace("Z", "+00:00"))
        bot.signal_indicators_status = data.get("signalIndicatorsStatus")
        
        # Parse price range tracking (Grid/Loop/Combo bots)
        bot.price_range_status = data.get("priceRangeStatus")
        if data.get("gridLowerBound"):
            bot.grid_lower_bound = Decimal(data["gridLowerBound"])
        if data.get("gridUpperBound"):
            bot.grid_upper_bound = Decimal(data["gridUpperBound"])
        
        # Parse cooldown tracking
        if data.get("cooldownUntil"):
            bot.cooldown_until = datetime.fromisoformat(data["cooldownUntil"].replace("Z", "+00:00"))
        if data.get("lastOrderAt"):
            bot.last_order_at = datetime.fromisoformat(data["lastOrderAt"].replace("Z", "+00:00"))
        
        # Parse deal/cycle tracking
        bot.current_deal_id = data.get("currentDealId")
        bot.completed_deals = data.get("completedDeals", 0)
        
        return bot


# =============================================================================
# Bot History Models
# =============================================================================

@dataclass
class BotHistoryEntry:
    """
    Historical record of a bot's operation.
    
    Created when a bot is stopped or completed, preserving
    its configuration and final performance metrics.
    """
    
    id: str = field(default_factory=lambda: str(uuid4()))
    bot_id: str = ""
    user_id: str = ""
    name: str = ""
    
    # Configuration snapshot
    symbol: str = ""
    exchange: str = ""
    bot_type: str = ""
    configuration_snapshot: Dict[str, Any] = field(default_factory=dict)
    
    # Final state
    final_state: str = "stopped"
    error_message: Optional[str] = None
    
    # Performance summary
    total_invested: Decimal = Decimal("0")
    total_profit: Decimal = Decimal("0")
    total_profit_percent: Decimal = Decimal("0")
    total_trades: int = 0
    win_rate: Decimal = Decimal("0")
    
    # Time range
    started_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    trading_duration_seconds: int = 0
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    deleted_at: Optional[datetime] = None  # Soft delete
    
    @property
    def is_deleted(self) -> bool:
        """Check if history entry has been deleted."""
        return self.deleted_at is not None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "botId": self.bot_id,
            "userId": self.user_id,
            "name": self.name,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "botType": self.bot_type,
            "configurationSnapshot": self.configuration_snapshot,
            "finalState": self.final_state,
            "errorMessage": self.error_message,
            "totalInvested": str(self.total_invested),
            "totalProfit": str(self.total_profit),
            "totalProfitPercent": str(self.total_profit_percent),
            "totalTrades": self.total_trades,
            "winRate": str(self.win_rate),
            "startedAt": self.started_at.isoformat() if self.started_at else None,
            "stoppedAt": self.stopped_at.isoformat() if self.stopped_at else None,
            "tradingDurationSeconds": self.trading_duration_seconds,
            "createdAt": self.created_at.isoformat(),
            "isDeleted": self.is_deleted
        }
    
    @classmethod
    def from_bot(cls, bot: Bot) -> "BotHistoryEntry":
        """Create history entry from a stopped bot."""
        duration = 0
        if bot.started_at and bot.stopped_at:
            duration = int((bot.stopped_at - bot.started_at).total_seconds())
        
        return cls(
            bot_id=bot.id,
            user_id=bot.user_id,
            name=bot.name,
            symbol=bot.symbol,
            exchange=bot.exchange,
            bot_type=bot.bot_type.value,
            configuration_snapshot=bot.configuration.to_dict(),
            final_state=bot.state.value,
            error_message=bot.error_message,
            total_invested=bot.performance.total_invested,
            total_profit=bot.performance.bot_profit,
            total_profit_percent=bot.performance.bot_profit_percent,
            total_trades=bot.performance.total_trades,
            win_rate=bot.performance.win_rate,
            started_at=bot.started_at,
            stopped_at=bot.stopped_at,
            trading_duration_seconds=duration
        )
