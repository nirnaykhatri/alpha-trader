"""
Event bus for centralized event distribution.
Implements Publisher-Subscriber pattern for loose coupling.
"""

import asyncio
from typing import Callable, Dict, List, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from collections import defaultdict
import uuid

from src.core.logging_config import get_logger


logger = get_logger(__name__)


class EventPriority(Enum):
    """Priority levels for event processing."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Event:
    """Base event class."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    priority: EventPriority = EventPriority.NORMAL
    data: Dict[str, Any] = field(default_factory=dict)
    source: Optional[str] = None
    
    def __post_init__(self):
        """Ensure timestamp is set."""
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()


class EventBus:
    """
    Centralized event bus for publish-subscribe pattern.
    Enables loose coupling between components with back-pressure handling.
    """
    
    def __init__(
        self,
        max_queue_size: int = 10000,
        enable_back_pressure: bool = True,
        drop_threshold: float = 0.9
    ):
        """
        Initialize event bus with back-pressure support.
        
        Args:
            max_queue_size: Maximum event queue size
            enable_back_pressure: Enable adaptive back-pressure handling
            drop_threshold: Queue fullness threshold (0.0-1.0) to start dropping low-priority events
        """
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self._subscriber_priorities: Dict[str, Dict[Callable, EventPriority]] = defaultdict(dict)
        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)
        self._running = False
        self._processor_task: Optional[asyncio.Task] = None
        self._event_history: List[Event] = []
        self._max_history = 1000
        self._enable_back_pressure = enable_back_pressure
        self._drop_threshold = max_queue_size * drop_threshold
        self._dropped_events_count = 0
        self._on_drop_handlers: List[Callable] = []
        
        logger.info(
            f"Event bus initialized (max_queue: {max_queue_size}, "
            f"back_pressure: {enable_back_pressure}, drop_threshold: {drop_threshold})"
        )
    
    def register_drop_handler(self, handler: Callable) -> None:
        """
        Register a handler to be called when events are dropped.
        
        Args:
            handler: Callable that takes (event, reason) parameters
            
        Example:
            def on_event_dropped(event, reason):
                logger.warning(f"Event {event.event_id} dropped: {reason}")
                metrics.dropped_events_total.inc()
            
            event_bus.register_drop_handler(on_event_dropped)
        """
        self._on_drop_handlers.append(handler)
        logger.info(f"Registered drop handler: {handler.__name__}")
    
    async def _handle_event_drop(self, event: Event, reason: str) -> None:
        """
        Handle event drop by notifying registered handlers.
        
        Args:
            event: Dropped event
            reason: Reason for dropping
        """
        self._dropped_events_count += 1
        
        logger.warning(
            f"Event dropped: {event.event_type} (id: {event.event_id}, "
            f"priority: {event.priority.value}, reason: {reason})",
            extra={
                "event_id": event.event_id,
                "event_type": event.event_type,
                "priority": event.priority.value,
                "reason": reason,
                "queue_size": self._event_queue.qsize()
            }
        )
        
        # Notify drop handlers
        for handler in self._on_drop_handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event, reason)
                else:
                    handler(event, reason)
            except Exception as e:
                logger.error(f"Error in drop handler {handler.__name__}: {e}")
    
    def subscribe(
        self, 
        event_type: str, 
        handler: Callable,
        priority: EventPriority = EventPriority.NORMAL
    ) -> None:
        """
        Subscribe to an event type.
        
        Args:
            event_type: Type of event to subscribe to
            handler: Async callable to handle the event
            priority: Handler priority (higher priority handlers execute first)
        """
        self._subscribers[event_type].append(handler)
        self._subscriber_priorities[event_type][handler] = priority
        
        # Sort subscribers by priority
        self._subscribers[event_type].sort(
            key=lambda h: self._subscriber_priorities[event_type][h].value,
            reverse=True
        )
        
        logger.info(
            f"Subscribed {handler.__name__} to {event_type} "
            f"(priority: {priority.value})"
        )
    
    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """
        Unsubscribe from an event type.
        
        Args:
            event_type: Event type to unsubscribe from
            handler: Handler to remove
        """
        if handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)
            del self._subscriber_priorities[event_type][handler]
            logger.info(f"Unsubscribed {handler.__name__} from {event_type}")
    
    async def publish(self, event: Event) -> None:
        """
        Publish an event to all subscribers with back-pressure handling.
        
        Args:
            event: Event to publish
        """
        queue_size = self._event_queue.qsize()
        max_size = self._event_queue.maxsize
        
        # Check if back-pressure should be applied
        if self._enable_back_pressure and queue_size >= self._drop_threshold:
            # Drop low-priority events when queue is nearly full
            if event.priority in [EventPriority.LOW, EventPriority.NORMAL]:
                await self._handle_event_drop(
                    event,
                    f"back_pressure (queue: {queue_size}/{max_size})"
                )
                return
            
            logger.warning(
                f"Queue near capacity: {queue_size}/{max_size} "
                f"(accepting {event.priority.name} priority event)"
            )
        
        try:
            # Try to add to queue with immediate timeout
            await asyncio.wait_for(
                self._event_queue.put(event),
                timeout=0.001  # 1ms timeout
            )
            
            logger.debug(
                f"Published event {event.event_type} "
                f"(id: {event.event_id}, priority: {event.priority.value}, "
                f"queue: {queue_size + 1}/{max_size})"
            )
            
        except asyncio.TimeoutError:
            await self._handle_event_drop(
                event,
                f"queue_full ({queue_size}/{max_size})"
            )
        except Exception as e:
            logger.error(f"Error publishing event {event.event_id}: {e}")
    
    async def publish_sync(self, event: Event) -> None:
        """
        Publish event and wait for all handlers to complete.
        
        Args:
            event: Event to publish
        """
        await self._process_event(event)
    
    async def _process_event(self, event: Event) -> None:
        """
        Process a single event by notifying all subscribers.
        
        Args:
            event: Event to process
        """
        event_type = event.event_type
        handlers = self._subscribers.get(event_type, [])
        
        if not handlers:
            logger.debug(f"No subscribers for event type {event_type}")
            return
        
        logger.debug(
            f"Processing event {event_type} for {len(handlers)} subscribers "
            f"(priority: {event.priority.value})"
        )
        
        # Execute handlers (already sorted by priority)
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(
                    f"Error in event handler {handler.__name__} "
                    f"for event {event_type}: {str(e)}",
                    exc_info=True
                )
        
        # Add to history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)
    
    async def _event_processor(self) -> None:
        """Background event processor task."""
        logger.info("Event processor started")
        
        while self._running:
            try:
                # Get event with timeout to allow checking _running flag
                event = await asyncio.wait_for(
                    self._event_queue.get(),
                    timeout=0.1
                )
                
                await self._process_event(event)
                self._event_queue.task_done()
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error in event processor: {str(e)}", exc_info=True)
        
        logger.info("Event processor stopped")
    
    async def start(self) -> None:
        """Start the event bus processor."""
        if self._running:
            logger.warning("Event bus already running")
            return
        
        self._running = True
        self._processor_task = asyncio.create_task(self._event_processor())
        logger.info("Event bus started")
    
    async def stop(self) -> None:
        """Stop the event bus processor."""
        if not self._running:
            logger.debug("Event bus not running")
            return
        
        logger.info("Stopping event bus...")
        self._running = False
        
        if self._processor_task:
            try:
                await asyncio.wait_for(self._processor_task, timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("Event processor stop timeout")
                self._processor_task.cancel()
        
        logger.info("Event bus stopped")
    
    def get_subscriber_count(self, event_type: str) -> int:
        """
        Get number of subscribers for an event type.
        
        Args:
            event_type: Event type to check
            
        Returns:
            Number of subscribers
        """
        return len(self._subscribers.get(event_type, []))
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get event bus statistics including back-pressure metrics.
        
        Returns:
            Dictionary with statistics
        """
        queue_size = self._event_queue.qsize()
        max_size = self._event_queue.maxsize
        
        return {
            "running": self._running,
            "queue_size": queue_size,
            "max_queue_size": max_size,
            "queue_utilization_pct": (queue_size / max_size * 100) if max_size > 0 else 0,
            "back_pressure_enabled": self._enable_back_pressure,
            "drop_threshold": self._drop_threshold,
            "dropped_events_total": self._dropped_events_count,
            "total_event_types": len(self._subscribers),
            "total_subscribers": sum(len(handlers) for handlers in self._subscribers.values()),
            "events_processed": len(self._event_history),
            "subscribers_by_type": {
                event_type: len(handlers)
                for event_type, handlers in self._subscribers.items()
            }
        }
    
    def get_recent_events(self, count: int = 10) -> List[Event]:
        """
        Get recent events from history.
        
        Args:
            count: Number of events to retrieve
            
        Returns:
            List of recent events
        """
        return self._event_history[-count:]
