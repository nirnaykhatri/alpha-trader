"""
Bot Management Router.

Handles bot CRUD operations:
- Create bot
- Get bot details
- Update bot
- Delete bot
- Bot actions (start, stop, manual average)
- Bot orders and performance

Author: Trading Bot Team
Version: 2.0.0
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, validator
from fastapi import Request, HTTPException, Header
from fastapi.responses import JSONResponse

from src.core.logging_config import get_logger
from src.constants import HTTPStatus
from src.signals.routers.base_router import BaseAdminRouter, handle_route_errors

# Bot service import - may not exist in older installations
try:
    from src.services.bot_service_interface import IBotService
except ImportError:
    IBotService = None  # type: ignore

# Bot models import
try:
    from src.domain.bot_models import (
        Bot, BotConfiguration, BotState, BotType,
        DCAConfig, PositionMode, MarginMode,
        BotStartCondition, BotOrderType, TakeProfitType, PriceReference,
        QuickSetupPreset, BotStartSettings, AveragingOrdersConfig,
        TakeProfitConfig, StopLossConfig, RiskManagementConfig,
        SignalConfig, IndicatorConfig, IndicatorType, IndicatorTimeframe,
        TradingViewWebhookConfig, PriceConditionConfig
    )
except ImportError:
    Bot = None  # type: ignore


logger = get_logger(__name__)


# =============================================================================
# Bot Management Request/Response Models
# =============================================================================

class IndicatorConfigRequest(BaseModel):
    """Single indicator configuration for entry/exit signals."""
    type: str = Field(default="rsi", description="Indicator type")
    timeframe: str = Field(default="1m", description="Timeframe")
    enabled: bool = Field(default=True, description="Whether enabled")


class SignalConfigRequest(BaseModel):
    """Signal configuration for indicator-based entry/exit."""
    indicators: List[IndicatorConfigRequest] = Field(default_factory=list)
    signal_lookback_days: int = Field(default=24, ge=1)


class TradingViewWebhookConfigRequest(BaseModel):
    """TradingView webhook configuration."""
    enabled: bool = Field(default=False)
    webhook_secret: Optional[str] = None
    alert_message_pattern: Optional[str] = None


class PriceConditionRequest(BaseModel):
    """Price condition for on_price start condition."""
    operator: str = Field(default="above")
    price: float = Field(default=0, ge=0)


class BotStartSettingsRequest(BaseModel):
    """Bot start settings configuration."""
    start_condition: str = Field(default="immediately")
    base_order_amount: float = Field(default=100, gt=0)
    base_order_type: str = Field(default="limit")
    base_order_limit_price: Optional[float] = Field(None, gt=0)
    signal_config: Optional[SignalConfigRequest] = None
    tradingview_config: Optional[TradingViewWebhookConfigRequest] = None
    price_condition: Optional[PriceConditionRequest] = None


class AveragingOrdersRequest(BaseModel):
    """
    Averaging orders (safety orders) configuration.
    
    PERCENTAGE CONVENTION: Use human-readable percentages.
    Example: step_percent=1.5 means 1.5% price drop triggers DCA.
    """
    total_amount: float = Field(default=400, gt=0, description="Total amount for averaging orders")
    orders_count: int = Field(default=4, ge=1, le=50, description="Number of DCA orders")
    step_percent: float = Field(default=1.99, gt=0, description="Price drop % to trigger DCA (e.g., 1.5 = 1.5%)")
    active_orders_limit: bool = Field(default=False)
    max_active_orders: int = Field(default=1, ge=1)
    amount_multiplier: float = Field(default=1.3, ge=1, description="Multiplier for each DCA order")
    amount_multiplier_enabled: bool = Field(default=False)
    step_multiplier: float = Field(default=1.3, ge=1, description="Progressive step multiplier")
    step_multiplier_enabled: bool = Field(default=False)


class TakeProfitRequest(BaseModel):
    """
    Take profit configuration.
    
    PERCENTAGE CONVENTION: Use human-readable percentages.
    Example: price_change_percent=2.0 means take profit at 2% gain.
    Example: trailing_deviation=0.5 means 0.5% trailing stop.
    """
    enabled: bool = Field(default=True)
    type: str = Field(default="regular")
    price_change_percent: float = Field(default=1.0, gt=0, description="Take profit target % (e.g., 2.0 = 2%)")
    price_reference: str = Field(default="average_price")
    order_type: str = Field(default="limit")
    trailing_deviation: Optional[float] = Field(None, gt=0, description="Trailing stop % (e.g., 0.5 = 0.5%)")
    signal_config: Optional[SignalConfigRequest] = None


class StopLossRequest(BaseModel):
    """
    Stop loss configuration.
    
    PERCENTAGE CONVENTION: Use human-readable percentages.
    Example: percent=10.0 means stop loss at 10% loss.
    """
    enabled: bool = Field(default=False)
    percent: float = Field(default=10.0, gt=0, description="Stop loss % (e.g., 10.0 = 10%)")
    order_type: str = Field(default="market")
    trailing_enabled: bool = Field(default=False)
    trailing_deviation_percent: Optional[float] = Field(None, gt=0, description="Trailing deviation % (e.g., 0.5 = 0.5%)")


class RiskManagementRequest(BaseModel):
    """
    Risk management settings.
    
    PERCENTAGE CONVENTION: Use human-readable percentages.
    Example: target_total_profit_percent=5.0 means 5% target.
    """
    pump_dump_protection: bool = Field(default=True)
    target_total_profit_enabled: bool = Field(default=False)
    target_total_profit_amount: Optional[float] = Field(None, gt=0)
    target_total_profit_percent: Optional[float] = Field(None, gt=0, description="Target profit % (e.g., 5.0 = 5%)")
    allowed_total_loss_enabled: bool = Field(default=False)
    allowed_total_loss_amount: Optional[float] = Field(None, gt=0)
    allowed_total_loss_percent: Optional[float] = Field(None, gt=0, description="Max loss % (e.g., 10.0 = 10%)")
    max_price_enabled: bool = Field(default=False)
    max_price: Optional[float] = Field(None, gt=0)
    min_price_enabled: bool = Field(default=False)
    min_price: Optional[float] = Field(None, gt=0)
    renewal_profit_enabled: bool = Field(default=False)
    cooldown_period: int = Field(default=0, ge=0)
    max_deals: int = Field(default=1, ge=1)


class DCAConfigRequest(BaseModel):
    """DCA strategy configuration."""
    quick_setup: str = Field(default="mid_term")
    start_settings: Optional[BotStartSettingsRequest] = None
    averaging_orders: Optional[AveragingOrdersRequest] = None
    take_profit: Optional[TakeProfitRequest] = None
    stop_loss: Optional[StopLossRequest] = None
    risk_management: Optional[RiskManagementRequest] = None


class CreateBotRequest(BaseModel):
    """Request model for creating a new bot."""
    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    symbol: str = Field(..., min_length=1, max_length=20)
    exchange: str = Field(...)
    asset_class: str = Field(default="stock")
    bot_type: str = Field(default="dca")
    position_mode: str = Field(default="long")
    investment_amount: float = Field(..., gt=0)
    leverage: int = Field(default=1, ge=1, le=125)
    margin_mode: str = Field(default="isolated")
    dca_config: DCAConfigRequest = Field(default_factory=DCAConfigRequest)
    tags: List[str] = Field(default_factory=list)
    
    @validator('symbol')
    def uppercase_symbol(cls, v: str) -> str:
        return v.upper().strip()
    
    @validator('bot_type')
    def validate_bot_type(cls, v: str) -> str:
        v = v.lower().strip()
        valid_types = ('dca', 'combo', 'grid', 'futures_dca', 'futures_combo', 'spot_loop')
        if v not in valid_types:
            raise ValueError(f"Bot type must be one of: {', '.join(valid_types)}")
        return v


class UpdateBotRequest(BaseModel):
    """Request model for updating a bot."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    tags: Optional[List[str]] = None
    dca_config: Optional[DCAConfigRequest] = None


