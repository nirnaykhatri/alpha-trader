"""
Azure-Native Configuration Provider.

Provides centralized configuration management using Azure services:
- Azure Key Vault: Secrets (API keys, connection strings)
- Azure App Configuration: Runtime settings (changeable without deployment)
- Managed Identity: Authentication (no connection strings in code)

This replaces TOML-based configuration for Azure deployments.

Usage:
    config = AzureConfigProvider()
    await config.initialize()
    
    # Get secrets from Key Vault
    api_key = await config.get_secret("alpaca-api-key")
    
    # Get runtime config from App Configuration
    db_url = await config.get_config("database.url")
    
    # Register for hot-reload
    config.on_change(my_callback)

Environment Variables (for local development fallback):
    AZURE_KEYVAULT_URL: Key Vault URL (https://<name>.vault.azure.net)
    AZURE_APP_CONFIGURATION_ENDPOINT: App Config URL (https://<name>.azconfig.io)
    AZURE_APP_CONFIGURATION_LABEL: Config label (default: same as environment)
    
    For local development without Azure:
    ALPACA_API_KEY, ALPACA_SECRET_KEY, etc.
    DATABASE_URL, LOG_LEVEL, etc.
"""

import os
import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration Keys (Constants)
# ============================================================================

class ConfigKeys:
    """
    Configuration key constants for type-safe access.
    
    All runtime configuration keys are defined here to prevent typos
    and provide IntelliSense support.
    """
    
    # Database
    DATABASE_URL = "database.url"
    DATABASE_ECHO = "database.echo"
    DATABASE_POOL_SIZE = "database.pool_size"
    
    # Logging
    LOG_LEVEL = "logging.level"
    LOG_FORMAT = "logging.format"
    LOG_FILE = "logging.file"
    LOG_CONSOLE = "logging.console_enabled"
    
    # Trading
    TRADING_ORDER_TYPE = "trading.order_type"
    TRADING_LIMIT_OFFSET = "trading.limit_order_offset"
    TRADING_MAX_DAILY_TRADES = "trading.max_daily_trades"
    TRADING_PAPER_MODE = "trading.paper_mode"
    
    # Webhook
    WEBHOOK_HOST = "api.webhook.host"
    WEBHOOK_PORT = "api.webhook.port"
    WEBHOOK_SECURITY_ENABLED = "api.webhook.security_enabled"
    
    # Monitoring
    MONITORING_ENABLED = "monitoring.enabled"
    MONITORING_METRICS_PORT = "monitoring.metrics_port"
    MONITORING_HEALTH_CHECK_INTERVAL = "monitoring.health_check_interval"
    
    # Broker settings
    BROKER_DEFAULT = "broker.default"
    ALPACA_BASE_URL = "broker.alpaca.base_url"
    ALPACA_TIMEOUT = "broker.alpaca.timeout"
    TASTYTRADE_SANDBOX = "broker.tastytrade.is_sandbox"


class SecretKeys:
    """
    Secret key constants for Key Vault access.
    
    These are the names of secrets stored in Azure Key Vault.
    """
    
    # Alpaca
    ALPACA_API_KEY = "alpaca-api-key"
    ALPACA_SECRET_KEY = "alpaca-secret-key"
    
    # Tastytrade
    TASTYTRADE_CLIENT_SECRET = "tastytrade-client-secret"
    TASTYTRADE_REFRESH_TOKEN = "tastytrade-refresh-token"
    TASTYTRADE_ACCOUNT_ID = "tastytrade-account-id"
    
    # Webhook
    WEBHOOK_SECRET = "webhook-secret"
    
    # Ngrok
    NGROK_AUTH_TOKEN = "ngrok-auth-token"
    
    # Database (if using connection string with password)
    DATABASE_CONNECTION_STRING = "database-connection-string"


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class CachedValue:
    """Cached configuration value with metadata."""
    value: Any
    etag: Optional[str]
    last_modified: Optional[datetime]
    cached_at: datetime


