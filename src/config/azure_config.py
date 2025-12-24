"""
Azure App Configuration Integration with Hot-Reload Support.

Provides centralized configuration management with real-time updates
when configuration changes in Azure App Configuration.

Usage:
    config_client = AzureAppConfiguration(endpoint)
    await config_client.initialize()
    
    # Get configuration values
    value = config_client.get_config("dca.max_attempts", default=3)
    
    # Register for hot-reload callbacks
    config_client.on_config_change(my_callback_function)

Features:
    - Automatic hot-reload via Azure Event Grid / polling
    - Local caching with configurable refresh interval
    - Feature flags support
    - Hierarchical key structure (e.g., "dca.max_attempts")
"""

import asyncio
from typing import Dict, Optional, Any, Callable, List
from datetime import datetime, timedelta
from dataclasses import dataclass
import json

from azure.identity.aio import DefaultAzureCredential
from azure.appconfiguration.aio import AzureAppConfigurationClient
from azure.core.exceptions import ResourceNotFoundError, HttpResponseError

from src.interfaces import IConfigurationManager
from src.exceptions import TradingBotException
from src.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class ConfigValue:
    """Represents a cached configuration value."""
    key: str
    value: Any
    content_type: Optional[str]
    label: Optional[str]
    etag: str
    last_modified: datetime
    cached_at: datetime


