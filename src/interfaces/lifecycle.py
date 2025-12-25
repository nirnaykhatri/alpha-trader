"""
Lifecycle Management Interfaces.

This module defines interfaces for async component lifecycle management,
distinguishing between runtime processing (start/stop) and resource
management (initialize/close).

Canonical location for:
- IAsyncContextManager (runtime lifecycle: start/stop)
- IAsyncResource (resource lifecycle: initialize/close)

Author: Trading Bot Team
Version: 1.0.0
"""

from abc import ABC, abstractmethod


# =============================================================================
# Lifecycle Interfaces
# =============================================================================

class IAsyncContextManager(ABC):
    """
    Interface for components requiring async runtime lifecycle management.
    
    Use this interface for components that have an active runtime state:
    - Signal listeners
    - Trading bots
    - Market data streams
    - Event processors
    
    Pattern: start() -> [active processing] -> stop()
    
    For resource management (connections, clients), use IAsyncResource instead.
    """
    
    @abstractmethod
    async def start(self) -> None:
        """Start the component's active processing."""
        pass
        
    @abstractmethod
    async def stop(self) -> None:
        """Stop the component and cleanup resources."""
        pass
    
    @property
    def is_running(self) -> bool:
        """Check if the component is currently running."""
        return False


class IAsyncResource(ABC):
    """
    Interface for components requiring async resource lifecycle management.
    
    Use this interface for components that manage external resources:
    - Database connections
    - Azure clients (Key Vault, App Configuration)
    - Message queue connections
    - Cache clients
    
    Pattern: initialize() -> [resource available] -> close()
    
    For runtime processing components, use IAsyncContextManager instead.
    """
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the resource connection.
        
        Called once during application startup to establish
        connections and configure the resource.
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close the resource and release connections.
        
        Called during application shutdown to properly
        cleanup resources and close connections.
        """
        pass
    
    @property
    def is_initialized(self) -> bool:
        """Check if the resource has been initialized."""
        return False


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "IAsyncContextManager",
    "IAsyncResource",
]
