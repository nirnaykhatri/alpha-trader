"""
Configuration Management - Sync Wrapper for Azure-Native Configuration.

This module provides backward-compatible synchronous access to configuration
by wrapping the AzureConfigProvider with cached values.

For new code, use the async AzureConfigProvider directly:
    from src.config.azure_config_provider import config_provider
    value = await config_provider.get_config("key")

This legacy wrapper is maintained for backward compatibility with existing code.

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
    Synchronous configuration manager for backward compatibility.
    
    Wraps AzureConfigProvider to provide sync access via cached values.
    For new code, use AzureConfigProvider directly for async operations.
    
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
    
    Environment Variables:
        AZURE_KEYVAULT_URL: Key Vault URL for secrets
        AZURE_APP_CONFIGURATION_ENDPOINT: App Config URL for runtime settings
        
        Fallback environment variables (for local development):
        DATABASE_URL, LOG_LEVEL, ALPACA_API_KEY, etc.
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
        
        ConfigurationManager._initialized = True
        
        # Load environment variables into cache for immediate sync access
        self._load_from_environment()
        
        logger.info("ConfigurationManager initialized (sync wrapper)")
    
    def _load_from_environment(self) -> None:
        """Load configuration from environment variables."""
        # Database
        if db_url := os.environ.get("DATABASE_URL"):
            self._cache["database.url"] = db_url
        if db_echo := os.environ.get("DATABASE_ECHO"):
            self._cache["database.echo"] = db_echo.lower() in ("true", "1", "yes")
        
        # Logging
        if log_level := os.environ.get("LOG_LEVEL"):
            self._cache["logging.level"] = log_level
        if log_format := os.environ.get("LOG_FORMAT"):
            self._cache["logging.format"] = log_format
        
        # Trading
        if order_type := os.environ.get("TRADING_ORDER_TYPE"):
            self._cache["trading.order_type"] = order_type
        if paper_mode := os.environ.get("TRADING_PAPER_MODE"):
            self._cache["trading.paper_mode"] = paper_mode.lower() in ("true", "1", "yes")
        
        # Webhook
        if webhook_port := os.environ.get("WEBHOOK_PORT"):
            self._cache["api.webhook.port"] = int(webhook_port)
        if webhook_host := os.environ.get("WEBHOOK_HOST"):
            self._cache["api.webhook.host"] = webhook_host
        
        # Broker URLs
        if alpaca_url := os.environ.get("ALPACA_BASE_URL"):
            self._cache["broker.alpaca.base_url"] = alpaca_url
        
        # Secrets from environment (for local development)
        if api_key := os.environ.get("ALPACA_API_KEY"):
            self._secrets_cache["alpaca-api-key"] = api_key
        if secret_key := os.environ.get("ALPACA_SECRET_KEY"):
            self._secrets_cache["alpaca-secret-key"] = secret_key
        if webhook_secret := os.environ.get("WEBHOOK_SECRET"):
            self._secrets_cache["webhook-secret"] = webhook_secret
        if ngrok_token := os.environ.get("NGROK_AUTH_TOKEN"):
            self._secrets_cache["ngrok-auth-token"] = ngrok_token
    
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
        """Get database configuration (sync, from cache/environment)."""
        from src.config.azure_config_provider import DatabaseConfig
        
        # Try secret first (for connection string with credentials)
        db_url = self.get_secret("database-connection-string")
        if not db_url:
            db_url = self.get_config("database.url", "sqlite:///trading_bot.db")
        
        return DatabaseConfig(
            url=db_url,
            echo=bool(self.get_config("database.echo", False)),
            pool_size=int(self.get_config("database.pool_size", 5)),
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

