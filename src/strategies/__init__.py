"""
Strategies module initialization.
"""

from src.strategies.trailing_profit import ConfigurableTrailingProfitManager
from src.strategies.config_accessor import StrategyConfigAccessor

__all__ = [
    "ConfigurableTrailingProfitManager",
    "StrategyConfigAccessor"
]
