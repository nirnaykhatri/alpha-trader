"""
Configuration Management - Unified Configuration Access (Azure-First).

This module provides the centralized configuration manager that:
1. Implements the canonical configuration contract (single source of truth)
2. Validates configuration at startup (fail-fast)
3. Supports multiple sources with clear precedence (Key Vault > App Config > Env > Default)
4. Enables runtime configuration updates WITHOUT redeployment via Azure services

CONFIGURATION STRATEGY:
All configuration should be managed via Azure for production deployments:
- Secrets → Azure Key Vault (API keys, passwords, connection strings)
- Runtime config → Azure App Configuration (feature flags, settings)
- Local dev → Environment variables (overrides)

CONFIGURATION PRECEDENCE (highest to lowest):
    1. Azure Key Vault (secrets only)
    2. Azure App Configuration (runtime config)
    3. Environment variables
    4. Default values from ConfigContract

NOTE: Local TOML files are NOT supported. This ensures configuration can be
updated in production without requiring redeployment.

For new async code, use the async AzureConfigProvider directly:
    from src.config.azure_config_provider import config_provider
    value = await config_provider.get_config("key")

Dependency Injection Pattern:
    For testable code, use create_configuration_manager() factory:
        config = create_configuration_manager()  # Production
        config = create_configuration_manager(cache={"key": "value"})  # Testing

    The singleton pattern is preserved for backward compatibility but
    new code should use dependency injection.
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from src.interfaces import IConfigurationManager
from src.config.config_contract import ConfigContract, ConfigField, ConfigSource


logger = logging.getLogger(__name__)


def create_configuration_manager(
    cache: Optional[Dict[str, Any]] = None,
    secrets_cache: Optional[Dict[str, str]] = None,
    use_singleton: bool = True
) -> "ConfigurationManager":
    """
    Factory function for creating ConfigurationManager instances.
    
    This supports dependency injection patterns for testing while
    maintaining backward compatibility with the singleton pattern.
    
    Args:
        cache: Optional pre-populated config cache (for testing)
        secrets_cache: Optional pre-populated secrets cache (for testing)
        use_singleton: If True, returns the singleton instance (production).
                      If False, creates a new instance (testing).
    
    Returns:
        ConfigurationManager instance
        
    Usage:
        # Production - uses singleton
        config = create_configuration_manager()
        
        # Testing - creates isolated instance with mock data
        mock_config = create_configuration_manager(
            cache={"database.url": "sqlite:///test.db"},
            secrets_cache={"api-key": "test-key"},
            use_singleton=False
        )
    """
    if use_singleton:
        return ConfigurationManager()
    
    # Create non-singleton instance for testing
    instance = ConfigurationManager.__new__(ConfigurationManager)
    instance._cache = cache or {}
    instance._secrets_cache = secrets_cache or {}
    instance._azure_provider = None
    instance._azure_initialized = False
    
    # Load environment if no cache provided
    if cache is None:
        instance._load_from_environment()
    
    return instance


class ConfigurationManager(IConfigurationManager):
    """
    Unified configuration manager with contract-based validation (Azure-First).
    
    Provides sync access to configuration via cached values, with values
    resolved according to the canonical ConfigContract precedence rules.
    
    CONFIGURATION CONTRACT:
        All configuration fields are defined in src/config/config_contract.py
        which serves as the single source of truth for field names, types,
        required status, and validation rules.
    
    AZURE-FIRST STRATEGY:
        Production deployments use Azure Key Vault (secrets) and Azure App
        Configuration (runtime settings), enabling configuration updates
        WITHOUT redeployment.
    
    DEPENDENCY INJECTION:
        For testable code, use the create_configuration_manager() factory
        instead of instantiating directly. This allows injecting mock
        configurations in tests.
        
        # Production
        config = create_configuration_manager()
        
        # Testing
        config = create_configuration_manager(
            cache={"key": "test_value"},
            use_singleton=False
        )
    
    Configuration Sources (by precedence):
        1. Azure Key Vault (secrets via AZURE_KEYVAULT_URL)
        2. Azure App Configuration (via AZURE_APP_CONFIGURATION_ENDPOINT)
        3. Environment variables (using canonical env var names)
        4. Default values from ConfigContract
    """
    
    _instance: Optional["ConfigurationManager"] = None
    _initialized: bool = False
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None
        cls._initialized = False
    
    @classmethod
    def get_instance(cls) -> "ConfigurationManager":
        """
        Get the singleton instance.
        
        Prefer using create_configuration_manager() factory for new code.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __new__(cls):
        """Singleton pattern - preserved for backward compatibility."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Initialize configuration manager."""
        if ConfigurationManager._initialized:
            return
        
        # Local cache for sync access
        self._cache: Dict[str, Any] = {}
        self._secrets_cache: Dict[str, str] = {}
        
        # Azure provider (lazy initialized)
        self._azure_provider = None
        self._azure_initialized = False
        
        # Contract reference for validation
        self._contract = ConfigContract
        
        ConfigurationManager._initialized = True
        
        # Load from all available sources
        self._load_from_environment()
        self._load_from_contract_defaults()
        
        logger.info("ConfigurationManager initialized with contract-based configuration")
    
    def _load_from_environment(self) -> None:
        """
        Load configuration from environment variables using canonical names from contract.
        
        This method reads environment variables using the standardized names
        defined in ConfigContract, ensuring consistency across all config sources.
        """
        # Load all contract-defined fields from environment
        for field_name, field_def in self._contract.get_all_fields().items():
            env_var = field_def.get_env_var()
            env_value = os.environ.get(env_var)
            
            if env_value is not None:
                # Parse and cache the value
                parsed_value = self._parse_value(env_value)
                
                # Store in appropriate cache
                if field_def.secret:
                    # Also store with Key Vault name for backward compatibility
                    if field_def.key_vault_name:
                        self._secrets_cache[field_def.key_vault_name] = str(parsed_value)
                    self._secrets_cache[field_name] = str(parsed_value)
                else:
                    # Store with both canonical name and legacy paths for compatibility
                    self._cache[field_name] = parsed_value
                    if field_def.app_config_key:
                        self._cache[field_def.app_config_key] = parsed_value
        
        # Legacy mappings for backward compatibility
        # These ensure old code using dot-notation keys still works
        legacy_mappings = {
            "azure.cosmos.endpoint": "cosmos_endpoint",
            "azure.cosmos.database_name": "cosmos_database",
            "logging.level": "log_level",
            "logging.format": "log_format",
            "trading.order_type": "trading_order_type",
            "trading.paper_mode": "trading_paper_mode",
            "api.webhook.port": "webhook_port",
            "api.webhook.host": "webhook_host",
            "broker.alpaca.base_url": "alpaca_base_url",
        }
        
        for legacy_key, canonical_name in legacy_mappings.items():
            if canonical_name in self._cache and legacy_key not in self._cache:
                self._cache[legacy_key] = self._cache[canonical_name]
    
    def _load_from_contract_defaults(self) -> None:
        """Load default values from contract for fields not already set."""
        for field_name, field_def in self._contract.get_all_fields().items():
            if field_def.default is not None:
                # Only set if not already in cache
                if field_name not in self._cache and not field_def.secret:
                    self._cache[field_name] = field_def.default
                    # Also set legacy paths
                    if field_def.app_config_key and field_def.app_config_key not in self._cache:
                        self._cache[field_def.app_config_key] = field_def.default
    
    def validate_required_config(self) -> None:
        """
        Validate that all required configuration is present.
        
        This method checks the current configuration against the canonical
        contract and raises ConfigurationException if required fields are missing.
        
        Raises:
            ConfigurationException: If required configuration is missing or invalid
        """
        from src.exceptions import ConfigurationException
        
        # Collect current values using canonical names
        config_values = {}
        
        for field_name, field_def in self._contract.get_all_fields().items():
            if field_def.secret:
                # Check secrets cache
                value = self._secrets_cache.get(field_name) or self._secrets_cache.get(field_def.key_vault_name or "")
            else:
                value = self._cache.get(field_name)
            
            if value is not None:
                config_values[field_name] = value
        
        # Validate using contract
        errors = self._contract.validate_required(config_values, check_broker=True)
        
        if errors:
            error_message = self._contract.format_validation_errors(errors)
            logger.error(error_message)
            raise ConfigurationException(f"Configuration validation failed: {len(errors)} error(s)")
    
    def get_validation_status(self) -> Dict[str, Any]:
        """
        Get configuration validation status without raising exceptions.
        
        Returns:
            Dict with 'valid', 'errors', 'warnings' keys
        """
        config_values = {}
        
        for field_name, field_def in self._contract.get_all_fields().items():
            if field_def.secret:
                value = self._secrets_cache.get(field_name) or self._secrets_cache.get(field_def.key_vault_name or "")
            else:
                value = self._cache.get(field_name)
            
            if value is not None:
                config_values[field_name] = value
        
        errors = self._contract.validate_required(config_values, check_broker=False)
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "configured_fields": list(config_values.keys()),
            "missing_required": [
                f.canonical_name 
                for f in self._contract.get_required_fields()
                if f.canonical_name not in config_values
            ],
        }
    
    async def _ensure_azure_initialized(self) -> None:
        """Ensure Azure provider is initialized."""
        if self._azure_initialized:
            return
        
        try:
            from src.config.azure_config_provider import config_provider
            self._azure_provider = config_provider
            await config_provider.initialize()
            self._azure_initialized = True
            
            # Load all configs into cache
            for key in self._azure_provider._config_cache:
                self._cache[key] = self._azure_provider._config_cache[key].value
            
            logger.info("Azure configuration loaded into sync cache")
            
        except Exception as e:
            logger.warning(f"Azure config not available, using environment variables: {e}")
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value (synchronous, from cache).
        
        Priority:
        1. Local cache (from Azure App Config or environment variables)
        2. Environment variable (converted from key: database.url -> DATABASE_URL)
        3. Default value
        """
        # Check cache first
        if key in self._cache:
            return self._cache[key]
        
        # Check environment variable
        env_var = key.upper().replace(".", "_")
        if env_value := os.environ.get(env_var):
            return self._parse_value(env_value)
        
        return default
    
    def get_secret(self, name: str, default: str = "") -> str:
        """
        Get secret value (synchronous, from cache).
        
        For async access from Key Vault, use AzureConfigProvider.get_secret().
        """
        # Check cache
        if name in self._secrets_cache:
            return self._secrets_cache[name]
        
        # Check environment variable
        env_var = name.upper().replace("-", "_")
        if env_value := os.environ.get(env_var):
            return env_value
        
        return default
    
    def set_config(self, key: str, value: Any) -> None:
        """Set configuration value in local cache."""
        self._cache[key] = value
    
    def reload_config(self) -> None:
        """Reload configuration from environment variables."""
        self._cache.clear()
        self._secrets_cache.clear()
        self._load_from_environment()
        logger.info("Configuration reloaded from environment")
    
    def _parse_value(self, value: str) -> Any:
        """Parse string value to appropriate type."""
        if value is None:
            return None
        
        # Try integer
        try:
            return int(value)
        except ValueError:
            pass
        
        # Try float
        try:
            return float(value)
        except ValueError:
            pass
        
        # Boolean
        if value.lower() in ("true", "yes", "1"):
            return True
        if value.lower() in ("false", "no", "0"):
            return False
        
        return value
    
    # =========================================================================
    # Typed Access Methods (Backward Compatibility)
    # =========================================================================
    
    def get_alpaca_config(self):
        """Get Alpaca configuration (sync, from cache/environment)."""
        from src.config.azure_config_provider import AlpacaBrokerConfig
        
        return AlpacaBrokerConfig(
            api_key=self.get_secret("alpaca-api-key"),
            secret_key=self.get_secret("alpaca-secret-key"),
            base_url=self.get_config("broker.alpaca.base_url", "https://paper-api.alpaca.markets"),
            timeout=int(self.get_config("broker.alpaca.timeout", 30)),
        )
    
    def get_tastytrade_config(self):
        """Get Tastytrade configuration (sync, from cache/environment)."""
        from src.config.azure_config_provider import TastytradeBrokerConfig
        
        return TastytradeBrokerConfig(
            client_secret=self.get_secret("tastytrade-client-secret"),
            refresh_token=self.get_secret("tastytrade-refresh-token"),
            account_id=self.get_secret("tastytrade-account-id"),
            is_sandbox=bool(self.get_config("broker.tastytrade.is_sandbox", True)),
        )
    
    def get_webhook_config(self):
        """Get webhook configuration (sync, from cache/environment)."""
        from src.config.azure_config_provider import WebhookConfig
        
        return WebhookConfig(
            host=self.get_config("api.webhook.host", "0.0.0.0"),
            port=int(self.get_config("api.webhook.port", 8080)),
            security_enabled=bool(self.get_config("api.webhook.security_enabled", True)),
            secret=self.get_secret("webhook-secret"),
        )
    
    def get_database_config(self):
        """Get database configuration (Cosmos DB)."""
        from src.config.azure_config_provider import DatabaseConfig
        
        return DatabaseConfig(
            throughput_ru=int(self.get_config("database.throughput_ru", 400)),
            consistency_level=self.get_config("database.consistency_level", "Session"),
        )
    
    def get_logging_config(self):
        """Get logging configuration (sync, from cache/environment)."""
        from src.config.azure_config_provider import LoggingConfig
        
        return LoggingConfig(
            level=self.get_config("logging.level", "INFO"),
            format=self.get_config("logging.format", "json"),
            file=self.get_config("logging.file", "logs/trading_bot.log"),
            console_enabled=bool(self.get_config("logging.console_enabled", True)),
        )
    
    def get_configured_brokers(self) -> List[str]:
        """Get list of configured brokers."""
        configured = []
        
        alpaca = self.get_alpaca_config()
        if alpaca.is_configured:
            configured.append("alpaca")
        
        tastytrade = self.get_tastytrade_config()
        if tastytrade.is_configured:
            configured.append("tastytrade")
        
        return configured
    
    def get_broker_for_symbol(self, symbol: str) -> str:
        """Get broker to use for a symbol."""
        # Check symbol-specific config
        broker = self.get_config(f"symbols.{symbol}.broker")
        if broker:
            return broker
        
        # Default broker
        return self.get_config("broker.default", "alpaca")
    
    @property
    def current_environment(self) -> str:
        """Get current environment."""
        return os.environ.get("ENVIRONMENT", "demo")
    
    def is_azure_deployment(self) -> bool:
        """Check if running in Azure."""
        return bool(
            os.environ.get("AZURE_KEYVAULT_URL") or
            os.environ.get("AZURE_APP_CONFIGURATION_ENDPOINT")
        )