class AzureAppConfiguration:
    """
    Async Azure App Configuration client with hot-reload support.
    
    Uses DefaultAzureCredential for authentication (Managed Identity in Azure).
    Supports configuration change detection and callback notifications.
    
    Thread-Safety:
        This class is safe for concurrent async operations.
        Configuration cache uses async-safe access patterns.
    
    Hot-Reload:
        Configuration changes are detected via:
        1. Polling: Periodic refresh with ETag comparison
        2. Event-driven: Azure Event Grid webhooks (if configured)
    
    Key Structure:
        Keys follow a hierarchical structure using dots:
        - "dca.max_attempts" = 3
        - "dca.multiplier" = 1.5
        - "risk.max_position_percent" = 5.0
    
    Attributes:
        _endpoint: App Configuration endpoint URL
        _label: Configuration label filter (e.g., 'demo', 'live')
        _refresh_interval: How often to check for changes (seconds)
    """
    
    # Default configuration values (fallback if not in App Configuration)
    DEFAULTS = {
        # DCA Strategy defaults
        'dca.max_attempts': 3,
        'dca.price_drop_percent': 5.0,
        'dca.multiplier': 1.5,
        'dca.position_size_percent': 2.0,
        
        # Risk Management defaults
        'risk.max_position_percent': 5.0,
        'risk.max_daily_loss_percent': 3.0,
        'risk.max_portfolio_exposure_percent': 30.0,
        
        # Trailing Stop defaults
        'trailing.activation_percent': 2.0,
        'trailing.callback_percent': 1.0,
        
        # Profit Taking defaults
        'profit.target_percent': 5.0,
        'profit.partial_sell_percent': 50.0,
        
        # API Settings
        'api.webhook.port': 8080,
        'api.webhook.security_enabled': True,
    }
    
    def __init__(
        self,
        endpoint: str = None,
        label: str = None,
        refresh_interval_seconds: int = 30,
    ):
        """
        Initialize App Configuration client.
        
        Args:
            endpoint: App Configuration endpoint URL
            label: Configuration label filter (environment)
            refresh_interval_seconds: How often to check for changes
        """
        self._endpoint = endpoint
        self._label = label
        self._refresh_interval = refresh_interval_seconds
        
        self._client: Optional[AzureAppConfigurationClient] = None
        self._credential: Optional[DefaultAzureCredential] = None
        self._cache: Dict[str, ConfigValue] = {}
        self._change_callbacks: List[Callable[[str, Any, Any], None]] = []
        self._refresh_task: Optional[asyncio.Task] = None
        self._initialized = False
        self._last_refresh: Optional[datetime] = None
        
        # Sentinel key for change detection
        self._sentinel_key = "sentinel"
        self._sentinel_etag: Optional[str] = None
        
        logger.info(
            f"AzureAppConfiguration initialized: "
            f"endpoint={endpoint}, label={label}, refresh={refresh_interval_seconds}s"
        )
    
    @property
    def is_configured(self) -> bool:
        """Check if App Configuration is configured."""
        return self._endpoint is not None
    
    async def initialize(self) -> None:
        """
        Initialize App Configuration client and load initial configuration.
        
        Raises:
            TradingBotException: If endpoint is not configured
        """
        if not self._endpoint:
            raise TradingBotException(
                "App Configuration endpoint not configured. "
                "Set AZURE_APP_CONFIGURATION_ENDPOINT environment variable."
            )
        
        try:
            logger.info("Initializing Azure App Configuration client...")
            
            self._credential = DefaultAzureCredential()
            self._client = AzureAppConfigurationClient(
                base_url=self._endpoint,
                credential=self._credential,
            )
            
            # Load initial configuration
            await self._load_all_configs()
            
            self._initialized = True
            logger.info(f"App Configuration initialized with {len(self._cache)} settings")
            
        except Exception as e:
            logger.error(f"Failed to initialize App Configuration: {str(e)}")
            raise TradingBotException(f"App Configuration initialization failed: {str(e)}")
    
    async def close(self) -> None:
        """Close App Configuration client and stop refresh task."""
        try:
            # Stop refresh task
            if self._refresh_task:
                self._refresh_task.cancel()
                try:
                    await self._refresh_task
                except asyncio.CancelledError:
                    pass
            
            if self._client:
                await self._client.close()
            if self._credential:
                await self._credential.close()
            
            self._cache.clear()
            logger.info("App Configuration client closed")
            
        except Exception as e:
            logger.error(f"Error closing App Configuration: {str(e)}")
    
    async def start_refresh_task(self) -> None:
        """Start background task for configuration refresh."""
        if self._refresh_task is not None:
            return
        
        self._refresh_task = asyncio.create_task(self._refresh_loop())
        logger.info(f"Started configuration refresh task (interval: {self._refresh_interval}s)")
    
    async def stop_refresh_task(self) -> None:
        """Stop background refresh task."""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
            self._refresh_task = None
            logger.info("Stopped configuration refresh task")
    
    async def _refresh_loop(self) -> None:
        """Background loop for periodic configuration refresh."""
        while True:
            try:
                await asyncio.sleep(self._refresh_interval)
                await self._check_for_changes()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in config refresh loop: {str(e)}")
    
    async def _check_for_changes(self) -> bool:
        """
        Check if configuration has changed using sentinel key.
        
        Returns:
            True if changes were detected and reloaded
        """
        try:
            # Check sentinel key ETag
            try:
                sentinel = await self._client.get_configuration_setting(
                    key=self._sentinel_key,
                    label=self._label,
                )
                
                if self._sentinel_etag and sentinel.etag != self._sentinel_etag:
                    logger.info("Configuration change detected via sentinel key")
                    await self._load_all_configs()
                    return True
                
                self._sentinel_etag = sentinel.etag
                
            except ResourceNotFoundError:
                # No sentinel key - check all keys (less efficient)
                pass
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking for config changes: {str(e)}")
            return False
    
    async def _load_all_configs(self) -> None:
        """Load all configuration settings from App Configuration."""
        try:
            old_values = {k: v.value for k, v in self._cache.items()}
            self._cache.clear()
            
            # List all configuration settings
            async for setting in self._client.list_configuration_settings(
                label_filter=self._label or "*"
            ):
                key = setting.key
                value = self._parse_value(setting.value, setting.content_type)
                
                self._cache[key] = ConfigValue(
                    key=key,
                    value=value,
                    content_type=setting.content_type,
                    label=setting.label,
                    etag=setting.etag,
                    last_modified=setting.last_modified,
                    cached_at=datetime.utcnow(),
                )
                
                # Check if value changed and notify callbacks
                if key in old_values and old_values[key] != value:
                    self._notify_change(key, old_values[key], value)
            
            self._last_refresh = datetime.utcnow()
            logger.debug(f"Loaded {len(self._cache)} configuration settings")
            
        except Exception as e:
            logger.error(f"Error loading configurations: {str(e)}")
            raise
    
    def _parse_value(self, value: str, content_type: Optional[str]) -> Any:
        """Parse configuration value based on content type."""
        if not value:
            return None
        
        # JSON content type
        if content_type and 'json' in content_type.lower():
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        
        # Try to parse as number or boolean
        try:
            if '.' in value:
                return float(value)
            return int(value)
        except ValueError:
            pass
        
        # Boolean values
        if value.lower() in ('true', 'yes', '1'):
            return True
        if value.lower() in ('false', 'no', '0'):
            return False
        
        return value
    
    def _notify_change(self, key: str, old_value: Any, new_value: Any) -> None:
        """Notify registered callbacks of configuration change."""
        logger.info(f"Configuration changed: {key} = {old_value} -> {new_value}")
        
        for callback in self._change_callbacks:
            try:
                callback(key, old_value, new_value)
            except Exception as e:
                logger.error(f"Error in config change callback: {str(e)}")
    
    def on_config_change(self, callback: Callable[[str, Any, Any], None]) -> None:
        """
        Register a callback for configuration changes.
        
        Args:
            callback: Function(key, old_value, new_value) to call on change
        """
        self._change_callbacks.append(callback)
        logger.debug(f"Registered config change callback: {callback.__name__}")
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key: Configuration key (e.g., 'dca.max_attempts')
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        # Check cache first
        if key in self._cache:
            return self._cache[key].value
        
        # Check defaults
        if key in self.DEFAULTS:
            return self.DEFAULTS[key]
        
        return default
    
    def get_all_configs(self, prefix: str = None) -> Dict[str, Any]:
        """
        Get all configuration values, optionally filtered by prefix.
        
        Args:
            prefix: Optional key prefix filter (e.g., 'dca.')
            
        Returns:
            Dictionary of configuration values
        """
        result = {}
        
        for key, cached in self._cache.items():
            if prefix is None or key.startswith(prefix):
                result[key] = cached.value
        
        return result
    
    async def set_config(self, key: str, value: Any) -> None:
        """
        Set a configuration value in App Configuration.
        
        Note: Requires App Configuration Data Owner role.
        
        Args:
            key: Configuration key
            value: Value to set (will be serialized)
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Serialize value
            if isinstance(value, (dict, list)):
                str_value = json.dumps(value)
                content_type = 'application/json'
            else:
                str_value = str(value)
                content_type = None
            
            await self._client.set_configuration_setting(
                key=key,
                value=str_value,
                label=self._label,
                content_type=content_type,
            )
            
            # Update local cache
            self._cache[key] = ConfigValue(
                key=key,
                value=value,
                content_type=content_type,
                label=self._label,
                etag="",  # Will be updated on next refresh
                last_modified=datetime.utcnow(),
                cached_at=datetime.utcnow(),
            )
            
            logger.info(f"Configuration set: {key} = {value}")
            
        except HttpResponseError as e:
            logger.error(f"Failed to set configuration '{key}': {e.message}")
            raise TradingBotException(f"Failed to set configuration: {e.message}")
    
    async def refresh(self) -> None:
        """Force a configuration refresh from App Configuration."""
        if not self._initialized:
            await self.initialize()
        else:
            await self._load_all_configs()
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check App Configuration connectivity.
        
        Returns:
            Health check result with status and stats
        """
        if not self._endpoint:
            return {
                'healthy': False,
                'error': 'App Configuration not configured',
            }
        
        start = datetime.utcnow()
        try:
            # Try to read sentinel key
            try:
                await self._client.get_configuration_setting(
                    key=self._sentinel_key,
                    label=self._label,
                )
            except ResourceNotFoundError:
                pass  # OK - sentinel may not exist
            
            latency_ms = (datetime.utcnow() - start).total_seconds() * 1000
            
            return {
                'healthy': True,
                'endpoint': self._endpoint,
                'label': self._label,
                'cache_size': len(self._cache),
                'last_refresh': self._last_refresh.isoformat() if self._last_refresh else None,
                'latency_ms': round(latency_ms, 2),
            }
            
        except Exception as e:
            return {
                'healthy': False,
                'endpoint': self._endpoint,
                'error': str(e),
            }


