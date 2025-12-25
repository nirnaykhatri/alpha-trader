"""
Core module initialization.

Provides configuration management via Azure services (Key Vault + App Configuration)
with environment variable fallback for local development.

Also provides TaskRegistry for structured concurrency and proper task lifecycle management.
"""

from src.core.configuration import ConfigurationManager, create_configuration_manager
from src.core.logging_config import setup_logging, get_logger

# Azure-native async configuration (preferred for new code)
from src.config.azure_config_provider import (
    AzureConfigProvider,
    config_provider,
    get_secret,
    get_config,
    ConfigKeys,
    SecretKeys,
)

# Task lifecycle management
from src.core.task_registry import (
    TaskRegistry,
    TaskCategory,
    TaskInfo,
    TaskRegistryStats,
    get_task_registry,
    set_task_registry,
    reset_task_registry,
)

__all__ = [
    # Legacy sync interface (for backward compatibility)
    "ConfigurationManager",
    # Factory function for dependency injection
    "create_configuration_manager",
    
    # Logging
    "setup_logging",
    "get_logger",
    
    # Azure-native async configuration
    "AzureConfigProvider",
    "config_provider",
    "get_secret",
    "get_config",
    "ConfigKeys",
    "SecretKeys",
    
    # Task lifecycle management
    "TaskRegistry",
    "TaskCategory",
    "TaskInfo",
    "TaskRegistryStats",
    "get_task_registry",
    "set_task_registry",
    "reset_task_registry",
]
