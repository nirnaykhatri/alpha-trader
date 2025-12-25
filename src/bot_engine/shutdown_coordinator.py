"""
Shutdown Coordinator - Handles graceful shutdown of trading bot components.

Extracted from TradingBotOrchestrator to follow Single Responsibility Principle.
This class is responsible for coordinating the orderly shutdown of all subsystems.

Key Improvements (v1.1.0):
- Integration with TaskRegistry for proper task lifecycle management
- Ordered shutdown by task category (signal handlers first, infrastructure last)
- Deterministic exception handling during shutdown
- Proper cancellation with configurable timeouts

Author: Trading Bot Team
Version: 1.1.0
"""

import asyncio
from typing import List, Optional, TYPE_CHECKING

from src.core.logging_config import get_logger
from src.core.task_registry import TaskRegistry, TaskCategory, get_task_registry

if TYPE_CHECKING:
    from src.signals import TradingViewSignalListener
    from src.broker.subsystem import BrokerSubsystem
    from src.database import CosmosDBManager
    from src.trading import OrderManager


logger = get_logger(__name__)


class ShutdownCoordinator:
    """
    Coordinates graceful shutdown of trading bot components.
    
    Responsibilities:
    - Stopping signal listeners
    - Canceling background tasks via TaskRegistry
    - Canceling open orders
    - Closing database connections
    - Signaling shutdown completion
    
    The shutdown sequence is ordered to minimize risk:
    1. Stop accepting new signals
    2. Stop broker subsystem
    3. Cancel background tasks (ordered by category via TaskRegistry)
    4. Cancel open orders (optional, configurable)
    5. Close database connections
    6. Signal completion
    
    Task Category Order (during shutdown):
    1. SIGNAL_HANDLERS - Stop accepting new work first
    2. PROCESSING - Stop processing pipelines
    3. MONITORING - Stop monitoring loops
    4. STREAMING - Stop data streams
    5. MAINTENANCE - Stop background maintenance
    6. INFRASTRUCTURE - Stop infrastructure last
    
    Usage:
        coordinator = ShutdownCoordinator(
            signal_listener=listener,
            broker_subsystem=broker,
            database=db,
            order_manager=orders,
            background_tasks=tasks,
            shutdown_event=event
        )
        await coordinator.shutdown()
    """
    
    # Timeout for background task cancellation (seconds)
    TASK_CANCEL_TIMEOUT = 3.0
    
    # Timeout per category during ordered shutdown
    CATEGORY_CANCEL_TIMEOUT = 2.0
    
    def __init__(
        self,
        signal_listener: Optional["TradingViewSignalListener"] = None,
        broker_subsystem: Optional["BrokerSubsystem"] = None,
        database: Optional["CosmosDBManager"] = None,
        order_manager: Optional["OrderManager"] = None,
        background_tasks: Optional[List[asyncio.Task]] = None,
        shutdown_event: Optional[asyncio.Event] = None,
        cancel_orders_on_shutdown: bool = True,
        task_registry: Optional[TaskRegistry] = None
    ):
        """
        Initialize shutdown coordinator with component references.
        
        Args:
            signal_listener: Signal listener to stop
            broker_subsystem: Broker subsystem to stop
            database: Database manager to close
            order_manager: Order manager for canceling orders
            background_tasks: List of background tasks to cancel (legacy support)
            shutdown_event: Event to signal shutdown completion
            cancel_orders_on_shutdown: Whether to cancel open orders on shutdown
            task_registry: TaskRegistry for structured task management (preferred)
        """
        self._signal_listener = signal_listener
        self._broker_subsystem = broker_subsystem
        self._database = database
        self._order_manager = order_manager
        self._background_tasks = background_tasks or []
        self._shutdown_event = shutdown_event or asyncio.Event()
        self._cancel_orders = cancel_orders_on_shutdown
        self._task_registry = task_registry
        self._shutdown_errors: List[Exception] = []
        
        logger.debug("ShutdownCoordinator initialized")
    
    @property
    def shutdown_event(self) -> asyncio.Event:
        """Get the shutdown event."""
        return self._shutdown_event
    
    @property
    def task_registry(self) -> TaskRegistry:
        """Get the task registry (uses global if not set)."""
        if self._task_registry is None:
            self._task_registry = get_task_registry()
        return self._task_registry
    
    @property
    def shutdown_errors(self) -> List[Exception]:
        """Get list of errors that occurred during shutdown."""
        return self._shutdown_errors.copy()
    
    def update_components(
        self,
        signal_listener: Optional["TradingViewSignalListener"] = None,
        broker_subsystem: Optional["BrokerSubsystem"] = None,
        database: Optional["CosmosDBManager"] = None,
        order_manager: Optional["OrderManager"] = None,
        background_tasks: Optional[List[asyncio.Task]] = None,
        task_registry: Optional[TaskRegistry] = None
    ) -> None:
        """
        Update component references after initialization.
        
        This allows the coordinator to be created early and have
        components added as they are initialized.
        """
        if signal_listener is not None:
            self._signal_listener = signal_listener
        if broker_subsystem is not None:
            self._broker_subsystem = broker_subsystem
        if database is not None:
            self._database = database
        if order_manager is not None:
            self._order_manager = order_manager
        if background_tasks is not None:
            self._background_tasks = background_tasks
        if task_registry is not None:
            self._task_registry = task_registry
    
    def add_background_task(self, task: asyncio.Task) -> None:
        """
        Add a background task to be canceled on shutdown.
        
        Note: Prefer using TaskRegistry.create_task() for new tasks.
        This method is kept for backward compatibility.
        """
        self._background_tasks.append(task)
    
    async def shutdown(self) -> None:
        """
        Execute graceful shutdown sequence.
        
        Order of operations:
        1. Stop signal listener (stop accepting new work)
        2. Stop broker subsystem
        3. Cancel registered tasks (via TaskRegistry, ordered by category)
        4. Cancel legacy background tasks
        5. Cancel open orders (if configured)
        6. Close database connections
        7. Signal shutdown completion
        
        Errors are collected and logged but do not prevent other shutdown steps.
        
        Raises:
            Exception: Re-raises the first exception after cleanup if any occurred
        """
        logger.info("Shutting down Trading Bot System...")
        self._shutdown_errors.clear()
        
        try:
            # Step 1: Stop signal listener first (stop accepting new signals)
            await self._stop_signal_listener()
            
            # Step 2: Stop broker subsystem
            await self._stop_broker_subsystem()
            
            # Step 3: Cancel registered tasks via TaskRegistry (ordered by category)
            await self._cancel_registered_tasks()
            
            # Step 4: Cancel legacy background tasks (for backward compatibility)
            await self._cancel_background_tasks()
            
            # Step 5: Cancel open orders (configurable)
            if self._cancel_orders:
                await self._cancel_all_orders()
            
            # Step 6: Close database connections
            await self._close_database()
            
            # Step 7: Signal shutdown completion
            self._signal_completion()
            
            # Log shutdown summary
            if self._shutdown_errors:
                logger.warning(f"Trading Bot System stopped with {len(self._shutdown_errors)} error(s)")
                for i, err in enumerate(self._shutdown_errors, 1):
                    logger.warning(f"  Error {i}: {type(err).__name__}: {err}")
            else:
                logger.info("Trading Bot System stopped successfully")
            
        except Exception as e:
            logger.error(f"Critical error during shutdown: {str(e)}")
            self._shutdown_errors.append(e)
            # Still signal completion even on error
            self._signal_completion()
            raise
    
    async def _stop_signal_listener(self) -> None:
        """Stop the signal listener."""
        if not self._signal_listener:
            return
        
        logger.info("Stopping signal listener...")
        try:
            # Force stop the server if running
            if self._signal_listener._server:
                self._signal_listener._server.should_exit = True
                if hasattr(self._signal_listener._server, 'force_exit'):
                    self._signal_listener._server.force_exit = True
            
            await self._signal_listener.stop()
            logger.debug("Signal listener stopped")
        except Exception as e:
            logger.error(f"Error stopping signal listener: {e}")
            self._shutdown_errors.append(e)
    
    async def _stop_broker_subsystem(self) -> None:
        """Stop the broker subsystem."""
        if not self._broker_subsystem:
            return
        
        logger.info("Stopping broker subsystem...")
        try:
            await self._broker_subsystem.stop()
            logger.debug("Broker subsystem stopped")
        except Exception as e:
            logger.error(f"Error stopping broker subsystem: {e}")
            self._shutdown_errors.append(e)
    
    async def _cancel_registered_tasks(self) -> None:
        """Cancel all tasks registered with the TaskRegistry (ordered by category)."""
        try:
            registry = self.task_registry
            active_count = registry.active_count
            
            if active_count == 0:
                logger.debug("No registered tasks to cancel")
                return
            
            logger.info(f"Cancelling {active_count} registered tasks (ordered by category)...")
            
            # Cancel tasks in category order
            # This ensures signal handlers stop first, infrastructure stops last
            cancelled = await registry.cancel_all(
                timeout=self.TASK_CANCEL_TIMEOUT,
                ordered=True
            )
            
            logger.info(f"Cancelled {cancelled}/{active_count} registered tasks")
            
            # Log any tasks that couldn't be cancelled
            remaining = registry.active_count
            if remaining > 0:
                logger.warning(f"{remaining} tasks did not cancel within timeout")
                for task_info in registry.get_active_tasks():
                    logger.warning(f"  - {task_info.name} (category={task_info.category.name})")
                    
        except Exception as e:
            logger.error(f"Error cancelling registered tasks: {e}")
            self._shutdown_errors.append(e)
    
    async def _cancel_background_tasks(self) -> None:
        """Cancel legacy background tasks with timeout (for backward compatibility)."""
        if not self._background_tasks:
            return
        
        # Filter out tasks that are already in the registry to avoid double-cancellation
        legacy_tasks = [
            task for task in self._background_tasks
            if not task.done() and self.task_registry.get_task_info(task) is None
        ]
        
        if not legacy_tasks:
            return
        
        logger.info(f"Cancelling {len(legacy_tasks)} legacy background tasks...")
        
        # Request cancellation for all tasks
        for task in legacy_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for cancellation with timeout
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._background_tasks, return_exceptions=True),
                timeout=self.TASK_CANCEL_TIMEOUT
            )
            logger.info("All background tasks stopped")
        except asyncio.TimeoutError:
            logger.warning(
                f"Some background tasks did not cancel within "
                f"{self.TASK_CANCEL_TIMEOUT}s timeout"
            )
    
    async def _cancel_all_orders(self) -> None:
        """Cancel all open orders."""
        if not self._order_manager:
            return
        
        logger.info("Canceling open orders...")
        try:
            open_orders = await self._order_manager.get_open_orders()
            
            for order in open_orders:
                try:
                    await self._order_manager.cancel_order(order.order_id)
                except Exception as e:
                    logger.error(f"Error canceling order {order.order_id}: {e}")
            
            logger.info(f"Canceled {len(open_orders)} open orders")
        except Exception as e:
            logger.error(f"Error canceling orders: {e}")
    
    async def _close_database(self) -> None:
        """Close database connections."""
        if not self._database:
            return
        
        logger.info("Closing database connections...")
        try:
            await self._database.close()
            logger.debug("Database connections closed")
        except Exception as e:
            logger.error(f"Error closing database: {e}")
    
    def _signal_completion(self) -> None:
        """Signal shutdown completion via event."""
        if not self._shutdown_event.is_set():
            self._shutdown_event.set()
            logger.debug("Shutdown event signaled")
