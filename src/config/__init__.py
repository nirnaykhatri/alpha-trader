"""
Configuration management module.

This module provides configuration access via Dynaconf with Pydantic validation.

Quick Usage:
    from src.config.settings import ConfigurationManager, get_config
    
    config = ConfigurationManager()
    value = config.get_config("trading.order_type")
    
    # Or use the convenience function
    value = get_config("trading.order_type")

For backward compatibility, you can also import from src.core:
    from src.core import ConfigurationManager
"""

from src.config.settings import (
    ConfigurationManager,
    get_config,
    get_settings,
    reload_settings,
    validate_startup,
    validate_and_exit_on_error,
    AlpacaBrokerConfig,
    TastytradeBrokerConfig,
    SymbolConfig,
    WebhookConfig,
    PositionSizingConfig,
    ConfigValidationError,
    BrokerNotConfiguredError,
    MissingConfigFileError,
    ValidationIssue,
    VALID_ENVIRONMENTS,
    VALID_BROKERS,
    VALID_RISK_PROFILES,
)

__all__ = [
    # Main classes
    "ConfigurationManager",
    
    # Convenience functions
    "get_config",
    "get_settings",
    "reload_settings",
    
    # Validation
    "validate_startup",
    "validate_and_exit_on_error",
    
    # Pydantic models
    "AlpacaBrokerConfig",
    "TastytradeBrokerConfig",
    "SymbolConfig",
    "WebhookConfig",
    "PositionSizingConfig",
    
    # Exceptions
    "ConfigValidationError",
    "BrokerNotConfiguredError",
    "MissingConfigFileError",
    "ValidationIssue",
    
    # Constants
    "VALID_ENVIRONMENTS",
    "VALID_BROKERS",
    "VALID_RISK_PROFILES",
]
