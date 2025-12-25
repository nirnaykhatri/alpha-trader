"""
Bot Configuration Models.

Defines configuration dataclasses for bot settings including:
- Signal and indicator configuration
- Start settings and conditions
- Averaging orders (safety orders)
- Take profit and stop loss settings
- Risk management configuration
- DCA strategy configuration
- Complete bot configuration

These models are independent of persistence and can be serialized
to/from dictionaries for API transport and database storage.

Author: Trading Bot Team
Version: 1.0.0
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional, List, Dict, Any

from .bot_enums import (
    BotType,
    PositionMode,
    MarginMode,
    BotStartCondition,
    BotOrderType,
    TakeProfitType,
    PriceReference,
    IndicatorType,
    IndicatorTimeframe,
    QuickSetupPreset,
)


# =============================================================================
# Signal Configuration Models
# =============================================================================

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


# =============================================================================
# Bot Start Settings
# =============================================================================

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


# =============================================================================
# Averaging Orders Configuration
# =============================================================================

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


# =============================================================================
# Take Profit and Stop Loss Configuration
# =============================================================================

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


# =============================================================================
# Risk Management Configuration
# =============================================================================

@dataclass
class RiskManagementConfig:
    """
    Risk management settings.
    
    Includes reinvest profit feature that allocates realized profit
    proportionally to base order and DCA (safety) orders based on
    their share of total investment.
    """
    
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
    # Reinvest profit settings (replaces renewal_profit)
    reinvest_profit_enabled: bool = False
    reinvest_profit_percent: Decimal = Decimal("100")  # 0-100% of profit to reinvest
    # Legacy alias for backward compatibility
    renewal_profit_enabled: bool = False  # DEPRECATED: Use reinvest_profit_enabled
    # New Bitsgap-style fields
    cooldown_period: int = 0  # Seconds between safety orders
    max_deals: int = 1  # Maximum concurrent deals for this bot
    
    def __post_init__(self):
        """Sync legacy field with new field for backward compatibility."""
        # If renewal_profit was set but reinvest wasn't, sync them
        if self.renewal_profit_enabled and not self.reinvest_profit_enabled:
            self.reinvest_profit_enabled = self.renewal_profit_enabled
        # Keep them in sync
        self.renewal_profit_enabled = self.reinvest_profit_enabled
    
    def calculate_reinvest_allocation(
        self,
        realized_profit: Decimal,
        base_order_amount: Decimal,
        dca_total_amount: Decimal,
    ) -> tuple[Decimal, Decimal]:
        """
        Calculate how to allocate reinvested profit between base order and DCA orders.
        
        The allocation is proportional to the original investment split:
        - If base order is 20% and DCA is 80% of total, profit is split 20/80.
        
        Args:
            realized_profit: Total realized profit from the completed deal
            base_order_amount: Original base order amount
            dca_total_amount: Total amount allocated to DCA (safety) orders
            
        Returns:
            Tuple of (base_order_addition, dca_orders_addition)
            
        Example:
            If total investment is $1000 (base=$200, DCA=$800) and profit is $100
            with 50% reinvest:
            - Reinvest amount = $100 * 50% = $50
            - Base order gets: $50 * ($200/$1000) = $10
            - DCA orders get: $50 * ($800/$1000) = $40
        """
        if not self.reinvest_profit_enabled:
            return Decimal("0"), Decimal("0")
        
        # Calculate reinvest amount based on percentage
        reinvest_amount = realized_profit * (self.reinvest_profit_percent / Decimal("100"))
        
        # Calculate total investment
        total_investment = base_order_amount + dca_total_amount
        if total_investment <= 0:
            return Decimal("0"), Decimal("0")
        
        # Calculate proportional allocation
        base_ratio = base_order_amount / total_investment
        dca_ratio = dca_total_amount / total_investment
        
        base_addition = (reinvest_amount * base_ratio).quantize(Decimal("0.01"))
        dca_addition = (reinvest_amount * dca_ratio).quantize(Decimal("0.01"))
        
        return base_addition, dca_addition
    
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
            "reinvestProfit": {
                "enabled": self.reinvest_profit_enabled,
                "percent": str(self.reinvest_profit_percent),
            },
            # Legacy key for backward compatibility with older frontends
            "renewalProfit": {
                "enabled": self.reinvest_profit_enabled,
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
        # Support both new reinvestProfit and legacy renewalProfit
        reinvest = data.get("reinvestProfit", {})
        renewal = data.get("renewalProfit", {})
        
        # Prefer reinvestProfit if present, fall back to renewalProfit for legacy data
        reinvest_enabled = reinvest.get("enabled", renewal.get("enabled", False))
        reinvest_percent = Decimal(str(reinvest.get("percent", "100"))) if reinvest.get("percent") else Decimal("100")
        
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
            reinvest_profit_enabled=reinvest_enabled,
            reinvest_profit_percent=reinvest_percent,
            renewal_profit_enabled=reinvest_enabled,  # Keep legacy field in sync
            cooldown_period=data.get("cooldownPeriod", 0),
            max_deals=data.get("maxDeals", 1),
        )


# =============================================================================
# DCA Strategy Configuration
# =============================================================================

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


# =============================================================================
# Complete Bot Configuration
# =============================================================================

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
