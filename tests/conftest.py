"""
PyTest configuration and shared fixtures.

This conftest uses lazy imports to avoid pulling heavy dependencies (Azure SDK,
FastAPI, etc.) at module load time. This allows unit tests to run without
requiring all optional dependencies to be installed.

For unit tests that don't need infrastructure dependencies, use the fakes from:
    from tests.fixtures.fakes import FakeCosmosDBManager, FakeOrderManager, etc.

For integration tests that need real implementations, use:
    from tests.fixtures.optional_deps import requires_azure, requires_fastapi, etc.
"""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import sys
from typing import TYPE_CHECKING, Dict, Any, Generator, Optional

# Mock tastytrade module BEFORE importing anything that uses it
sys.modules["tastytrade"] = MagicMock()
sys.modules["tastytrade.session"] = MagicMock()
sys.modules["tastytrade.account"] = MagicMock()
sys.modules["tastytrade.instruments"] = MagicMock()
sys.modules["tastytrade.order"] = MagicMock()
sys.modules["tastytrade.dxfeed"] = MagicMock()
sys.modules["tastytrade.market_data"] = MagicMock()

from datetime import datetime

# Import optional dependency utilities (lightweight - no heavy deps)
from tests.fixtures.optional_deps import (
    AZURE_AVAILABLE,
    FASTAPI_AVAILABLE,
    ALPACA_AVAILABLE,
    TASTYTRADE_AVAILABLE,
    REDIS_AVAILABLE,
    HYPOTHESIS_AVAILABLE,
    requires_azure,
    requires_fastapi,
    requires_alpaca,
    lazy_import,
)

# Import lightweight fakes (no external dependencies)
from tests.fixtures.fakes import (
    FakeCosmosDBManager,
    FakeOrderManager,
    FakeMarketDataProvider,
    FakeRiskManager,
    FakeConfigurationManager,
    FakeTradingSignal,
    FakePosition,
    FakeOrder,
    FakeSignalType,
    FakeOrderSide,
    FakeOrderType,
    FakeOrderStatus,
    create_test_signal,
    create_test_position,
    create_test_order,
)

# Configure pytest-asyncio
pytest_plugins = ("pytest_asyncio",)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_config_data() -> Dict[str, Any]:
    """Sample configuration data for testing."""
    return {
        "api": {
            "alpaca": {
                "api_key": "test_api_key",
                "secret_key": "test_secret_key",
                "base_url": "https://paper-api.alpaca.markets",
                "timeout": 30,
                "max_retries": 3,
                "retry_delay": 1.0
            },
            "webhook": {
                "host": "0.0.0.0",
                "port": 8080,
                "secret": "test_webhook_secret"
            }
        },
        "trading": {
            "default_quantity": 100,
            "max_position_size": 1000,
            "max_daily_trades": 50,
            "risk_per_trade": 0.02,
            "max_portfolio_risk": 0.10,
            "order_timeout_minutes": 5,
            "use_market_orders": False,
            "limit_order_offset": 0.001
        },
        "strategies": {
            "averaging_down": {
                "enabled": True,
                "max_attempts": 3,
                "step_percentage": 0.02,
                "timeframe": "1h",
                "min_gap_percentage": 0.01
            },
            "trailing_profit": {
                "enabled": True,
                "initial_trail_percent": 0.05,
                "trail_step_percent": 0.01,
                "min_profit_percent": 0.02,
                "max_trail_percent": 0.15,
                "trail_adjustment_threshold": 0.03
            }
        },
        "database": {
            "url": "",  # Cosmos DB - uses mock in tests
            "echo": False
        },
        "logging": {
            "level": "INFO",
            "file": "test_trading_bot.log",
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            "max_file_size": 10485760,
            "backup_count": 5
        }
    }


