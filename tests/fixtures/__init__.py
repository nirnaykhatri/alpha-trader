"""
Test fixtures package.

Provides:
- optional_deps: Optional dependency checking and skip decorators
- fakes: In-memory test fakes for heavy dependencies
"""

from tests.fixtures.optional_deps import (
    # Availability flags
    AZURE_AVAILABLE,
    AZURE_COSMOS_AVAILABLE,
    FASTAPI_AVAILABLE,
    PYDANTIC_AVAILABLE,
    ALPACA_AVAILABLE,
    TASTYTRADE_AVAILABLE,
    REDIS_AVAILABLE,
    HYPOTHESIS_AVAILABLE,
    # Decorators
    requires_azure,
    requires_cosmos,
    requires_fastapi,
    requires_alpaca,
    requires_tastytrade,
    requires_redis,
    requires_hypothesis,
    requires_all_brokers,
    requires_web_stack,
    skip_if_missing,
    # Markers
    integration_test,
    unit_test,
    slow_test,
    network_test,
    api_test,
    # Utilities
    lazy_import,
    OptionalDependencyContext,
)

from tests.fixtures.fakes import (
    # Enums
    FakeSignalType,
    FakeOrderSide,
    FakeOrderType,
    FakeOrderStatus,
    # Data models
    FakeTradingSignal,
    FakePosition,
    FakeOrder,
    # Fakes
    FakeCosmosDBManager,
    FakeOrderManager,
    FakeMarketDataProvider,
    FakeRiskManager,
    FakeConfigurationManager,
    # Factory functions
    create_test_signal,
    create_test_position,
    create_test_order,
)

__all__ = [
    # optional_deps
    "AZURE_AVAILABLE",
    "AZURE_COSMOS_AVAILABLE",
    "FASTAPI_AVAILABLE",
    "PYDANTIC_AVAILABLE",
    "ALPACA_AVAILABLE",
    "TASTYTRADE_AVAILABLE",
    "REDIS_AVAILABLE",
    "HYPOTHESIS_AVAILABLE",
    "requires_azure",
    "requires_cosmos",
    "requires_fastapi",
    "requires_alpaca",
    "requires_tastytrade",
    "requires_redis",
    "requires_hypothesis",
    "requires_all_brokers",
    "requires_web_stack",
    "skip_if_missing",
    "integration_test",
    "unit_test",
    "slow_test",
    "network_test",
    "api_test",
    "lazy_import",
    "OptionalDependencyContext",
    # fakes
    "FakeSignalType",
    "FakeOrderSide",
    "FakeOrderType",
    "FakeOrderStatus",
    "FakeTradingSignal",
    "FakePosition",
    "FakeOrder",
    "FakeCosmosDBManager",
    "FakeOrderManager",
    "FakeMarketDataProvider",
    "FakeRiskManager",
    "FakeConfigurationManager",
    "create_test_signal",
    "create_test_position",
    "create_test_order",
]
