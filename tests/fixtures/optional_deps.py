"""
Optional dependency checking and auto-skip decorators for tests.

This module provides utilities to gracefully handle optional heavy dependencies
(Azure SDK, FastAPI, Pydantic, etc.) so unit tests can run without them.

Usage:
    from tests.fixtures.optional_deps import (
        requires_azure,
        requires_fastapi,
        requires_cosmos,
        skip_if_missing,
        AZURE_AVAILABLE,
        FASTAPI_AVAILABLE,
    )
    
    @requires_azure
    def test_cosmos_integration():
        ...
    
    @skip_if_missing("redis")
    def test_redis_cache():
        ...
"""

import functools
import importlib
from typing import Callable, Optional, TypeVar, Any

import pytest


# Type variable for decorator
F = TypeVar("F", bound=Callable[..., Any])


def _check_module_available(module_name: str) -> bool:
    """
    Check if a module is available for import by actually trying to import it.
    
    This uses try/except import because importlib.util.find_spec() fails for
    submodules (like 'azure.cosmos') when the parent package isn't installed.
    
    Args:
        module_name: Fully qualified module name (e.g., 'azure.cosmos')
        
    Returns:
        True if module can be imported, False otherwise
    """
    try:
        importlib.import_module(module_name)
        return True
    except (ImportError, ModuleNotFoundError):
        return False


def _try_import(module_name: str) -> bool:
    """Try to import a module and return True if successful."""
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


# Check availability of optional dependencies
# These checks run at module load time to set availability flags
AZURE_COSMOS_AVAILABLE = _check_module_available("azure.cosmos")
AZURE_IDENTITY_AVAILABLE = _check_module_available("azure.identity")
AZURE_APPCONFIG_AVAILABLE = _check_module_available("azure.appconfiguration")
AZURE_AVAILABLE = AZURE_COSMOS_AVAILABLE and AZURE_IDENTITY_AVAILABLE

FASTAPI_AVAILABLE = _check_module_available("fastapi")
PYDANTIC_AVAILABLE = _check_module_available("pydantic")
UVICORN_AVAILABLE = _check_module_available("uvicorn")

ALPACA_AVAILABLE = _check_module_available("alpaca")
TASTYTRADE_AVAILABLE = _check_module_available("tastytrade")

REDIS_AVAILABLE = _check_module_available("redis") or _check_module_available("aioredis")
HYPOTHESIS_AVAILABLE = _check_module_available("hypothesis")

# Prometheus metrics
PROMETHEUS_AVAILABLE = _check_module_available("prometheus_client")

# SignalR for real-time communication
SIGNALR_AVAILABLE = _check_module_available("signalrcore")


def skip_if_missing(module_name: str, reason: Optional[str] = None) -> Callable[[F], F]:
    """
    Decorator to skip a test if a module is not available.
    
    Args:
        module_name: The name of the module to check
        reason: Optional custom reason for skipping
        
    Usage:
        @skip_if_missing("azure.cosmos")
        def test_cosmos_operations():
            ...
    """
    available = _check_module_available(module_name)
    skip_reason = reason or f"Requires {module_name} to be installed"
    
    return pytest.mark.skipif(not available, reason=skip_reason)


def requires_azure(func: F) -> F:
    """
    Decorator to skip a test if Azure SDK is not available.
    
    Usage:
        @requires_azure
        async def test_cosmos_db_operations():
            ...
    """
    return pytest.mark.skipif(
        not AZURE_AVAILABLE,
        reason="Requires azure-cosmos and azure-identity packages"
    )(func)


def requires_cosmos(func: F) -> F:
    """
    Decorator to skip a test if Azure Cosmos SDK is not available.
    
    Usage:
        @requires_cosmos
        async def test_cosmos_query():
            ...
    """
    return pytest.mark.skipif(
        not AZURE_COSMOS_AVAILABLE,
        reason="Requires azure-cosmos package"
    )(func)


def requires_fastapi(func: F) -> F:
    """
    Decorator to skip a test if FastAPI is not available.
    
    Usage:
        @requires_fastapi
        def test_webhook_endpoint():
            ...
    """
    return pytest.mark.skipif(
        not FASTAPI_AVAILABLE,
        reason="Requires fastapi package"
    )(func)


def requires_alpaca(func: F) -> F:
    """
    Decorator to skip a test if Alpaca SDK is not available.
    
    Usage:
        @requires_alpaca
        async def test_alpaca_order():
            ...
    """
    return pytest.mark.skipif(
        not ALPACA_AVAILABLE,
        reason="Requires alpaca-py package"
    )(func)