@pytest.fixture
def test_config_file(test_config_data: Dict[str, Any]) -> Generator[str, None, None]:
    """
    Fixture for backward compatibility - config_file parameter is now ignored.
    The new TOML-based configuration system loads from config/ directory.
    This fixture yields a dummy path for compatibility with existing tests.
    
    Note: Uses lazy import for ConfigurationManager.
    """
    # Lazy import to avoid requiring Azure SDK for unit tests
    ConfigurationManager = lazy_import("src.core", "ConfigurationManager")
    if ConfigurationManager is None:
        pytest.skip("ConfigurationManager not available")
    
    # Reset the singleton before each test to ensure clean state
    ConfigurationManager.reset_instance()
    
    # Yield a dummy path - ConfigurationManager ignores this and uses config/ directory
    yield "config_ignored_uses_toml"
    
    # Reset after test to ensure clean state for next test
    ConfigurationManager.reset_instance()


@pytest.fixture
def validated_config():
    """
    Fixture that provides a properly validated ConfigurationManager for tests.
    
    This fixture ensures tests use configuration that has passed validation,
    preventing bypass of configuration checks (addresses Issue #14).
    
    Note: Uses lazy import - tests requiring this will skip if deps unavailable.
    
    Usage:
        def test_something(validated_config):
            # validated_config is already validated and safe to use
            broker = validated_config.get_broker_for_symbol("AAPL")
    
    Returns:
        ConfigurationManager instance that has been validated
    """
    # Lazy import to avoid requiring Azure SDK for unit tests
    ConfigurationManager = lazy_import("src.core", "ConfigurationManager")
    if ConfigurationManager is None:
        pytest.skip("ConfigurationManager not available - Azure SDK may not be installed")
    
    # Reset the singleton before test
    ConfigurationManager.reset_instance()
    
    # Create and validate configuration
    config = ConfigurationManager()
    config.validate_required_config()
    
    yield config
    
    # Reset after test
    ConfigurationManager.reset_instance()


@pytest.fixture
def mock_alpaca_trading_client():
    """Mock Alpaca trading client."""
    mock_client = Mock()
    mock_client.get_account.return_value = Mock(
        buying_power=10000.0,
        cash=10000.0,
        equity=10000.0,
        status="ACTIVE"
    )
    mock_client.get_positions.return_value = []
    mock_client.get_orders.return_value = []
    mock_client.submit_order.return_value = Mock(
        id="test_order_id",
        status="NEW",
        filled_qty=0,
        qty=100,
        symbol="AAPL",
        side="buy",
        order_type="limit",
        limit_price=150.0
    )
    return mock_client


@pytest.fixture
def mock_alpaca_data_client():
    """Mock Alpaca data client."""
    mock_client = Mock()
    mock_client.get_stock_bars.return_value = Mock(
        df=Mock(
            iloc=Mock(
                __getitem__=Mock(return_value=Mock(
                    close=150.0,
                    high=155.0,
                    low=145.0,
                    volume=1000000
                ))
            )
        )
    )
    mock_client.get_stock_latest_quote.return_value = Mock(
        ask_price=150.05,
        bid_price=149.95,
        ask_size=100,
        bid_size=100
    )
    return mock_client


@pytest.fixture
def sample_trading_signal():
    """
    Sample trading signal for testing.
    
    Returns a FakeTradingSignal for unit tests. For integration tests
    that need the real TradingSignal, use lazy import in the test.
    """
    return create_test_signal(
        symbol="AAPL",
        signal_type=FakeSignalType.BUY,
        price=150.0,
    )


@pytest.fixture
def sample_trading_signal_real():
    """
    Sample trading signal using real src/interfaces types.
    
    Use this fixture for integration tests that need actual types.
    Will skip if dependencies are not available.
    """
    TradingSignal = lazy_import("src.interfaces", "TradingSignal")
    SignalType = lazy_import("src.interfaces", "SignalType")
    
    if TradingSignal is None or SignalType is None:
        pytest.skip("TradingSignal not available - src.interfaces may not import")
    
    return TradingSignal(
        signal_id="test-signal-123",
        symbol="AAPL",
        signal_type=SignalType.BUY,
        price=150.0,
        timestamp=datetime.utcnow(),
        metadata={"test": "data"}
    )


