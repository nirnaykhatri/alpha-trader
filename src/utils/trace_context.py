"""
Trace Context Management

Distributed tracing infrastructure for correlating operations
across webhook → signal → order → fill lifecycle.
"""

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import structlog

# Context variable for trace propagation across async boundaries
_trace_context: ContextVar[Optional['TraceContext']] = ContextVar('trace_context', default=None)

logger = structlog.get_logger(__name__)


@dataclass
class TraceContext:
    """
    Immutable trace context for request correlation.
    
    Attributes:
        trace_id: Unique identifier for the entire operation chain
        span_id: Identifier for current operation span
        parent_span_id: Identifier of parent span (if any)
        operation: Name of current operation
        symbol: Trading symbol (if applicable)
        timestamp: Trace creation timestamp
        metadata: Additional context data
    """
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    operation: str = "unknown"
    symbol: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: dict = field(default_factory=dict)
    
    def create_child_span(self, operation: str) -> 'TraceContext':
        """
        Create a child span for a sub-operation.
        
        Args:
            operation: Name of the child operation
            
        Returns:
            New TraceContext with same trace_id but new span_id
        """
        return TraceContext(
            trace_id=self.trace_id,
            span_id=str(uuid.uuid4()),
            parent_span_id=self.span_id,
            operation=operation,
            symbol=self.symbol,
            metadata=self.metadata.copy()
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/serialization."""
        return {
            'trace_id': self.trace_id,
            'span_id': self.span_id,
            'parent_span_id': self.parent_span_id,
            'operation': self.operation,
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }


def create_trace_context(
    operation: str,
    symbol: Optional[str] = None,
    metadata: Optional[dict] = None
) -> TraceContext:
    """
    Create a new root trace context.
    
    Args:
        operation: Name of the operation (e.g., 'webhook_processing')
        symbol: Trading symbol if applicable
        metadata: Additional context data
        
    Returns:
        New TraceContext instance
    """
    trace_id = str(uuid.uuid4())
    span_id = str(uuid.uuid4())
    
    context = TraceContext(
        trace_id=trace_id,
        span_id=span_id,
        operation=operation,
        symbol=symbol,
        metadata=metadata or {}
    )
    
    logger.debug(
        "trace_context_created",
        trace_id=trace_id,
        span_id=span_id,
        operation=operation,
        symbol=symbol
    )
    
    return context


def get_trace_context() -> Optional[TraceContext]:
    """
    Get the current trace context from context variable.
    
    Returns:
        Current TraceContext or None if not set
    """
    return _trace_context.get()


def set_trace_context(context: Optional[TraceContext]) -> None:
    """
    Set the trace context in context variable.
    
    Args:
        context: TraceContext to set (or None to clear)
    """
    _trace_context.set(context)


def get_trace_id() -> Optional[str]:
    """
    Get current trace ID for logging.
    
    Returns:
        Trace ID string or None if no context
    """
    context = get_trace_context()
    return context.trace_id if context else None


def get_span_id() -> Optional[str]:
    """
    Get current span ID for logging.
    
    Returns:
        Span ID string or None if no context
    """
    context = get_trace_context()
    return context.span_id if context else None


class TraceContextManager:
    """
    Context manager for trace context propagation.
    
    Example:
        with TraceContextManager("process_signal", symbol="AAPL"):
            # trace_id available in all logs within this block
            await process_signal(signal)
    """
    
    def __init__(
        self,
        operation: str,
        symbol: Optional[str] = None,
        metadata: Optional[dict] = None,
        parent_context: Optional[TraceContext] = None
    ):
        """
        Initialize trace context manager.
        
        Args:
            operation: Name of the operation
            symbol: Trading symbol if applicable
            metadata: Additional context data
            parent_context: Parent trace context for span creation
        """
        if parent_context:
            self.context = parent_context.create_child_span(operation)
        else:
            self.context = create_trace_context(operation, symbol, metadata)
        
        self.previous_context: Optional[TraceContext] = None
    
    def __enter__(self) -> TraceContext:
        """Enter context manager and set trace context."""
        self.previous_context = get_trace_context()
        set_trace_context(self.context)
        
        logger.debug(
            "trace_span_started",
            trace_id=self.context.trace_id,
            span_id=self.context.span_id,
            operation=self.context.operation
        )
        
        return self.context
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context manager and restore previous context."""
        logger.debug(
            "trace_span_ended",
            trace_id=self.context.trace_id,
            span_id=self.context.span_id,
            operation=self.context.operation,
            error=str(exc_val) if exc_val else None
        )
        
        set_trace_context(self.previous_context)
        return False


def bind_trace_to_logger():
    """
    Bind current trace context to structlog for automatic inclusion.
    
    Call this during logger configuration to automatically include
    trace_id and span_id in all log messages.
    """
    def add_trace_context(logger, method_name, event_dict):
        """Processor to add trace context to log events."""
        context = get_trace_context()
        if context:
            event_dict['trace_id'] = context.trace_id
            event_dict['span_id'] = context.span_id
            if context.symbol:
                event_dict['symbol'] = context.symbol
        return event_dict
    
    # This would be added to structlog processors
    return add_trace_context
