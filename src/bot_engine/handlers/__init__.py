"""
Bot Engine Handlers Module.

Extracted handler classes from BotRunner to improve maintainability
and follow Single Responsibility Principle.

Components:
- OrderHandler: Manages order placement and execution
- SignalHandler: Processes trading signals
- ConditionChecker: Evaluates trading conditions (TP, SL, DCA)

Author: Trading Bot Team
Version: 1.0.0
"""

from .order_handler import OrderHandler
from .signal_handler import SignalHandler
from .condition_checker import ConditionChecker

__all__ = [
    "OrderHandler",
    "SignalHandler", 
    "ConditionChecker",
]
