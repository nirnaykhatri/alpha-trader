"""
Strategies module initialization.
"""

from .support_calculator import TechnicalSupportCalculator
from .trailing_profit import ConfigurableTrailingProfitManager

__all__ = ["TechnicalSupportCalculator", "ConfigurableTrailingProfitManager"]
