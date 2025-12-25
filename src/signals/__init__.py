"""
Signals module initialization.
Modular refactored version with separated components.
"""

from src.signals.signal_listener import TradingViewSignalListener
from src.signals.signal_processor import WebhookSignalParser, SignalProcessor  # SignalProcessor is deprecated alias
from src.signals.webhook_handlers import WebhookHandler
from src.signals.monitoring_router import MonitoringRouter

__all__ = [
    "TradingViewSignalListener",
    "WebhookSignalParser",  # Preferred name
    "SignalProcessor",       # DEPRECATED: Use WebhookSignalParser
    "WebhookHandler",
    "MonitoringRouter"
]