@pytest.fixture
def sample_position():
    """
    Sample position for testing.
    
    Returns a FakePosition for unit tests. For integration tests
    that need the real Position, use sample_position_real.
    """
    return create_test_position(
        symbol="AAPL",
        quantity=100,
        avg_price=150.0,
    )


@pytest.fixture
def sample_position_real():
    """
    Sample position using real src/interfaces types.
    
    Use this fixture for integration tests that need actual types.
    Will skip if dependencies are not available.
    """
    Position = lazy_import("src.interfaces", "Position")
    
    if Position is None:
        pytest.skip("Position not available - src.interfaces may not import")
    
    return Position(
        symbol="AAPL",
        quantity=100,
        avg_price=150.0,
        current_price=155.0,
        unrealized_pnl=500.0,
        realized_pnl=0.0,
        broker="alpaca"
    )


@pytest.fixture
def sample_order():
    """
    Sample order for testing.
    
    Returns a FakeOrder for unit tests. For integration tests
    that need the real Order, use sample_order_real.
    """
    return create_test_order(
        symbol="AAPL",
        quantity=100,
        side=FakeOrderSide.BUY,
        price=150.0,
    )


@pytest.fixture
def sample_order_real():
    """
    Sample order using real src/interfaces types.
    
    Use this fixture for integration tests that need actual types.
    Will skip if dependencies are not available.
    """
    Order = lazy_import("src.interfaces", "Order")
    OrderType = lazy_import("src.interfaces", "OrderType")
    OrderSide = lazy_import("src.interfaces", "OrderSide")
    OrderStatus = lazy_import("src.interfaces", "OrderStatus")
    
    if any(x is None for x in [Order, OrderType, OrderSide, OrderStatus]):
        pytest.skip("Order types not available - src.interfaces may not import")
    
    return Order(
        order_id="test_order_id",
        symbol="AAPL",
        quantity=100,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=150.0,
        status=OrderStatus.PENDING,
        filled_quantity=0,
        filled_price=None
    )


@pytest.fixture
async def mock_database():
    """
    Mock database for testing.
    
    Returns FakeCosmosDBManager for unit tests. This is an in-memory
    implementation that doesn't require Azure SDK.
    """
    return FakeCosmosDBManager()


@pytest.fixture
async def mock_database_real():
    """
    Mock database using real CosmosDBManager spec.
    
    Use for integration tests that need the real interface shape.
    Will skip if Azure SDK is not available.
    """
    CosmosDBManager = lazy_import("src.database", "CosmosDBManager")
    if CosmosDBManager is None:
        pytest.skip("CosmosDBManager not available - Azure SDK may not be installed")
    
    mock_db = Mock(spec=CosmosDBManager)
    mock_db.initialize = AsyncMock()
    mock_db.close = AsyncMock()
    mock_db.save_signal = AsyncMock()
    mock_db.save_order = AsyncMock()
    mock_db.save_position = AsyncMock()
    mock_db.get_positions = AsyncMock(return_value=[])
    mock_db.get_orders = AsyncMock(return_value=[])
    mock_db.get_signals = AsyncMock(return_value=[])
    return mock_db


@pytest.fixture
def mock_order_manager(mock_alpaca_trading_client):
    """
    Mock order manager for testing.
    
    Returns FakeOrderManager for unit tests. This is an in-memory
    implementation that doesn't require broker SDK.
    """
    return FakeOrderManager(auto_fill=True)


@pytest.fixture
def mock_order_manager_real(mock_alpaca_trading_client):
    """
    Mock order manager using real OrderManager spec.
    
    Use for integration tests that need the real interface shape.
    """
    OrderManager = lazy_import("src.trading", "OrderManager")
    if OrderManager is None:
        pytest.skip("OrderManager not available")
    
    mock_manager = Mock(spec=OrderManager)
    mock_manager.trading_client = mock_alpaca_trading_client
    mock_manager.submit_order = AsyncMock()
    mock_manager.cancel_order = AsyncMock()
    mock_manager.get_order_status = AsyncMock()
    mock_manager.get_active_orders = AsyncMock(return_value=[])
    return mock_manager