class BotActionRequest(BaseModel):
    """Request model for bot actions."""
    action: str = Field(...)
    amount: Optional[float] = Field(None, gt=0)
    close_positions: bool = Field(default=False)
    cancel_orders: bool = Field(default=True)
    percentage: float = Field(default=100.0, gt=0, le=100)
    
    @validator('action')
    def validate_action(cls, v: str) -> str:
        v = v.lower().strip()
        valid_actions = ('start', 'stop', 'pause', 'resume', 'manual_average', 'adjust_margin', 'close_position')
        if v not in valid_actions:
            raise ValueError(f"Action must be one of: {', '.join(valid_actions)}")
        return v


class BotManagementRouter(BaseAdminRouter):
    """
    Router for bot management (CRUD) operations.
    
    Provides endpoints for:
    - GET /bots - List all bots
    - POST /bots - Create a new bot
    - GET /bots/{bot_id} - Get bot details
    - PATCH /bots/{bot_id} - Update a bot
    - DELETE /bots/{bot_id} - Delete a bot
    - POST /bots/{bot_id}/actions - Perform bot action
    - GET /bots/{bot_id}/orders - Get bot orders
    - GET /bots/{bot_id}/performance - Get bot performance
    """
    
    def __init__(
        self,
        bot_service: Optional["IBotService"] = None,
        auth_service=None
    ):
        """
        Initialize bot management router.
        
        Args:
            bot_service: Bot management service
            auth_service: Authentication service
        """
        super().__init__(auth_service=auth_service, prefix="/admin", tags=["bots"])
        
        self._bot_service = bot_service
        
        self._setup_routes()
        logger.info("✅ BotManagementRouter initialized")
    
    def set_bot_service(self, bot_service: "IBotService") -> None:
        """Set the bot service."""
        self._bot_service = bot_service
        logger.info("Bot service set for BotManagementRouter")
    
    def _get_mock_bots_list(self, state=None, symbol=None, exchange=None) -> JSONResponse:
        """Return mock bots list for development."""
        mock_bots = [
            {
                "id": "bot-001",
                "name": "AAPL DCA Bot",
                "symbol": "AAPL",
                "state": "running",
                "type": "dca",
                "pnl_percent": 2.5,
                "investment_amount": 1000
            }
        ]
        return JSONResponse(content={"bots": mock_bots, "count": len(mock_bots)})
    
    def _get_mock_bot_detail(self, bot_id: str) -> JSONResponse:
        """Return mock bot detail for development."""
        return JSONResponse(content={
            "bot": {
                "id": bot_id,
                "name": "Mock Bot",
                "symbol": "AAPL",
                "state": "running"
            }
        })
    
    def _setup_routes(self) -> None:
        """Setup bot management routes."""
        
        @self.router.get("/bots")
        @handle_route_errors(operation_name="list_bots")
        async def list_bots(
            request: Request,
            authorization: Optional[str] = Header(None),
            state: Optional[str] = None,
            symbol: Optional[str] = None,
            exchange: Optional[str] = None
        ):
            """List all bots for the authenticated user."""
            claims = await self.validate_auth(request, authorization)
            user_id = claims.user_id if claims else "anonymous"
            
            if not self._bot_service:
                return self._get_mock_bots_list(state, symbol, exchange)
            
            state_filter = None
            if state:
                state_filter = [BotState(s.strip()) for s in state.split(",")]
            
            bots = await self._bot_service.list_bots(
                user_id=user_id,
                state_filter=state_filter,
                symbol_filter=symbol,
                exchange_filter=exchange,
                include_performance=True
            )
            
            return JSONResponse(content={
                "bots": [bot.to_dict() for bot in bots],
                "count": len(bots)
            })
        
        @self.router.post("/bots")
        @handle_route_errors(operation_name="create_bot")
        async def create_bot(
            bot_request: CreateBotRequest,
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Create a new trading bot."""
            claims = await self.validate_auth(request, authorization)
            user_id = claims.user_id if claims else "anonymous"
            
            if not self._bot_service:
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR,
                    detail="Bot service not available"
                )
            
            # Build configuration from request
            configuration = self._build_configuration(bot_request)
            
            bot = await self._bot_service.create_bot(
                user_id=user_id,
                name=bot_request.name,
                configuration=configuration,
                description=bot_request.description,
                tags=bot_request.tags
            )
            
            logger.info(f"Created bot {bot.id} for user {user_id}")
            
            return JSONResponse(content={
                "status": "created",
                "bot_id": bot.id,
                "bot": bot.to_dict()
            })
        
        @self.router.get("/bots/{bot_id}")
        async def get_bot(
            bot_id: str,
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Get a specific bot by ID."""
            claims = await self.validate_auth(request, authorization)
            user_id = claims.user_id if claims else "anonymous"
            
            if not self._bot_service:
                return self._get_mock_bot_detail(bot_id)
            
            bot = await self._bot_service.get_bot(bot_id, user_id)
            if not bot:
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Bot not found")
            
            return JSONResponse(content={"bot": bot.to_dict()})
        
        @self.router.patch("/bots/{bot_id}")
        @handle_route_errors(operation_name="update_bot")
        async def update_bot(
            bot_id: str,
            update_request: UpdateBotRequest,
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Update a bot's settings."""
            claims = await self.validate_auth(request, authorization)
            user_id = claims.user_id if claims else "anonymous"
            
            if not self._bot_service:
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR,
                    detail="Bot service not available"
                )
            
            bot = await self._bot_service.update_bot(
                bot_id=bot_id,
                user_id=user_id,
                name=update_request.name,
                description=update_request.description,
                tags=update_request.tags
            )
            
            if not bot:
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Bot not found")
            
            return JSONResponse(content={"status": "updated", "bot": bot.to_dict()})
        
        @self.router.delete("/bots/{bot_id}")
        @handle_route_errors(operation_name="delete_bot")
        async def delete_bot(
            bot_id: str,
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Delete a bot."""
            claims = await self.validate_auth(request, authorization)
            user_id = claims.user_id if claims else "anonymous"
            
            if not self._bot_service:
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR,
                    detail="Bot service not available"
                )
            
            deleted = await self._bot_service.delete_bot(bot_id, user_id)
            if not deleted:
                raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Bot not found")
            
            return JSONResponse(content={"status": "deleted", "bot_id": bot_id})
        
        @self.router.post("/bots/{bot_id}/actions")
        @handle_route_errors(operation_name="bot_action")
        async def bot_action(
            bot_id: str,
            action_request: BotActionRequest,
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Perform an action on a bot."""
            claims = await self.validate_auth(request, authorization)
            user_id = claims.user_id if claims else "anonymous"
            
            if not self._bot_service:
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR,
                    detail="Bot service not available"
                )
            
            action = action_request.action
            
            if action == "start":
                bot = await self._bot_service.start_bot(bot_id, user_id)
            elif action == "stop":
                bot = await self._bot_service.stop_bot(
                    bot_id, user_id,
                    close_positions=action_request.close_positions,
                    cancel_orders=action_request.cancel_orders
                )
            elif action == "pause":
                bot = await self._bot_service.pause_bot(bot_id, user_id)
            elif action == "resume":
                bot = await self._bot_service.resume_bot(bot_id, user_id)
            elif action == "manual_average":
                amount = Decimal(str(action_request.amount)) if action_request.amount else None
                bot = await self._bot_service.manual_average(bot_id, user_id, amount)
            elif action == "close_position":
                bot = await self._bot_service.close_position(
                    bot_id, user_id, 
                    Decimal(str(action_request.percentage))
                )
            else:
                raise ValueError(f"Unknown action: {action}")
            
            logger.info(f"Bot {bot_id} action '{action}' completed")
            
            return JSONResponse(content={
                "status": "success",
                "action": action,
                "bot": bot.to_dict()
            })
        
        @self.router.get("/bots/{bot_id}/orders")
        async def get_bot_orders(
            bot_id: str,
            request: Request,
            authorization: Optional[str] = Header(None),
            status: Optional[str] = None,
            limit: int = 50
        ):
            """Get orders for a specific bot."""
            claims = await self.validate_auth(request, authorization)
            user_id = claims.user_id if claims else "anonymous"
            
            if not self._bot_service:
                return JSONResponse(content={"orders": [], "count": 0})
            
            status_filter = status.split(",") if status else None
            orders = await self._bot_service.get_bot_orders(
                bot_id, user_id, status_filter, limit
            )
            
            return JSONResponse(content={
                "orders": [o.to_dict() for o in orders],
                "count": len(orders)
            })
        
        @self.router.get("/bots/{bot_id}/performance")
        async def get_bot_performance(
            bot_id: str,
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Get performance metrics for a specific bot."""
            claims = await self.validate_auth(request, authorization)
            user_id = claims.user_id if claims else "anonymous"
            
            if not self._bot_service:
                return JSONResponse(content={"performance": {}})
            
            performance = await self._bot_service.get_bot_performance(bot_id, user_id)
            return JSONResponse(content={"performance": performance.to_dict()})
    
    def _build_configuration(self, bot_request: CreateBotRequest) -> "BotConfiguration":
        """Build BotConfiguration from request."""
        # Build enhanced DCA configuration
        start_settings = None
        if bot_request.dca_config.start_settings:
            start_settings = BotStartSettings(
                start_condition=BotStartCondition(bot_request.dca_config.start_settings.start_condition),
                base_order_amount=Decimal(str(bot_request.dca_config.start_settings.base_order_amount)),
                base_order_type=BotOrderType(bot_request.dca_config.start_settings.base_order_type),
                base_order_limit_price=Decimal(str(bot_request.dca_config.start_settings.base_order_limit_price)) if bot_request.dca_config.start_settings.base_order_limit_price else None,
                signal_config=self._build_signal_config(bot_request.dca_config.start_settings.signal_config),
                tradingview_config=self._build_tradingview_config(bot_request.dca_config.start_settings.tradingview_config),
                price_condition=self._build_price_condition(bot_request.dca_config.start_settings.price_condition),
            )
        
        averaging_orders = None
        if bot_request.dca_config.averaging_orders:
            averaging_orders = AveragingOrdersConfig(
                total_amount=Decimal(str(bot_request.dca_config.averaging_orders.total_amount)),
                orders_count=bot_request.dca_config.averaging_orders.orders_count,
                step_percent=Decimal(str(bot_request.dca_config.averaging_orders.step_percent)),
                active_orders_limit=bot_request.dca_config.averaging_orders.active_orders_limit,
                max_active_orders=bot_request.dca_config.averaging_orders.max_active_orders,
                amount_multiplier=Decimal(str(bot_request.dca_config.averaging_orders.amount_multiplier)),
                amount_multiplier_enabled=bot_request.dca_config.averaging_orders.amount_multiplier_enabled,
                step_multiplier=Decimal(str(bot_request.dca_config.averaging_orders.step_multiplier)),
                step_multiplier_enabled=bot_request.dca_config.averaging_orders.step_multiplier_enabled,
            )
        
        take_profit = None
        if bot_request.dca_config.take_profit:
            take_profit = TakeProfitConfig(
                enabled=bot_request.dca_config.take_profit.enabled,
                type=TakeProfitType(bot_request.dca_config.take_profit.type),
                price_change_percent=Decimal(str(bot_request.dca_config.take_profit.price_change_percent)),
                price_reference=PriceReference(bot_request.dca_config.take_profit.price_reference),
                order_type=BotOrderType(bot_request.dca_config.take_profit.order_type),
                trailing_deviation=Decimal(str(bot_request.dca_config.take_profit.trailing_deviation)) if bot_request.dca_config.take_profit.trailing_deviation else None,
                signal_config=self._build_signal_config(bot_request.dca_config.take_profit.signal_config),
            )
        
        stop_loss = None
        if bot_request.dca_config.stop_loss:
            stop_loss = StopLossConfig(
                enabled=bot_request.dca_config.stop_loss.enabled,
                percent=Decimal(str(bot_request.dca_config.stop_loss.percent)),
                order_type=BotOrderType(bot_request.dca_config.stop_loss.order_type),
                trailing_enabled=bot_request.dca_config.stop_loss.trailing_enabled,
                trailing_deviation_percent=Decimal(str(bot_request.dca_config.stop_loss.trailing_deviation_percent)) if bot_request.dca_config.stop_loss.trailing_deviation_percent else None,
            )
        
        risk_management = None
        if bot_request.dca_config.risk_management:
            risk_management = RiskManagementConfig(
                pump_dump_protection=bot_request.dca_config.risk_management.pump_dump_protection,
                target_total_profit_enabled=bot_request.dca_config.risk_management.target_total_profit_enabled,
                target_total_profit_amount=Decimal(str(bot_request.dca_config.risk_management.target_total_profit_amount)) if bot_request.dca_config.risk_management.target_total_profit_amount else None,
                target_total_profit_percent=Decimal(str(bot_request.dca_config.risk_management.target_total_profit_percent)) if bot_request.dca_config.risk_management.target_total_profit_percent else None,
                allowed_total_loss_enabled=bot_request.dca_config.risk_management.allowed_total_loss_enabled,
                allowed_total_loss_amount=Decimal(str(bot_request.dca_config.risk_management.allowed_total_loss_amount)) if bot_request.dca_config.risk_management.allowed_total_loss_amount else None,
                allowed_total_loss_percent=Decimal(str(bot_request.dca_config.risk_management.allowed_total_loss_percent)) if bot_request.dca_config.risk_management.allowed_total_loss_percent else None,
                max_price_enabled=bot_request.dca_config.risk_management.max_price_enabled,
                max_price=Decimal(str(bot_request.dca_config.risk_management.max_price)) if bot_request.dca_config.risk_management.max_price else None,
                min_price_enabled=bot_request.dca_config.risk_management.min_price_enabled,
                min_price=Decimal(str(bot_request.dca_config.risk_management.min_price)) if bot_request.dca_config.risk_management.min_price else None,
                renewal_profit_enabled=bot_request.dca_config.risk_management.renewal_profit_enabled,
                cooldown_period=bot_request.dca_config.risk_management.cooldown_period,
                max_deals=bot_request.dca_config.risk_management.max_deals,
            )
        
        dca_config = DCAConfig(
            quick_setup=QuickSetupPreset(bot_request.dca_config.quick_setup),
            start_settings=start_settings,
            averaging_orders=averaging_orders,
            take_profit=take_profit,
            stop_loss=stop_loss,
            risk_management=risk_management,
        )
        
        return BotConfiguration(
            symbol=bot_request.symbol,
            exchange=bot_request.exchange,
            asset_class=bot_request.asset_class,
            position_mode=PositionMode(bot_request.position_mode),
            investment_amount=Decimal(str(bot_request.investment_amount)),
            leverage=bot_request.leverage,
            margin_mode=MarginMode(bot_request.margin_mode),
            bot_type=BotType(bot_request.bot_type),
            dca_config=dca_config
        )
    
    def _build_signal_config(
        self, signal_request: Optional[SignalConfigRequest]
    ) -> Optional[SignalConfig]:
        """
        Build SignalConfig domain model from request.
        
        Args:
            signal_request: Signal configuration from API request
            
        Returns:
            SignalConfig domain model or None if not provided
        """
        if not signal_request:
            return None
        
        indicators = [
            IndicatorConfig(
                type=IndicatorType(ind.type),
                timeframe=IndicatorTimeframe(ind.timeframe),
                enabled=ind.enabled,
            )
            for ind in signal_request.indicators
        ]
        
        return SignalConfig(
            indicators=indicators,
            signal_lookback_days=signal_request.signal_lookback_days,
        )
    
    def _build_tradingview_config(
        self, tv_request: Optional[TradingViewWebhookConfigRequest]
    ) -> Optional[TradingViewWebhookConfig]:
        """
        Build TradingViewWebhookConfig domain model from request.
        
        Args:
            tv_request: TradingView webhook configuration from API request
            
        Returns:
            TradingViewWebhookConfig domain model or None if not provided
        """
        if not tv_request:
            return None
        
        return TradingViewWebhookConfig(
            enabled=tv_request.enabled,
            webhook_secret=tv_request.webhook_secret,
            alert_message_pattern=tv_request.alert_message_pattern,
        )
    
    def _build_price_condition(
        self, price_request: Optional[PriceConditionRequest]
    ) -> Optional[PriceConditionConfig]:
        """
        Build PriceConditionConfig domain model from request.
        
        Args:
            price_request: Price condition configuration from API request
            
        Returns:
            PriceConditionConfig domain model or None if not provided
        """
        if not price_request:
            return None
        
        return PriceConditionConfig(
            operator=price_request.operator,
            price=Decimal(str(price_request.price)),
        )
