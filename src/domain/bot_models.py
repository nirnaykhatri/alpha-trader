"""
Bot Domain Models.

Defines the core domain models for bot management including:
- Bot configuration and state
- Bot types (DCA, COMBO, GRID, etc.)
- Bot lifecycle states
- Bot actions and history

These models represent the business domain and are independent of
persistence or presentation concerns.

Author: Trading Bot Team
Version: 1.0.0
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any
from uuid import uuid4


# =============================================================================
# Enums
# =============================================================================

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


# =============================================================================
# Configuration Models
# =============================================================================

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


@dataclass
class IndicatorConfig:
    """
    Single indicator configuration for entry/exit signals.
    
    Used to define which indicators are enabled and their timeframes
    for signal-based start conditions and take profit with indicators.
    """
    
    type: IndicatorType = IndicatorType.RSI
    timeframe: IndicatorTimeframe = IndicatorTimeframe.ONE_MINUTE
    enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "timeframe": self.timeframe.value,
            "enabled": self.enabled,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IndicatorConfig":
        return cls(
            type=IndicatorType(data.get("type", "rsi")),
            timeframe=IndicatorTimeframe(data.get("timeframe", "1m")),
            enabled=data.get("enabled", True),
        )


@dataclass
class SignalConfig:
    """
    Signal configuration for indicator-based entry/exit.
    
    Combines multiple indicators with a lookback period for
    signal generation on start conditions and take profit.
    """
    
    indicators: List["IndicatorConfig"] = field(default_factory=list)
    signal_lookback_days: int = 24
    
    def __post_init__(self):
        """Initialize default indicators if none provided."""
        if not self.indicators:
            self.indicators = [
                IndicatorConfig(type=IndicatorType.RSI, enabled=True),
                IndicatorConfig(type=IndicatorType.STOCHASTIC, enabled=False),
                IndicatorConfig(type=IndicatorType.MACD, enabled=False),
            ]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "indicators": [ind.to_dict() for ind in self.indicators],
            "signalLookbackDays": self.signal_lookback_days,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SignalConfig":
        indicators = [
            IndicatorConfig.from_dict(ind)
            for ind in data.get("indicators", [])
        ]
        return cls(
            indicators=indicators,
            signal_lookback_days=data.get("signalLookbackDays", 24),
        )


@dataclass
class TradingViewWebhookConfig:
    """
    TradingView webhook configuration for signal-based start.
    
    Allows bots to start trading based on TradingView alerts
    received via webhook.
    """
    
    enabled: bool = False
    webhook_secret: Optional[str] = None
    alert_message_pattern: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "webhookSecret": self.webhook_secret,
            "alertMessagePattern": self.alert_message_pattern,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TradingViewWebhookConfig":
        return cls(
            enabled=data.get("enabled", False),
            webhook_secret=data.get("webhookSecret"),
            alert_message_pattern=data.get("alertMessagePattern"),
        )


@dataclass
class PriceConditionConfig:
    """Price condition for on_price start condition."""
    
    operator: str = "above"  # above, below, crosses_above, crosses_below
    price: Decimal = Decimal("0")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "operator": self.operator,
            "price": str(self.price),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PriceConditionConfig":
        return cls(
            operator=data.get("operator", "above"),
            price=Decimal(str(data.get("price", "0"))),
        )


@dataclass
class BotStartSettings:
    """
    Bot start settings configuration.
    
    Enhanced to support multiple start conditions:
    - Immediately: Start trading right away
    - On Signal: Start when indicator signals align (RSI, Stochastic, MACD)
    - On Price: Start when price crosses a threshold
    - TradingView Webhook: Start when webhook signal is received
    """
    
    start_condition: BotStartCondition = BotStartCondition.IMMEDIATELY
    base_order_amount: Decimal = Decimal("100")
    base_order_type: BotOrderType = BotOrderType.LIMIT
    base_order_limit_price: Optional[Decimal] = None
    # Signal configuration (for ON_SIGNAL start condition)
    signal_config: Optional[SignalConfig] = None
    # TradingView webhook configuration (for TRADINGVIEW_WEBHOOK start condition)
    tradingview_config: Optional[TradingViewWebhookConfig] = None
    # Price condition (for ON_PRICE start condition)
    price_condition: Optional[PriceConditionConfig] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "startCondition": self.start_condition.value,
            "baseOrderAmount": str(self.base_order_amount),
            "baseOrderType": self.base_order_type.value,
            "baseOrderLimitPrice": str(self.base_order_limit_price) if self.base_order_limit_price else None,
            "signalConfig": self.signal_config.to_dict() if self.signal_config else None,
            "tradingViewConfig": self.tradingview_config.to_dict() if self.tradingview_config else None,
            "priceCondition": self.price_condition.to_dict() if self.price_condition else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BotStartSettings":
        return cls(
            start_condition=BotStartCondition(data.get("startCondition", "immediately")),
            base_order_amount=Decimal(str(data.get("baseOrderAmount", "100"))),
            base_order_type=BotOrderType(data.get("baseOrderType", "limit")),
            base_order_limit_price=Decimal(str(data["baseOrderLimitPrice"])) if data.get("baseOrderLimitPrice") else None,
            signal_config=SignalConfig.from_dict(data["signalConfig"]) if data.get("signalConfig") else None,
            tradingview_config=TradingViewWebhookConfig.from_dict(data["tradingViewConfig"]) if data.get("tradingViewConfig") else None,
            price_condition=PriceConditionConfig.from_dict(data["priceCondition"]) if data.get("priceCondition") else None,
        )


@dataclass
class AveragingOrdersConfig:
    """
    Averaging orders (safety orders) configuration.
    
    PERCENTAGE CONVENTION:
        All percentage fields use HUMAN-READABLE format.
        - User enters: 1.5 for 1.5%
        - Stored as: Decimal("1.5")
        - Business logic uses directly (already in % form)
    
    Attributes:
        step_percent: Price drop to trigger DCA (e.g., 1.5 = 1.5%)
        step_multiplier: Multiplier for progressive steps (e.g., 1.3 = 1.3x)
    """
    
    total_amount: Decimal = Decimal("400")
    orders_count: int = 4
    step_percent: Decimal = Decimal("1.99")  # 1.99 = 1.99%
    active_orders_limit: bool = False
    max_active_orders: int = 1
    amount_multiplier: Decimal = Decimal("1.3")
    amount_multiplier_enabled: bool = False
    step_multiplier: Decimal = Decimal("1.3")
    step_multiplier_enabled: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "totalAmount": str(self.total_amount),
            "ordersCount": self.orders_count,
            "stepPercent": str(self.step_percent),
            "activeOrdersLimit": self.active_orders_limit,
            "maxActiveOrders": self.max_active_orders,
            "amountMultiplier": str(self.amount_multiplier),
            "amountMultiplierEnabled": self.amount_multiplier_enabled,
            "stepMultiplier": str(self.step_multiplier),
            "stepMultiplierEnabled": self.step_multiplier_enabled,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AveragingOrdersConfig":
        return cls(
            total_amount=Decimal(str(data.get("totalAmount", "400"))),
            orders_count=data.get("ordersCount", 4),
            step_percent=Decimal(str(data.get("stepPercent", "1.99"))),
            active_orders_limit=data.get("activeOrdersLimit", False),
            max_active_orders=data.get("maxActiveOrders", 1),
            amount_multiplier=Decimal(str(data.get("amountMultiplier", "1.3"))),
            amount_multiplier_enabled=data.get("amountMultiplierEnabled", False),
            step_multiplier=Decimal(str(data.get("stepMultiplier", "1.3"))),
            step_multiplier_enabled=data.get("stepMultiplierEnabled", False),
        )


@dataclass
class TakeProfitConfig:
    """
    Take profit configuration with indicator support.
    
    PERCENTAGE CONVENTION:
        All percentage fields use HUMAN-READABLE format.
        - User enters: 2.0 for 2%
        - Stored as: Decimal("2.0")
        - Business logic divides by 100 when calculating
    
    Enhanced price reference options:
    - average_price: Standard take profit from average entry
    - average_price_indicators: Use indicator signals (reverse of entry)
    - base_order_price: Take profit from base order price
    - base_order_price_indicators: Base order + indicator signals
    
    Attributes:
        price_change_percent: Take profit target (e.g., 2.0 = 2%)
        trailing_deviation: Trailing stop deviation (e.g., 0.5 = 0.5%)
    """
    
    enabled: bool = True
    type: TakeProfitType = TakeProfitType.REGULAR
    price_change_percent: Decimal = Decimal("1.0")  # 1.0 = 1%
    price_reference: PriceReference = PriceReference.AVERAGE_PRICE
    order_type: BotOrderType = BotOrderType.LIMIT
    trailing_deviation: Optional[Decimal] = None  # e.g., 0.5 = 0.5%
    # Signal config for indicator-based take profit (reverse signals of entry)
    signal_config: Optional[SignalConfig] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "type": self.type.value,
            "priceChangePercent": str(self.price_change_percent),
            "priceReference": self.price_reference.value,
            "orderType": self.order_type.value,
            "trailingDeviation": str(self.trailing_deviation) if self.trailing_deviation else None,
            "signalConfig": self.signal_config.to_dict() if self.signal_config else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TakeProfitConfig":
        return cls(
            enabled=data.get("enabled", True),
            type=TakeProfitType(data.get("type", "regular")),
            price_change_percent=Decimal(str(data.get("priceChangePercent", "1.0"))),
            price_reference=PriceReference(data.get("priceReference", "average_price")),
            order_type=BotOrderType(data.get("orderType", "limit")),
            trailing_deviation=Decimal(str(data["trailingDeviation"])) if data.get("trailingDeviation") else None,
            signal_config=SignalConfig.from_dict(data["signalConfig"]) if data.get("signalConfig") else None,
        )


@dataclass
class StopLossConfig:
    """
    Stop loss configuration with trailing support.
    
    Enhanced with trailing stop loss that follows price movement:
    - trailing_enabled: Activate trailing stop functionality
    - trailing_deviation_percent: How far price must move to trail the stop
    """
    
    enabled: bool = False
    percent: Decimal = Decimal("10.0")
    order_type: BotOrderType = BotOrderType.MARKET
    # Trailing stop loss configuration
    trailing_enabled: bool = False
    trailing_deviation_percent: Optional[Decimal] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "percent": str(self.percent),
            "orderType": self.order_type.value,
            "trailingEnabled": self.trailing_enabled,
            "trailingDeviationPercent": str(self.trailing_deviation_percent) if self.trailing_deviation_percent else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StopLossConfig":
        return cls(
            enabled=data.get("enabled", False),
            percent=Decimal(str(data.get("percent", "10.0"))),
            order_type=BotOrderType(data.get("orderType", "market")),
            trailing_enabled=data.get("trailingEnabled", False),
            trailing_deviation_percent=Decimal(str(data["trailingDeviationPercent"])) if data.get("trailingDeviationPercent") else None,
        )


@dataclass
class RiskManagementConfig:
    """Risk management settings."""
    
    pump_dump_protection: bool = True
    target_total_profit_enabled: bool = False
    target_total_profit_amount: Optional[Decimal] = None
    target_total_profit_percent: Optional[Decimal] = None
    allowed_total_loss_enabled: bool = False
    allowed_total_loss_amount: Optional[Decimal] = None
    allowed_total_loss_percent: Optional[Decimal] = None
    max_price_enabled: bool = False
    max_price: Optional[Decimal] = None
    min_price_enabled: bool = False
    min_price: Optional[Decimal] = None
    renewal_profit_enabled: bool = False
    # New Bitsgap-style fields
    cooldown_period: int = 0  # Seconds between safety orders
    max_deals: int = 1  # Maximum concurrent deals for this bot
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pumpDumpProtection": self.pump_dump_protection,
            "targetTotalProfit": {
                "enabled": self.target_total_profit_enabled,
                "amount": str(self.target_total_profit_amount) if self.target_total_profit_amount else None,
                "percent": str(self.target_total_profit_percent) if self.target_total_profit_percent else None,
            },
            "allowedTotalLoss": {
                "enabled": self.allowed_total_loss_enabled,
                "amount": str(self.allowed_total_loss_amount) if self.allowed_total_loss_amount else None,
                "percent": str(self.allowed_total_loss_percent) if self.allowed_total_loss_percent else None,
            },
            "maxPrice": {
                "enabled": self.max_price_enabled,
                "price": str(self.max_price) if self.max_price else None,
            },
            "minPrice": {
                "enabled": self.min_price_enabled,
                "price": str(self.min_price) if self.min_price else None,
            },
            "renewalProfit": {
                "enabled": self.renewal_profit_enabled,
            },
            "cooldownPeriod": self.cooldown_period,
            "maxDeals": self.max_deals,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RiskManagementConfig":
        target_profit = data.get("targetTotalProfit", {})
        allowed_loss = data.get("allowedTotalLoss", {})
        max_price = data.get("maxPrice", {})
        min_price = data.get("minPrice", {})
        renewal = data.get("renewalProfit", {})
        
        return cls(
            pump_dump_protection=data.get("pumpDumpProtection", True),
            target_total_profit_enabled=target_profit.get("enabled", False),
            target_total_profit_amount=Decimal(str(target_profit["amount"])) if target_profit.get("amount") else None,
            target_total_profit_percent=Decimal(str(target_profit["percent"])) if target_profit.get("percent") else None,
            allowed_total_loss_enabled=allowed_loss.get("enabled", False),
            allowed_total_loss_amount=Decimal(str(allowed_loss["amount"])) if allowed_loss.get("amount") else None,
            allowed_total_loss_percent=Decimal(str(allowed_loss["percent"])) if allowed_loss.get("percent") else None,
            max_price_enabled=max_price.get("enabled", False),
            max_price=Decimal(str(max_price["price"])) if max_price.get("price") else None,
            min_price_enabled=min_price.get("enabled", False),
            min_price=Decimal(str(min_price["price"])) if min_price.get("price") else None,
            renewal_profit_enabled=renewal.get("enabled", False),
            cooldown_period=data.get("cooldownPeriod", 0),
            max_deals=data.get("maxDeals", 1),
        )


@dataclass
class DCAConfig:
    """
    Configuration for DCA (Dollar Cost Averaging) strategy.
    
    Clean configuration without legacy fields - all configuration is
    user-driven and stored in the database per-bot.
    
    Supports Bitsgap-style configuration with:
    - Bot start settings (base order with signal/webhook options)
    - Averaging orders configuration
    - Take profit settings (with indicator support)
    - Stop loss settings (with trailing support)
    - Risk management options
    """
    
    # Enhanced configuration (user-driven)
    quick_setup: QuickSetupPreset = QuickSetupPreset.MID_TERM
    start_settings: Optional[BotStartSettings] = None
    averaging_orders: Optional[AveragingOrdersConfig] = None
    take_profit: Optional[TakeProfitConfig] = None
    stop_loss: Optional[StopLossConfig] = None
    risk_management: Optional[RiskManagementConfig] = None
    
    def __post_init__(self):
        """Initialize nested configs if not provided."""
        if self.start_settings is None:
            self.start_settings = BotStartSettings()
        if self.averaging_orders is None:
            self.averaging_orders = AveragingOrdersConfig()
        if self.take_profit is None:
            self.take_profit = TakeProfitConfig()
        if self.stop_loss is None:
            self.stop_loss = StopLossConfig()
        if self.risk_management is None:
            self.risk_management = RiskManagementConfig()
    
    # =========================================================================
    # Backward-Compatible Properties (Legacy Field Mapping)
    # =========================================================================
    # These properties provide backward compatibility during migration.
    # They map legacy field names to the new nested configuration structure.
    # DEPRECATED: Use the nested configs directly (averaging_orders, take_profit, etc.)
    
    @property
    def max_layers(self) -> int:
        """
        DEPRECATED: Use averaging_orders.orders_count instead.
        Maps to averaging_orders.orders_count for backward compatibility.
        """
        return self.averaging_orders.orders_count if self.averaging_orders else 5
    
    @property
    def layer_multiplier(self) -> Decimal:
        """
        DEPRECATED: Use averaging_orders.amount_multiplier instead.
        Maps to averaging_orders.amount_multiplier for backward compatibility.
        """
        return self.averaging_orders.amount_multiplier if self.averaging_orders else Decimal("1.3")
    
    @property
    def price_deviation_percent(self) -> Decimal:
        """
        DEPRECATED: Use averaging_orders.step_percent instead.
        Maps to averaging_orders.step_percent for backward compatibility.
        """
        return self.averaging_orders.step_percent if self.averaging_orders else Decimal("1.99")
    
    @property
    def take_profit_percent(self) -> Decimal:
        """
        DEPRECATED: Use take_profit.price_change_percent instead.
        Maps to take_profit.price_change_percent for backward compatibility.
        """
        return self.take_profit.price_change_percent if self.take_profit else Decimal("1.5")
    
    @property
    def stop_loss_percent(self) -> Optional[Decimal]:
        """
        DEPRECATED: Use stop_loss.percent instead.
        Maps to stop_loss.percent for backward compatibility.
        Returns None if stop loss is disabled.
        """
        if self.stop_loss and self.stop_loss.enabled:
            return self.stop_loss.percent
        return None
    
    @property
    def use_martingale(self) -> bool:
        """
        DEPRECATED: Martingale is now controlled via averaging_orders.step_multiplier > 1.
        Returns True if step_multiplier > 1.0 (progressive spacing).
        """
        if self.averaging_orders and self.averaging_orders.step_multiplier:
            return self.averaging_orders.step_multiplier > Decimal("1.0")
        return False
    
    @property
    def martingale_multiplier(self) -> Decimal:
        """
        DEPRECATED: Use averaging_orders.step_multiplier instead.
        Maps to averaging_orders.step_multiplier for backward compatibility.
        """
        return self.averaging_orders.step_multiplier if self.averaging_orders else Decimal("1.0")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "quickSetup": self.quick_setup.value,
            "startSettings": self.start_settings.to_dict() if self.start_settings else None,
            "averagingOrders": self.averaging_orders.to_dict() if self.averaging_orders else None,
            "takeProfit": self.take_profit.to_dict() if self.take_profit else None,
            "stopLoss": self.stop_loss.to_dict() if self.stop_loss else None,
            "riskManagement": self.risk_management.to_dict() if self.risk_management else None,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DCAConfig":
        """Create from dictionary."""
        return cls(
            quick_setup=QuickSetupPreset(data.get("quickSetup", "mid_term")),
            start_settings=BotStartSettings.from_dict(data["startSettings"]) if data.get("startSettings") else None,
            averaging_orders=AveragingOrdersConfig.from_dict(data["averagingOrders"]) if data.get("averagingOrders") else None,
            take_profit=TakeProfitConfig.from_dict(data["takeProfit"]) if data.get("takeProfit") else None,
            stop_loss=StopLossConfig.from_dict(data["stopLoss"]) if data.get("stopLoss") else None,
            risk_management=RiskManagementConfig.from_dict(data["riskManagement"]) if data.get("riskManagement") else None,
        )


@dataclass
class BotConfiguration:
    """
    Complete bot configuration.
    
    Contains all settings needed to run a trading bot including:
    - Asset and exchange selection
    - Position mode and sizing
    - Strategy-specific settings (DCA config)
    - Risk management parameters
    
    Note: leverage and margin_mode are only applicable for futures bots
    (FUTURES_DCA, FUTURES_COMBO). For spot bots, leverage defaults to 1.
    """
    
    # Asset Configuration
    symbol: str                           # Trading pair (e.g., "BTC/USD", "AAPL")
    exchange: str                         # Exchange/broker (e.g., "alpaca", "coinbase")
    asset_class: str = "stock"            # stock, crypto, forex, etc.
    
    # Position Configuration
    position_mode: PositionMode = PositionMode.LONG
    investment_amount: Decimal = Decimal("1000")
    # Leverage (only for futures_dca, futures_combo - defaults to 1 for spot)
    leverage: int = 1
    # Margin mode (only for futures_dca, futures_combo)
    margin_mode: MarginMode = MarginMode.ISOLATED
    
    # Strategy Configuration
    bot_type: BotType = BotType.DCA
    dca_config: DCAConfig = field(default_factory=DCAConfig)
    
    # Risk Management
    max_drawdown_percent: Optional[Decimal] = Decimal("20.0")
    daily_loss_limit: Optional[Decimal] = None
    
    # Execution Settings
    use_limit_orders: bool = True
    limit_order_offset_percent: Decimal = Decimal("0.1")
    
    @property
    def is_futures_bot(self) -> bool:
        """Check if this is a futures bot (requires leverage/margin settings)."""
        return self.bot_type in (BotType.FUTURES_DCA, BotType.FUTURES_COMBO)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "symbol": self.symbol,
            "exchange": self.exchange,
            "asset_class": self.asset_class,
            "position_mode": self.position_mode.value,
            "investment_amount": str(self.investment_amount),
            "leverage": self.leverage,
            "margin_mode": self.margin_mode.value,
            "bot_type": self.bot_type.value,
            "dca_config": self.dca_config.to_dict(),
            "max_drawdown_percent": str(self.max_drawdown_percent) if self.max_drawdown_percent else None,
            "daily_loss_limit": str(self.daily_loss_limit) if self.daily_loss_limit else None,
            "use_limit_orders": self.use_limit_orders,
            "limit_order_offset_percent": str(self.limit_order_offset_percent)
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BotConfiguration":
        """Create from dictionary."""
        return cls(
            symbol=data["symbol"],
            exchange=data["exchange"],
            asset_class=data.get("asset_class", "stock"),
            position_mode=PositionMode(data.get("position_mode", "long")),
            investment_amount=Decimal(str(data.get("investment_amount", "1000"))),
            leverage=data.get("leverage", 1),
            margin_mode=MarginMode(data.get("margin_mode", "isolated")),
            bot_type=BotType(data.get("bot_type", "dca")),
            dca_config=DCAConfig.from_dict(data.get("dca_config", {})),
            max_drawdown_percent=Decimal(str(data["max_drawdown_percent"])) if data.get("max_drawdown_percent") else None,
            daily_loss_limit=Decimal(str(data["daily_loss_limit"])) if data.get("daily_loss_limit") else None,
            use_limit_orders=data.get("use_limit_orders", True),
            limit_order_offset_percent=Decimal(str(data.get("limit_order_offset_percent", "0.1")))
        )


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
