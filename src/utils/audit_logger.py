"""
Structured Audit Logger

Standardized logging templates for trading operations with consistent formatting,
structured fields, and automatic context propagation.

Prevents logging format divergence across components and ensures compliance-ready audit trails.
"""

import logging
from datetime import datetime
from typing import Optional, Any, Dict
from enum import Enum

from src.utils.trace_context import get_trace_id


class AuditEventType(Enum):
    """Categorization of audit events for filtering and compliance."""
    
    # Trading operations
    SIGNAL_RECEIVED = "signal_received"
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    DCA_EXECUTED = "dca_executed"
    DCA_REJECTED = "dca_rejected"
    ORDER_PLACED = "order_placed"
    ORDER_FILLED = "order_filled"
    ORDER_CANCELLED = "order_cancelled"
    
    # Risk events
    RISK_BREACH = "risk_breach"
    SAFETY_CHECK_FAILED = "safety_check_failed"
    EMERGENCY_STOP = "emergency_stop"
    
    # System events
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    CONFIG_CHANGED = "config_changed"
    
    # External API events
    API_CALL = "api_call"
    API_ERROR = "api_error"
    WEBHOOK_RECEIVED = "webhook_received"


class AuditLogger:
    """
    Structured audit logger with standardized templates.
    
    Provides consistent logging format across components with:
    - Automatic trace ID propagation
    - Structured field injection
    - Standardized templates for common operations
    - Compliance-ready audit trails
    
    Example:
        logger = AuditLogger("AdvancedStrategy")
        
        logger.position_opened(
            symbol="AAPL",
            entry_price=150.00,
            quantity=100,
            direction="long"
        )
        
        # Output:
        # [2025-01-01 12:00:00] INFO [AdvancedStrategy] [trace_id=abc123] 
        # POSITION_OPENED symbol=AAPL entry_price=150.00 quantity=100 direction=long
    """
    
    def __init__(self, component: str, logger: Optional[logging.Logger] = None):
        """
        Initialize audit logger for a component.
        
        Args:
            component: Component name (e.g., "AdvancedStrategy", "OrderManager")
            logger: Optional logger instance (creates new one if not provided)
        """
        self.component = component
        self.logger = logger or logging.getLogger(component)
    
    def _log(
        self,
        level: int,
        event_type: AuditEventType,
        message: str,
        **fields: Any
    ):
        """
        Internal logging method with structured field injection.
        
        Args:
            level: Logging level (logging.INFO, logging.WARNING, etc.)
            event_type: Audit event type
            message: Human-readable message
            **fields: Structured fields (key-value pairs)
        """
        trace_id = get_trace_id()
        
        # Build structured message
        field_str = " ".join(f"{k}={v}" for k, v in fields.items())
        
        # Format: [component] [trace_id] EVENT_TYPE message field1=value1 field2=value2
        structured_msg = f"[{self.component}] [trace_id={trace_id}] {event_type.value.upper()} {message}"
        if field_str:
            structured_msg += f" {field_str}"
        
        self.logger.log(level, structured_msg, extra={"audit_event": event_type.value, **fields})
    
    # === Signal Processing ===
    
    def signal_received(
        self,
        symbol: str,
        action: str,
        timeframe: str,
        source: str = "tradingview",
        hmac_verified: bool = True,
        **extra: Any
    ):
        """Log webhook signal received."""
        self._log(
            logging.INFO,
            AuditEventType.SIGNAL_RECEIVED,
            f"Signal received: {action} {symbol}",
            symbol=symbol,
            action=action,
            timeframe=timeframe,
            source=source,
            hmac_verified=hmac_verified,
            **extra
        )
    
    # === Position Lifecycle ===
    
    def position_opened(
        self,
        symbol: str,
        entry_price: float,
        quantity: float,
        direction: str,
        position_lifecycle_id: str,
        entry_size: float,
        strategy: str,
        **extra: Any
    ):
        """Log position opened."""
        self._log(
            logging.INFO,
            AuditEventType.POSITION_OPENED,
            f"Position opened: {direction} {quantity} {symbol} @ ${entry_price:.2f}",
            symbol=symbol,
            entry_price=entry_price,
            quantity=quantity,
            direction=direction,
            position_lifecycle_id=position_lifecycle_id,
            entry_size=entry_size,
            strategy=strategy,
            **extra
        )
    
    def position_closed(
        self,
        symbol: str,
        exit_price: float,
        quantity: float,
        realized_pnl: float,
        realized_pnl_percent: float,
        close_reason: str,
        position_lifecycle_id: str,
        hold_duration_seconds: int,
        **extra: Any
    ):
        """Log position closed."""
        pnl_sign = "+" if realized_pnl >= 0 else ""
        
        self._log(
            logging.INFO,
            AuditEventType.POSITION_CLOSED,
            f"Position closed: {symbol} {pnl_sign}${realized_pnl:.2f} ({pnl_sign}{realized_pnl_percent:.2f}%)",
            symbol=symbol,
            exit_price=exit_price,
            quantity=quantity,
            realized_pnl=realized_pnl,
            realized_pnl_percent=realized_pnl_percent,
            close_reason=close_reason,
            position_lifecycle_id=position_lifecycle_id,
            hold_duration_seconds=hold_duration_seconds,
            **extra
        )
    
    # === DCA Operations ===
    
    def dca_executed(
        self,
        symbol: str,
        dca_attempt: int,
        dca_price: float,
        dca_quantity: float,
        new_average_price: float,
        trigger_level: float,
        is_progressive: bool,
        position_lifecycle_id: str,
        **extra: Any
    ):
        """Log DCA order executed."""
        self._log(
            logging.INFO,
            AuditEventType.DCA_EXECUTED,
            f"DCA #{dca_attempt} executed: {symbol} {dca_quantity} @ ${dca_price:.2f}, new avg ${new_average_price:.2f}",
            symbol=symbol,
            dca_attempt=dca_attempt,
            dca_price=dca_price,
            dca_quantity=dca_quantity,
            new_average_price=new_average_price,
            trigger_level=trigger_level,
            is_progressive=is_progressive,
            position_lifecycle_id=position_lifecycle_id,
            **extra
        )
    
    def dca_rejected(
        self,
        symbol: str,
        attempted_price: float,
        reason: str,
        validator: str,
        current_attempts: int,
        max_attempts: int,
        position_lifecycle_id: str,
        **extra: Any
    ):
        """Log DCA order rejected by safety validator."""
        self._log(
            logging.WARNING,
            AuditEventType.DCA_REJECTED,
            f"DCA rejected: {symbol} @ ${attempted_price:.2f}, reason: {reason}",
            symbol=symbol,
            attempted_price=attempted_price,
            reason=reason,
            validator=validator,
            current_attempts=current_attempts,
            max_attempts=max_attempts,
            position_lifecycle_id=position_lifecycle_id,
            **extra
        )
    
    # === Order Execution ===
    
    def order_placed(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str,
        limit_price: Optional[float] = None,
        is_dca_order: bool = False,
        position_lifecycle_id: Optional[str] = None,
        **extra: Any
    ):
        """Log order placed with broker."""
        price_str = f"@ ${limit_price:.2f}" if limit_price else "market"
        
        self._log(
            logging.INFO,
            AuditEventType.ORDER_PLACED,
            f"Order placed: {side} {quantity} {symbol} {price_str}",
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            is_dca_order=is_dca_order,
            position_lifecycle_id=position_lifecycle_id,
            **extra
        )
    
    def order_filled(
        self,
        symbol: str,
        side: str,
        filled_qty: float,
        filled_avg_price: float,
        order_id: str,
        fill_latency_ms: int,
        is_dca_order: bool = False,
        position_lifecycle_id: Optional[str] = None,
        **extra: Any
    ):
        """Log order filled by broker."""
        self._log(
            logging.INFO,
            AuditEventType.ORDER_FILLED,
            f"Order filled: {side} {filled_qty} {symbol} @ ${filled_avg_price:.2f} ({fill_latency_ms}ms)",
            symbol=symbol,
            side=side,
            filled_qty=filled_qty,
            filled_avg_price=filled_avg_price,
            order_id=order_id,
            fill_latency_ms=fill_latency_ms,
            is_dca_order=is_dca_order,
            position_lifecycle_id=position_lifecycle_id,
            **extra
        )
    
    def order_cancelled(
        self,
        symbol: str,
        order_id: str,
        reason: str,
        **extra: Any
    ):
        """Log order cancelled."""
        self._log(
            logging.WARNING,
            AuditEventType.ORDER_CANCELLED,
            f"Order cancelled: {symbol} order_id={order_id}, reason: {reason}",
            symbol=symbol,
            order_id=order_id,
            reason=reason,
            **extra
        )
    
    # === Risk Events ===
    
    def risk_breach(
        self,
        breach_type: str,
        severity: str,
        current_value: float,
        limit_value: float,
        affected_symbols: list,
        action_taken: str,
        **extra: Any
    ):
        """Log risk limit breach."""
        self._log(
            logging.CRITICAL,
            AuditEventType.RISK_BREACH,
            f"RISK BREACH: {breach_type} ({severity}) - {current_value:.2f} > {limit_value:.2f}, action: {action_taken}",
            breach_type=breach_type,
            severity=severity,
            current_value=current_value,
            limit_value=limit_value,
            affected_symbols=affected_symbols,
            action_taken=action_taken,
            **extra
        )
    
    def safety_check_failed(
        self,
        check_name: str,
        symbol: str,
        reason: str,
        details: Dict[str, Any],
        **extra: Any
    ):
        """Log safety check failure."""
        self._log(
            logging.WARNING,
            AuditEventType.SAFETY_CHECK_FAILED,
            f"Safety check failed: {check_name} for {symbol}, reason: {reason}",
            check_name=check_name,
            symbol=symbol,
            reason=reason,
            details=details,
            **extra
        )
    
    # === System Events ===
    
    def system_startup(
        self,
        version: str,
        config_version: str,
        components_initialized: list,
        startup_duration_ms: int,
        **extra: Any
    ):
        """Log system startup."""
        self._log(
            logging.INFO,
            AuditEventType.SYSTEM_STARTUP,
            f"System started: v{version} ({startup_duration_ms}ms)",
            version=version,
            config_version=config_version,
            components_initialized=components_initialized,
            startup_duration_ms=startup_duration_ms,
            **extra
        )
    
    def system_shutdown(
        self,
        reason: str,
        active_positions_count: int,
        pending_orders_count: int,
        uptime_seconds: int,
        **extra: Any
    ):
        """Log system shutdown."""
        self._log(
            logging.INFO,
            AuditEventType.SYSTEM_SHUTDOWN,
            f"System shutdown: reason={reason}, uptime={uptime_seconds}s",
            reason=reason,
            active_positions_count=active_positions_count,
            pending_orders_count=pending_orders_count,
            uptime_seconds=uptime_seconds,
            **extra
        )
    
    # === External API Events ===
    
    def api_call(
        self,
        api_name: str,
        method: str,
        endpoint: str,
        latency_ms: int,
        status_code: Optional[int] = None,
        **extra: Any
    ):
        """Log external API call."""
        self._log(
            logging.DEBUG,
            AuditEventType.API_CALL,
            f"API call: {method} {api_name}{endpoint} ({latency_ms}ms)",
            api_name=api_name,
            method=method,
            endpoint=endpoint,
            latency_ms=latency_ms,
            status_code=status_code,
            **extra
        )
    
    def api_error(
        self,
        api_name: str,
        method: str,
        endpoint: str,
        error: str,
        status_code: Optional[int] = None,
        retry_count: int = 0,
        **extra: Any
    ):
        """Log external API error."""
        self._log(
            logging.ERROR,
            AuditEventType.API_ERROR,
            f"API error: {method} {api_name}{endpoint} - {error}",
            api_name=api_name,
            method=method,
            endpoint=endpoint,
            error=error,
            status_code=status_code,
            retry_count=retry_count,
            **extra
        )
    
    # === Generic Audit Log ===
    
    def audit(
        self,
        event_type: AuditEventType,
        message: str,
        level: int = logging.INFO,
        **fields: Any
    ):
        """
        Generic audit log for custom events.
        
        Use when predefined templates don't fit.
        
        Args:
            event_type: Audit event type
            message: Human-readable message
            level: Logging level (default: INFO)
            **fields: Structured fields
        """
        self._log(level, event_type, message, **fields)


# === Convenience Functions ===

def get_audit_logger(component: str, logger: Optional[logging.Logger] = None) -> AuditLogger:
    """
    Get audit logger instance for a component.
    
    Args:
        component: Component name
        logger: Optional logger instance
        
    Returns:
        AuditLogger instance
        
    Example:
        audit = get_audit_logger("AdvancedStrategy")
        audit.position_opened(...)
    """
    return AuditLogger(component, logger)