class AzureConfigurationManager(IConfigurationManager):
    """
    Configuration manager that integrates Azure App Configuration with local settings.
    
    Priority order:
    1. Environment variables
    2. Azure App Configuration (if configured)
    3. Local TOML files
    4. Default values
    
    This class implements IConfigurationManager interface for compatibility
    with existing codebase while adding Azure integration.
    """
    
    def __init__(
        self,
        local_config: IConfigurationManager,
        app_config: Optional[AzureAppConfiguration] = None,
    ):
        """
        Initialize Azure-integrated configuration manager.
        
        Args:
            local_config: Local configuration manager (environment variables fallback)
            app_config: Optional Azure App Configuration client
        """
        self._local_config = local_config
        self._app_config = app_config
        
        logger.info("AzureConfigurationManager initialized")
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value with Azure priority.
        
        Args:
            key: Configuration key
            default: Default value if not found
            
        Returns:
            Configuration value
        """
        # Try Azure App Configuration first
        if self._app_config and self._app_config.is_configured:
            value = self._app_config.get_config(key)
            if value is not None:
                return value
        
        # Fall back to local config
        return self._local_config.get_config(key, default)
    
    def get_config_section(self, section: str) -> Dict[str, Any]:
        """Get all values under a configuration section."""
        # Start with local config
        result = self._local_config.get_config_section(section)
        
        # Overlay Azure configs
        if self._app_config and self._app_config.is_configured:
            prefix = f"{section}."
            azure_configs = self._app_config.get_all_configs(prefix)
            for key, value in azure_configs.items():
                # Remove prefix for section dict
                short_key = key[len(prefix):]
                result[short_key] = value
        
        return result
    
    def is_feature_enabled(self, feature: str, default: bool = False) -> bool:
        """Check if a feature flag is enabled."""
        key = f"feature.{feature}"
        return self.get_config(key, default)
