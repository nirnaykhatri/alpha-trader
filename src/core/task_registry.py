"""
Task Registry - Structured Concurrency for Background Tasks

Provides a centralized registry for tracking and managing async tasks with proper
lifecycle management. This prevents fire-and-forget patterns where tasks can be
dropped on shutdown or exceptions go unhandled.

Key Features:
- Centralized task tracking with metadata
- Proper shutdown ordering with timeouts
- Exception handling with configurable callbacks
- Task categorization for ordered shutdown
- Metrics tracking for observability

Author: Trading Bot Team
Version: 1.0.0
"""

import asyncio
import weakref
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Any, Callable, Coroutine, Dict, List, Optional, Set, TypeVar, 
    Union, Awaitable
)

from src.core.logging_config import get_logger


logger = get_logger(__name__)


# Type alias for coroutine functions
T = TypeVar("T")
CoroFunc = Callable[..., Coroutine[Any, Any, T]]


class TaskCategory(Enum):
    """
    Task categories for ordered shutdown.
    
    Tasks are cancelled in order from highest priority (most critical to stop first)
    to lowest priority. Within a category, all tasks are cancelled concurrently.
    """
    # Critical tasks that should stop first (e.g., accepting new work)
    SIGNAL_HANDLERS = 100
    
    # Processing tasks (e.g., webhooks, signal processing)
    PROCESSING = 200
    
    # Monitoring tasks (e.g., position monitor, order monitor)
    MONITORING = 300
    
    # Data streaming tasks (e.g., market data, websockets)
    STREAMING = 400
    
    # Background maintenance (e.g., config refresh, cache cleanup)
    MAINTENANCE = 500
    
    # Infrastructure tasks (should stop last)
    INFRASTRUCTURE = 600
    
    # Default category for unspecified tasks
    DEFAULT = 999


@dataclass
class TaskInfo:
    """
    Metadata for a tracked task.
    
    Attributes:
        task: The asyncio Task object
        name: Human-readable name for the task
        category: Task category for shutdown ordering
        created_at: When the task was registered
        owner: Optional weak reference to owning object (for debugging)
        critical: Whether task failure should trigger shutdown
        allow_cancel: Whether task can be cancelled on shutdown
    """
    task: asyncio.Task
    name: str
    category: TaskCategory = TaskCategory.DEFAULT
    created_at: datetime = field(default_factory=datetime.utcnow)
    owner: Optional[weakref.ref] = None
    critical: bool = False
    allow_cancel: bool = True
    
    @property
    def is_done(self) -> bool:
        """Check if the task has completed."""
        return self.task.done()
    
    @property
    def is_cancelled(self) -> bool:
        """Check if the task was cancelled."""
        return self.task.cancelled()
    
    @property
    def exception(self) -> Optional[BaseException]:
        """Get the task exception if any."""
        if self.task.done() and not self.task.cancelled():
            try:
                return self.task.exception()
            except asyncio.InvalidStateError:
                return None
        return None


@dataclass
class TaskRegistryStats:
    """Statistics for task registry operations."""
    total_registered: int = 0
    total_completed: int = 0
    total_cancelled: int = 0
    total_failed: int = 0
    active_tasks: int = 0
    tasks_by_category: Dict[str, int] = field(default_factory=dict)


