"""
Azure App Configuration Client.

Provides integration with Azure App Configuration service for centralized
configuration management. Supports dynamic configuration updates without
redeployment.

Usage:
    client = AzureAppConfigClient(connection_string)
    await client.initialize()
    
    # Get a single setting
    value = await client.get_setting("dca.max_attempts")
    
    # Get all settings with a prefix
    dca_settings = await client.get_settings_by_prefix("dca")
    
    # Watch for changes
    await client.start_watching(callback=on_config_changed)

Features:
    - Async/await pattern for non-blocking operations
    - Automatic caching with configurable refresh interval
    - Prefix-based setting retrieval
    - Feature flag support
    - Graceful fallback to local config on Azure unavailability

Author: Trading Bot Team
Version: 1.0.0
"""

import asyncio
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import json

from src.core.logging_config import get_logger

logger = get_logger(__name__)


# Try to import Azure SDK, gracefully handle if not installed
try:
    from azure.appconfiguration.aio import AzureAppConfigurationClient
    from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential
    from azure.core.exceptions import AzureError, ResourceNotFoundError
    AZURE_SDK_AVAILABLE = True
except ImportError:
    AZURE_SDK_AVAILABLE = False
    logger.warning("Azure App Configuration SDK not installed. Using local config only.")


@dataclass
class ConfigSetting:
    """Represents a configuration setting from Azure App Configuration."""
    
    key: str
    value: Any
    label: Optional[str] = None
    content_type: Optional[str] = None
    etag: Optional[str] = None
    last_modified: Optional[datetime] = None
    
    def as_typed(self) -> Any:
        """
        Convert value to appropriate Python type based on content_type.
        
        Returns:
            Typed value (bool, int, float, dict, or str)
        """
        if self.content_type == "application/json":
            try:
                return json.loads(self.value)
            except (json.JSONDecodeError, TypeError):
                return self.value
        
        # Try to infer type
        if isinstance(self.value, str):
            # Boolean
            if self.value.lower() in ('true', 'false'):
                return self.value.lower() == 'true'
            
            # Integer
            try:
                return int(self.value)
            except ValueError:
                pass
            
            # Float
            try:
                return float(self.value)
            except ValueError:
                pass
        
        return self.value


@dataclass
class ConfigCache:
    """In-memory cache for configuration settings."""
    
    settings: Dict[str, ConfigSetting] = field(default_factory=dict)
    last_refresh: Optional[datetime] = None
    refresh_interval: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    
    def is_stale(self) -> bool:
        """Check if cache needs refresh."""
        if self.last_refresh is None:
            return True
        return datetime.utcnow() - self.last_refresh > self.refresh_interval
    
    def get(self, key: str) -> Optional[ConfigSetting]:
        """Get setting from cache."""
        return self.settings.get(key)
    
    def set(self, setting: ConfigSetting) -> None:
        """Add or update setting in cache."""
        self.settings[setting.key] = setting
    
    def clear(self) -> None:
        """Clear all cached settings."""
        self.settings.clear()
        self.last_refresh = None


