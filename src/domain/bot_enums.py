"""
Bot Domain Enums.

Defines all enumeration types used in bot domain models including:
- Bot types (DCA, COMBO, GRID, etc.)
- Bot lifecycle states
- Bot operational phases
- Configuration option enums

These enums provide type-safe, self-documenting values for
bot configuration and state management.

Author: Trading Bot Team
Version: 1.0.0
"""

from enum import Enum


class BotType(str, Enum):
    """Types of trading bots supported by the system."""
    
    DCA = "dca"                    # Dollar Cost Averaging
    COMBO = "combo"                # Combined long/short positions
    GRID = "grid"                  # Grid trading
    FUTURES_DCA = "futures_dca"    # Futures DCA
    FUTURES_COMBO = "futures_combo" # Futures COMBO
    SPOT_LOOP = "spot_loop"        # Spot Loop (sideways market)
    
    @property
    def display_name(self) -> str:
        """Get human-readable display name."""
        names = {
            "dca": "DCA Bot",
            "combo": "COMBO Bot",
            "grid": "GRID Bot",
            "futures_dca": "Futures DCA",
            "futures_combo": "Futures COMBO",
            "spot_loop": "Spot LOOP"
        }
        return names.get(self.value, self.value.upper())


class BotState(str, Enum):
    """Lifecycle states for a trading bot."""
    
    CREATED = "created"       # Bot configured but not started
    STARTING = "starting"     # Bot is initializing
    RUNNING = "running"       # Bot is actively trading
    PAUSED = "paused"         # Bot paused by user
    STOPPING = "stopping"     # Bot is shutting down
    STOPPED = "stopped"       # Bot stopped by user
    COMPLETED = "completed"   # Bot reached profit target
    ERROR = "error"           # Bot stopped due to error
    
    @property
    def is_active(self) -> bool:
        """Check if bot is in an active trading state."""
        return self in (BotState.RUNNING, BotState.STARTING)
    
    @property
    def can_start(self) -> bool:
        """Check if bot can be started."""
        return self in (BotState.CREATED, BotState.STOPPED, BotState.PAUSED, BotState.ERROR)
    
    @property
    def can_stop(self) -> bool:
        """Check if bot can be stopped."""
        return self in (BotState.RUNNING, BotState.PAUSED, BotState.STARTING)


class BotOperationalPhase(str, Enum):
    """
    Detailed operational phase within a running bot.
    
    Tracks what the bot is currently doing at a granular level,
    persisted to database for state recovery after restart.
    """
    
    # Signal-based phases (DCA, COMBO)
    WAITING_FOR_SIGNAL = "waiting_for_signal"     # Waiting for indicator signals to match
    SIGNAL_MATCHED = "signal_matched"             # Signal conditions met, ready to enter
    
    # Position phases
    ENTERING_POSITION = "entering_position"       # Placing base order
    IN_POSITION = "in_position"                   # Holding active position(s)
    AVERAGING_DOWN = "averaging_down"             # Placing safety/averaging orders
    TAKING_PROFIT = "taking_profit"               # Exit order placed, waiting for fill
    STOPPING_LOSS = "stopping_loss"               # Stop loss triggered, exiting
    CLOSING_POSITION = "closing_position"         # Manually closing position
    POSITION_CLOSED = "position_closed"           # All positions closed, cycle complete
    
    # Grid/Loop/Combo specific phases
    PRICE_IN_RANGE = "price_in_range"             # Price within configured grid/range
    PRICE_OUT_OF_RANGE = "price_out_of_range"     # Price outside grid range (waiting)
    REBALANCING = "rebalancing"                   # Adjusting grid levels or positions
    
    # Webhook/External signal phases
    WAITING_FOR_WEBHOOK = "waiting_for_webhook"   # Waiting for TradingView webhook
    WEBHOOK_RECEIVED = "webhook_received"         # Webhook signal received, processing
    
    # Cooldown phases
    IN_COOLDOWN = "in_cooldown"                   # Waiting for cooldown period
    COOLDOWN_EXPIRED = "cooldown_expired"         # Ready to process next signal
    
    # Idle state
    IDLE = "idle"                                 # Not actively trading (paused but running)
    
    @property
    def is_holding_position(self) -> bool:
        """Check if bot currently has open positions."""
        return self in (
            BotOperationalPhase.IN_POSITION,
            BotOperationalPhase.AVERAGING_DOWN,
            BotOperationalPhase.TAKING_PROFIT,
            BotOperationalPhase.STOPPING_LOSS,
            BotOperationalPhase.CLOSING_POSITION,
        )
    
    @property
    def is_waiting_for_entry(self) -> bool:
        """Check if bot is waiting to enter a position."""
        return self in (
            BotOperationalPhase.WAITING_FOR_SIGNAL,
            BotOperationalPhase.WAITING_FOR_WEBHOOK,
            BotOperationalPhase.PRICE_OUT_OF_RANGE,
            BotOperationalPhase.IN_COOLDOWN,
            BotOperationalPhase.POSITION_CLOSED,
        )


class BotAction(str, Enum):
    """Actions that can be performed on a bot."""
    
    START = "start"
    STOP = "stop"
    PAUSE = "pause"
    RESUME = "resume"
    MODIFY = "modify"
    MANUAL_AVERAGE = "manual_average"    # Manual position averaging
    ADJUST_MARGIN = "adjust_margin"      # Adjust margin (futures)
    CLOSE_POSITION = "close_position"    # Close all positions
    VIEW_DETAILS = "view_details"
    DELETE = "delete"


class PositionMode(str, Enum):
    """Position mode for the bot."""
    
    LONG = "long"
    SHORT = "short"
    BOTH = "both"   # For COMBO bots


class MarginMode(str, Enum):
    """Margin mode for futures bots."""
    
    ISOLATED = "isolated"
    CROSS = "cross"


class BotStartCondition(str, Enum):
    """When to place the base order."""
    IMMEDIATELY = "immediately"
    ON_SIGNAL = "on_signal"
    ON_PRICE = "on_price"
    TRADINGVIEW_WEBHOOK = "tradingview_webhook"


class BotOrderType(str, Enum):
    """Order type for bot operations."""
    LIMIT = "limit"
    MARKET = "market"


class TakeProfitType(str, Enum):
    """Take profit type."""
    REGULAR = "regular"
    TRAILING = "trailing"


class PriceReference(str, Enum):
    """
    Price reference for take profit calculation.
    
    - AVERAGE_PRICE: Take profit based on average entry price
    - AVERAGE_PRICE_INDICATORS: Average price + indicator signals (reverse of entry)
    - BASE_ORDER_PRICE: Take profit based on base order price
    - BASE_ORDER_PRICE_INDICATORS: Base order price + indicator signals (reverse of entry)
    """
    AVERAGE_PRICE = "average_price"
    AVERAGE_PRICE_INDICATORS = "average_price_indicators"
    BASE_ORDER_PRICE = "base_order_price"
    BASE_ORDER_PRICE_INDICATORS = "base_order_price_indicators"


class IndicatorType(str, Enum):
    """Technical indicator types for signal-based entry/exit."""
    RSI = "rsi"
    STOCHASTIC = "stochastic"
    MACD = "macd"


class IndicatorTimeframe(str, Enum):
    """Timeframe for indicator calculations."""
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    ONE_DAY = "1d"


class QuickSetupPreset(str, Enum):
    """Quick setup preset options."""
    SHORT_TERM = "short_term"
    MID_TERM = "mid_term"
    LONG_TERM = "long_term"
    CUSTOM = "custom"
