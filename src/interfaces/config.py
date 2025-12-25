"""
Configuration Interfaces.

This module defines interfaces for configuration management,
supporting both synchronous (cached) and asynchronous (Azure-native) access patterns.

Canonical location for:
- IConfigurationManager (sync/cached)
- IAsyncConfigurationManager (Azure Key Vault + App Configuration)

Author: Trading Bot Team
Version: 1.0.0
"""

from abc import ABC, abstractmethod
from typing import Any


# =============================================================================
# Configuration Interfaces
# =============================================================================

class IConfigurationManager(ABC):
    """
    Interface for configuration management.
    
    Supports both synchronous (cached) and asynchronous access patterns.
    Async methods are preferred for Azure-native configuration.
    """
    
    @abstractmethod
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key (synchronous, from cache).
        
        For async access with Azure priority, use get_config_async().
        """
        pass
    
    @abstractmethod
    def set_config(self, key: str, value: Any) -> None:
        """Set configuration value (local cache only, use set_config_async for persistence)."""
        pass
    
    @abstractmethod
    def reload_config(self) -> None:
        """Reload configuration from source."""
        pass


class IAsyncConfigurationManager(ABC):
    """
    Async interface for Azure-native configuration management.
    
    Uses Azure Key Vault for secrets and App Configuration for runtime settings.
    Supports hot-reload and Managed Identity authentication.
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize Azure clients using Managed Identity."""
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """Close Azure clients and stop background tasks."""
        pass
    
    @abstractmethod
    async def get_secret(self, name: str, default: str = "") -> str:
        """Get secret from Azure Key Vault."""
        pass
    
    @abstractmethod
    async def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration from Azure App Configuration."""
        pass
    
    @abstractmethod
    async def set_config(self, key: str, value: Any) -> None:
        """Set configuration in Azure App Configuration."""
        pass
    
    @abstractmethod
    async def refresh(self) -> None:
        """Force refresh configuration from Azure."""
        pass
    
    @abstractmethod
    def on_change(self, callback) -> None:
        """Register callback for configuration changes (hot-reload)."""
        pass


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "IConfigurationManager",
    "IAsyncConfigurationManager",
]