class AzureAppConfigClient:
    """
    Client for Azure App Configuration service.
    
    Provides async access to centralized configuration with:
    - Automatic caching and refresh
    - Prefix-based retrieval for structured configs
    - Feature flag support
    - Change watching for dynamic updates
    
    Thread Safety:
        This class is safe for concurrent async operations.
        Uses locks to prevent cache race conditions.
    
    Fallback Behavior:
        If Azure App Configuration is unavailable, methods return None
        and callers should fall back to local configuration.
    
    Example:
        >>> client = AzureAppConfigClient(connection_string)
        >>> await client.initialize()
        >>> 
        >>> # Get DCA settings
        >>> dca = await client.get_settings_by_prefix("dca")
        >>> max_attempts = dca.get("dca.max_attempts", 5)
    """
    
    def __init__(
        self,
        connection_string: Optional[str] = None,
        endpoint: Optional[str] = None,
        credential: Optional[Any] = None,
        cache_refresh_seconds: int = 300,
        label: Optional[str] = None,
    ):
        """
        Initialize Azure App Configuration client.
        
        Args:
            connection_string: Azure App Configuration connection string
            endpoint: Endpoint URL (alternative to connection string)
            credential: Azure credential (for managed identity)
            cache_refresh_seconds: How often to refresh cache (default: 5 min)
            label: Configuration label filter (e.g., "production")
        """
        self._connection_string = connection_string
        self._endpoint = endpoint
        self._credential = credential
        self._label = label
        
        self._client: Optional[Any] = None
        self._cache = ConfigCache(
            refresh_interval=timedelta(seconds=cache_refresh_seconds)
        )
        self._cache_lock = asyncio.Lock()
        
        self._watch_task: Optional[asyncio.Task] = None
        self._watch_callback: Optional[Callable[[str, Any, Any], None]] = None
        
        self._initialized = False
        
        logger.info("AzureAppConfigClient created")
    
    @property
    def is_available(self) -> bool:
        """Check if Azure App Configuration is available."""
        return AZURE_SDK_AVAILABLE and self._initialized and self._client is not None
    
    async def initialize(self) -> bool:
        """
        Initialize connection to Azure App Configuration.
        
        Returns:
            True if connected successfully, False otherwise
        """
        if not AZURE_SDK_AVAILABLE:
            logger.warning("Azure SDK not available, using local config only")
            return False
        
        try:
            if self._connection_string:
                self._client = AzureAppConfigurationClient.from_connection_string(
                    self._connection_string
                )
            elif self._endpoint:
                # Use managed identity or default credential
                credential = self._credential or DefaultAzureCredential()
                self._client = AzureAppConfigurationClient(
                    base_url=self._endpoint,
                    credential=credential
                )
            else:
                logger.warning("No connection string or endpoint provided")
                return False
            
            # Test connection by listing a few settings
            async for _ in self._client.list_configuration_settings(
                label_filter=self._label,
                max_page_size=1
            ):
                break
            
            self._initialized = True
            logger.info("✅ Azure App Configuration connected")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Azure App Configuration: {str(e)}")
            self._client = None
            return False
    
    async def close(self) -> None:
        """Close the client and stop any watch tasks."""
        try:
            # Stop watching
            if self._watch_task:
                self._watch_task.cancel()
                try:
                    await self._watch_task
                except asyncio.CancelledError:
                    pass
            
            # Close client
            if self._client:
                await self._client.close()
            
            self._initialized = False
            logger.info("Azure App Configuration client closed")
            
        except Exception as e:
            logger.error(f"Error closing App Configuration client: {str(e)}")
    
    async def get_setting(
        self,
        key: str,
        default: Any = None,
        use_cache: bool = True,
    ) -> Any:
        """
        Get a single configuration setting.
        
        Args:
            key: Setting key (e.g., "dca.max_attempts")
            default: Default value if setting not found
            use_cache: Whether to use cached value if available
            
        Returns:
            Setting value or default
        """
        if not self.is_available:
            return default
        
        try:
            # Check cache first
            if use_cache:
                cached = self._cache.get(key)
                if cached and not self._cache.is_stale():
                    return cached.as_typed()
            
            # Fetch from Azure
            setting = await self._client.get_configuration_setting(
                key=key,
                label=self._label
            )
            
            config_setting = ConfigSetting(
                key=setting.key,
                value=setting.value,
                label=setting.label,
                content_type=setting.content_type,
                etag=setting.etag,
                last_modified=setting.last_modified
            )
            
            # Update cache
            async with self._cache_lock:
                self._cache.set(config_setting)
            
            return config_setting.as_typed()
            
        except ResourceNotFoundError:
            logger.debug(f"Setting not found: {key}")
            return default
        except Exception as e:
            logger.error(f"Error getting setting {key}: {str(e)}")
            return default
    
    async def get_settings_by_prefix(
        self,
        prefix: str,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """
        Get all settings with a given prefix.
        
        Args:
            prefix: Key prefix (e.g., "dca" returns "dca.max_attempts", "dca.enabled", etc.)
            use_cache: Whether to use cached values
            
        Returns:
            Dictionary of key -> value pairs
        """
        if not self.is_available:
            return {}
        
        try:
            # Ensure prefix ends with dot for proper matching
            key_filter = f"{prefix}*" if prefix.endswith('.') or prefix.endswith('*') else f"{prefix}.*"
            
            result = {}
            
            async for setting in self._client.list_configuration_settings(
                key_filter=key_filter,
                label_filter=self._label
            ):
                config_setting = ConfigSetting(
                    key=setting.key,
                    value=setting.value,
                    label=setting.label,
                    content_type=setting.content_type,
                    etag=setting.etag,
                    last_modified=setting.last_modified
                )
                
                # Update cache
                async with self._cache_lock:
                    self._cache.set(config_setting)
                
                result[setting.key] = config_setting.as_typed()
            
            # Update cache refresh time
            async with self._cache_lock:
                self._cache.last_refresh = datetime.utcnow()
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting settings by prefix {prefix}: {str(e)}")
            return {}
    
    async def get_feature_flag(
        self,
        feature_name: str,
        default: bool = False,
    ) -> bool:
        """
        Get a feature flag value.
        
        Args:
            feature_name: Feature flag name
            default: Default value if flag not found
            
        Returns:
            Feature flag enabled status
        """
        if not self.is_available:
            return default
        
        try:
            # Feature flags use special key format
            key = f".appconfig.featureflag/{feature_name}"
            
            setting = await self._client.get_configuration_setting(
                key=key,
                label=self._label
            )
            
            # Parse feature flag JSON
            if setting.content_type == "application/vnd.microsoft.appconfig.ff+json;charset=utf-8":
                flag_data = json.loads(setting.value)
                return flag_data.get("enabled", default)
            
            return default
            
        except ResourceNotFoundError:
            return default
        except Exception as e:
            logger.error(f"Error getting feature flag {feature_name}: {str(e)}")
            return default
    
    async def refresh_cache(self) -> None:
        """Force refresh of all cached settings."""
        if not self.is_available:
            return
        
        try:
            async with self._cache_lock:
                self._cache.clear()
            
            # Re-fetch all settings
            async for setting in self._client.list_configuration_settings(
                label_filter=self._label
            ):
                config_setting = ConfigSetting(
                    key=setting.key,
                    value=setting.value,
                    label=setting.label,
                    content_type=setting.content_type,
                    etag=setting.etag,
                    last_modified=setting.last_modified
                )
                
                async with self._cache_lock:
                    self._cache.set(config_setting)
            
            async with self._cache_lock:
                self._cache.last_refresh = datetime.utcnow()
            
            logger.info("Configuration cache refreshed")
            
        except Exception as e:
            logger.error(f"Error refreshing cache: {str(e)}")
    
    async def start_watching(
        self,
        callback: Callable[[str, Any, Any], None],
        interval_seconds: int = 30,
        keys: Optional[List[str]] = None,
    ) -> None:
        """
        Start watching for configuration changes.
        
        Args:
            callback: Function called on changes: callback(key, old_value, new_value)
            interval_seconds: How often to check for changes
            keys: Specific keys to watch (None = watch all)
        """
        if not self.is_available:
            logger.warning("Cannot start watching: App Configuration not available")
            return
        
        self._watch_callback = callback
        
        async def watch_loop():
            while True:
                try:
                    await asyncio.sleep(interval_seconds)
                    await self._check_for_changes(keys)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in watch loop: {str(e)}")
        
        self._watch_task = asyncio.create_task(watch_loop())
        logger.info(f"Started watching for config changes (interval: {interval_seconds}s)")
    
    async def stop_watching(self) -> None:
        """Stop watching for configuration changes."""
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
            self._watch_task = None
            logger.info("Stopped watching for config changes")
    
    async def _check_for_changes(self, keys: Optional[List[str]] = None) -> None:
        """Check for configuration changes and invoke callback."""
        if not self._watch_callback:
            return
        
        try:
            if keys:
                # Check specific keys
                for key in keys:
                    old_setting = self._cache.get(key)
                    new_value = await self.get_setting(key, use_cache=False)
                    
                    old_value = old_setting.as_typed() if old_setting else None
                    
                    if old_value != new_value:
                        self._watch_callback(key, old_value, new_value)
            else:
                # Check all cached keys for changes
                keys_to_check = list(self._cache.settings.keys())
                
                for key in keys_to_check:
                    old_setting = self._cache.get(key)
                    new_value = await self.get_setting(key, use_cache=False)
                    
                    old_value = old_setting.as_typed() if old_setting else None
                    
                    if old_value != new_value:
                        self._watch_callback(key, old_value, new_value)
                        
        except Exception as e:
            logger.error(f"Error checking for changes: {str(e)}")
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check Azure App Configuration connectivity.
        
        Returns:
            Health check result
        """
        if not AZURE_SDK_AVAILABLE:
            return {
                "healthy": False,
                "error": "Azure SDK not installed",
            }
        
        if not self._initialized:
            return {
                "healthy": False,
                "error": "Client not initialized",
            }
        
        try:
            # Try to list settings
            count = 0
            async for _ in self._client.list_configuration_settings(max_page_size=1):
                count += 1
                break
            
            return {
                "healthy": True,
                "cached_settings": len(self._cache.settings),
                "cache_age_seconds": (
                    (datetime.utcnow() - self._cache.last_refresh).total_seconds()
                    if self._cache.last_refresh else None
                ),
            }
            
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
            }


class AzureAppConfigIntegration:
    """
    Integration layer between AzureAppConfigClient and ConfigManager.
    
    Provides seamless fallback to local config when Azure is unavailable.
    
    Example:
        >>> integration = AzureAppConfigIntegration(
        ...     azure_client=azure_client,
        ...     local_config=config_manager
        ... )
        >>> value = await integration.get("dca.max_attempts", default=5)
    """
    
    def __init__(
        self,
        azure_client: AzureAppConfigClient,
        local_config: Any,
        azure_priority: bool = True,
    ):
        """
        Initialize integration layer.
        
        Args:
            azure_client: Azure App Configuration client
            local_config: Local configuration manager (IConfigurationManager)
            azure_priority: If True, Azure config takes precedence over local
        """
        self._azure = azure_client
        self._local = local_config
        self._azure_priority = azure_priority
    
    async def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value with fallback.
        
        Args:
            key: Configuration key
            default: Default value if not found
            
        Returns:
            Configuration value
        """
        if self._azure_priority and self._azure.is_available:
            # Try Azure first
            value = await self._azure.get_setting(key)
            if value is not None:
                return value
        
        # Fall back to local config
        if hasattr(self._local, 'get_config'):
            local_value = self._local.get_config(key)
            if local_value is not None:
                return local_value
        
        # Try Azure as fallback if not priority
        if not self._azure_priority and self._azure.is_available:
            value = await self._azure.get_setting(key)
            if value is not None:
                return value
        
        return default
    
    async def get_section(self, prefix: str) -> Dict[str, Any]:
        """
        Get all settings under a prefix.
        
        Args:
            prefix: Configuration prefix (e.g., "dca")
            
        Returns:
            Dictionary of settings
        """
        result = {}
        
        # Get from Azure
        if self._azure.is_available:
            azure_settings = await self._azure.get_settings_by_prefix(prefix)
            result.update(azure_settings)
        
        # Merge with local (Azure priority = Azure overwrites local)
        if hasattr(self._local, 'get_config'):
            local_section = self._local.get_config(prefix, {})
            if isinstance(local_section, dict):
                if self._azure_priority:
                    # Local as base, Azure overwrites
                    merged = {f"{prefix}.{k}": v for k, v in local_section.items()}
                    merged.update(result)
                    result = merged
                else:
                    # Azure as base, local overwrites
                    for k, v in local_section.items():
                        result[f"{prefix}.{k}"] = v
        
        return result
