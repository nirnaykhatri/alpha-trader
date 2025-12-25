"""
Bot Engine Manager - Central Orchestrator for Multi-Bot Execution.

The BotEngineManager is responsible for:
- Managing the lifecycle of all running bots
- Coordinating shared resources
- Enforcing capacity limits
- Providing real-time status for all bots

This is the single point of entry for the multi-bot architecture.

Author: Trading Bot Team
Version: 1.1.0 (Added trading service injection)
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
import uuid

from src.core.logging_config import get_logger
from src.domain.bot_models import Bot, BotState, BotOperationalPhase
from src.bot_engine.interfaces import (
    IBotEngineManager,
    IBotRunner,
    IMarketDataHub,
    ISignalRouter,
    IBrokerConnectionPool,
    BotEngineConfig,
    BotStatus,
)
from src.bot_engine.exceptions import (
    BotEngineException,
    BotAlreadyRunningError,
    BotNotRunningError,
    BotNotFoundError,
    ResourceLimitError,
    BotStartupError,
    BotShutdownError,
)
from src.bot_engine.bot_runner import BotRunner, BotRunnerContext

if TYPE_CHECKING:
    from src.database.database_interface import IBotRepository
    from src.interfaces import IOrderManager, IMarketDataProvider, IRiskManager, IPositionManager

logger = get_logger(__name__)


class BotEngineManager(IBotEngineManager):
    """
    Central orchestrator managing all running bot instances.
    
    The BotEngineManager implements a single-process, multi-bot async
    architecture optimized for hundreds of concurrent bots with
    minimal resource overhead (~10KB per bot).
    
    Key Features:
    - Efficient resource sharing via shared hubs and pools
    - Capacity limits enforcement (per-user, per-symbol, total)
    - Real-time status tracking for all bots
    - Graceful shutdown with optional position closing
    
    Resource Sharing Model:
    - All bots share a single MarketDataHub (symbol-deduplicated streams)
    - All bots share a single SignalRouter (efficient webhook routing)
    - All bots share broker connection pools (connection reuse)
    
    Thread Safety:
    - All operations are async and run in a single event loop
    - State mutations are atomic within coroutines
    - No explicit locking required
    
    Usage:
        manager = BotEngineManager(config, ...)
        await manager.start_engine()
        
        bot_id = await manager.start_bot(bot_model)
        status = manager.get_bot_status(bot_id)
        
        await manager.stop_bot(bot_id)
        await manager.shutdown()
    
    Capacity Limits (configurable):
    - max_concurrent_bots: 500 (total across all users)
    - max_bots_per_user: 100 (per user)
    - max_bots_per_symbol: 50 (per trading pair)
    """
    
    def __init__(
        self,
        config: BotEngineConfig,
        market_data_hub: IMarketDataHub,
        signal_router: ISignalRouter,
        broker_pool: IBrokerConnectionPool,
        bot_repository: "IBotRepository",
        order_manager: Optional["IOrderManager"] = None,
        market_data: Optional["IMarketDataProvider"] = None,
        risk_manager: Optional["IRiskManager"] = None,
        position_manager: Optional["IPositionManager"] = None,
    ):
        """
        Initialize the bot engine manager.
        
        Args:
            config: Engine configuration with capacity limits
            market_data_hub: Shared market data streaming hub
            signal_router: Webhook signal routing service
            broker_pool: Shared broker connection pool
            bot_repository: Database repository for bots
            order_manager: Optional shared order manager for trade execution
            market_data: Optional shared market data provider
            risk_manager: Optional shared risk management service
            position_manager: Optional shared position manager
            
        Note:
            Trading services (order_manager, market_data, risk_manager, position_manager)
            are optional during initialization. When provided, they are shared across
            all bot runners. This enables production trading execution. When not provided,
            bots will run in monitoring/simulation mode.
        """
        self._config = config
        self._market_data_hub = market_data_hub
        self._signal_router = signal_router
        self._broker_pool = broker_pool
        self._bot_repository = bot_repository
        
        # Trading services (shared across all bot runners)
        self._order_manager = order_manager
        self._market_data = market_data
        self._risk_manager = risk_manager
        self._position_manager = position_manager
        
        # Running bots storage: bot_id -> BotRunner
        self._running_bots: Dict[str, BotRunner] = {}
        
        # User bot counts for limit enforcement
        self._user_bot_counts: Dict[str, int] = {}
        
        # Symbol bot counts for limit enforcement
        self._symbol_bot_counts: Dict[str, int] = {}
        
        # Engine state
        self._is_running = False
        self._started_at: Optional[datetime] = None
        
        # Background tasks
        self._health_check_task: Optional[asyncio.Task] = None
        self._state_persist_task: Optional[asyncio.Task] = None
        
        # Log trading services status
        trading_services_status = (
            f"order_manager={'✅' if order_manager else '❌'}, "
            f"market_data={'✅' if market_data else '❌'}, "
            f"risk_manager={'✅' if risk_manager else '❌'}, "
            f"position_manager={'✅' if position_manager else '❌'}"
        )
        
        logger.info(
            f"BotEngineManager initialized with config: "
            f"max_bots={config.max_concurrent_bots}, "
            f"max_per_user={config.max_bots_per_user}, "
            f"max_per_symbol={config.max_bots_per_symbol}, "
            f"trading_services=[{trading_services_status}]"
        )
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def is_running(self) -> bool:
        """Check if the engine is running."""
        return self._is_running
    
    @property
    def running_bot_count(self) -> int:
        """Get the number of currently running bots."""
        return len(self._running_bots)
    
    @property
    def config(self) -> BotEngineConfig:
        """Get the engine configuration."""
        return self._config
    
    # =========================================================================
    # Engine Lifecycle
    # =========================================================================
    
    async def start_engine(self) -> None:
        """
        Start the bot engine.
        
        This initializes all shared resources and starts background tasks.
        Should be called once during application startup.
        """
        if self._is_running:
            logger.warning("BotEngineManager is already running")
            return
        
        logger.info("Starting BotEngineManager...")
        
        try:
            # Start shared resources
            await self._market_data_hub.start()
            await self._signal_router.start()
            await self._broker_pool.start()
            
            # Start background tasks
            self._health_check_task = asyncio.create_task(
                self._health_check_loop(),
                name="bot_engine_health_check"
            )
            
            self._state_persist_task = asyncio.create_task(
                self._state_persist_loop(),
                name="bot_engine_state_persist"
            )
            
            self._is_running = True
            self._started_at = datetime.utcnow()
            
            logger.info("BotEngineManager started successfully")
            
            # Restore previously running bots
            await self._restore_running_bots()
            
        except Exception as e:
            logger.error(f"Failed to start BotEngineManager: {e}")
            await self._cleanup_on_error()
            raise BotStartupError(f"Engine startup failed: {e}")
    
    async def shutdown(self, close_all_positions: bool = False) -> None:
        """
        Shutdown the bot engine gracefully.
        
        Args:
            close_all_positions: Whether to close all positions before shutdown
        """
        if not self._is_running:
            logger.warning("BotEngineManager is not running")
            return
        
        logger.info(
            f"Shutting down BotEngineManager "
            f"(close_positions={close_all_positions}, "
            f"bots={len(self._running_bots)})"
        )
        
        # Stop all running bots
        stop_tasks = [
            self.stop_bot(bot_id, close_position=close_all_positions)
            for bot_id in list(self._running_bots.keys())
        ]
        
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)
        
        # Cancel background tasks
        for task in [self._health_check_task, self._state_persist_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Stop shared resources
        await self._market_data_hub.stop()
        await self._signal_router.stop()
        await self._broker_pool.stop()
        
        self._is_running = False
        logger.info("BotEngineManager shutdown complete")
    
    # =========================================================================
    # Bot Lifecycle Management
    # =========================================================================
    
    async def start_bot(self, bot: Bot) -> str:
        """
        Start a bot instance.
        
        Args:
            bot: Bot domain model with configuration
            
        Returns:
            The bot ID
            
        Raises:
            BotAlreadyRunningError: If bot is already running
            ResourceLimitError: If capacity limits exceeded
            BotStartupError: If bot fails to start
        """
        if not self._is_running:
            raise BotEngineException("BotEngineManager is not running")
        
        bot_id = bot.id
        
        # Check if already running
        if bot_id in self._running_bots:
            raise BotAlreadyRunningError(bot_id, f"Bot {bot_id} is already running")
        
        # Validate capacity limits
        self._validate_capacity_limits(bot)
        
        logger.info(
            f"Starting bot {bot_id} ({bot.name}) for user {bot.user_id} "
            f"trading {bot.symbol}"
        )
        
        try:
            # Create runner context with shared resources and trading services
            context = BotRunnerContext(
                market_data_hub=self._market_data_hub,
                signal_router=self._signal_router,
                broker_pool=self._broker_pool,
                bot_repository=self._bot_repository,
                # Trading services (enables actual trade execution when available)
                order_manager=self._order_manager,
                market_data=self._market_data,
                risk_manager=self._risk_manager,
                position_manager=self._position_manager,
            )
            
            # Create bot runner
            runner = BotRunner(bot, context)
            
            # Create and store the task
            task = asyncio.create_task(
                runner.start(),
                name=f"bot_{bot_id}"
            )
            runner.task = task
            
            # Register runner
            self._running_bots[bot_id] = runner
            self._increment_counts(bot)
            
            logger.info(f"Bot {bot_id} started successfully")
            return bot_id
            
        except Exception as e:
            logger.error(f"Failed to start bot {bot_id}: {e}")
            # Cleanup on failure
            if bot_id in self._running_bots:
                del self._running_bots[bot_id]
                self._decrement_counts(bot)
            raise BotStartupError(bot_id, f"Bot startup failed: {e}")
    
    async def stop_bot(
        self, 
        bot_id: str, 
        close_position: bool = False
    ) -> None:
        """
        Stop a running bot.
        
        Args:
            bot_id: Bot identifier
            close_position: Whether to close open position
            
        Raises:
            BotNotRunningError: If bot is not running
            BotShutdownError: If shutdown fails
        """
        runner = self._running_bots.get(bot_id)
        if not runner:
            raise BotNotRunningError(bot_id, f"Bot {bot_id} is not running")
        
        logger.info(f"Stopping bot {bot_id} (close_position={close_position})")
        
        try:
            await runner.stop(close_positions=close_position)
            
            # Unregister runner
            del self._running_bots[bot_id]
            self._decrement_counts(runner.bot)
            
            logger.info(f"Bot {bot_id} stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping bot {bot_id}: {e}")
            raise BotShutdownError(bot_id, f"Bot shutdown failed: {e}")
    
    async def pause_bot(self, bot_id: str) -> None:
        """
        Pause a running bot.
        
        Args:
            bot_id: Bot identifier
            
        Raises:
            BotNotRunningError: If bot is not running
        """
        runner = self._running_bots.get(bot_id)
        if not runner:
            raise BotNotRunningError(bot_id, f"Bot {bot_id} is not running")
        
        await runner.pause()
        logger.info(f"Bot {bot_id} paused")
    
    async def resume_bot(self, bot_id: str) -> None:
        """
        Resume a paused bot.
        
        Args:
            bot_id: Bot identifier
            
        Raises:
            BotNotRunningError: If bot is not running
        """
        runner = self._running_bots.get(bot_id)
        if not runner:
            raise BotNotRunningError(bot_id, f"Bot {bot_id} is not running")
        
        await runner.resume()
        logger.info(f"Bot {bot_id} resumed")
    
    # =========================================================================
    # Status & Monitoring
    # =========================================================================
    
    def get_bot_status(self, bot_id: str) -> Optional[BotStatus]:
        """
        Get status of a specific bot.
        
        Args:
            bot_id: Bot identifier
            
        Returns:
            BotStatus if running, None otherwise
        """
        runner = self._running_bots.get(bot_id)
        if runner:
            return runner.get_status()
        return None
    
    def get_all_statuses(self) -> List[BotStatus]:
        """
        Get status of all running bots.
        
        Returns:
            List of BotStatus for all running bots
        """
        return [runner.get_status() for runner in self._running_bots.values()]
    
    def get_user_bots(self, user_id: str) -> List[BotStatus]:
        """
        Get status of all bots for a specific user.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of BotStatus for user's running bots
        """
        return [
            runner.get_status()
            for runner in self._running_bots.values()
            if runner.bot.user_id == user_id
        ]
    
    def get_symbol_bots(self, symbol: str) -> List[BotStatus]:
        """
        Get status of all bots trading a specific symbol.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSD")
            
        Returns:
            List of BotStatus for bots trading this symbol
        """
        return [
            runner.get_status()
            for runner in self._running_bots.values()
            if runner.bot.symbol == symbol
        ]
    
    def is_bot_running(self, bot_id: str) -> bool:
        """
        Check if a specific bot is running.
        
        Args:
            bot_id: Bot identifier
            
        Returns:
            True if bot is running
        """
        return bot_id in self._running_bots
    
    def get_engine_stats(self) -> Dict[str, Any]:
        """
        Get engine statistics.
        
        Returns:
            Dictionary with engine statistics
        """
        return {
            "is_running": self._is_running,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "total_running_bots": len(self._running_bots),
            "max_concurrent_bots": self._config.max_concurrent_bots,
            "capacity_used_percent": (
                len(self._running_bots) / self._config.max_concurrent_bots * 100
                if self._config.max_concurrent_bots > 0 else 0
            ),
            "unique_users": len(self._user_bot_counts),
            "unique_symbols": len(self._symbol_bot_counts),
            "user_bot_counts": dict(self._user_bot_counts),
            "symbol_bot_counts": dict(self._symbol_bot_counts),
        }
    
    # =========================================================================
    # Signal Routing
    # =========================================================================
    
    async def route_signal(self, signal: Dict[str, Any]) -> List[str]:
        """
        Route a signal to relevant bots.
        
        Args:
            signal: Signal data from webhook
            
        Returns:
            List of bot IDs that received the signal
        """
        return await self._signal_router.route_signal(signal)
    
    # =========================================================================
    # Capacity Management
    # =========================================================================
    
    def _validate_capacity_limits(self, bot: Bot) -> None:
        """
        Validate that starting this bot doesn't exceed capacity limits.
        
        Args:
            bot: Bot to start
            
        Raises:
            ResourceLimitError: If any limit would be exceeded
        """
        # Check total bot limit
        if len(self._running_bots) >= self._config.max_concurrent_bots:
            raise ResourceLimitError(
                f"Maximum concurrent bots reached: {self._config.max_concurrent_bots}"
            )
        
        # Check per-user limit
        user_count = self._user_bot_counts.get(bot.user_id, 0)
        if user_count >= self._config.max_bots_per_user:
            raise ResourceLimitError(
                f"User {bot.user_id} has reached maximum bots: "
                f"{self._config.max_bots_per_user}"
            )
        
        # Check per-symbol limit
        symbol_count = self._symbol_bot_counts.get(bot.symbol, 0)
        if symbol_count >= self._config.max_bots_per_symbol:
            raise ResourceLimitError(
                f"Symbol {bot.symbol} has reached maximum bots: "
                f"{self._config.max_bots_per_symbol}"
            )
    
    def _increment_counts(self, bot: Bot) -> None:
        """Increment user and symbol bot counts."""
        self._user_bot_counts[bot.user_id] = (
            self._user_bot_counts.get(bot.user_id, 0) + 1
        )
        self._symbol_bot_counts[bot.symbol] = (
            self._symbol_bot_counts.get(bot.symbol, 0) + 1
        )
    
    def _decrement_counts(self, bot: Bot) -> None:
        """Decrement user and symbol bot counts."""
        if bot.user_id in self._user_bot_counts:
            self._user_bot_counts[bot.user_id] -= 1
            if self._user_bot_counts[bot.user_id] <= 0:
                del self._user_bot_counts[bot.user_id]
        
        if bot.symbol in self._symbol_bot_counts:
            self._symbol_bot_counts[bot.symbol] -= 1
            if self._symbol_bot_counts[bot.symbol] <= 0:
                del self._symbol_bot_counts[bot.symbol]
    
    def get_available_capacity(self) -> Dict[str, int]:
        """
        Get available capacity for new bots.
        
        Returns:
            Dictionary with available capacity for each limit type
        """
        return {
            "total_available": (
                self._config.max_concurrent_bots - len(self._running_bots)
            ),
            "max_per_user": self._config.max_bots_per_user,
            "max_per_symbol": self._config.max_bots_per_symbol,
        }
    
    def get_user_available_capacity(self, user_id: str) -> int:
        """
        Get available bot capacity for a specific user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Number of additional bots this user can start
        """
        current = self._user_bot_counts.get(user_id, 0)
        return max(0, self._config.max_bots_per_user - current)
    
    # =========================================================================
    # Background Tasks
    # =========================================================================
    
    async def _health_check_loop(self) -> None:
        """
        Background task that periodically checks bot health.
        
        Detects crashed bots, stale states, and resource issues.
        """
        interval = self._config.health_check_interval_seconds
        
        while self._is_running:
            try:
                await asyncio.sleep(interval)
                await self._check_bot_health()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
    
    async def _check_bot_health(self) -> None:
        """Check health of all running bots."""
        crashed_bots = []
        
        for bot_id, runner in self._running_bots.items():
            # Check if task is still running
            if runner.task and runner.task.done():
                # Task completed unexpectedly
                exception = runner.task.exception()
                if exception:
                    logger.error(f"Bot {bot_id} crashed: {exception}")
                    crashed_bots.append(bot_id)
                else:
                    logger.warning(f"Bot {bot_id} task completed unexpectedly")
                    crashed_bots.append(bot_id)
        
        # Clean up crashed bots
        for bot_id in crashed_bots:
            runner = self._running_bots.pop(bot_id, None)
            if runner:
                self._decrement_counts(runner.bot)
                # Update bot state to error in database
                try:
                    runner.bot.state = BotState.ERROR
                    runner.bot.error_message = "Bot crashed unexpectedly"
                    await self._bot_repository.update(runner.bot)
                except Exception as e:
                    logger.error(f"Failed to update crashed bot state: {e}")
    
    async def _state_persist_loop(self) -> None:
        """
        Background task that periodically persists bot states.
        
        Ensures state is saved even if individual bots don't persist.
        """
        interval = self._config.state_persist_interval_seconds
        
        while self._is_running:
            try:
                await asyncio.sleep(interval)
                # States are persisted by individual runners
                # This loop can be used for bulk operations if needed
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"State persist error: {e}")
    
    async def _restore_running_bots(self) -> None:
        """
        Restore bots that were running before shutdown.
        
        Called during engine startup to resume previously active bots.
        """
        try:
            # Query bots that should be running
            running_bots = await self._bot_repository.get_by_state(BotState.RUNNING)
            starting_bots = await self._bot_repository.get_by_state(BotState.STARTING)
            
            bots_to_restore = running_bots + starting_bots
            
            if not bots_to_restore:
                logger.info("No bots to restore")
                return
            
            logger.info(f"Restoring {len(bots_to_restore)} bots...")
            
            for bot in bots_to_restore:
                try:
                    await self.start_bot(bot)
                except Exception as e:
                    logger.error(f"Failed to restore bot {bot.id}: {e}")
                    # Mark as error state
                    bot.state = BotState.ERROR
                    bot.error_message = f"Failed to restore: {e}"
                    await self._bot_repository.update(bot)
            
            logger.info(f"Restored {len(self._running_bots)} bots successfully")
            
        except Exception as e:
            logger.error(f"Error restoring bots: {e}")
    
    async def _cleanup_on_error(self) -> None:
        """Cleanup resources if startup fails."""
        try:
            await self._market_data_hub.stop()
        except Exception:
            pass
        
        try:
            await self._signal_router.stop()
        except Exception:
            pass
        
        try:
            await self._broker_pool.stop()
        except Exception:
            pass
    
    # =========================================================================
    # Batch Operations
    # =========================================================================
    
    async def start_bots(self, bots: List[Bot]) -> Dict[str, str]:
        """
        Start multiple bots.
        
        Args:
            bots: List of bot models to start
            
        Returns:
            Dictionary mapping bot_id to result ("started" or error message)
        """
        results = {}
        
        for bot in bots:
            try:
                await self.start_bot(bot)
                results[bot.id] = "started"
            except Exception as e:
                results[bot.id] = str(e)
        
        return results
    
    async def stop_all_user_bots(
        self, 
        user_id: str, 
        close_positions: bool = False
    ) -> Dict[str, str]:
        """
        Stop all bots for a specific user.
        
        Args:
            user_id: User identifier
            close_positions: Whether to close positions
            
        Returns:
            Dictionary mapping bot_id to result
        """
        user_bot_ids = [
            bot_id for bot_id, runner in self._running_bots.items()
            if runner.bot.user_id == user_id
        ]
        
        results = {}
        for bot_id in user_bot_ids:
            try:
                await self.stop_bot(bot_id, close_position=close_positions)
                results[bot_id] = "stopped"
            except Exception as e:
                results[bot_id] = str(e)
        
        return results
    
    async def stop_all_symbol_bots(
        self, 
        symbol: str, 
        close_positions: bool = False
    ) -> Dict[str, str]:
        """
        Stop all bots trading a specific symbol.
        
        Args:
            symbol: Trading symbol
            close_positions: Whether to close positions
            
        Returns:
            Dictionary mapping bot_id to result
        """
        symbol_bot_ids = [
            bot_id for bot_id, runner in self._running_bots.items()
            if runner.bot.symbol == symbol
        ]
        
        results = {}
        for bot_id in symbol_bot_ids:
            try:
                await self.stop_bot(bot_id, close_position=close_positions)
                results[bot_id] = "stopped"
            except Exception as e:
                results[bot_id] = str(e)
        
        return results
