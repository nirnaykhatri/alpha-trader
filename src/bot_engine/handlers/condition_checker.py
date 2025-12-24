"""
Condition Checker - Extracted from BotRunner.

Evaluates trading conditions for bot decision making:
- Take profit conditions (fixed and trailing)
- Stop loss conditions (fixed and trailing)
- Safety order (DCA) conditions
- Grid range conditions

This class follows Single Responsibility Principle by focusing
exclusively on condition evaluation concerns.

Author: Trading Bot Team
Version: 1.0.0
"""

from decimal import Decimal
from typing import Optional, TYPE_CHECKING

from src.core.logging_config import get_logger
from src.domain.bot_models import PriceReference

if TYPE_CHECKING:
    from src.domain.bot_models import Bot

logger = get_logger(__name__)


class ConditionChecker:
    """
    Evaluates trading conditions for a bot.
    
    Extracted from BotRunner to separate condition checking concerns
    from the main bot lifecycle management.
    
    Responsibilities:
    - Evaluate take profit conditions (fixed and trailing)
    - Evaluate stop loss conditions (fixed and trailing)
    - Evaluate safety order (DCA) trigger conditions
    - Evaluate grid range conditions
    
    Thread Safety:
    - All evaluation methods are pure functions or async-safe
    - State (peak_price, trailing_stop_price) is managed per-instance
    
    Usage:
        checker = ConditionChecker(bot)
        if await checker.should_take_profit(current_price, avg_entry, base_price):
            await order_handler.execute_take_profit(...)
    """
    
    def __init__(self, bot: "Bot"):
        """
        Initialize the condition checker.
        
        Args:
            bot: Bot domain model with configuration
        """
        self._bot = bot
        
        # Trailing stop loss tracking
        self._peak_price: Optional[Decimal] = None
        self._trailing_stop_price: Optional[Decimal] = None
    
    # =========================================================================
    # Take Profit Conditions
    # =========================================================================
    
    async def should_take_profit(
        self,
        current_price: Decimal,
        avg_entry_price: Optional[Decimal],
        base_order_price: Optional[Decimal],
    ) -> bool:
        """
        Check if take profit conditions are met.
        
        Uses price_reference setting to determine whether to calculate
        profit from average entry price or base order price.
        
        Args:
            current_price: Current market price
            avg_entry_price: Average entry price of position
            base_order_price: Price of the initial base order
            
        Returns:
            True if take profit should be triggered
        """
        dca_config = self._bot.configuration.dca_config
        if not dca_config or not dca_config.take_profit.enabled:
            return False
        
        if not current_price:
            return False
        
        # Determine reference price based on configuration
        reference_price = self._get_take_profit_reference_price(
            avg_entry_price, base_order_price
        )
        if not reference_price:
            return False
        
        tp_percent = Decimal(str(dca_config.take_profit.price_change_percent))
        current_pnl_percent = (
            (current_price - reference_price) / reference_price * 100
        )
        
        return current_pnl_percent >= tp_percent
    
    def _get_take_profit_reference_price(
        self,
        avg_entry_price: Optional[Decimal],
        base_order_price: Optional[Decimal],
    ) -> Optional[Decimal]:
        """
        Get the reference price for take profit calculation.
        
        Based on the price_reference setting in configuration:
        - AVERAGE_PRICE: Use average entry price (default)
        - BASE_ORDER_PRICE: Use initial base order price
        - BASE_ORDER_PRICE_INDICATORS: Base order + indicators
        - AVERAGE_PRICE_INDICATORS: Average + indicators
        
        Args:
            avg_entry_price: Average entry price
            base_order_price: Base order price
            
        Returns:
            Reference price for take profit calculation
        """
        dca_config = self._bot.configuration.dca_config
        if not dca_config or not dca_config.take_profit:
            return avg_entry_price
        
        price_reference = dca_config.take_profit.price_reference
        
        if price_reference == PriceReference.BASE_ORDER_PRICE:
            if base_order_price:
                return base_order_price
            logger.debug(
                f"Bot {self._bot.id}: Base order price not set, "
                "falling back to average entry"
            )
            return avg_entry_price
        
        elif price_reference == PriceReference.BASE_ORDER_PRICE_INDICATORS:
            # Base order price + indicator signals (indicators not implemented)
            if base_order_price:
                return base_order_price
            return avg_entry_price
        
        elif price_reference == PriceReference.AVERAGE_PRICE_INDICATORS:
            # Average price + indicator signals (indicators not implemented)
            return avg_entry_price
        
        # Default: AVERAGE_PRICE
        return avg_entry_price
    
    # =========================================================================
    # Stop Loss Conditions
    # =========================================================================
    
    async def should_stop_loss(
        self,
        current_price: Decimal,
        avg_entry_price: Optional[Decimal],
    ) -> bool:
        """
        Check if stop loss conditions are met.
        
        Supports both fixed and trailing stop loss:
        - Fixed: Triggers when price drops below entry by stop_loss.percent
        - Trailing: Follows price up, triggers when price drops from peak
        
        Args:
            current_price: Current market price
            avg_entry_price: Average entry price of position
            
        Returns:
            True if stop loss should be triggered
        """
        dca_config = self._bot.configuration.dca_config
        if not dca_config or not dca_config.stop_loss.enabled:
            return False
        
        if not current_price or not avg_entry_price:
            return False
        
        stop_loss_config = dca_config.stop_loss
        
        # Check for trailing stop loss
        if (stop_loss_config.trailing_enabled and 
            stop_loss_config.trailing_deviation_percent):
            return await self._check_trailing_stop_loss(current_price)
        
        # Fixed stop loss check
        sl_percent = Decimal(str(stop_loss_config.percent))
        current_pnl_percent = (
            (current_price - avg_entry_price) / avg_entry_price * 100
        )
        
        return current_pnl_percent <= -sl_percent
    
    async def _check_trailing_stop_loss(
        self,
        current_price: Decimal,
    ) -> bool:
        """
        Check if trailing stop loss should trigger.
        
        Trailing stop loss tracks the highest price and triggers when price
        drops by trailing_deviation_percent from that peak.
        
        Args:
            current_price: Current market price
            
        Returns:
            True if trailing stop should trigger
        """
        dca_config = self._bot.configuration.dca_config
        if not dca_config or not dca_config.stop_loss.trailing_deviation_percent:
            return False
        
        if not current_price:
            return False
        
        trailing_deviation = Decimal(
            str(dca_config.stop_loss.trailing_deviation_percent)
        )
        
        # Initialize peak price if not set
        if self._peak_price is None:
            self._peak_price = current_price
            self._trailing_stop_price = current_price * (1 - trailing_deviation / 100)
            return False
        
        # Update peak price if we have a new high
        if current_price > self._peak_price:
            self._peak_price = current_price
            # Update trailing stop level
            self._trailing_stop_price = self._peak_price * (1 - trailing_deviation / 100)
            logger.debug(
                f"Bot {self._bot.id}: New peak ${self._peak_price:.2f}, "
                f"trailing stop at ${self._trailing_stop_price:.2f}"
            )
        
        # Check if current price has hit the trailing stop
        if self._trailing_stop_price and current_price <= self._trailing_stop_price:
            logger.info(
                f"🛑 Bot {self._bot.id}: Trailing stop loss triggered! "
                f"Peak: ${self._peak_price:.2f}, Current: ${current_price:.2f}, "
                f"Stop: ${self._trailing_stop_price:.2f}"
            )
            return True
        
        return False
    
    # =========================================================================
    # Safety Order (DCA) Conditions
    # =========================================================================
    
    async def should_place_safety_order(
        self,
        current_price: Decimal,
        avg_entry_price: Optional[Decimal],
        safety_orders_used: int,
    ) -> bool:
        """
        Check if safety order conditions are met.
        
        Evaluates whether price has dropped enough to trigger the next
        safety order based on step_percent configuration.
        
        Args:
            current_price: Current market price
            avg_entry_price: Average entry price of position
            safety_orders_used: Number of safety orders already used
            
        Returns:
            True if safety order should be placed
        """
        dca_config = self._bot.configuration.dca_config
        if not dca_config:
            return False
        
        max_orders = dca_config.averaging_orders.orders_count
        if safety_orders_used >= max_orders:
            return False
        
        if not current_price or not avg_entry_price:
            return False
        
        # Check if price has dropped enough for next safety order
        step_percent = Decimal(str(dca_config.averaging_orders.step_percent))
        price_drop_percent = (
            (avg_entry_price - current_price) / avg_entry_price * 100
        )
        
        required_drop = step_percent * (safety_orders_used + 1)
        return price_drop_percent >= required_drop
    
    # =========================================================================
    # Grid Trading Conditions
    # =========================================================================
    
    def check_price_in_grid_range(
        self,
        current_price: Decimal,
    ) -> bool:
        """
        Check if price is within grid range.
        
        Args:
            current_price: Current market price
            
        Returns:
            True if price is within configured grid bounds
        """
        if not current_price:
            return False
        
        lower = self._bot.grid_lower_bound
        upper = self._bot.grid_upper_bound
        
        if lower and upper:
            return lower <= current_price <= upper
        
        return True
    
    # =========================================================================
    # State Management
    # =========================================================================
    
    def reset_trailing_state(self) -> None:
        """Reset trailing stop loss state for a new deal."""
        self._peak_price = None
        self._trailing_stop_price = None
    
    @property
    def peak_price(self) -> Optional[Decimal]:
        """Get the current peak price for trailing stop."""
        return self._peak_price
    
    @property
    def trailing_stop_price(self) -> Optional[Decimal]:
        """Get the current trailing stop price."""
        return self._trailing_stop_price
    
    def get_max_safety_orders(self) -> int:
        """
        Get maximum number of safety orders from config.
        
        Returns:
            Maximum safety order count, or 0 if not configured
        """
        dca_config = self._bot.configuration.dca_config
        if dca_config and dca_config.averaging_orders:
            return dca_config.averaging_orders.orders_count
        return 0