@pytest.fixture
def mock_position_manager(mock_database):
    """
    Mock position manager for testing.
    
    Uses in-memory fake database.
    """
    PositionManager = lazy_import("src.position", "PositionManager")
    if PositionManager is None:
        # Return a simple mock if real implementation unavailable
        mock_manager = Mock()
        mock_manager.database = mock_database
        mock_manager.get_position = AsyncMock()
        mock_manager.update_position = AsyncMock()
        mock_manager.get_all_positions = AsyncMock(return_value=[])
        mock_manager.calculate_unrealized_pnl = AsyncMock()
        return mock_manager
    
    mock_manager = Mock(spec=PositionManager)
    mock_manager.database = mock_database
    mock_manager.get_position = AsyncMock()
    mock_manager.update_position = AsyncMock()
    mock_manager.get_all_positions = AsyncMock(return_value=[])
    mock_manager.calculate_unrealized_pnl = AsyncMock()
    return mock_manager


@pytest.fixture
def mock_risk_manager():
    """
    Mock risk manager for testing.
    
    Returns FakeRiskManager for unit tests.
    """
    return FakeRiskManager(approve_all=True)


@pytest.fixture
def mock_risk_manager_real():
    """
    Mock risk manager using real RiskManager spec.
    
    Use for integration tests that need the real interface shape.
    """
    RiskManager = lazy_import("src.risk", "RiskManager")
    if RiskManager is None:
        pytest.skip("RiskManager not available")
    
    mock_manager = Mock(spec=RiskManager)
    mock_manager.validate_trade = AsyncMock(return_value=True)
    mock_manager.calculate_position_size = AsyncMock(return_value=100)
    mock_manager.check_portfolio_risk = AsyncMock(return_value=True)
    mock_manager.get_risk_metrics = AsyncMock(return_value={})
    return mock_manager


@pytest.fixture
def mock_market_data(mock_alpaca_data_client):
    """
    Mock market data provider for testing.
    
    Returns FakeMarketDataProvider for unit tests.
    """
    fake_provider = FakeMarketDataProvider(default_price=150.0)
    fake_provider.set_price("AAPL", 150.0)
    return fake_provider


@pytest.fixture
def mock_market_data_real(mock_alpaca_data_client):
    """
    Mock market data using real AlpacaMarketDataProvider spec.
    
    Use for integration tests that need the real interface shape.
    """
    AlpacaMarketDataProvider = lazy_import("src.data", "AlpacaMarketDataProvider")
    if AlpacaMarketDataProvider is None:
        pytest.skip("AlpacaMarketDataProvider not available")
    
    mock_provider = Mock(spec=AlpacaMarketDataProvider)
    mock_provider.data_client = mock_alpaca_data_client
    mock_provider.get_current_price = AsyncMock(return_value=150.0)
    mock_provider.get_historical_data = AsyncMock()
    mock_provider.get_latest_quote = AsyncMock()
    return mock_provider


@pytest.fixture
def mock_trailing_profit_manager():
    """Mock trailing profit manager."""
    TrailingManager = lazy_import("src.strategies", "TrailingManager")
    if TrailingManager is None:
        # Return simple mock if unavailable
        mock_manager = Mock()
        mock_manager.should_take_profit = AsyncMock(return_value=False)
        mock_manager.update_trailing_stop = AsyncMock()
        mock_manager.get_trailing_stop_price = AsyncMock(return_value=148.0)
        return mock_manager
    
    mock_manager = Mock(spec=TrailingManager)
    mock_manager.should_take_profit = AsyncMock(return_value=False)
    mock_manager.update_trailing_stop = AsyncMock()
    mock_manager.get_trailing_stop_price = AsyncMock(return_value=148.0)
    return mock_manager