def requires_tastytrade(func: F) -> F:
    """
    Decorator to skip a test if Tastytrade SDK is not available.
    
    Usage:
        @requires_tastytrade
        async def test_tastytrade_auth():
            ...
    """
    return pytest.mark.skipif(
        not TASTYTRADE_AVAILABLE,
        reason="Requires tastytrade package"
    )(func)


def requires_redis(func: F) -> F:
    """
    Decorator to skip a test if Redis client is not available.
    
    Usage:
        @requires_redis
        async def test_redis_cache():
            ...
    """
    return pytest.mark.skipif(
        not REDIS_AVAILABLE,
        reason="Requires redis or aioredis package"
    )(func)


def requires_hypothesis(func: F) -> F:
    """
    Decorator to skip a test if Hypothesis is not available.
    
    Usage:
        @requires_hypothesis
        def test_property_based():
            ...
    """
    return pytest.mark.skipif(
        not HYPOTHESIS_AVAILABLE,
        reason="Requires hypothesis package for property-based testing"
    )(func)


def requires_all_brokers(func: F) -> F:
    """
    Decorator to skip a test if any broker SDK is not available.
    
    Usage:
        @requires_all_brokers
        async def test_multi_broker_order():
            ...
    """
    return pytest.mark.skipif(
        not (ALPACA_AVAILABLE and TASTYTRADE_AVAILABLE),
        reason="Requires both alpaca-py and tastytrade packages"
    )(func)


def requires_web_stack(func: F) -> F:
    """
    Decorator to skip a test if web stack (FastAPI + Uvicorn) is not available.
    
    Usage:
        @requires_web_stack
        async def test_webhook_server():
            ...
    """
    return pytest.mark.skipif(
        not (FASTAPI_AVAILABLE and UVICORN_AVAILABLE),
        reason="Requires fastapi and uvicorn packages"
    )(func)


# Pytest markers for test categorization
integration_test = pytest.mark.integration
unit_test = pytest.mark.unit
slow_test = pytest.mark.slow
network_test = pytest.mark.network
api_test = pytest.mark.api


def lazy_import(module_name: str, attribute: Optional[str] = None):
    """
    Lazily import a module or attribute from a module.
    
    Args:
        module_name: The full module path (e.g., "azure.cosmos")
        attribute: Optional attribute to get from the module
        
    Returns:
        The module or attribute, or None if import fails
        
    Usage:
        CosmosClient = lazy_import("azure.cosmos", "CosmosClient")
        if CosmosClient:
            client = CosmosClient(...)
    """
    try:
        module = importlib.import_module(module_name)
        if attribute:
            return getattr(module, attribute, None)
        return module
    except ImportError:
        return None


class OptionalDependencyContext:
    """
    Context manager for tests that need optional dependencies.
    
    Provides a clean way to handle missing dependencies in test setup.
    
    Usage:
        with OptionalDependencyContext("azure.cosmos") as cosmos:
            if cosmos.available:
                client = cosmos.module.CosmosClient(...)
            else:
                pytest.skip("Azure Cosmos not available")
    """
    
    def __init__(self, module_name: str):
        self.module_name = module_name
        self.available = _check_module_available(module_name)
        self.module = None
    
    def __enter__(self):
        if self.available:
            self.module = importlib.import_module(self.module_name)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.module = None
        return False


# Export dependency status for use in conftest.py
__all__ = [
    # Availability flags
    "AZURE_AVAILABLE",
    "AZURE_COSMOS_AVAILABLE",
    "AZURE_IDENTITY_AVAILABLE",
    "AZURE_APPCONFIG_AVAILABLE",
    "FASTAPI_AVAILABLE",
    "PYDANTIC_AVAILABLE",
    "UVICORN_AVAILABLE",
    "ALPACA_AVAILABLE",
    "TASTYTRADE_AVAILABLE",
    "REDIS_AVAILABLE",
    "HYPOTHESIS_AVAILABLE",
    "PROMETHEUS_AVAILABLE",
    "SIGNALR_AVAILABLE",
    # Decorators
    "skip_if_missing",
    "requires_azure",
    "requires_cosmos",
    "requires_fastapi",
    "requires_alpaca",
    "requires_tastytrade",
    "requires_redis",
    "requires_hypothesis",
    "requires_all_brokers",
    "requires_web_stack",
    # Markers
    "integration_test",
    "unit_test",
    "slow_test",
    "network_test",
    "api_test",
    # Utilities
    "lazy_import",
    "OptionalDependencyContext",
]
