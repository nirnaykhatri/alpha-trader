"""
Configuration management module.

This module provides configuration access via Azure services:
- Azure Key Vault: Secrets (API keys, connection strings)
- Azure App Configuration: Runtime settings (hot-reload support)
- Managed Identity: Authentication (no connection strings in code)

Quick Usage:
    # Async (preferred for Azure-native)
    from src.config.azure_config_provider import config_provider, get_config, get_secret
    
    await config_provider.initialize()
    api_key = await get_secret("alpaca-api-key")
    db_url = await get_config("database.url")
    
    # Sync (backward compatibility, uses environment variables)
    from src.core import ConfigurationManager
    
    config = ConfigurationManager()
    value = config.get_config("database.url")

Environment Variables (local development fallback):
    AZURE_KEYVAULT_URL: Key Vault URL
    AZURE_APP_CONFIGURATION_ENDPOINT: App Config URL
    DATABASE_URL, LOG_LEVEL, ALPACA_API_KEY, etc.

Configuration Contract:
    All configuration fields are defined in src/config/config_contract.py
    which serves as the single source of truth for field names, types,
    required status, and validation rules.
"""

from src.config.azure_config_provider import (
    AzureConfigProvider,
    config_provider,
    get_config,
    get_secret,
    ConfigKeys,
    SecretKeys,
    DEFAULT_CONFIG,
    AlpacaBrokerConfig,
    TastytradeBrokerConfig,
    WebhookConfig,
    DatabaseConfig,
    LoggingConfig,
)

# Import contract for type-safe config access
from src.config.config_contract import (
    ConfigContract,
    ConfigField,
    ConfigCategory,
    ConfigSource,
)

# Note: ConfigurationManager is imported from src.core to avoid circular imports
# Use: from src.core import ConfigurationManager

__all__ = [
    # Azure-native async configuration
    "AzureConfigProvider",
    "config_provider",
    "get_config",
    "get_secret",
    "ConfigKeys",
    "SecretKeys",
    "DEFAULT_CONFIG",
    
    # Configuration contract
    "ConfigContract",
    "ConfigField",
    "ConfigCategory",
    "ConfigSource",
    
    # Configuration data classes
    "AlpacaBrokerConfig",
    "TastytradeBrokerConfig",
    "WebhookConfig",
    "DatabaseConfig",
    "LoggingConfig",
]
