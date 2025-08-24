"""
Strategies module initialization.
"""

from .support_calculator import TechnicalSupportCalculator
from .trailing_profit import ConfigurableTrailingProfitManager
from .martingale_dca_manager import MartingaleDCAManager

__all__ = ["TechnicalSupportCalculator", "ConfigurableTrailingProfitManager", "MartingaleDCAManager"]
