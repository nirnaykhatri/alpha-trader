"""Configuration management implementation.

This module provides backward-compatible access to the configuration system.
The implementation delegates to src.config.settings which uses Dynaconf for
layered TOML configuration with environment support.

.. deprecated::
    This module is DEPRECATED. New code should import from src.config.settings:
    
        from src.config.settings import ConfigurationManager, get_config
    
    This legacy wrapper will be removed in a future version.
"""

import warnings

from typing import Any, Dict, Optional

from src.interfaces import IConfigurationManager
from src.exceptions import ConfigurationException


# Import the new Dynaconf-based implementation
from src.config.settings import (
    ConfigurationManager as DynaconfConfigManager,
    validate_startup,
)


class ConfigurationManager(IConfigurationManager):
    """
    Configuration manager providing backward-compatible interface.
    
    Delegates to the new Dynaconf-based ConfigurationManager while maintaining
    the legacy API for existing code.
    """
    
    _instance: Optional['ConfigurationManager'] = None
    _initialized: bool = False
    
    @classmethod
    def reset_instance(cls) -> None:
        """
        Reset the singleton instance.
        
        This is primarily used for testing to ensure a clean state between tests.
        """
        cls._instance = None
        cls._initialized = False
        DynaconfConfigManager.reset_instance()
    
    def __new__(cls, config_file: Optional[str] = None):
        """
        Create or return existing singleton instance.
        
        Args:
            config_file: Ignored - retained for backward compatibility
            
        Returns:
            Singleton ConfigurationManager instance
        """
        if cls._instance is None:
            cls._instance = super(ConfigurationManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize configuration manager (only runs once).
        
        Args:
            config_file: Ignored - configuration now loaded from config/ directory
            
        .. deprecated::
            Use src.config.settings.ConfigurationManager instead.
        """
        if self._initialized:
            return
        
        # Emit deprecation warning on first initialization
        warnings.warn(
            "src.core.configuration.ConfigurationManager is deprecated. "
            "Use src.config.settings.ConfigurationManager instead.",
            DeprecationWarning,
            stacklevel=3
        )
        
        # Use the new Dynaconf-based manager
        self._manager = DynaconfConfigManager()
        self._initialized = True
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key.
        
        Supports dot notation for accessing nested configuration values.
        
        Args:
            key: Configuration key (supports dot notation, e.g., "api.alpaca.api_key")
            default: Default value to return if the key is not found.
            
        Returns:
            The configuration value if found, otherwise the default value.
        """
        if not key or not isinstance(key, str):
            raise ConfigurationException("Configuration key must be a non-empty string")
        
        return self._manager.get_config(key, default)
    
    def set_config(self, key: str, value: Any) -> None:
        """
        Set configuration value at runtime.
        
        Note: Changes are not persisted to files.
        
        Args:
            key: Configuration key (supports dot notation)
            value: Value to set
        """
        self._manager.set_config(key, value)
    
    def reload_config(self) -> None:
        """Reload configuration from all sources."""
        self._manager.reload_config()
    
    def get_all_config(self) -> Dict[str, Any]:
        """
        Get all configuration as dictionary.
        
        Returns:
            Dictionary containing all configuration values
        """
        # Build a dict from common config paths
        settings = self._manager._settings
        
        # Return the settings as a dict
        if hasattr(settings, 'as_dict'):
            return settings.as_dict()
        
        # Fallback: build from known top-level keys
        result = {}
        top_level_keys = ['api', 'ngrok', 'trading', 'strategies', 'logging', 
                         'database', 'monitoring', 'symbols', 'performance',
                         'data', 'development', 'extended_hours', 'risk',
                         'resilience', 'confidence', 'technical_analysis']
        
        for key in top_level_keys:
            value = self.get_config(key)
            if value is not None:
                result[key] = value
        
        return result
    
    def validate_required_config(self) -> None:
        """
        Validate that all required configuration is present.
        
        Raises:
            ConfigurationException: If validation fails
        """
        issues = validate_startup()
        errors = [i for i in issues if i.severity == "ERROR"]
        
        if errors:
            error_messages = [str(e) for e in errors]
            raise ConfigurationException(
                f"Configuration validation failed: {'; '.join(error_messages)}"
            )
    
    # Additional methods for typed access (delegate to new manager)
    
    def get_alpaca_config(self):
        """Get validated Alpaca broker configuration."""
        return self._manager.get_alpaca_config()
    
    def get_tastytrade_config(self):
        """Get validated Tastytrade broker configuration."""
        return self._manager.get_tastytrade_config()
    
    def get_webhook_config(self):
        """Get validated webhook configuration."""
        return self._manager.get_webhook_config()
    
    def get_broker_for_symbol(self, symbol: str) -> str:
        """Get the broker to use for a specific symbol."""
        return self._manager.get_broker_for_symbol(symbol)
    
    def get_configured_brokers(self):
        """Get list of properly configured brokers."""
        return self._manager.get_configured_brokers()
    
    def load_profile(self, profile_name: str) -> None:
        """Load a risk profile to override current settings."""
        self._manager.load_profile(profile_name)
    
    @property
    def current_profile(self) -> Optional[str]:
        """Get currently loaded risk profile name."""
        return self._manager.current_profile
    
    @property
    def current_environment(self) -> str:
        """Get current environment (demo/live)."""
        return self._manager.current_environment