@pytest.fixture
def mock_signal_listener():
    """Mock signal listener."""
    TradingViewSignalListener = lazy_import("src.signals", "TradingViewSignalListener")
    if TradingViewSignalListener is None:
        # Return simple mock if unavailable
        mock_listener = Mock()
        mock_listener.start = AsyncMock()
        mock_listener.stop = AsyncMock()
        mock_listener.register_signal_handler = Mock()
        return mock_listener
    
    mock_listener = Mock(spec=TradingViewSignalListener)
    mock_listener.start = AsyncMock()
    mock_listener.stop = AsyncMock()
    mock_listener.register_signal_handler = Mock()
    return mock_listener


@pytest.fixture
async def test_database_url():
    """Temporary database URL for testing (Cosmos uses mocks)."""
    return "cosmos://localhost:8081/test-db"  # Use Cosmos emulator for local testing


@pytest.fixture
async def cleanup_test_database(test_database_url):
    """Clean up test database after tests (no-op for Cosmos DB - uses mocks)."""
    yield
    # Cosmos DB uses containers, not local files - no cleanup needed
    # Tests should use mocks or Cosmos emulator which handles its own cleanup
    pass


class MockWebhookRequest:
    """Mock webhook request for testing."""
    def __init__(self, json_data: Dict[str, Any], headers: Dict[str, str] = None):
        self.json_data = json_data
        self.headers = headers or {}
    
    async def json(self):
        return self.json_data
    
    def get_header(self, name: str, default: str = None):
        return self.headers.get(name, default)


# Test utilities
def create_mock_webhook_payload(symbol: str = "AAPL", action: str = "buy", price: float = 150.0) -> Dict[str, Any]:
    """Create a mock webhook payload for testing."""
    return {
        "symbol": symbol,
        "action": action,
        "price": price,
        "timestamp": 1234567890,
        "source": "tradingview",
        "metadata": {"test": "data"}
    }


# ============================================================================
# Pytest Hooks for Automatic Dependency Management
# ============================================================================

def pytest_configure(config):
    """
    Register custom markers and configure dependency-aware testing.
    
    This hook runs at pytest startup and:
    1. Registers custom markers for dependency requirements
    2. Logs available/missing optional dependencies
    """
    # Register markers for optional dependencies
    config.addinivalue_line(
        "markers",
        "requires_azure: marks test as requiring Azure SDK (skip if not installed)"
    )
    config.addinivalue_line(
        "markers",
        "requires_fastapi: marks test as requiring FastAPI (skip if not installed)"
    )
    config.addinivalue_line(
        "markers",
        "requires_alpaca: marks test as requiring Alpaca SDK (skip if not installed)"
    )
    config.addinivalue_line(
        "markers",
        "requires_tastytrade: marks test as requiring TastyTrade SDK (skip if not installed)"
    )
    config.addinivalue_line(
        "markers",
        "requires_redis: marks test as requiring Redis (skip if not installed)"
    )
    config.addinivalue_line(
        "markers",
        "requires_hypothesis: marks test as requiring Hypothesis (skip if not installed)"
    )


def pytest_collection_modifyitems(config, items):
    """
    Automatically skip tests based on marker-declared dependencies.
    
    This hook runs after test collection and:
    1. Checks each test for requires_* markers
    2. Skips tests whose dependencies are missing
    3. Allows tests to run if all dependencies are available
    """
    # Define marker to dependency check mapping
    marker_checks = {
        "requires_azure": (AZURE_AVAILABLE, "Azure SDK not installed"),
        "requires_fastapi": (FASTAPI_AVAILABLE, "FastAPI not installed"),
        "requires_alpaca": (ALPACA_AVAILABLE, "Alpaca SDK not installed"),
        "requires_tastytrade": (TASTYTRADE_AVAILABLE, "TastyTrade SDK not installed"),
        "requires_redis": (REDIS_AVAILABLE, "Redis not installed"),
        "requires_hypothesis": (HYPOTHESIS_AVAILABLE, "Hypothesis not installed"),
    }
    
    for item in items:
        for marker_name, (is_available, reason) in marker_checks.items():
            marker = item.get_closest_marker(marker_name)
            if marker is not None and not is_available:
                skip_marker = pytest.mark.skip(reason=reason)
                item.add_marker(skip_marker)
