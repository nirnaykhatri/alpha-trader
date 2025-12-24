"""
Signal Handler - Extracted from BotRunner.

Handles processing of trading signals for bot execution:
- Buy signals (enter long positions)
- Sell signals (exit positions)
- Close signals (force close positions)

This class follows Single Responsibility Principle by focusing
exclusively on signal processing concerns.

Author: Trading Bot Team
Version: 1.0.0
"""

from typing import Dict, Any, TYPE_CHECKING, Callable, Awaitable

from src.core.logging_config import get_logger
from src.domain.bot_models import BotOperationalPhase

if TYPE_CHECKING:
    from src.domain.bot_models import Bot
    from src.bot_engine.handlers.order_handler import OrderHandler

logger = get_logger(__name__)


# Type aliases for callbacks
PhaseUpdateCallback = Callable[[BotOperationalPhase], Awaitable[None]]
PersistCallback = Callable[[], Awaitable[None]]


class SignalHandler:
    """
    Handles trading signal processing for a bot.
    
    Extracted from BotRunner to separate signal handling concerns
    from the main bot lifecycle management.
    
    Responsibilities:
    - Process buy signals (webhook, indicator-based)
    - Process sell signals (take profit triggers)
    - Process close signals (manual close)
    
    Thread Safety:
    - All methods are async and run in single event loop
    - Delegates order execution to OrderHandler
    
    Usage:
        handler = SignalHandler(bot, order_handler)
        await handler.handle_buy_signal(signal_data)
    """
    
    def __init__(
        self,
        bot: "Bot",
        order_handler: "OrderHandler",
    ):
        """
        Initialize the signal handler.
        
        Args:
            bot: Bot domain model with configuration
            order_handler: Order handler for executing trades
        """
        self._bot = bot
        self._order_handler = order_handler
    
    # =========================================================================
    # Signal Processing Methods
    # =========================================================================
    
    async def handle_buy_signal(
        self,
        signal: Dict[str, Any],
        current_price: float,
        on_phase_update: PhaseUpdateCallback,
        on_persist: PersistCallback,
    ) -> bool:
        """
        Handle a buy signal.
        
        Processes buy signals based on the bot's start condition configuration.
        For tradingview_webhook start condition, waits for webhook before entering.
        
        Args:
            signal: Signal data dictionary
            current_price: Current market price
            on_phase_update: Callback to update bot operational phase
            on_persist: Callback to persist bot state
            
        Returns:
            True if signal was processed and position entered
        """
        dca_config = self._bot.configuration.dca_config
        if not dca_config:
            logger.warning(f"Bot {self._bot.id}: No DCA config for buy signal")
            return False
        
        start_condition = dca_config.start_settings.start_condition
        
        if start_condition == "tradingview_webhook":
            if self._bot.operational_phase == BotOperationalPhase.WAITING_FOR_WEBHOOK:
                logger.info(f"Bot {self._bot.id}: Webhook received, entering position")
                await on_phase_update(BotOperationalPhase.WEBHOOK_RECEIVED)
                await on_phase_update(BotOperationalPhase.ENTERING_POSITION)
                
                from decimal import Decimal
                return await self._order_handler.place_base_order(
                    current_price=Decimal(str(current_price)),
                    on_phase_update=on_phase_update,
                    on_persist=on_persist,
                )
        
        elif start_condition == "immediately":
            if self._bot.operational_phase == BotOperationalPhase.SIGNAL_MATCHED:
                logger.info(f"Bot {self._bot.id}: Immediate start, entering position")
                await on_phase_update(BotOperationalPhase.ENTERING_POSITION)
                
                from decimal import Decimal
                return await self._order_handler.place_base_order(
                    current_price=Decimal(str(current_price)),
                    on_phase_update=on_phase_update,
                    on_persist=on_persist,
                )
        
        logger.debug(
            f"Bot {self._bot.id}: Buy signal ignored "
            f"(phase={self._bot.operational_phase.value}, "
            f"condition={start_condition})"
        )
        return False
    
    async def handle_sell_signal(
        self,
        signal: Dict[str, Any],
        on_phase_update: PhaseUpdateCallback,
        on_persist: PersistCallback,
    ) -> bool:
        """
        Handle a sell signal.
        
        Triggers take profit if bot has an active position.
        
        Args:
            signal: Signal data dictionary
            on_phase_update: Callback to update bot operational phase
            on_persist: Callback to persist bot state
            
        Returns:
            True if position was closed
        """
        if self._order_handler.has_position:
            logger.info(f"Bot {self._bot.id}: Sell signal received, taking profit")
            return await self._order_handler.execute_take_profit(
                on_phase_update=on_phase_update,
                on_persist=on_persist,
            )
        
        logger.debug(f"Bot {self._bot.id}: Sell signal ignored (no position)")
        return False
    
    async def handle_close_signal(
        self,
        signal: Dict[str, Any],
        on_phase_update: PhaseUpdateCallback,
        on_persist: PersistCallback,
    ) -> bool:
        """
        Handle a close signal.
        
        Forces immediate position closure regardless of P&L.
        
        Args:
            signal: Signal data dictionary
            on_phase_update: Callback to update bot operational phase
            on_persist: Callback to persist bot state
            
        Returns:
            True if position was closed
        """
        if self._order_handler.has_position:
            logger.info(f"Bot {self._bot.id}: Close signal received, closing position")
            return await self._order_handler.close_position(
                on_phase_update=on_phase_update,
                on_persist=on_persist,
            )
        
        logger.debug(f"Bot {self._bot.id}: Close signal ignored (no position)")
        return False
    
    async def handle_signal(
        self,
        signal: Dict[str, Any],
        current_price: float,
        on_phase_update: PhaseUpdateCallback,
        on_persist: PersistCallback,
    ) -> bool:
        """
        Route a signal to the appropriate handler based on signal type.
        
        Args:
            signal: Signal data dictionary (must include 'type' key)
            current_price: Current market price
            on_phase_update: Callback to update bot operational phase
            on_persist: Callback to persist bot state
            
        Returns:
            True if signal was processed successfully
        """
        signal_type = signal.get("type", "").lower()
        
        if signal_type == "buy":
            return await self.handle_buy_signal(
                signal, current_price, on_phase_update, on_persist
            )
        elif signal_type == "sell":
            return await self.handle_sell_signal(
                signal, on_phase_update, on_persist
            )
        elif signal_type == "close":
            return await self.handle_close_signal(
                signal, on_phase_update, on_persist
            )
        else:
            logger.warning(f"Bot {self._bot.id}: Unknown signal type '{signal_type}'")
            return False