@dataclass 
class AlpacaBrokerConfig:
    """Alpaca broker configuration."""
    api_key: str
    secret_key: str
    base_url: str = "https://paper-api.alpaca.markets"
    timeout: int = 30
    max_retries: int = 3
    
    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.secret_key)
    
    @property
    def is_paper(self) -> bool:
        return "paper" in self.base_url.lower()


@dataclass
class TastytradeBrokerConfig:
    """Tastytrade broker configuration."""
    client_secret: str
    refresh_token: str
    account_id: str = ""
    is_sandbox: bool = True
    
    @property
    def is_configured(self) -> bool:
        return bool(self.client_secret and self.refresh_token)


@dataclass
class WebhookConfig:
    """Webhook server configuration."""
    host: str = "0.0.0.0"
    port: int = 8080
    security_enabled: bool = True
    secret: str = ""


@dataclass
class DatabaseConfig:
    """Database configuration."""
    url: str
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    format: str = "json"
    file: str = "logs/trading_bot.log"
    console_enabled: bool = True


# ============================================================================
# Default Values
# ============================================================================

DEFAULT_CONFIG: Dict[str, Any] = {
    # Database
    ConfigKeys.DATABASE_URL: "sqlite:///trading_bot.db",
    ConfigKeys.DATABASE_ECHO: False,
    ConfigKeys.DATABASE_POOL_SIZE: 5,
    
    # Logging
    ConfigKeys.LOG_LEVEL: "INFO",
    ConfigKeys.LOG_FORMAT: "json",
    ConfigKeys.LOG_FILE: "logs/trading_bot.log",
    ConfigKeys.LOG_CONSOLE: True,
    
    # Trading
    ConfigKeys.TRADING_ORDER_TYPE: "limit",
    ConfigKeys.TRADING_LIMIT_OFFSET: 0.001,
    ConfigKeys.TRADING_MAX_DAILY_TRADES: 50,
    ConfigKeys.TRADING_PAPER_MODE: True,
    
    # Webhook
    ConfigKeys.WEBHOOK_HOST: "0.0.0.0",
    ConfigKeys.WEBHOOK_PORT: 8080,
    ConfigKeys.WEBHOOK_SECURITY_ENABLED: True,
    
    # Monitoring
    ConfigKeys.MONITORING_ENABLED: True,
    ConfigKeys.MONITORING_METRICS_PORT: 9090,
    ConfigKeys.MONITORING_HEALTH_CHECK_INTERVAL: 30,
    
    # Broker
    ConfigKeys.BROKER_DEFAULT: "alpaca",
    ConfigKeys.ALPACA_BASE_URL: "https://paper-api.alpaca.markets",
    ConfigKeys.ALPACA_TIMEOUT: 30,
    ConfigKeys.TASTYTRADE_SANDBOX: True,
}


# ============================================================================
# Azure Configuration Provider
# ============================================================================

