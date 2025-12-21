"""
Trading-specific event definitions.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional
from datetime import datetime

from src.events.event_bus import Event, EventPriority


@dataclass
class OrderFilledEvent(Event):
    """Event fired when an order is filled."""
    
    def __init__(
        self,
        order_id: str,
        symbol: str,
        side: str,
        filled_qty: float,
        filled_price: float,
        is_dca_order: bool = False,
        position_lifecycle_id: Optional[str] = None,
        **kwargs
    ):
        super().__init__(
            event_type="order_filled",
            priority=EventPriority.HIGH,
            data={
                "order_id": order_id,
                "symbol": symbol,
                "side": side,
                "filled_qty": filled_qty,
                "filled_price": filled_price,
                "is_dca_order": is_dca_order,
                "position_lifecycle_id": position_lifecycle_id
            },
            **kwargs
        )


@dataclass
class PositionOpenedEvent(Event):
    """Event fired when a new position is opened."""
    
    def __init__(
        self,
        symbol: str,
        direction: str,
        quantity: float,
        entry_price: float,
        position_lifecycle_id: str,
        **kwargs
    ):
        super().__init__(
            event_type="position_opened",
            priority=EventPriority.HIGH,
            data={
                "symbol": symbol,
                "direction": direction,
                "quantity": quantity,
                "entry_price": entry_price,
                "position_lifecycle_id": position_lifecycle_id
            },
            **kwargs
        )


@dataclass
class PositionClosedEvent(Event):
    """Event fired when a position is closed."""
    
    def __init__(
        self,
        symbol: str,
        direction: str,
        quantity: float,
        entry_price: float,
        exit_price: float,
        pnl: float,
        pnl_percent: float,
        position_lifecycle_id: str,
        **kwargs
    ):
        super().__init__(
            event_type="position_closed",
            priority=EventPriority.HIGH,
            data={
                "symbol": symbol,
                "direction": direction,
                "quantity": quantity,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "pnl": pnl,
                "pnl_percent": pnl_percent,
                "position_lifecycle_id": position_lifecycle_id
            },
            **kwargs
        )


@dataclass
class RiskLimitReachedEvent(Event):
    """Event fired when a risk limit is reached."""
    
    def __init__(
        self,
        limit_type: str,
        symbol: Optional[str],
        current_value: float,
        limit_value: float,
        severity: str = "warning",
        **kwargs
    ):
        priority_map = {
            "info": EventPriority.LOW,
            "warning": EventPriority.NORMAL,
            "error": EventPriority.HIGH,
            "critical": EventPriority.CRITICAL
        }
        
        super().__init__(
            event_type="risk_limit_reached",
            priority=priority_map.get(severity, EventPriority.NORMAL),
            data={
                "limit_type": limit_type,
                "symbol": symbol,
                "current_value": current_value,
                "limit_value": limit_value,
                "severity": severity
            },
            **kwargs
        )


@dataclass
class DCAExecutedEvent(Event):
    """Event fired when a DCA order is executed."""
    
    def __init__(
        self,
        symbol: str,
        support_level: float,
        dca_quantity: float,
        dca_price: float,
        attempt_number: int,
        is_progressive: bool,
        position_lifecycle_id: str,
        **kwargs
    ):
        super().__init__(
            event_type="dca_executed",
            priority=EventPriority.HIGH,
            data={
                "symbol": symbol,
                "support_level": support_level,
                "dca_quantity": dca_quantity,
                "dca_price": dca_price,
                "attempt_number": attempt_number,
                "is_progressive": is_progressive,
                "position_lifecycle_id": position_lifecycle_id
            },
            **kwargs
        )


@dataclass
class MarketDataUpdateEvent(Event):
    """Event fired when market data is updated."""
    
    def __init__(
        self,
        symbol: str,
        price: float,
        volume: Optional[float] = None,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        **kwargs
    ):
        super().__init__(
            event_type="market_data_update",
            priority=EventPriority.NORMAL,
            data={
                "symbol": symbol,
                "price": price,
                "volume": volume,
                "bid": bid,
                "ask": ask
            },
            **kwargs
        )
