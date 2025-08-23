"""
PyTest configuration and shared fixtures.
"""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any, Generator, AsyncGenerator
from datetime import datetime
import yaml

# Import the modules we're testing
from src.core import ConfigurationManager
from src.database import DatabaseManager
from src.trading import OrderManager
from src.position import PositionManager
from src.risk import RiskManager
from src.signals import TradingViewSignalListener
from src.data import AlpacaMarketDataProvider
from src.strategies import TechnicalSupportCalculator, ConfigurableTrailingProfitManager
from src.trading_bot import TradingBotOrchestrator
from src.interfaces import TradingSignal, Position, Order, OrderType, OrderStatus, SignalType
from src.exceptions import *

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
            "url": "sqlite:///test_trading_bot.db",
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
    """Create a temporary config file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(test_config_data, f)
        config_file = f.name
    
    yield config_file
    
    # Cleanup
    if os.path.exists(config_file):
        os.unlink(config_file)


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
def sample_trading_signal() -> TradingSignal:
    """Sample trading signal for testing."""
    return TradingSignal(
        signal_id="test-signal-123",
        symbol="AAPL",
        signal_type=SignalType.BUY,
        price=150.0,
        timestamp=datetime.utcnow(),
        metadata={"test": "data"}
    )


@pytest.fixture
def sample_position() -> Position:
    """Sample position for testing."""
    return Position(
        symbol="AAPL",
        quantity=100,
        average_price=150.0,
        current_price=155.0,
        market_value=15500.0,
        unrealized_pnl=500.0,
        unrealized_pnl_percent=0.033,
        side="long",
        created_at=1234567890,
        updated_at=1234567890
    )


@pytest.fixture
def sample_order() -> Order:
    """Sample order for testing."""
    return Order(
        id="test_order_id",
        symbol="AAPL",
        quantity=100,
        side="buy",
        order_type=OrderType.LIMIT,
        limit_price=150.0,
        status=OrderStatus.NEW,
        filled_quantity=0,
        filled_average_price=0.0,
        created_at=1234567890,
        updated_at=1234567890
    )


@pytest.fixture
async def mock_database():
    """Mock database for testing."""
    mock_db = Mock(spec=DatabaseManager)
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
    """Mock order manager."""
    mock_manager = Mock(spec=OrderManager)
    mock_manager.trading_client = mock_alpaca_trading_client
    mock_manager.submit_order = AsyncMock()
    mock_manager.cancel_order = AsyncMock()
    mock_manager.get_order_status = AsyncMock()
    mock_manager.get_active_orders = AsyncMock(return_value=[])
    return mock_manager


@pytest.fixture
def mock_position_manager(mock_database):
    """Mock position manager."""
    mock_manager = Mock(spec=PositionManager)
    mock_manager.database = mock_database
    mock_manager.get_position = AsyncMock()
    mock_manager.update_position = AsyncMock()
    mock_manager.get_all_positions = AsyncMock(return_value=[])
    mock_manager.calculate_unrealized_pnl = AsyncMock()
    return mock_manager


@pytest.fixture
def mock_risk_manager():
    """Mock risk manager."""
    mock_manager = Mock(spec=RiskManager)
    mock_manager.validate_trade = AsyncMock(return_value=True)
    mock_manager.calculate_position_size = AsyncMock(return_value=100)
    mock_manager.check_portfolio_risk = AsyncMock(return_value=True)
    mock_manager.get_risk_metrics = AsyncMock(return_value={})
    return mock_manager


@pytest.fixture
def mock_market_data(mock_alpaca_data_client):
    """Mock market data provider."""
    mock_provider = Mock(spec=AlpacaMarketDataProvider)
    mock_provider.data_client = mock_alpaca_data_client
    mock_provider.get_current_price = AsyncMock(return_value=150.0)
    mock_provider.get_historical_data = AsyncMock()
    mock_provider.get_latest_quote = AsyncMock()
    return mock_provider


@pytest.fixture
def mock_support_calculator():
    """Mock technical support calculator."""
    mock_calc = Mock(spec=TechnicalSupportCalculator)
    mock_calc.calculate_support_levels = AsyncMock(return_value=[140.0, 145.0])
    mock_calc.should_average_down = AsyncMock(return_value=True)
    return mock_calc


@pytest.fixture
def mock_trailing_profit_manager():
    """Mock trailing profit manager."""
    mock_manager = Mock(spec=ConfigurableTrailingProfitManager)
    mock_manager.should_take_profit = AsyncMock(return_value=False)
    mock_manager.update_trailing_stop = AsyncMock()
    mock_manager.get_trailing_stop_price = AsyncMock(return_value=148.0)
    return mock_manager


@pytest.fixture
def mock_signal_listener():
    """Mock signal listener."""
    mock_listener = Mock(spec=TradingViewSignalListener)
    mock_listener.start = AsyncMock()
    mock_listener.stop = AsyncMock()
    mock_listener.register_signal_handler = Mock()
    return mock_listener


@pytest.fixture
async def test_database_url():
    """Temporary database URL for testing."""
    return "sqlite:///test_trading_bot.db"


@pytest.fixture
async def cleanup_test_database(test_database_url):
    """Clean up test database after tests."""
    yield
    # Remove test database file
    db_file = test_database_url.replace("sqlite:///", "")
    if os.path.exists(db_file):
        os.unlink(db_file)


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