class AzureConfigProvider:
    """
    Azure-native configuration provider.
    
    Uses Managed Identity to authenticate with:
    - Azure Key Vault (secrets)
    - Azure App Configuration (runtime config)
    
    For local development, falls back to environment variables.
    
    Thread-Safety:
        Safe for concurrent async operations.
        
    Hot-Reload:
        Runtime configuration from App Configuration supports hot-reload.
        Register callbacks with on_change() to react to config updates.
    """
    
    _instance: Optional["AzureConfigProvider"] = None
    
    def __new__(cls) -> "AzureConfigProvider":
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        if cls._instance:
            cls._instance._initialized = False
        cls._instance = None
    
    def __init__(self):
        """Initialize provider (only runs once)."""
        if getattr(self, '_initialized', False):
            return
        
        # Azure service URLs from environment
        self._keyvault_url = os.environ.get("AZURE_KEYVAULT_URL", "")
        self._app_config_endpoint = os.environ.get("AZURE_APP_CONFIGURATION_ENDPOINT", "")
        self._app_config_label = os.environ.get("AZURE_APP_CONFIGURATION_LABEL", "")
        
        # Azure clients (lazy initialized)
        self._credential = None
        self._keyvault_client = None
        self._app_config_client = None
        
        # Caches
        self._secret_cache: Dict[str, CachedValue] = {}
        self._config_cache: Dict[str, CachedValue] = {}
        
        # Change callbacks
        self._change_callbacks: List[Callable[[str, Any, Any], None]] = []
        
        # Refresh task
        self._refresh_task: Optional[asyncio.Task] = None
        self._refresh_interval = 30  # seconds
        
        self._initialized = True
        
        logger.info(
            f"AzureConfigProvider initialized: "
            f"keyvault={'configured' if self._keyvault_url else 'not configured'}, "
            f"app_config={'configured' if self._app_config_endpoint else 'not configured'}"
        )
    
    @property
    def is_azure_configured(self) -> bool:
        """Check if Azure services are configured."""
        return bool(self._keyvault_url or self._app_config_endpoint)
    
    @property
    def is_keyvault_configured(self) -> bool:
        """Check if Key Vault is configured."""
        return bool(self._keyvault_url)
    
    @property
    def is_app_config_configured(self) -> bool:
        """Check if App Configuration is configured."""
        return bool(self._app_config_endpoint)
    
    @property
    def current_environment(self) -> str:
        """Get current environment label."""
        return self._app_config_label or os.environ.get("ENVIRONMENT", "demo")
    
    async def initialize(self) -> None:
        """
        Initialize Azure clients using Managed Identity.
        
        Call this at application startup.
        """
        if self._credential is not None:
            return
        
        try:
            from azure.identity.aio import DefaultAzureCredential
            
            # Use DefaultAzureCredential (Managed Identity in Azure, CLI locally)
            self._credential = DefaultAzureCredential()
            
            # Initialize Key Vault client
            if self._keyvault_url:
                from azure.keyvault.secrets.aio import SecretClient
                self._keyvault_client = SecretClient(
                    vault_url=self._keyvault_url,
                    credential=self._credential
                )
                logger.info(f"✅ Key Vault client initialized: {self._keyvault_url}")
            
            # Initialize App Configuration client
            if self._app_config_endpoint:
                from azure.appconfiguration.aio import AzureAppConfigurationClient
                self._app_config_client = AzureAppConfigurationClient(
                    base_url=self._app_config_endpoint,
                    credential=self._credential
                )
                logger.info(f"✅ App Configuration client initialized: {self._app_config_endpoint}")
                
                # Load initial configuration
                await self._load_all_configs()
            
        except ImportError as e:
            logger.warning(
                f"Azure SDK not installed ({e}). Using environment variables only. "
                "Install with: pip install azure-identity azure-keyvault-secrets azure-appconfiguration"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Azure clients: {e}")
            # Continue without Azure - will fall back to env vars
    
    async def close(self) -> None:
        """Close Azure clients and stop refresh task."""
        try:
            if self._refresh_task:
                self._refresh_task.cancel()
                try:
                    await self._refresh_task
                except asyncio.CancelledError:
                    pass
                self._refresh_task = None
            
            if self._keyvault_client:
                await self._keyvault_client.close()
                self._keyvault_client = None
            
            if self._app_config_client:
                await self._app_config_client.close()
                self._app_config_client = None
            
            if self._credential:
                await self._credential.close()
                self._credential = None
            
            self._secret_cache.clear()
            self._config_cache.clear()
            
            logger.info("Azure config provider closed")
            
        except Exception as e:
            logger.error(f"Error closing Azure config provider: {e}")
    
    # =========================================================================
    # Secret Access (Key Vault)
    # =========================================================================
    
    async def get_secret(self, name: str, default: str = "") -> str:
        """
        Get a secret from Azure Key Vault.
        
        Falls back to environment variable if Key Vault not configured.
        
        Args:
            name: Secret name in Key Vault (e.g., "alpaca-api-key")
            default: Default value if not found
            
        Returns:
            Secret value
        """
        # Check cache first
        if name in self._secret_cache:
            return self._secret_cache[name].value
        
        # Try Key Vault
        if self._keyvault_client:
            try:
                secret = await self._keyvault_client.get_secret(name)
                value = secret.value or default
                
                self._secret_cache[name] = CachedValue(
                    value=value,
                    etag=secret.properties.version,
                    last_modified=secret.properties.updated_on,
                    cached_at=datetime.utcnow()
                )
                
                logger.debug(f"Retrieved secret from Key Vault: {name}")
                return value
                
            except Exception as e:
                logger.warning(f"Failed to get secret '{name}' from Key Vault: {e}")
        
        # Fall back to environment variable
        # Convert key-vault-name to ENV_VAR_NAME
        env_var = name.upper().replace("-", "_")
        value = os.environ.get(env_var, default)
        
        if value != default:
            logger.debug(f"Using environment variable for secret: {env_var}")
        
        return value
    
    async def get_alpaca_config(self) -> AlpacaBrokerConfig:
        """Get Alpaca broker configuration from secrets and config."""
        return AlpacaBrokerConfig(
            api_key=await self.get_secret(SecretKeys.ALPACA_API_KEY),
            secret_key=await self.get_secret(SecretKeys.ALPACA_SECRET_KEY),
            base_url=await self.get_config(ConfigKeys.ALPACA_BASE_URL, DEFAULT_CONFIG[ConfigKeys.ALPACA_BASE_URL]),
            timeout=int(await self.get_config(ConfigKeys.ALPACA_TIMEOUT, DEFAULT_CONFIG[ConfigKeys.ALPACA_TIMEOUT])),
        )
    
    async def get_tastytrade_config(self) -> TastytradeBrokerConfig:
        """Get Tastytrade broker configuration from secrets and config."""
        return TastytradeBrokerConfig(
            client_secret=await self.get_secret(SecretKeys.TASTYTRADE_CLIENT_SECRET),
            refresh_token=await self.get_secret(SecretKeys.TASTYTRADE_REFRESH_TOKEN),
            account_id=await self.get_secret(SecretKeys.TASTYTRADE_ACCOUNT_ID),
            is_sandbox=bool(await self.get_config(ConfigKeys.TASTYTRADE_SANDBOX, DEFAULT_CONFIG[ConfigKeys.TASTYTRADE_SANDBOX])),
        )
    
    async def get_webhook_config(self) -> WebhookConfig:
        """Get webhook server configuration."""
        return WebhookConfig(
            host=await self.get_config(ConfigKeys.WEBHOOK_HOST, DEFAULT_CONFIG[ConfigKeys.WEBHOOK_HOST]),
            port=int(await self.get_config(ConfigKeys.WEBHOOK_PORT, DEFAULT_CONFIG[ConfigKeys.WEBHOOK_PORT])),
            security_enabled=bool(await self.get_config(ConfigKeys.WEBHOOK_SECURITY_ENABLED, DEFAULT_CONFIG[ConfigKeys.WEBHOOK_SECURITY_ENABLED])),
            secret=await self.get_secret(SecretKeys.WEBHOOK_SECRET),
        )
    
    async def get_database_config(self) -> DatabaseConfig:
        """Get database configuration."""
        # Try secret first for connection string with credentials
        db_url = await self.get_secret(SecretKeys.DATABASE_CONNECTION_STRING)
        if not db_url:
            db_url = await self.get_config(ConfigKeys.DATABASE_URL, DEFAULT_CONFIG[ConfigKeys.DATABASE_URL])
        
        return DatabaseConfig(
            url=db_url,
            echo=bool(await self.get_config(ConfigKeys.DATABASE_ECHO, DEFAULT_CONFIG[ConfigKeys.DATABASE_ECHO])),
            pool_size=int(await self.get_config(ConfigKeys.DATABASE_POOL_SIZE, DEFAULT_CONFIG[ConfigKeys.DATABASE_POOL_SIZE])),
        )
    
    async def get_logging_config(self) -> LoggingConfig:
        """Get logging configuration."""
        return LoggingConfig(
            level=await self.get_config(ConfigKeys.LOG_LEVEL, DEFAULT_CONFIG[ConfigKeys.LOG_LEVEL]),
            format=await self.get_config(ConfigKeys.LOG_FORMAT, DEFAULT_CONFIG[ConfigKeys.LOG_FORMAT]),
            file=await self.get_config(ConfigKeys.LOG_FILE, DEFAULT_CONFIG[ConfigKeys.LOG_FILE]),
            console_enabled=bool(await self.get_config(ConfigKeys.LOG_CONSOLE, DEFAULT_CONFIG[ConfigKeys.LOG_CONSOLE])),
        )
    
    async def get_configured_brokers(self) -> List[str]:
        """Get list of configured brokers."""
        configured = []
        
        alpaca = await self.get_alpaca_config()
        if alpaca.is_configured:
            configured.append("alpaca")
        
        tastytrade = await self.get_tastytrade_config()
        if tastytrade.is_configured:
            configured.append("tastytrade")
        
        return configured
    
    # =========================================================================
    # Runtime Config Access (App Configuration)
    # =========================================================================
    
    async def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value from Azure App Configuration.
        
        Falls back to environment variable if App Config not configured.
        
        Args:
            key: Configuration key (e.g., "database.url")
            default: Default value if not found
            
        Returns:
            Configuration value
        """
        # Check cache first
        if key in self._config_cache:
            return self._config_cache[key].value
        
        # Try App Configuration
        if self._app_config_client:
            try:
                setting = await self._app_config_client.get_configuration_setting(
                    key=key,
                    label=self._app_config_label or None
                )
                
                value = self._parse_value(setting.value, setting.content_type)
                
                self._config_cache[key] = CachedValue(
                    value=value,
                    etag=setting.etag,
                    last_modified=setting.last_modified,
                    cached_at=datetime.utcnow()
                )
                
                logger.debug(f"Retrieved config from App Configuration: {key}")
                return value
                
            except Exception as e:
                # Key not found or error - fall through to defaults
                logger.debug(f"Config '{key}' not in App Configuration: {e}")
        
        # Fall back to environment variable
        # Convert dot.notation to ENV_VAR_NAME
        env_var = key.upper().replace(".", "_")
        env_value = os.environ.get(env_var)
        
        if env_value is not None:
            logger.debug(f"Using environment variable for config: {env_var}")
            return self._parse_value(env_value, None)
        
        # Return default
        return default
    
    def get_config_sync(self, key: str, default: Any = None) -> Any:
        """
        Synchronous config access from cache.
        
        Only returns cached values. Use get_config() for async access.
        """
        if key in self._config_cache:
            return self._config_cache[key].value
        
        # Check environment variable
        env_var = key.upper().replace(".", "_")
        env_value = os.environ.get(env_var)
        if env_value is not None:
            return self._parse_value(env_value, None)
        
        return default
    
    async def set_config(self, key: str, value: Any) -> None:
        """
        Set a configuration value in Azure App Configuration.
        
        Note: Requires App Configuration Data Owner role.
        
        Args:
            key: Configuration key
            value: Value to set
        """
        if not self._app_config_client:
            raise RuntimeError("App Configuration not configured")
        
        try:
            str_value = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
            content_type = "application/json" if isinstance(value, (dict, list)) else None
            
            await self._app_config_client.set_configuration_setting(
                key=key,
                value=str_value,
                label=self._app_config_label or None,
                content_type=content_type,
            )
            
            # Update cache
            old_value = self._config_cache.get(key)
            self._config_cache[key] = CachedValue(
                value=value,
                etag=None,
                last_modified=datetime.utcnow(),
                cached_at=datetime.utcnow()
            )
            
            # Notify callbacks
            if old_value:
                self._notify_change(key, old_value.value, value)
            
            logger.info(f"Configuration set: {key}")
            
        except Exception as e:
            logger.error(f"Failed to set configuration '{key}': {e}")
            raise
    
    def _parse_value(self, value: str, content_type: Optional[str]) -> Any:
        """Parse configuration value based on content type."""
        if value is None:
            return None
        
        # JSON content
        if content_type and "json" in content_type.lower():
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        
        # Try to parse as number
        try:
            if "." in str(value):
                return float(value)
            return int(value)
        except (ValueError, TypeError):
            pass
        
        # Boolean
        if str(value).lower() in ("true", "yes", "1"):
            return True
        if str(value).lower() in ("false", "no", "0"):
            return False
        
        return value
    
    # =========================================================================
    # Hot-Reload Support
    # =========================================================================
    
    def on_change(self, callback: Callable[[str, Any, Any], None]) -> None:
        """
        Register callback for configuration changes.
        
        Args:
            callback: Function(key, old_value, new_value) to call on change
        """
        self._change_callbacks.append(callback)
        logger.debug(f"Registered config change callback")
    
    def _notify_change(self, key: str, old_value: Any, new_value: Any) -> None:
        """Notify registered callbacks of configuration change."""
        logger.info(f"Configuration changed: {key} = {old_value} -> {new_value}")
        
        for callback in self._change_callbacks:
            try:
                callback(key, old_value, new_value)
            except Exception as e:
                logger.error(f"Error in config change callback: {e}")
    
    async def start_refresh_task(self) -> None:
        """Start background task for configuration refresh."""
        if self._refresh_task is not None or not self._app_config_client:
            return
        
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        logger.info(f"Started config refresh task (interval: {self._refresh_interval}s)")
    
    async def stop_refresh_task(self) -> None:
        """Stop background refresh task."""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None
    
    async def _refresh_loop(self) -> None:
        """Background loop for periodic configuration refresh."""
        while True:
            try:
                await asyncio.sleep(self._refresh_interval)
                await self._load_all_configs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in config refresh loop: {e}")
    
    async def _load_all_configs(self) -> None:
        """Load all configuration from App Configuration."""
        if not self._app_config_client:
            return
        
        try:
            old_values = {k: v.value for k, v in self._config_cache.items()}
            
            async for setting in self._app_config_client.list_configuration_settings(
                label_filter=self._app_config_label or "*"
            ):
                key = setting.key
                value = self._parse_value(setting.value, setting.content_type)
                
                self._config_cache[key] = CachedValue(
                    value=value,
                    etag=setting.etag,
                    last_modified=setting.last_modified,
                    cached_at=datetime.utcnow()
                )
                
                # Check for changes
                if key in old_values and old_values[key] != value:
                    self._notify_change(key, old_values[key], value)
            
            logger.debug(f"Loaded {len(self._config_cache)} configuration settings")
            
        except Exception as e:
            logger.error(f"Error loading configurations: {e}")
    
    async def refresh(self) -> None:
        """Force a configuration refresh."""
        await self._load_all_configs()
    
    # =========================================================================
    # Health Check
    # =========================================================================
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check Azure services connectivity.
        
        Returns:
            Health status for each Azure service
        """
        result = {
            "healthy": True,
            "services": {},
            "environment": self.current_environment,
        }
        
        # Check Key Vault
        if self._keyvault_url:
            try:
                # Try to list secrets (just checks connectivity)
                if self._keyvault_client:
                    async for _ in self._keyvault_client.list_properties_of_secrets():
                        break
                result["services"]["keyvault"] = {
                    "healthy": True,
                    "url": self._keyvault_url,
                }
            except Exception as e:
                result["services"]["keyvault"] = {
                    "healthy": False,
                    "url": self._keyvault_url,
                    "error": str(e),
                }
                result["healthy"] = False
        
        # Check App Configuration
        if self._app_config_endpoint:
            try:
                if self._app_config_client:
                    # Try to read a setting
                    async for _ in self._app_config_client.list_configuration_settings():
                        break
                result["services"]["app_config"] = {
                    "healthy": True,
                    "endpoint": self._app_config_endpoint,
                    "cache_size": len(self._config_cache),
                }
            except Exception as e:
                result["services"]["app_config"] = {
                    "healthy": False,
                    "endpoint": self._app_config_endpoint,
                    "error": str(e),
                }
                result["healthy"] = False
        
        return result


# ============================================================================
# Global Instance
# ============================================================================

# Singleton instance for easy import
config_provider = AzureConfigProvider()


async def get_secret(name: str, default: str = "") -> str:
    """Convenience function to get secret."""
    return await config_provider.get_secret(name, default)


async def get_config(key: str, default: Any = None) -> Any:
    """Convenience function to get config."""
    return await config_provider.get_config(key, default)
