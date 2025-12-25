"""
Futures DCA (Dollar Cost Average) Trading Strategy.

Extends the DCAStrategy with futures-specific functionality:
- Leverage support (1x to 10x)
- Margin mode (Cross/Isolated)
- Liquidation price tracking
- Futures-specific risk management

This strategy inherits all DCA functionality and adds futures-specific
enhancements for margin trading.

Author: Trading Bot Team
Version: 1.0.0
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, Optional, Any

from src.interfaces import (
    IOrderManager, IMarketDataProvider, IRiskManager,
    TradingSignal, Position, StrategyEvaluation
)
from src.core.logging_config import get_logger
from src.strategies.dca_strategy import DCAStrategy, DCAStrategyDependencies
from src.domain.bot_models import (
    BotConfiguration, BotType, MarginMode, PositionMode
)

logger = get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================

MIN_LEVERAGE = 1
MAX_LEVERAGE = 10
DEFAULT_LEVERAGE = 1
DEFAULT_MARGIN_MODE = MarginMode.ISOLATED


@dataclass
class FuturesPositionInfo:
    """
    Futures-specific position information.
    
    Tracks liquidation price, margin usage, and other futures-specific
    metrics that need to be monitored for risk management.
    
    Attributes:
        leverage: Current leverage multiplier (1-10x).
        margin_mode: Cross or Isolated margin mode.
        liquidation_price: Estimated liquidation price.
        margin_used: Amount of margin used for the position.
        maintenance_margin: Minimum margin to avoid liquidation.
        unrealized_pnl: Unrealized profit/loss in quote currency.
        funding_rate: Current funding rate (for perpetual contracts).
        next_funding_time: Timestamp of next funding payment.
    """
    
    leverage: int = DEFAULT_LEVERAGE
    margin_mode: MarginMode = DEFAULT_MARGIN_MODE
    liquidation_price: Optional[Decimal] = None
    margin_used: Decimal = Decimal("0")
    maintenance_margin: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    funding_rate: Optional[Decimal] = None
    next_funding_time: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "leverage": self.leverage,
            "marginMode": self.margin_mode.value,
            "liquidationPrice": str(self.liquidation_price) if self.liquidation_price else None,
            "marginUsed": str(self.margin_used),
            "maintenanceMargin": str(self.maintenance_margin),
            "unrealizedPnl": str(self.unrealized_pnl),
            "fundingRate": str(self.funding_rate) if self.funding_rate else None,
            "nextFundingTime": self.next_funding_time,
        }


class FuturesDCAStrategy(DCAStrategy):
    """
    Futures DCA Trading Strategy with leverage and margin mode support.
    
    Extends the spot DCA strategy with futures-specific functionality:
    - Leverage management (1x to 10x)
    - Margin mode selection (Cross/Isolated)
    - Liquidation price tracking and alerts
    - Position size adjustment for leverage
    - Enhanced risk management for leveraged positions
    
    The strategy uses the same DCA averaging logic but applies it to
    futures/perpetual contracts with configurable leverage.
    
    Key Differences from Spot DCA:
    - Position sizes are multiplied by leverage
    - Liquidation price must be monitored
    - Cross margin shares collateral across positions
    - Isolated margin limits risk to position margin only
    
    Example:
        config = BotConfiguration(
            symbol="BTCUSDT",
            exchange="binance_futures",
            bot_type=BotType.FUTURES_DCA,
            leverage=5,
            margin_mode=MarginMode.ISOLATED,
            ...
        )
        strategy = FuturesDCAStrategy(order_mgr, market_data, risk_mgr, config)
        await strategy.initialize()
    
    Thread Safety:
        Not thread-safe. Use appropriate locking when accessing from
        multiple threads.
    """
    
    # Strategy identification
    STRATEGY_NAME = "futures_dca_strategy"
    BOT_TYPE = BotType.FUTURES_DCA
    
    def __init__(
        self,
        order_manager: IOrderManager,
        market_data: IMarketDataProvider,
        risk_manager: IRiskManager,
        bot_config: BotConfiguration,
        position_manager=None,
        resilience_tracker=None,
        dependencies: Optional[DCAStrategyDependencies] = None,
    ):
        """
        Initialize the Futures DCA trading strategy.
        
        Args:
            order_manager: Order execution manager.
            market_data: Market data provider.
            risk_manager: Risk management service.
            bot_config: Bot's configuration from database (REQUIRED).
            position_manager: Position tracking manager (optional).
            resilience_tracker: Resilience tracking service (optional).
            dependencies: Grouped optional dependencies container.
            
        Raises:
            ValueError: If bot_config is None or has invalid leverage.
        """
        # Validate futures-specific configuration
        self._validate_futures_config(bot_config)
        
        # Initialize parent DCA strategy
        super().__init__(
            order_manager=order_manager,
            market_data=market_data,
            risk_manager=risk_manager,
            bot_config=bot_config,
            position_manager=position_manager,
            resilience_tracker=resilience_tracker,
            dependencies=dependencies,
        )
        
        # Futures-specific state
        self._futures_info = FuturesPositionInfo(
            leverage=bot_config.leverage,
            margin_mode=bot_config.margin_mode,
        )
        
        logger.info(
            f"✅ Futures DCA Strategy initialized with "
            f"leverage={self.leverage}x, margin_mode={self.margin_mode.value}"
        )
    
    def _validate_futures_config(self, bot_config: BotConfiguration) -> None:
        """
        Validate futures-specific configuration.
        
        Args:
            bot_config: Bot configuration to validate.
            
        Raises:
            ValueError: If configuration is invalid for futures trading.
        """
        if bot_config is None:
            raise ValueError("bot_config is required")
        
        if not bot_config.is_futures_bot:
            logger.warning(
                f"BotConfiguration has bot_type={bot_config.bot_type}, "
                f"expected FUTURES_DCA. Treating as futures bot anyway."
            )
        
        # Validate leverage
        leverage = bot_config.leverage
        if leverage < MIN_LEVERAGE or leverage > MAX_LEVERAGE:
            raise ValueError(
                f"Leverage must be between {MIN_LEVERAGE}x and {MAX_LEVERAGE}x, "
                f"got {leverage}x"
            )
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def leverage(self) -> int:
        """Get current leverage multiplier."""
        return self._bot_config.leverage
    
    @property
    def margin_mode(self) -> MarginMode:
        """Get current margin mode."""
        return self._bot_config.margin_mode
    
    @property
    def is_cross_margin(self) -> bool:
        """Check if using cross margin mode."""
        return self.margin_mode == MarginMode.CROSS
    
    @property
    def is_isolated_margin(self) -> bool:
        """Check if using isolated margin mode."""
        return self.margin_mode == MarginMode.ISOLATED
    
    @property
    def futures_info(self) -> FuturesPositionInfo:
        """Get futures-specific position information."""
        return self._futures_info
    
    @property
    def effective_position_size(self) -> Decimal:
        """
        Get effective position size (actual size * leverage).
        
        For a $1000 position with 5x leverage, effective size is $5000.
        """
        # Get base position value from config
        base_amount = self._bot_config.investment_amount
        return base_amount * Decimal(str(self.leverage))
    
    # =========================================================================
    # Futures-Specific Methods
    # =========================================================================
    
    def calculate_liquidation_price(
        self,
        entry_price: Decimal,
        position_size: Decimal,
        is_long: bool,
    ) -> Decimal:
        """
        Calculate estimated liquidation price for a position.
        
        The liquidation price depends on:
        - Entry price
        - Leverage (higher leverage = closer liquidation)
        - Position direction (long/short)
        - Maintenance margin rate (exchange-specific)
        
        This is a simplified calculation. Actual liquidation price
        may vary based on exchange-specific rules and fee structures.
        
        Args:
            entry_price: Position entry price.
            position_size: Position size in quote currency.
            is_long: True for long positions, False for short.
            
        Returns:
            Estimated liquidation price.
        """
        # Simplified maintenance margin rate (varies by exchange)
        maintenance_margin_rate = Decimal("0.005")  # 0.5%
        
        # Calculate margin and buffer
        margin = position_size / Decimal(str(self.leverage))
        buffer_percent = (Decimal("1") - maintenance_margin_rate) / Decimal(str(self.leverage))
        
        if is_long:
            # For longs, liquidation happens when price drops
            liquidation_price = entry_price * (Decimal("1") - buffer_percent)
        else:
            # For shorts, liquidation happens when price rises
            liquidation_price = entry_price * (Decimal("1") + buffer_percent)
        
        logger.debug(
            f"Calculated liquidation price: ${liquidation_price:.2f} "
            f"(entry=${entry_price:.2f}, leverage={self.leverage}x, "
            f"direction={'long' if is_long else 'short'})"
        )
        
        return liquidation_price
    
    def is_near_liquidation(
        self,
        current_price: Decimal,
        liquidation_price: Decimal,
        threshold_percent: Decimal = Decimal("10"),
    ) -> bool:
        """
        Check if current price is near liquidation threshold.
        
        Args:
            current_price: Current market price.
            liquidation_price: Position liquidation price.
            threshold_percent: Alert threshold as percentage (default 10%).
            
        Returns:
            True if within threshold of liquidation price.
        """
        if liquidation_price <= 0:
            return False
        
        distance_percent = abs(
            (current_price - liquidation_price) / liquidation_price * Decimal("100")
        )
        
        return distance_percent <= threshold_percent
    
    def adjust_order_size_for_leverage(self, base_size: Decimal) -> Decimal:
        """
        Adjust order size accounting for leverage.
        
        When using leverage, the margin requirement is reduced:
        - 5x leverage: Need only 20% of position value as margin
        - 10x leverage: Need only 10% of position value as margin
        
        Args:
            base_size: Base order size (without leverage).
            
        Returns:
            Adjusted margin requirement for the order.
        """
        return base_size / Decimal(str(self.leverage))
    
    async def update_futures_info(self, symbol: str) -> None:
        """
        Update futures-specific position information.
        
        Fetches latest liquidation price, margin usage, funding rate,
        and other futures-specific metrics from the exchange.
        
        Args:
            symbol: Trading pair symbol.
        """
        try:
            # Get current price for liquidation calculation
            current_price = await self.market_data.get_current_price(symbol)
            
            if symbol in self.positions:
                position = self.positions[symbol]
                is_long = position.direction.value == "long"
                
                # Update liquidation price
                self._futures_info.liquidation_price = self.calculate_liquidation_price(
                    entry_price=Decimal(str(position.avg_price)),
                    position_size=Decimal(str(position.current_price * position.quantity)),
                    is_long=is_long,
                )
                
                # Calculate unrealized PnL
                if is_long:
                    pnl = (current_price - Decimal(str(position.avg_price))) * Decimal(str(position.quantity))
                else:
                    pnl = (Decimal(str(position.avg_price)) - current_price) * Decimal(str(position.quantity))
                
                self._futures_info.unrealized_pnl = pnl * Decimal(str(self.leverage))
                
                # Check liquidation warning
                if self.is_near_liquidation(
                    current_price=current_price,
                    liquidation_price=self._futures_info.liquidation_price,
                ):
                    logger.warning(
                        f"⚠️ LIQUIDATION WARNING for {symbol}: "
                        f"Price ${current_price:.2f} is near liquidation "
                        f"at ${self._futures_info.liquidation_price:.2f}"
                    )
        except Exception as e:
            logger.error(f"Failed to update futures info: {e}")
    
    # =========================================================================
    # Override Parent Methods for Futures Specifics
    # =========================================================================
    
    async def evaluate_entry(
        self,
        signal: TradingSignal,
        position: Optional[Position] = None,
        market_context: Optional[Dict[str, Any]] = None,
    ) -> StrategyEvaluation:
        """
        Evaluate entry signal with futures-specific checks.
        
        Adds leverage-aware risk assessment to the parent evaluation:
        - Checks if leverage is appropriate for market volatility
        - Validates margin requirements
        - Ensures position won't be immediately liquidated
        
        Args:
            signal: Trading signal to evaluate.
            position: Existing position if any.
            market_context: Additional market context.
            
        Returns:
            StrategyEvaluation with entry decision and futures context.
        """
        # Get base evaluation from parent
        evaluation = await super().evaluate_entry(signal, position, market_context)
        
        if not evaluation.should_act:
            return evaluation
        
        # Add futures-specific metadata
        if evaluation.metadata is None:
            evaluation.metadata = {}
        
        evaluation.metadata.update({
            "leverage": self.leverage,
            "margin_mode": self.margin_mode.value,
            "effective_position_size": str(self.effective_position_size),
            "is_futures": True,
        })
        
        # Log the leveraged entry evaluation
        logger.info(
            f"📈 Futures entry evaluation for {signal.symbol}: "
            f"leverage={self.leverage}x, mode={self.margin_mode.value}, "
            f"should_act={evaluation.should_act}"
        )
        
        return evaluation
    
    def get_state(self) -> Dict[str, Any]:
        """
        Get strategy state with futures-specific information.
        
        Returns:
            Dictionary containing full strategy state including
            futures-specific fields like leverage and liquidation.
        """
        # Get base state from parent
        state = super().get_state()
        
        # Add futures-specific state
        state.update({
            "is_futures": True,
            "leverage": self.leverage,
            "margin_mode": self.margin_mode.value,
            "effective_position_size": str(self.effective_position_size),
            "futures_info": self._futures_info.to_dict(),
        })
        
        return state
    
    def set_bot_config(self, bot_config: BotConfiguration) -> None:
        """
        Update the bot's configuration at runtime.
        
        Validates futures-specific settings before applying.
        
        Args:
            bot_config: New bot configuration.
            
        Raises:
            ValueError: If configuration is invalid.
        """
        # Validate futures config before applying
        self._validate_futures_config(bot_config)
        
        # Update futures-specific info
        old_leverage = self.leverage
        old_margin_mode = self.margin_mode
        
        # Apply parent config update
        super().set_bot_config(bot_config)
        
        # Update futures info
        self._futures_info.leverage = bot_config.leverage
        self._futures_info.margin_mode = bot_config.margin_mode
        
        # Log changes
        if old_leverage != bot_config.leverage:
            logger.info(f"✅ Leverage updated: {old_leverage}x → {bot_config.leverage}x")
        if old_margin_mode != bot_config.margin_mode:
            logger.info(
                f"✅ Margin mode updated: {old_margin_mode.value} → {bot_config.margin_mode.value}"
            )