class TaskRegistry:
    """
    Centralized registry for tracking and managing async tasks.
    
    This class provides structured concurrency by tracking all background tasks
    and ensuring proper cleanup on shutdown. It prevents fire-and-forget patterns
    where tasks can be dropped or exceptions go unhandled.
    
    Usage:
        registry = TaskRegistry()
        
        # Register a task
        task = await registry.create_task(
            some_coroutine(),
            name="my_task",
            category=TaskCategory.MONITORING
        )
        
        # On shutdown
        await registry.cancel_all(timeout=5.0)
    
    Thread Safety:
        This class is designed for single-threaded async use. All methods
        should be called from the same event loop.
    """
    
    # Default timeout for task cancellation
    DEFAULT_CANCEL_TIMEOUT: float = 5.0
    
    # Maximum tasks to track (prevent memory leaks)
    MAX_TASKS: int = 10000
    
    def __init__(
        self,
        on_task_error: Optional[Callable[[TaskInfo, BaseException], None]] = None,
        on_critical_failure: Optional[Callable[[TaskInfo, BaseException], Awaitable[None]]] = None,
    ):
        """
        Initialize the task registry.
        
        Args:
            on_task_error: Callback for non-critical task errors (sync)
            on_critical_failure: Callback for critical task failures (async)
                                 If a critical task fails, this is called before
                                 potentially triggering shutdown.
        """
        self._tasks: Dict[int, TaskInfo] = {}  # task_id -> TaskInfo
        self._on_task_error = on_task_error
        self._on_critical_failure = on_critical_failure
        self._stats = TaskRegistryStats()
        self._shutdown_in_progress = False
        self._lock = asyncio.Lock()
        
        logger.debug("TaskRegistry initialized")
    
    @property
    def stats(self) -> TaskRegistryStats:
        """Get registry statistics."""
        self._update_stats()
        return self._stats
    
    @property
    def active_count(self) -> int:
        """Get count of currently active tasks."""
        return sum(1 for info in self._tasks.values() if not info.is_done)
    
    @property
    def is_shutting_down(self) -> bool:
        """Check if shutdown is in progress."""
        return self._shutdown_in_progress
    
    async def create_task(
        self,
        coro: Coroutine[Any, Any, T],
        name: str,
        category: TaskCategory = TaskCategory.DEFAULT,
        owner: Optional[Any] = None,
        critical: bool = False,
        allow_cancel: bool = True,
    ) -> asyncio.Task[T]:
        """
        Create and register a tracked task.
        
        This is the primary way to spawn background tasks. The task is
        automatically tracked and will be properly cancelled on shutdown.
        
        Args:
            coro: Coroutine to wrap in a task
            name: Human-readable name for the task
            category: Category for shutdown ordering
            owner: Optional owner object (stored as weak reference)
            critical: If True, task failure may trigger shutdown
            allow_cancel: If True, task can be cancelled on shutdown
        
        Returns:
            The created asyncio.Task
        
        Raises:
            RuntimeError: If shutdown is in progress or max tasks reached
        """
        if self._shutdown_in_progress:
            raise RuntimeError("Cannot create tasks during shutdown")
        
        if len(self._tasks) >= self.MAX_TASKS:
            # Clean up completed tasks first
            await self._cleanup_completed()
            if len(self._tasks) >= self.MAX_TASKS:
                raise RuntimeError(f"Maximum tasks ({self.MAX_TASKS}) reached")
        
        # Create the task with a wrapper for exception handling
        wrapped_coro = self._wrap_with_error_handler(coro, name, critical)
        task = asyncio.create_task(wrapped_coro, name=name)
        
        # Register task info
        task_info = TaskInfo(
            task=task,
            name=name,
            category=category,
            owner=weakref.ref(owner) if owner else None,
            critical=critical,
            allow_cancel=allow_cancel,
        )
        
        self._tasks[id(task)] = task_info
        self._stats.total_registered += 1
        
        logger.debug(f"Task registered: {name} (category={category.name}, critical={critical})")
        
        return task
    
    def register_existing_task(
        self,
        task: asyncio.Task,
        name: str,
        category: TaskCategory = TaskCategory.DEFAULT,
        owner: Optional[Any] = None,
        critical: bool = False,
        allow_cancel: bool = True,
    ) -> None:
        """
        Register an existing task with the registry.
        
        Use this when a task was created elsewhere but should still be
        tracked for shutdown. Note: error handling wrapper is not applied.
        
        Args:
            task: Existing asyncio.Task to track
            name: Human-readable name
            category: Category for shutdown ordering
            owner: Optional owner object
            critical: Whether task failure should trigger shutdown
            allow_cancel: Whether task can be cancelled on shutdown
        """
        if id(task) in self._tasks:
            logger.warning(f"Task {name} already registered")
            return
        
        task_info = TaskInfo(
            task=task,
            name=name,
            category=category,
            owner=weakref.ref(owner) if owner else None,
            critical=critical,
            allow_cancel=allow_cancel,
        )
        
        self._tasks[id(task)] = task_info
        self._stats.total_registered += 1
        
        # Add done callback for cleanup
        task.add_done_callback(lambda t: self._on_task_done(t, name, critical))
        
        logger.debug(f"Existing task registered: {name}")
    
    def unregister_task(self, task: asyncio.Task) -> bool:
        """
        Unregister a task from the registry.
        
        Args:
            task: Task to unregister
        
        Returns:
            True if task was found and removed
        """
        task_id = id(task)
        if task_id in self._tasks:
            del self._tasks[task_id]
            logger.debug(f"Task unregistered: {task.get_name()}")
            return True
        return False
    
    def get_task_info(self, task: asyncio.Task) -> Optional[TaskInfo]:
        """Get task info for a registered task."""
        return self._tasks.get(id(task))
    
    def get_tasks_by_category(self, category: TaskCategory) -> List[TaskInfo]:
        """Get all tasks in a specific category."""
        return [
            info for info in self._tasks.values()
            if info.category == category and not info.is_done
        ]
    
    def get_active_tasks(self) -> List[TaskInfo]:
        """Get all currently active (not done) tasks."""
        return [info for info in self._tasks.values() if not info.is_done]
    
    async def cancel_task(
        self,
        task: asyncio.Task,
        timeout: float = DEFAULT_CANCEL_TIMEOUT,
    ) -> bool:
        """
        Cancel a specific task with timeout.
        
        Args:
            task: Task to cancel
            timeout: Maximum time to wait for cancellation
        
        Returns:
            True if task was successfully cancelled
        """
        task_info = self._tasks.get(id(task))
        if not task_info:
            logger.warning(f"Task not found in registry: {task.get_name()}")
            return False
        
        if not task_info.allow_cancel:
            logger.warning(f"Task {task_info.name} does not allow cancellation")
            return False
        
        if task_info.is_done:
            return True  # Already done
        
        task.cancel()
        
        try:
            await asyncio.wait_for(
                asyncio.shield(task),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Task {task_info.name} did not cancel within {timeout}s")
            return False
        except asyncio.CancelledError:
            pass  # Expected
        
        self._stats.total_cancelled += 1
        return True
    
    async def cancel_category(
        self,
        category: TaskCategory,
        timeout: float = DEFAULT_CANCEL_TIMEOUT,
    ) -> int:
        """
        Cancel all tasks in a category.
        
        Args:
            category: Category of tasks to cancel
            timeout: Maximum time to wait for all cancellations
        
        Returns:
            Number of tasks successfully cancelled
        """
        tasks = self.get_tasks_by_category(category)
        if not tasks:
            return 0
        
        logger.info(f"Cancelling {len(tasks)} tasks in category {category.name}")
        
        # Request cancellation for all tasks
        for info in tasks:
            if info.allow_cancel and not info.is_done:
                info.task.cancel()
        
        # Wait for all to complete
        task_objs = [info.task for info in tasks if info.allow_cancel]
        try:
            await asyncio.wait_for(
                asyncio.gather(*task_objs, return_exceptions=True),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Some tasks in {category.name} did not cancel within {timeout}s")
        
        cancelled = sum(1 for info in tasks if info.is_cancelled)
        self._stats.total_cancelled += cancelled
        
        return cancelled
    
    async def cancel_all(
        self,
        timeout: float = DEFAULT_CANCEL_TIMEOUT,
        ordered: bool = True,
    ) -> int:
        """
        Cancel all registered tasks.
        
        Args:
            timeout: Maximum time per category (if ordered) or total
            ordered: If True, cancel by category priority order
        
        Returns:
            Total number of tasks cancelled
        """
        async with self._lock:
            self._shutdown_in_progress = True
        
        total_cancelled = 0
        
        try:
            if ordered:
                # Cancel by category order (lowest priority value = highest shutdown priority)
                categories = sorted(
                    set(info.category for info in self._tasks.values()),
                    key=lambda c: c.value
                )
                
                for category in categories:
                    cancelled = await self.cancel_category(
                        category,
                        timeout=timeout / len(categories) if categories else timeout
                    )
                    total_cancelled += cancelled
            else:
                # Cancel all at once
                active_tasks = self.get_active_tasks()
                logger.info(f"Cancelling {len(active_tasks)} tasks")
                
                for info in active_tasks:
                    if info.allow_cancel:
                        info.task.cancel()
                
                task_objs = [info.task for info in active_tasks if info.allow_cancel]
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*task_objs, return_exceptions=True),
                        timeout=timeout
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Some tasks did not cancel within {timeout}s")
                
                total_cancelled = sum(1 for info in active_tasks if info.is_cancelled)
                self._stats.total_cancelled += total_cancelled
            
            logger.info(f"Cancelled {total_cancelled} tasks")
            
        finally:
            # Clean up all tasks
            await self._cleanup_completed()
        
        return total_cancelled
    
    async def wait_all(
        self,
        timeout: Optional[float] = None,
        categories: Optional[List[TaskCategory]] = None,
    ) -> bool:
        """
        Wait for all (or specified category) tasks to complete.
        
        Args:
            timeout: Maximum time to wait (None = wait forever)
            categories: Optional list of categories to wait for
        
        Returns:
            True if all tasks completed, False if timeout
        """
        if categories:
            tasks = []
            for cat in categories:
                tasks.extend(self.get_tasks_by_category(cat))
        else:
            tasks = self.get_active_tasks()
        
        if not tasks:
            return True
        
        task_objs = [info.task for info in tasks]
        
        try:
            if timeout:
                await asyncio.wait_for(
                    asyncio.gather(*task_objs, return_exceptions=True),
                    timeout=timeout
                )
            else:
                await asyncio.gather(*task_objs, return_exceptions=True)
            return True
        except asyncio.TimeoutError:
            return False
    
    async def _wrap_with_error_handler(
        self,
        coro: Coroutine[Any, Any, T],
        name: str,
        critical: bool,
    ) -> T:
        """Wrap coroutine with error handling."""
        try:
            return await coro
        except asyncio.CancelledError:
            logger.debug(f"Task {name} was cancelled")
            raise
        except Exception as e:
            logger.error(f"Task {name} failed: {str(e)}", exc_info=True)
            
            # Get task info
            task_info = None
            for info in self._tasks.values():
                if info.name == name:
                    task_info = info
                    break
            
            # Call error callback
            if task_info and self._on_task_error:
                try:
                    self._on_task_error(task_info, e)
                except Exception as cb_error:
                    logger.error(f"Error in task error callback: {cb_error}")
            
            # Handle critical failure
            if critical and self._on_critical_failure and task_info:
                try:
                    await self._on_critical_failure(task_info, e)
                except Exception as cb_error:
                    logger.error(f"Error in critical failure callback: {cb_error}")
            
            self._stats.total_failed += 1
            raise
    
    def _on_task_done(
        self,
        task: asyncio.Task,
        name: str,
        critical: bool,
    ) -> None:
        """Callback when a task completes."""
        self._stats.total_completed += 1
        
        if task.cancelled():
            logger.debug(f"Task {name} completed (cancelled)")
        elif task.exception():
            exc = task.exception()
            logger.error(f"Task {name} completed with error: {exc}")
            self._stats.total_failed += 1
            
            # Get task info and call callbacks
            task_info = self._tasks.get(id(task))
            if task_info and self._on_task_error:
                try:
                    self._on_task_error(task_info, exc)
                except Exception as cb_error:
                    logger.error(f"Error in task error callback: {cb_error}")
        else:
            logger.debug(f"Task {name} completed successfully")
    
    async def _cleanup_completed(self) -> int:
        """Remove completed tasks from registry."""
        completed_ids = [
            task_id for task_id, info in self._tasks.items()
            if info.is_done
        ]
        
        for task_id in completed_ids:
            del self._tasks[task_id]
        
        if completed_ids:
            logger.debug(f"Cleaned up {len(completed_ids)} completed tasks")
        
        return len(completed_ids)
    
    def _update_stats(self) -> None:
        """Update statistics."""
        self._stats.active_tasks = self.active_count
        
        # Count by category
        category_counts: Dict[str, int] = {}
        for info in self._tasks.values():
            if not info.is_done:
                cat_name = info.category.name
                category_counts[cat_name] = category_counts.get(cat_name, 0) + 1
        
        self._stats.tasks_by_category = category_counts


# Global registry instance (singleton pattern)
_global_registry: Optional[TaskRegistry] = None


def get_task_registry() -> TaskRegistry:
    """
    Get the global task registry instance.
    
    Returns:
        The global TaskRegistry singleton
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = TaskRegistry()
    return _global_registry


def set_task_registry(registry: TaskRegistry) -> None:
    """
    Set the global task registry instance.
    
    Useful for testing or custom configurations.
    
    Args:
        registry: TaskRegistry instance to use globally
    """
    global _global_registry
    _global_registry = registry


async def reset_task_registry() -> None:
    """
    Reset the global task registry (for testing).
    
    Cancels all tasks and creates a fresh registry.
    """
    global _global_registry
    if _global_registry:
        await _global_registry.cancel_all(timeout=2.0)
    _global_registry = TaskRegistry()
