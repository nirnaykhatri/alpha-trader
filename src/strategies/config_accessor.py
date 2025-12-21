"""
Strategy Configuration Accessor

Centralized helper for accessing strategy-specific configuration values
to eliminate duplication and provide consistent config access patterns.
"""

from typing import Any, Optional
from src.interfaces import IConfigurationManager


class StrategyConfigAccessor:
    """
    Centralized configuration accessor for strategy components.
    
    Provides typed, documented methods for accessing strategy configuration
    with sensible defaults, eliminating duplicate config.get() calls.
    """
    
    def __init__(self, config: IConfigurationManager):
        """
        Initialize configuration accessor.
        
        Args:
            config: Configuration manager instance
        """
        self.config = config
    
    # DCA Configuration
    def get_min_support_confidence(self, default: float = 0.70) -> float:
        """Get minimum confidence threshold for support levels."""
        return self.config.get('strategies.dca.min_support_confidence', default)
    
    def get_min_resistance_confidence(self, default: float = 0.70) -> float:
        """Get minimum confidence threshold for resistance levels."""
        return self.config.get('strategies.dca.min_resistance_confidence', default)
    
    def get_support_buffer_percent(self, default: float = 0.005) -> float:
        """Get support level breach buffer (0.5% default)."""
        return self.config.get('strategies.dca.support_buffer_percent', default)
    
    def get_resistance_buffer_percent(self, default: float = 0.005) -> float:
        """Get resistance level breach buffer (0.5% default)."""
        return self.config.get('strategies.dca.resistance_buffer_percent', default)
    
    def get_max_dca_attempts(self, direction: str, default: int = 3) -> int:
        """
        Get maximum DCA attempts for a direction.
        
        Args:
            direction: 'long' or 'short'
            default: Default max attempts if not configured
            
        Returns:
            Maximum number of DCA attempts allowed
        """
        key = f'strategies.{direction}_strategy.support_averaging.max_attempts' if direction == 'long' \
              else f'strategies.{direction}_strategy.resistance_averaging.max_attempts'
        return self.config.get(key, default)
    
    # Sizing Configuration
    def get_entry_size(self, direction: str, default: float = 5000.0) -> float:
        """
        Get default entry position size.
        
        Args:
            direction: 'long' or 'short'
            default: Default size in dollars
            
        Returns:
            Position size in dollars
        """
        key = f'strategies.{direction}_strategy.entry.size'
        return self.config.get(key, default)
    
    def get_dca_multiplier(self, direction: str, default: float = 1.5) -> float:
        """
        Get DCA size multiplier.
        
        Args:
            direction: 'long' or 'short'
            default: Default multiplier (1.5x)
            
        Returns:
            Multiplier for DCA order sizes
        """
        key = f'strategies.{direction}_strategy.support_averaging.multiplier' if direction == 'long' \
              else f'strategies.{direction}_strategy.resistance_averaging.multiplier'
        return self.config.get(key, default)
    
    # Feature Flags
    def is_dca_enabled(self, direction: str, default: bool = True) -> bool:
        """
        Check if DCA is enabled for a direction.
        
        Args:
            direction: 'long' or 'short'
            default: Default enabled state
            
        Returns:
            True if DCA is enabled
        """
        key = f'strategies.{direction}_strategy.support_averaging.enabled' if direction == 'long' \
              else f'strategies.{direction}_strategy.resistance_averaging.enabled'
        return self.config.get(key, default)
    
    # Generic accessor for custom paths
    def get(self, key: str, default: Any = None) -> Any:
        """
        Generic configuration accessor.
        
        Args:
            key: Dot-separated configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        return self.config.get(key, default)
