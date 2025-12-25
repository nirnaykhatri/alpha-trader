"""
Bot Runner - Lightweight Async Bot Execution Wrapper.

Each BotRunner is a minimal async wrapper (~10KB memory) that
executes a single bot's trading strategy. Designed for efficient
resource sharing in a multi-bot environment.

Key Features:
- Minimal memory footprint for 100s of concurrent instances
- Uses shared resources (broker connections, market data)
- Strategy-agnostic execution framework via ITradingStrategy
- Real-time status tracking

Architecture:
- BotRunner is strategy-agnostic (knows nothing about DCA, Grid, etc.)
- Strategy-specific logic is handled by ITradingStrategy implementations
- Strategies are injected via BotRunnerContext or StrategyFactory

Architecture:
- BotRunner is strategy-agnostic (knows nothing about DCA, Grid, etc.)
- Strategy-specific logic is handled by ITradingStrategy implementations
- Strategies are injected via BotRunnerContext or StrategyFactory
- Order execution delegated to OrderHandler
- Signal processing delegated to SignalHandler
- Condition evaluation delegated to ConditionChecker

Author: Trading Bot Team
Version: 2.1.0 (Extracted handlers for SRP compliance)
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Coroutine, Dict, Optional, TYPE_CHECKING
import uuid

from src.core.logging_config import get_logger
from src.domain.bot_models import Bot, BotState, BotOperationalPhase, BotType, PriceReference
from src.bot_engine.interfaces import IBotRunner, BotStatus
from src.bot_engine.handlers import OrderHandler, SignalHandler, ConditionChecker
from src.interfaces import ITradingStrategy

if TYPE_CHECKING:
    from src.bot_engine.interfaces import IMarketDataHub, ISignalRouter, IBrokerConnectionPool
    from src.database.database_interface import IBotRepository
    from src.interfaces import (
        Order, Position, IOrderManager, IMarketDataProvider, 
        IRiskManager, IPositionManager
    )

logger = get_logger(__name__)


# Type aliases for callbacks
OrderPlacedCallback = Callable[["Order"], Coroutine[Any, Any, None]]
PositionUpdatedCallback = Callable[["Position"], Coroutine[Any, Any, None]]
ErrorCallback = Callable[[Exception], Coroutine[Any, Any, None]]


@dataclass
class BotRunnerContext:
    """
    Context data for bot execution.
    
    Contains all shared resources and state needed
    for bot strategy execution.
    
    Attributes:
        market_data_hub: Shared market data stream manager
        signal_router: Routes signals to appropriate bots
        broker_pool: Shared broker connection pool
        bot_repository: Database repository for bot state
        order_manager: Order execution manager (optional - uses broker_pool if None)
        market_data: Market data provider (optional - uses market_data_hub if None)
        risk_manager: Risk management service (optional)
        position_manager: Position tracking manager (optional)
        strategy: Optional injected strategy (created by StrategyFactory if not provided)
        on_order_placed: Callback when order is placed
        on_position_updated: Callback when position changes
        on_error: Callback on error
    """
    
    # Shared resources (references, not owned)
    market_data_hub: "IMarketDataHub"
    signal_router: "ISignalRouter"
    broker_pool: "IBrokerConnectionPool"
    bot_repository: "IBotRepository"
    
    # Trading services (optional - created from broker_pool if not provided)
    order_manager: Optional["IOrderManager"] = None
    market_data: Optional["IMarketDataProvider"] = None
    risk_manager: Optional["IRiskManager"] = None
    position_manager: Optional["IPositionManager"] = None
    
    # Injected strategy (optional - factory will create if None)
    strategy: Optional[ITradingStrategy] = None
    
    # Strategy execution callbacks with proper type hints
    on_order_placed: Optional[OrderPlacedCallback] = None
    on_position_updated: Optional[PositionUpdatedCallback] = None
    on_error: Optional[ErrorCallback] = None


class BotRunner(IBotRunner):
    """
    Lightweight async wrapper for executing a single bot's strategy.
    
    Each BotRunner instance consumes ~10KB of memory and runs as
    an asyncio Task. Multiple BotRunners share broker connections
    and market data streams for efficiency.
    
    Architecture (Strategy Pattern):
    - BotRunner is strategy-agnostic (doesn't know DCA, Grid, etc.)
    - All trading logic is delegated to injected ITradingStrategy
    - Strategy is created via StrategyFactory based on BotType
    
    Lifecycle:
    1. Created by BotEngineManager with bot config
    2. Strategy injected via context or created by factory
    3. start() called to begin execution loop
    4. Receives price updates and signals via callbacks
    5. Delegates to strategy.execute_tick() and strategy.handle_signal()
    6. stop() called for graceful shutdown
    
    Thread Safety:
    - All operations are async and run in single event loop
    - No thread synchronization needed
    - State mutations are atomic within coroutines
    
    Usage:
        runner = BotRunner(bot, context)
        task = asyncio.create_task(runner.start())
        # ... later ...
        await runner.stop()
    """
    
    def __init__(self, bot: Bot, context: BotRunnerContext):
        """
        Initialize the bot runner.
        
        Args:
            bot: Bot domain model with configuration
            context: Shared resources, callbacks, and optional strategy
            
        Note:
            If context.strategy is None, a strategy will be created
            via StrategyFactory when start() is called.
        """
        self._bot = bot
        self._context = context
        
        # Strategy (may be None initially, created on start())
        self._strategy: Optional[ITradingStrategy] = context.strategy
        
        # Execution state
        self._is_running = False
        self._is_paused = False
        self._shutdown_event = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        
        # Current deal/cycle tracking
        self._current_deal_id: Optional[str] = None
        self._deal_start_time: Optional[datetime] = None
        
        # Position tracking (lightweight - full position in DB)
        self._has_position = False
        self._position_size: Optional[Decimal] = None
        self._avg_entry_price: Optional[Decimal] = None
        self._base_order_price: Optional[Decimal] = None  # Price of initial base order
        self._current_price: Optional[Decimal] = None
        self._safety_orders_used = 0
        
        # Trailing stop loss tracking
        self._peak_price: Optional[Decimal] = None  # Highest price since entry (for trailing SL)
        self._trailing_stop_price: Optional[Decimal] = None  # Current trailing stop level
        
        # Cumulative P&L tracking for risk management
        self._cumulative_profit: Decimal = Decimal("0")
        self._cumulative_loss: Decimal = Decimal("0")
        self._active_deals_count: int = 0
        
        # Error tracking
        self._error_count = 0
        self._last_error: Optional[str] = None
        
        # Timestamps
        self._started_at: Optional[datetime] = None
        self._last_activity_at: Optional[datetime] = None
        self._last_order_at: Optional[datetime] = None
        
        # Initialize extracted handlers (SRP compliance)
        # Pass order_manager to OrderHandler for actual trade execution
        self._order_handler = OrderHandler(
            bot, 
            broker_pool=context.broker_pool,
            order_manager=context.order_manager
        )
        self._condition_checker = ConditionChecker(bot)
        self._signal_handler = SignalHandler(bot, self._order_handler)
        
        logger.debug(f"BotRunner created for bot {bot.id} ({bot.name})")
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def bot_id(self) -> str:
        """Get the bot's unique identifier."""
        return self._bot.id
    
    @property
    def bot(self) -> Bot:
        """Get the bot domain model."""
        return self._bot
    
    @property
    def strategy(self) -> Optional[ITradingStrategy]:
        """Get the injected trading strategy."""
        return self._strategy
    
    @property
    def is_running(self) -> bool:
        """Check if the bot is currently running."""
        return self._is_running and not self._shutdown_event.is_set()
    
    @property
    def is_paused(self) -> bool:
        """Check if the bot is paused."""
        return self._is_paused
    
    @property
    def task(self) -> Optional[asyncio.Task]:
        """Get the asyncio task for this runner."""
        return self._task
    
    @task.setter
    def task(self, value: asyncio.Task) -> None:
        """Set the asyncio task for this runner."""
        self._task = value
    
    # =========================================================================
    # Lifecycle Methods
    # =========================================================================
    
    async def _initialize_strategy(self) -> None:
        """
        Initialize the trading strategy for this bot.
        
        Creates strategy via StrategyFactory if not injected via context.
        Called during start() before entering the execution loop.
        
        Services are obtained from BotRunnerContext:
        - order_manager: From context or created from broker_pool
        - market_data: From context or from market_data_hub
        - risk_manager: From context (optional)
        - position_manager: From context (optional)
        """
        if self._strategy is not None:
            logger.debug(f"Bot {self.bot_id} using injected strategy: {self._strategy.name}")
        else:
            # Create strategy via factory
            from src.strategies.strategy_factory import StrategyFactory
            
            logger.info(f"Bot {self.bot_id} creating strategy for type: {self._bot.bot_type.value}")
            
            # Get services from context (injected by BotEngineManager)
            order_manager = self._context.order_manager
            market_data = self._context.market_data
            risk_manager = self._context.risk_manager
            position_manager = self._context.position_manager
            
            # Validate required services
            if order_manager is None:
                logger.warning(
                    f"Bot {self.bot_id}: order_manager not provided in context. "
                    f"Strategy will use simulated order execution."
                )
            
            if market_data is None:
                logger.warning(
                    f"Bot {self.bot_id}: market_data not provided in context. "
                    f"Strategy will use market_data_hub for price data."
                )
            
            if risk_manager is None:
                logger.warning(
                    f"Bot {self.bot_id}: risk_manager not provided in context. "
                    f"Strategy will operate without risk management constraints."
                )
            
            # Create strategy with available services
            # StrategyFactory will raise TypeError if required services missing
            try:
                self._strategy = StrategyFactory.create(
                    bot_type=self._bot.bot_type,
                    order_manager=order_manager,
                    market_data=market_data,
                    risk_manager=risk_manager,
                    bot_config=self._bot.configuration,
                    position_manager=position_manager,
                    resilience_tracker=None
                )
            except TypeError as e:
                # Services not available - log and skip strategy creation
                logger.warning(
                    f"Bot {self.bot_id}: Cannot create strategy - missing required services: {e}. "
                    f"Bot will run in monitoring mode only."
                )
                self._strategy = None
        
        # Initialize the strategy
        if self._strategy:
            await self._strategy.initialize()
            logger.info(f"✅ Bot {self.bot_id} strategy {self._strategy.name} initialized")
    
    async def start(self) -> None:
        """
        Start the bot execution loop.
        
        This method should be called via asyncio.create_task()
        for non-blocking execution. It runs until stop() is called.
        
        Lifecycle:
        1. Initialize strategy (via factory or injected)
        2. Subscribe to market data
        3. Register for signals
        4. Enter main execution loop
        5. Cleanup on shutdown
        """
        if self._is_running:
            logger.warning(f"Bot {self.bot_id} is already running")
            return
        
        logger.info(f"Starting bot {self.bot_id} ({self._bot.name})")
        
        try:
            self._is_running = True
            self._started_at = datetime.utcnow()
            self._last_activity_at = self._started_at
            
            # Update bot state in database
            await self._update_bot_state(BotState.STARTING)
            
            # Initialize strategy (creates via factory if not injected)
            await self._initialize_strategy()
            
            # Subscribe to market data for this bot's symbol
            await self._context.market_data_hub.subscribe(
                self._bot.symbol, 
                self.bot_id
            )
            
            # Register for signals
            self._context.signal_router.register_bot(
                self.bot_id,
                {self._bot.symbol},
                self.handle_signal
            )
            
            # Update to running state
            await self._update_bot_state(BotState.RUNNING)
            
            # Determine initial operational phase
            await self._determine_initial_phase()
            
            # Run the main execution loop
            await self._run_execution_loop()
            
        except asyncio.CancelledError:
            logger.info(f"Bot {self.bot_id} execution cancelled")
            raise
        except Exception as e:
            logger.error(f"Bot {self.bot_id} execution error: {e}")
            self._error_count += 1
            self._last_error = str(e)
            await self._update_bot_state(BotState.ERROR, error_message=str(e))
            raise
        finally:
            self._is_running = False
            await self._cleanup()
    
    async def stop(self, close_positions: bool = False) -> None:
        """
        Stop the bot execution gracefully.
        
        Args:
            close_positions: Whether to close open positions before stopping
        """
        logger.info(f"Stopping bot {self.bot_id} (close_positions={close_positions})")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Update state to stopping
        await self._update_bot_state(BotState.STOPPING)
        
        # Close positions if requested
        if close_positions and self._has_position:
            await self._close_position()
        
        # Wait for task to complete (with timeout)
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"Bot {self.bot_id} did not stop within timeout, cancelling")
                self._task.cancel()
        
        # Update to stopped state
        await self._update_bot_state(BotState.STOPPED)
        logger.info(f"Bot {self.bot_id} stopped successfully")
    
    async def pause(self) -> None:
        """Pause bot execution temporarily."""
        if not self._is_running:
            logger.warning(f"Cannot pause bot {self.bot_id}: not running")
            return
        
        logger.info(f"Pausing bot {self.bot_id}")
        self._is_paused = True
        await self._update_bot_state(BotState.PAUSED)
        await self._update_operational_phase(BotOperationalPhase.IDLE)
    
    async def resume(self) -> None:
        """Resume paused bot execution."""
        if not self._is_paused:
            logger.warning(f"Cannot resume bot {self.bot_id}: not paused")
            return
        
        logger.info(f"Resuming bot {self.bot_id}")
        self._is_paused = False
        await self._update_bot_state(BotState.RUNNING)
        await self._determine_initial_phase()
    
    # =========================================================================
    # Status
    # =========================================================================
    
    def get_status(self) -> BotStatus:
        """Get current bot status."""
        return BotStatus(
            bot_id=self.bot_id,
            bot_name=self._bot.name,
            user_id=self._bot.user_id,
            is_running=self.is_running,
            operational_phase=self._bot.operational_phase.value,
            state=self._bot.state.value,
            symbol=self._bot.symbol,
            exchange=self._bot.exchange,
            bot_type=self._bot.bot_type.value,
            has_position=self._has_position,
            position_size=self._position_size,
            avg_entry_price=self._avg_entry_price,
            current_price=self._current_price,
            unrealized_pnl=self._calculate_unrealized_pnl(),
            unrealized_pnl_percent=self._calculate_unrealized_pnl_percent(),
            total_pnl=self._bot.performance.total_pnl if self._bot.performance else Decimal("0"),
            total_pnl_percent=self._bot.performance.total_pnl_percent if self._bot.performance else Decimal("0"),
            completed_deals=self._bot.completed_deals,
            current_deal_id=self._current_deal_id,
            safety_orders_used=self._safety_orders_used,
            max_safety_orders=self._get_max_safety_orders(),
            started_at=self._started_at,
            last_activity_at=self._last_activity_at,
            last_order_at=self._last_order_at,
            error_message=self._last_error,
            error_count=self._error_count,
        )
    
    # =========================================================================
    # Signal & Price Handling
    # =========================================================================
    
    async def handle_signal(self, signal: Dict[str, Any]) -> None:
        """
        Handle an incoming trading signal.
        
        Delegates to strategy.handle_signal() for strategy-specific processing.
        Falls back to legacy signal handling if no strategy is injected.
        
        Args:
            signal: Signal data from webhook or other source
        """
        if not self.is_running or self._is_paused:
            logger.debug(f"Bot {self.bot_id} ignoring signal (not active)")
            return
        
        self._last_activity_at = datetime.utcnow()
        signal_type = signal.get("action", "").lower()
        symbol = signal.get("symbol", "")
        
        logger.info(f"Bot {self.bot_id} received signal: {signal_type} for {symbol}")
        
        try:
            # Delegate to strategy if available
            if self._strategy:
                evaluation = await self._strategy.handle_signal(signal)
                if evaluation and evaluation.should_act:
                    await self._handle_strategy_evaluation(evaluation)
                return
            
            # Legacy signal handling (backwards compatibility)
            if signal_type == "buy":
                await self._handle_buy_signal(signal)
            elif signal_type == "sell":
                await self._handle_sell_signal(signal)
            elif signal_type == "close":
                await self._handle_close_signal(signal)
            else:
                logger.warning(f"Bot {self.bot_id} received unknown signal type: {signal_type}")
        except Exception as e:
            logger.error(f"Bot {self.bot_id} error handling signal: {e}")
            self._error_count += 1
            self._last_error = str(e)
    
    async def handle_price_update(self, symbol: str, price: Decimal) -> None:
        """
        Handle a market price update.
        
        Args:
            symbol: Trading symbol
            price: Current market price
        """
        if symbol != self._bot.symbol:
            return
        
        self._current_price = price
        self._last_activity_at = datetime.utcnow()
        
        # If we have a position, check for profit/loss conditions
        if self._has_position and not self._is_paused:
            await self._check_exit_conditions(price)
    
    # =========================================================================
    # Execution Loop
    # =========================================================================
    
    async def _run_execution_loop(self) -> None:
        """
        Main execution loop for the bot.
        
        Runs until shutdown is signaled. The loop:
        1. Delegates to strategy.execute_tick() for strategy-specific logic
        2. Handles strategy evaluations (entry, exit, DCA decisions)
        3. Maintains operational phase state
        
        Strategy Pattern:
        - BotRunner is strategy-agnostic
        - All trading logic is in ITradingStrategy.execute_tick()
        - BotRunner only handles lifecycle and coordination
        """
        loop_interval = 0.1  # 100ms tick
        
        while not self._shutdown_event.is_set():
            try:
                if self._is_paused:
                    await asyncio.sleep(loop_interval)
                    continue
                
                # Delegate to strategy for execution
                if self._strategy:
                    current_price = float(self._current_price) if self._current_price else 0.0
                    
                    # Execute strategy tick
                    evaluation = await self._strategy.execute_tick(
                        current_price=current_price,
                        market_context={
                            'symbol': self._bot.symbol,
                            'has_position': self._has_position,
                            'operational_phase': self._bot.operational_phase.value
                        }
                    )
                    
                    # Handle strategy evaluation if action needed
                    if evaluation and evaluation.should_act:
                        await self._handle_strategy_evaluation(evaluation)
                else:
                    # Fallback to legacy execution if no strategy (backwards compatibility)
                    await self._execute_legacy_tick()
                
                # Wait for next tick or shutdown
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=loop_interval
                    )
                    break  # Shutdown signaled
                except asyncio.TimeoutError:
                    continue  # Continue loop
                    
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Bot {self.bot_id} tick error: {e}")
                self._error_count += 1
                await asyncio.sleep(1.0)  # Brief pause on error
    
    async def _handle_strategy_evaluation(self, evaluation) -> None:
        """
        Handle a strategy evaluation result.
        
        Converts strategy decisions into actions (orders, phase changes).
        
        Args:
            evaluation: StrategyEvaluation from strategy
        """
        action = evaluation.action_type
        
        logger.info(
            f"Bot {self.bot_id} handling strategy evaluation: "
            f"{action} (confidence={evaluation.confidence:.2f})"
        )
        
        if action == "entry":
            await self._update_operational_phase(BotOperationalPhase.ENTERING_POSITION)
            await self._place_base_order()
            
        elif action == "exit":
            exit_type = evaluation.metadata.get('exit_type', 'unknown')
            if exit_type == 'trailing_stop':
                await self._update_operational_phase(BotOperationalPhase.STOPPING_LOSS)
            else:
                await self._update_operational_phase(BotOperationalPhase.TAKING_PROFIT)
            await self._execute_take_profit()
            
        elif action == "dca":
            await self._update_operational_phase(BotOperationalPhase.AVERAGING_DOWN)
            await self._place_safety_order()
            
        elif action == "close":
            await self._close_position()
            
        elif action in ("skip", "hold"):
            # No action needed
            pass
    
    async def _execute_legacy_tick(self) -> None:
        """
        Legacy tick execution for backwards compatibility.
        
        Used when no strategy is injected. This preserves the original
        embedded logic during migration period.
        
        .. deprecated:: 2.1.0
            This method will be removed in v3.0.0. All bots should use
            ITradingStrategy injection via StrategyFactory.
            
        TODO: Remove this once all bots use injected strategies.
        """
        import warnings
        warnings.warn(
            "Legacy tick execution is deprecated. Use ITradingStrategy injection "
            "via StrategyFactory instead. Will be removed in v3.0.0.",
            DeprecationWarning,
            stacklevel=2
        )
        
        # Execute strategy-specific logic based on bot type
        if self._bot.bot_type == BotType.DCA:
            await self._execute_dca_tick()
        elif self._bot.bot_type == BotType.GRID:
            await self._execute_grid_tick()
        elif self._bot.bot_type == BotType.SPOT_LOOP:
            await self._execute_loop_tick()
        else:
            await self._execute_generic_tick()
    
    # =========================================================================
    # Legacy Strategy Execution (Backwards Compatibility)
    # DEPRECATED: Will be removed in v3.0.0
    # All bots should use ITradingStrategy injection via StrategyFactory
    # =========================================================================
    
    async def _execute_dca_tick(self) -> None:
        """
        Execute one tick of DCA strategy logic.
        
        .. deprecated:: 2.1.0
            Use DCAStrategy with ITradingStrategy interface instead.
        """
        phase = self._bot.operational_phase
        
        if phase == BotOperationalPhase.WAITING_FOR_SIGNAL:
            # Check if entry conditions are met
            if await self._check_dca_entry_conditions():
                await self._update_operational_phase(BotOperationalPhase.SIGNAL_MATCHED)
        
        elif phase == BotOperationalPhase.SIGNAL_MATCHED:
            # Place base order
            await self._update_operational_phase(BotOperationalPhase.ENTERING_POSITION)
            await self._place_base_order()
        
        elif phase == BotOperationalPhase.IN_POSITION:
            # Monitor position for safety orders and exit conditions
            await self._monitor_dca_position()
        
        elif phase == BotOperationalPhase.AVERAGING_DOWN:
            # Wait for safety order to fill
            pass
        
        elif phase in (BotOperationalPhase.TAKING_PROFIT, BotOperationalPhase.STOPPING_LOSS):
            # Wait for exit order to fill
            pass
        
        elif phase == BotOperationalPhase.POSITION_CLOSED:
            # Start new deal cycle
            await self._start_new_deal()
    
    async def _check_dca_entry_conditions(self) -> bool:
        """
        Check if DCA entry conditions are met.
        
        Returns:
            True if conditions are met and should enter position
        """
        dca_config = self._bot.configuration.dca_config
        if not dca_config:
            return False
        
        # First check risk management limits
        if not await self._check_risk_management_limits():
            return False
        
        start_condition = dca_config.start_settings.start_condition
        
        if start_condition == "immediately":
            return True
        
        elif start_condition == "on_signal":
            # Check indicator conditions
            return await self._check_indicator_conditions()
        
        elif start_condition == "tradingview_webhook":
            # Wait for webhook signal (handled by handle_signal)
            return False
        
        elif start_condition == "on_price":
            return await self._check_price_conditions()
        
        return False
    
    async def _check_risk_management_limits(self) -> bool:
        """
        Check if risk management limits allow entry.
        
        Validates:
        - max_deals: Maximum concurrent deals
        - max_price/min_price: Price boundaries
        - target_total_profit: Cumulative profit target
        - allowed_total_loss: Cumulative loss limit
        - pump_dump_protection: Market volatility check
        
        Returns:
            True if all risk checks pass, False if any limit is breached
        """
        dca_config = self._bot.configuration.dca_config
        if not dca_config:
            return True  # No config means no restrictions
        
        risk_mgmt = dca_config.risk_management
        
        # Check max deals limit
        if risk_mgmt.max_deals > 0 and self._active_deals_count >= risk_mgmt.max_deals:
            logger.warning(
                f"Bot {self.bot_id}: Max deals limit reached ({self._active_deals_count}/{risk_mgmt.max_deals})"
            )
            return False
        
        # Check price boundaries
        if self._current_price:
            # Max price check
            if risk_mgmt.max_price_enabled and risk_mgmt.max_price:
                if self._current_price > risk_mgmt.max_price:
                    logger.warning(
                        f"Bot {self.bot_id}: Price ${self._current_price:.2f} exceeds max price ${risk_mgmt.max_price:.2f}"
                    )
                    return False
            
            # Min price check
            if risk_mgmt.min_price_enabled and risk_mgmt.min_price:
                if self._current_price < risk_mgmt.min_price:
                    logger.warning(
                        f"Bot {self.bot_id}: Price ${self._current_price:.2f} below min price ${risk_mgmt.min_price:.2f}"
                    )
                    return False
        
        # Check cumulative profit target (stop trading if target reached)
        if risk_mgmt.target_total_profit_enabled:
            if risk_mgmt.target_total_profit_amount and self._cumulative_profit >= risk_mgmt.target_total_profit_amount:
                logger.info(
                    f"Bot {self.bot_id}: Target profit reached! ${self._cumulative_profit:.2f} >= ${risk_mgmt.target_total_profit_amount:.2f}"
                )
                return False
            if risk_mgmt.target_total_profit_percent:
                # Calculate percent based on initial capital if available
                # For now, just use cumulative profit check
                pass
        
        # Check cumulative loss limit (stop trading if limit reached)
        if risk_mgmt.allowed_total_loss_enabled:
            if risk_mgmt.allowed_total_loss_amount and self._cumulative_loss >= risk_mgmt.allowed_total_loss_amount:
                logger.warning(
                    f"Bot {self.bot_id}: Max loss limit reached! ${self._cumulative_loss:.2f} >= ${risk_mgmt.allowed_total_loss_amount:.2f}"
                )
                return False
        
        # Pump/dump protection check
        if risk_mgmt.pump_dump_protection:
            if not await self._check_pump_dump_protection():
                return False
        
        return True
    
    async def _check_pump_dump_protection(self) -> bool:
        """
        Check for pump and dump market conditions.
        
        Detects abnormal price movements that may indicate market manipulation.
        Protects against entering during high volatility.
        
        Returns:
            True if market is safe, False if pump/dump detected
        """
        # Get recent price change from market data hub
        try:
            market_data = await self._context.market_data_hub.get_market_data(self._bot.symbol)
            if not market_data:
                return True  # Allow if no data available
            
            # Check for extreme price changes (>10% in short period is suspicious)
            price_change_1h = market_data.get("price_change_1h", 0)
            if abs(price_change_1h) > 10:
                logger.warning(
                    f"Bot {self.bot_id}: Pump/dump protection triggered! "
                    f"1h price change: {price_change_1h:.2f}%"
                )
                return False
            
            return True
        except Exception as e:
            logger.debug(f"Bot {self.bot_id}: Pump/dump check failed: {e}")
            return True  # Allow on error (fail open)
    
    async def _check_indicator_conditions(self) -> bool:
        """Check if indicator conditions are met for entry."""
        # TODO: Implement indicator checking via market data hub
        # For now, return False to wait for signals
        return False
    
    async def _check_price_conditions(self) -> bool:
        """Check if price conditions are met for entry."""
        dca_config = self._bot.configuration.dca_config
        if not dca_config or not dca_config.start_settings.price_condition:
            return False
        
        price_condition = dca_config.start_settings.price_condition
        if not self._current_price:
            return False
        
        target_price = Decimal(str(price_condition.get("price", 0)))
        operator = price_condition.get("operator", "")
        
        if operator == "above":
            return self._current_price > target_price
        elif operator == "below":
            return self._current_price < target_price
        
        return False
    
    async def _monitor_dca_position(self) -> None:
        """Monitor DCA position for safety orders and exits."""
        if not self._current_price or not self._avg_entry_price:
            return
        
        # Check take profit
        if await self._should_take_profit():
            await self._update_operational_phase(BotOperationalPhase.TAKING_PROFIT)
            await self._execute_take_profit()
            return
        
        # Check stop loss
        if await self._should_stop_loss():
            await self._update_operational_phase(BotOperationalPhase.STOPPING_LOSS)
            await self._execute_stop_loss()
            return
        
        # Check for safety order conditions
        if await self._should_place_safety_order():
            await self._update_operational_phase(BotOperationalPhase.AVERAGING_DOWN)
            await self._place_safety_order()
    
    # =========================================================================
    # Strategy Execution (Grid/Loop - Placeholder)
    # =========================================================================
    
    async def _execute_grid_tick(self) -> None:
        """Execute one tick of Grid strategy logic."""
        phase = self._bot.operational_phase
        
        if phase == BotOperationalPhase.PRICE_OUT_OF_RANGE:
            # Check if price returned to grid range
            if self._check_price_in_grid_range():
                await self._update_operational_phase(BotOperationalPhase.PRICE_IN_RANGE)
        
        elif phase == BotOperationalPhase.PRICE_IN_RANGE:
            # Execute grid trading logic
            await self._manage_grid_orders()
    
    async def _execute_loop_tick(self) -> None:
        """Execute one tick of Spot Loop strategy logic."""
        # Similar to grid but for sideways markets
        await self._execute_grid_tick()
    
    async def _execute_generic_tick(self) -> None:
        """Execute one tick of generic strategy logic."""
        # Fallback for unsupported bot types
        pass
    
    # =========================================================================
    # Order Execution
    # =========================================================================
    
    async def _place_base_order(self) -> None:
        """Place the base order to enter position."""
        dca_config = self._bot.configuration.dca_config
        if not dca_config:
            return
        
        # Start new deal
        self._current_deal_id = str(uuid.uuid4())
        self._deal_start_time = datetime.utcnow()
        self._active_deals_count += 1
        
        base_amount = Decimal(str(dca_config.start_settings.base_order_amount))
        order_type = dca_config.start_settings.base_order_type
        
        logger.info(
            f"Bot {self.bot_id} placing base order: "
            f"{base_amount} {self._bot.symbol} ({order_type})"
        )
        
        # Delegate to OrderHandler for actual execution
        success = await self._order_handler.place_base_order(
            current_price=self._current_price or Decimal("0"),
            on_phase_update=self._update_operational_phase,
            on_persist=self._persist_state,
        )
        
        if success:
            # Sync state from OrderHandler
            state = self._order_handler.sync_to_runner()
            self._has_position = state["has_position"]
            self._position_size = state["position_size"]
            self._avg_entry_price = state["avg_entry_price"]
            self._base_order_price = state["base_order_price"]
            self._safety_orders_used = state["safety_orders_used"]
            self._last_order_at = state["last_order_at"]
            self._current_deal_id = state["current_deal_id"]
            self._deal_start_time = state["deal_start_time"]
            self._active_deals_count = state["active_deals_count"]
    
    async def _place_safety_order(self) -> None:
        """Place a safety order (DCA)."""
        logger.info(f"Bot {self.bot_id} placing safety order #{self._safety_orders_used + 1}")
        
        # Sync current state to OrderHandler before execution
        self._order_handler.sync_from_runner(
            has_position=self._has_position,
            position_size=self._position_size,
            avg_entry_price=self._avg_entry_price,
            base_order_price=self._base_order_price,
            safety_orders_used=self._safety_orders_used,
        )
        
        # Delegate to OrderHandler for actual execution
        success = await self._order_handler.place_safety_order(
            current_price=self._current_price or Decimal("0"),
            on_phase_update=self._update_operational_phase,
            on_persist=self._persist_state,
        )
        
        if success:
            # Sync state back from OrderHandler
            state = self._order_handler.sync_to_runner()
            self._safety_orders_used = state["safety_orders_used"]
            self._last_order_at = state["last_order_at"]
            self._position_size = state["position_size"]
            self._avg_entry_price = state["avg_entry_price"]
    
    async def _execute_take_profit(self) -> None:
        """Execute take profit order."""
        logger.info(f"Bot {self.bot_id} executing take profit")
        
        # Sync current state to OrderHandler
        self._order_handler.sync_from_runner(
            has_position=self._has_position,
            position_size=self._position_size,
            avg_entry_price=self._avg_entry_price,
            base_order_price=self._base_order_price,
            safety_orders_used=self._safety_orders_used,
        )
        
        # Delegate to OrderHandler for actual execution
        await self._order_handler.execute_take_profit(
            on_phase_update=self._update_operational_phase,
            on_persist=self._persist_state,
        )
        
        # Sync state back from OrderHandler
        state = self._order_handler.sync_to_runner()
        self._has_position = state["has_position"]
        self._position_size = state["position_size"]
        self._avg_entry_price = state["avg_entry_price"]
        self._last_order_at = state["last_order_at"]
    
    async def _execute_stop_loss(self) -> None:
        """Execute stop loss order."""
        logger.info(f"Bot {self.bot_id} executing stop loss")
        
        # Sync current state to OrderHandler
        self._order_handler.sync_from_runner(
            has_position=self._has_position,
            position_size=self._position_size,
            avg_entry_price=self._avg_entry_price,
            base_order_price=self._base_order_price,
            safety_orders_used=self._safety_orders_used,
        )
        
        # Delegate to OrderHandler for actual execution
        await self._order_handler.execute_stop_loss(
            on_phase_update=self._update_operational_phase,
            on_persist=self._persist_state,
        )
        
        # Sync state back from OrderHandler
        state = self._order_handler.sync_to_runner()
        self._has_position = state["has_position"]
        self._position_size = state["position_size"]
        self._avg_entry_price = state["avg_entry_price"]
        self._last_order_at = state["last_order_at"]
    
    async def _close_position(self) -> None:
        """Close the current position."""
        if not self._has_position:
            return
        
        logger.info(f"Bot {self.bot_id} closing position")
        
        # Sync current state to OrderHandler
        self._order_handler.sync_from_runner(
            has_position=self._has_position,
            position_size=self._position_size,
            avg_entry_price=self._avg_entry_price,
            base_order_price=self._base_order_price,
            safety_orders_used=self._safety_orders_used,
        )
        
        # Delegate to OrderHandler for actual execution
        await self._order_handler.close_position(
            on_phase_update=self._update_operational_phase,
            on_persist=self._persist_state,
        )
        
        # Sync state back from OrderHandler
        state = self._order_handler.sync_to_runner()
        self._has_position = state["has_position"]
        self._position_size = state["position_size"]
        self._avg_entry_price = state["avg_entry_price"]
    
    # =========================================================================
    # Signal Handlers
    # =========================================================================
    
    async def _handle_buy_signal(self, signal: Dict[str, Any]) -> None:
        """Handle buy signal."""
        start_condition = self._bot.configuration.dca_config.start_settings.start_condition
        
        if start_condition == "tradingview_webhook":
            if self._bot.operational_phase == BotOperationalPhase.WAITING_FOR_WEBHOOK:
                await self._update_operational_phase(BotOperationalPhase.WEBHOOK_RECEIVED)
                await self._update_operational_phase(BotOperationalPhase.ENTERING_POSITION)
                await self._place_base_order()
    
    async def _handle_sell_signal(self, signal: Dict[str, Any]) -> None:
        """Handle sell signal."""
        if self._has_position:
            await self._execute_take_profit()
    
    async def _handle_close_signal(self, signal: Dict[str, Any]) -> None:
        """Handle close signal."""
        await self._close_position()
    
    # =========================================================================
    # Condition Checks
    # =========================================================================
    
    async def _should_take_profit(self) -> bool:
        """
        Check if take profit conditions are met.
        
        Uses price_reference setting to determine whether to calculate
        profit from average entry price or base order price.
        """
        dca_config = self._bot.configuration.dca_config
        if not dca_config or not dca_config.take_profit.enabled:
            return False
        
        if not self._current_price:
            return False
        
        # Determine reference price based on configuration
        reference_price = self._get_take_profit_reference_price()
        if not reference_price:
            return False
        
        tp_percent = Decimal(str(dca_config.take_profit.price_change_percent))
        current_pnl_percent = (
            (self._current_price - reference_price) / reference_price * 100
        )
        
        return current_pnl_percent >= tp_percent
    
    def _get_take_profit_reference_price(self) -> Optional[Decimal]:
        """
        Get the reference price for take profit calculation based on price_reference setting.
        
        Returns:
            Reference price (average entry or base order price) or None if not available
        """
        dca_config = self._bot.configuration.dca_config
        if not dca_config or not dca_config.take_profit:
            return self._avg_entry_price
        
        price_reference = dca_config.take_profit.price_reference
        
        if price_reference == PriceReference.BASE_ORDER_PRICE:
            # Use base order price if available, fallback to average
            if self._base_order_price:
                return self._base_order_price
            logger.debug(
                f"Bot {self.bot_id}: Base order price not set, falling back to average entry"
            )
            return self._avg_entry_price
        
        elif price_reference == PriceReference.BASE_ORDER_PRICE_INDICATORS:
            # Base order price + indicator signals (indicators not implemented yet)
            if self._base_order_price:
                return self._base_order_price
            return self._avg_entry_price
        
        elif price_reference == PriceReference.AVERAGE_PRICE_INDICATORS:
            # Average price + indicator signals (indicators not implemented yet)
            return self._avg_entry_price
        
        # Default: AVERAGE_PRICE
        return self._avg_entry_price
    
    async def _should_stop_loss(self) -> bool:
        """
        Check if stop loss conditions are met.
        
        Supports both fixed and trailing stop loss:
        - Fixed: Triggers when price drops below entry by stop_loss.percent
        - Trailing: Follows price up, triggers when price drops by trailing_deviation_percent from peak
        """
        dca_config = self._bot.configuration.dca_config
        if not dca_config or not dca_config.stop_loss.enabled:
            return False
        
        if not self._current_price or not self._avg_entry_price:
            return False
        
        stop_loss_config = dca_config.stop_loss
        
        # Check for trailing stop loss
        if stop_loss_config.trailing_enabled and stop_loss_config.trailing_deviation_percent:
            return await self._check_trailing_stop_loss()
        
        # Fixed stop loss check
        sl_percent = Decimal(str(stop_loss_config.percent))
        current_pnl_percent = (
            (self._current_price - self._avg_entry_price) / self._avg_entry_price * 100
        )
        
        return current_pnl_percent <= -sl_percent
    
    async def _check_trailing_stop_loss(self) -> bool:
        """
        Check if trailing stop loss should trigger.
        
        Trailing stop loss tracks the highest price and triggers when price
        drops by trailing_deviation_percent from that peak.
        
        Returns:
            True if trailing stop should trigger, False otherwise
        """
        dca_config = self._bot.configuration.dca_config
        if not dca_config or not dca_config.stop_loss.trailing_deviation_percent:
            return False
        
        if not self._current_price:
            return False
        
        trailing_deviation = Decimal(str(dca_config.stop_loss.trailing_deviation_percent))
        
        # Initialize peak price if not set
        if self._peak_price is None:
            self._peak_price = self._current_price
            self._trailing_stop_price = self._current_price * (1 - trailing_deviation / 100)
            return False
        
        # Update peak price if we have a new high
        if self._current_price > self._peak_price:
            self._peak_price = self._current_price
            # Update trailing stop level
            self._trailing_stop_price = self._peak_price * (1 - trailing_deviation / 100)
            logger.debug(
                f"Bot {self.bot_id}: New peak ${self._peak_price:.2f}, "
                f"trailing stop at ${self._trailing_stop_price:.2f}"
            )
        
        # Check if current price has hit the trailing stop
        if self._trailing_stop_price and self._current_price <= self._trailing_stop_price:
            logger.info(
                f"🛑 Bot {self.bot_id}: Trailing stop loss triggered! "
                f"Peak: ${self._peak_price:.2f}, Current: ${self._current_price:.2f}, "
                f"Stop: ${self._trailing_stop_price:.2f}"
            )
            return True
        
        return False
    
    async def _should_place_safety_order(self) -> bool:
        """Check if safety order conditions are met."""
        dca_config = self._bot.configuration.dca_config
        if not dca_config:
            return False
        
        max_orders = dca_config.averaging_orders.orders_count
        if self._safety_orders_used >= max_orders:
            return False
        
        if not self._current_price or not self._avg_entry_price:
            return False
        
        # Check if price has dropped enough for next safety order
        step_percent = Decimal(str(dca_config.averaging_orders.step_percent))
        price_drop_percent = (
            (self._avg_entry_price - self._current_price) / self._avg_entry_price * 100
        )
        
        required_drop = step_percent * (self._safety_orders_used + 1)
        return price_drop_percent >= required_drop
    
    def _check_price_in_grid_range(self) -> bool:
        """Check if price is within grid range."""
        if not self._current_price:
            return False
        
        lower = self._bot.grid_lower_bound
        upper = self._bot.grid_upper_bound
        
        if lower and upper:
            return lower <= self._current_price <= upper
        
        return True
    
    async def _manage_grid_orders(self) -> None:
        """
        Manage grid orders for grid trading strategy.
        
        Raises:
            NotImplementedError: Grid trading is not yet implemented.
            
        Note:
            Grid trading requires a dedicated GridStrategy implementation.
            See: https://github.com/alpha-trader/alpha-trader/issues/XXX
        """
        raise NotImplementedError(
            "Grid trading strategy is not yet implemented. "
            "Use DCA or Combo bot types for now."
        )
    
    # =========================================================================
    # State Management
    # =========================================================================
    
    async def _determine_initial_phase(self) -> None:
        """Determine the initial operational phase based on bot state."""
        dca_config = self._bot.configuration.dca_config
        
        if self._has_position:
            await self._update_operational_phase(BotOperationalPhase.IN_POSITION)
        elif dca_config:
            start_condition = dca_config.start_settings.start_condition
            if start_condition == "immediately":
                await self._update_operational_phase(BotOperationalPhase.SIGNAL_MATCHED)
            elif start_condition == "tradingview_webhook":
                await self._update_operational_phase(BotOperationalPhase.WAITING_FOR_WEBHOOK)
            else:
                await self._update_operational_phase(BotOperationalPhase.WAITING_FOR_SIGNAL)
        else:
            await self._update_operational_phase(BotOperationalPhase.IDLE)
    
    async def _start_new_deal(self) -> None:
        """
        Start a new deal/cycle after completing previous one.
        
        If reinvest profit is enabled, calculates the profit from the completed deal
        and allocates it proportionally between base order and DCA orders based on
        their share of total investment.
        """
        # Track cumulative P&L from completed deal
        deal_pnl = self._calculate_unrealized_pnl()
        if deal_pnl is not None:
            if deal_pnl >= 0:
                self._cumulative_profit += deal_pnl
                # Apply reinvest profit if enabled and deal was profitable
                await self._apply_reinvest_profit(deal_pnl)
            else:
                self._cumulative_loss += abs(deal_pnl)
        
        self._bot.completed_deals += 1
        self._current_deal_id = None
        self._deal_start_time = None
        self._safety_orders_used = 0
        self._active_deals_count = max(0, self._active_deals_count - 1)
        
        # Reset trailing stop loss tracking for new deal
        self._peak_price = None
        self._trailing_stop_price = None
        
        # Reset base order price for new deal
        self._base_order_price = None
        
        # Check if should continue or wait for cooldown
        dca_config = self._bot.configuration.dca_config
        if dca_config and dca_config.risk_management.cooldown_period:
            self._bot.cooldown_until = datetime.utcnow()
            await self._update_operational_phase(BotOperationalPhase.IN_COOLDOWN)
        else:
            await self._determine_initial_phase()
        
        await self._persist_state()
    
    async def _apply_reinvest_profit(self, realized_profit: "Decimal") -> None:
        """
        Apply reinvest profit settings to increase base and DCA order sizes.
        
        Calculates the precise allocation based on the ratio of base order
        to DCA orders in the original configuration. This ensures proportional
        reinvestment that maintains the intended DCA structure.
        
        Args:
            realized_profit: The realized profit from the completed deal
        """
        from decimal import Decimal
        
        dca_config = self._bot.configuration.dca_config
        if not dca_config or not dca_config.risk_management:
            return
        
        risk_mgmt = dca_config.risk_management
        if not risk_mgmt.reinvest_profit_enabled:
            return
        
        if realized_profit <= Decimal("0"):
            return
        
        # Get current order amounts
        base_order_amount = dca_config.start_settings.base_order_amount
        dca_total_amount = dca_config.averaging_orders.total_amount
        
        # Calculate reinvest allocation
        base_addition, dca_addition = risk_mgmt.calculate_reinvest_allocation(
            realized_profit=realized_profit,
            base_order_amount=base_order_amount,
            dca_total_amount=dca_total_amount,
        )
        
        if base_addition > 0 or dca_addition > 0:
            # Update the configuration
            dca_config.start_settings.base_order_amount = base_order_amount + base_addition
            dca_config.averaging_orders.total_amount = dca_total_amount + dca_addition
            
            logger.info(
                f"Bot {self.bot_id} reinvesting profit: "
                f"${realized_profit:.2f} * {risk_mgmt.reinvest_profit_percent}% = "
                f"base order +${base_addition:.2f} (now ${dca_config.start_settings.base_order_amount:.2f}), "
                f"DCA orders +${dca_addition:.2f} (now ${dca_config.averaging_orders.total_amount:.2f})"
            )
            
            # Persist the updated configuration
            await self._persist_state()
    
    async def _update_bot_state(
        self, 
        state: BotState, 
        error_message: Optional[str] = None
    ) -> None:
        """Update bot lifecycle state."""
        self._bot.state = state
        if error_message:
            self._bot.error_message = error_message
        await self._persist_state()
    
    async def _update_operational_phase(self, phase: BotOperationalPhase) -> None:
        """Update bot operational phase."""
        old_phase = self._bot.operational_phase
        self._bot.operational_phase = phase
        logger.debug(f"Bot {self.bot_id} phase: {old_phase.value} -> {phase.value}")
        await self._persist_state()
    
    async def _persist_state(self) -> None:
        """Persist current bot state to database."""
        try:
            # Update timestamps
            self._bot.last_activity_at = self._last_activity_at
            self._bot.last_order_at = self._last_order_at
            self._bot.current_deal_id = self._current_deal_id
            
            # Persist via repository
            await self._context.bot_repository.update(self._bot)
        except Exception as e:
            logger.error(f"Bot {self.bot_id} failed to persist state: {e}")
    
    async def _cleanup(self) -> None:
        """Cleanup resources on shutdown."""
        try:
            # Close strategy if initialized
            if self._strategy:
                await self._strategy.close()
                logger.debug(f"Bot {self.bot_id} strategy closed")
            
            # Unsubscribe from market data
            await self._context.market_data_hub.unsubscribe(
                self._bot.symbol, 
                self.bot_id
            )
            
            # Unregister from signals
            self._context.signal_router.unregister_bot(self.bot_id)
            
            logger.debug(f"Bot {self.bot_id} cleanup completed")
        except Exception as e:
            logger.error(f"Bot {self.bot_id} cleanup error: {e}")
    
    # =========================================================================
    # Calculations
    # =========================================================================
    
    def _calculate_unrealized_pnl(self) -> Optional[Decimal]:
        """Calculate unrealized P&L."""
        if not self._has_position or not self._position_size or not self._current_price or not self._avg_entry_price:
            return None
        
        return (self._current_price - self._avg_entry_price) * self._position_size
    
    def _calculate_unrealized_pnl_percent(self) -> Optional[Decimal]:
        """Calculate unrealized P&L percentage."""
        if not self._current_price or not self._avg_entry_price:
            return None
        
        return (self._current_price - self._avg_entry_price) / self._avg_entry_price * 100
    
    def _get_max_safety_orders(self) -> int:
        """Get maximum number of safety orders from config."""
        dca_config = self._bot.configuration.dca_config
        if dca_config:
            return dca_config.averaging_orders.orders_count
        return 0
