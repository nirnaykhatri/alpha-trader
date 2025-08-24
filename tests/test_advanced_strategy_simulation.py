"""
Advanced Strategy Integration Tests
Comprehensive tests to simulate order placement, buy, trailing, sell and short scenarios.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timedelta
from typing import Dict, List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.strategies.advanced_strategy import AdvancedTradingStrategy, PositionState, PositionDirection, TradePhase
from src.interfaces import TradingSignal, SignalType, Order, OrderType, OrderSide, OrderStatus
from src.core import ConfigurationManager


class MockOrderManager:
    """Mock order manager for testing."""
    
    def __init__(self):
        self.placed_orders: List[Order] = []
        self.order_counter = 1
    
    async def place_order(self, order: Order) -> str:
        """Mock order placement."""
        order_id = f"order_{self.order_counter}"
        order.order_id = order_id
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.utcnow()
        order.filled_price = order.price or 100.0  # Default price
        order.filled_quantity = order.quantity
        
        self.placed_orders.append(order)
        self.order_counter += 1
        return order_id
    
    def get_orders_for_symbol(self, symbol: str) -> List[Order]:
        """Get all orders for a symbol."""
        return [order for order in self.placed_orders if order.symbol == symbol]
    
    def get_last_order(self) -> Order:
        """Get the last placed order."""
        return self.placed_orders[-1] if self.placed_orders else None


class MockMarketDataProvider:
    """Mock market data provider for testing."""
    
    def __init__(self):
        self.price_history: Dict[str, List[float]] = {}
        self.current_prices: Dict[str, float] = {}
    
    async def get_current_price(self, symbol: str) -> float:
        """Get current price for symbol."""
        return self.current_prices.get(symbol, 100.0)
    
    def set_price(self, symbol: str, price: float):
        """Set current price for symbol."""
        self.current_prices[symbol] = price
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        self.price_history[symbol].append(price)
    
    def simulate_price_movement(self, symbol: str, prices: List[float]):
        """Simulate a series of price movements."""
        for price in prices:
            self.set_price(symbol, price)


@pytest.fixture
def mock_config():
    """Create mock configuration."""
    config_data = {
        'trading': {
            'default_quantity': 100,
            'order_type': 'limit',
            'limit_order_offset': 0.001
        },
        'strategies': {
            'long_strategy': {
                'enabled': True,
                'entry_order_type': 'limit',
                'entry_limit_offset': 0.001,
                'profit_target': 0.05,
                'trailing_profit': {
                    'enabled': True,
                    'trailing_percentage': 0.015,
                    'activation_threshold': 0.03,
                    'min_profit_lock': 0.01,
                    'exit_order_type': 'market'
                },
                'support_averaging': {
                    'enabled': True,
                    'max_attempts': 3,
                    'position_multiplier': 1.5,
                    'support_method': 'technical',
                    'min_support_confidence': 0.7,
                    'support_trailing': {
                        'enabled': True,
                        'trailing_percentage': 0.01,
                        'entry_order_type': 'limit'
                    }
                }
            },
            'short_strategy': {
                'enabled': True,
                'entry_order_type': 'limit',
                'entry_limit_offset': 0.001,
                'profit_target': 0.05,
                'trailing_profit': {
                    'enabled': True,
                    'trailing_percentage': 0.015,
                    'activation_threshold': 0.03,
                    'min_profit_lock': 0.01,
                    'exit_order_type': 'market'
                },
                'resistance_averaging': {
                    'enabled': True,
                    'max_attempts': 3,
                    'position_multiplier': 1.5,
                    'resistance_method': 'technical',
                    'min_resistance_confidence': 0.7,
                    'resistance_trailing': {
                        'enabled': True,
                        'trailing_percentage': 0.01,
                        'entry_order_type': 'limit'
                    }
                }
            }
        }
    }
    
    config = Mock(spec=ConfigurationManager)
    config.get_config = Mock(side_effect=lambda key, default=None: 
        _get_nested_config(config_data, key, default))
    return config


def _get_nested_config(config_data, key, default=None):
    """Helper to get nested configuration values."""
    keys = key.split('.')
    current = config_data
    for k in keys:
        if isinstance(current, dict) and k in current:
            current = current[k]
        else:
            return default
    return current


@pytest.fixture
def mock_order_manager():
    """Create mock order manager."""
    return MockOrderManager()


@pytest.fixture
def mock_market_data():
    """Create mock market data provider."""
    return MockMarketDataProvider()


@pytest.fixture
def mock_support_calculator():
    """Create mock support calculator."""
    calculator = Mock()
    
    # Return empty support/resistance data by default
    empty_data = type('EmptyData', (), {'levels': []})()
    calculator.calculate_support_levels = AsyncMock(return_value=empty_data)
    calculator.calculate_resistance_levels = AsyncMock(return_value=empty_data)
    return calculator


@pytest.fixture
def advanced_strategy(mock_config, mock_order_manager, mock_market_data, mock_support_calculator):
    """Create advanced strategy instance."""
    return AdvancedTradingStrategy(mock_config, mock_order_manager, mock_market_data, mock_support_calculator)


class TestLongStrategySimulation:
    """Test long strategy complete workflow simulation."""
    
    @pytest.mark.asyncio
    async def test_long_entry_and_profit_trailing(self, advanced_strategy, mock_order_manager, mock_market_data):
        """Test long entry, profit rise, trailing, and profitable exit."""
        symbol = "AAPL"
        initial_price = 100.0
        mock_market_data.set_price(symbol, initial_price)
        
        # Step 1: Create long signal
        signal = TradingSignal(
            signal_id="test_long_1",
            symbol=symbol,
            signal_type=SignalType.BUY,
            price=initial_price,
            quantity=100,
            timestamp=datetime.utcnow()
        )
        
        # Step 2: Handle signal (should place entry order)
        result = await advanced_strategy.process_signal(signal)
        assert result is True
        
        # Verify entry order
        orders = mock_order_manager.get_orders_for_symbol(symbol)
        assert len(orders) == 1
        entry_order = orders[0]
        assert entry_order.side == OrderSide.BUY
        assert entry_order.order_type == OrderType.LIMIT
        assert entry_order.quantity == 100
        
        # Step 3: Simulate profitable price movement
        # Price rises 4% (above 3% activation threshold)
        profit_price = initial_price * 1.04
        mock_market_data.set_price(symbol, profit_price)
        
        # Update positions to trigger trailing
        await advanced_strategy.update_positions()
        
        # Verify position is in profit trailing phase
        position = advanced_strategy.positions.get(symbol)
        assert position is not None
        assert position.phase == TradePhase.PROFIT_TRAILING
        assert position.peak_price == profit_price
        
        # Step 4: Price continues to rise (should update trail)
        higher_price = initial_price * 1.06
        mock_market_data.set_price(symbol, higher_price)
        await advanced_strategy.update_positions()
        
        # Trail should update
        assert position.peak_price == higher_price
        
        # Step 5: Price falls to trigger trail exit
        # Falls 2% from peak (exceeds 1.5% trailing threshold)
        exit_price = higher_price * 0.98
        mock_market_data.set_price(symbol, exit_price)
        await advanced_strategy.update_positions()
        
        # Should trigger exit order
        orders = mock_order_manager.get_orders_for_symbol(symbol)
        assert len(orders) == 2  # Entry + Exit
        exit_order = orders[1]
        assert exit_order.side == OrderSide.SELL
        assert exit_order.order_type == OrderType.MARKET
        
        print(f"✅ Long Profit Test: Entry at ${initial_price}, Peak at ${higher_price}, Exit at ${exit_price}")
    
    @pytest.mark.asyncio
    async def test_long_support_averaging_simulation(self, advanced_strategy, mock_order_manager, mock_market_data, mock_support_calculator):
        """Test long entry, price drop, support detection, averaging, and recovery."""
        symbol = "TSLA"
        initial_price = 200.0
        mock_market_data.set_price(symbol, initial_price)
        
        # Step 1: Create long signal and enter position
        signal = TradingSignal(
            signal_id="test_long_2",
            symbol=symbol,
            signal_type=SignalType.BUY,
            price=initial_price,
            quantity=100,
            timestamp=datetime.utcnow()
        )
        
        await advanced_strategy.process_signal(signal)
        
        # Step 2: Simulate price drop to trigger support averaging
        # Drop 8% to hit support level
        support_price = initial_price * 0.90  # Support level at 180.0
        current_price = initial_price * 0.92  # Current price at 184.0 (above support)
        mock_market_data.set_price(symbol, current_price)
        
        # Configure mock support calculator to return support level BELOW current price
        mock_support_data = type('SupportData', (), {
            'levels': [
                type('SupportLevel', (), {
                    'price': support_price,  # 180.0 (below current price of 184.0)
                    'confidence': 0.8,
                    'method': 'technical'
                })()
            ]
        })()
        mock_support_calculator.calculate_support_levels.return_value = mock_support_data
        
        await advanced_strategy.update_positions()
        
        # Should enter support averaging phase
        position = advanced_strategy.positions.get(symbol)
        assert position.phase == TradePhase.SUPPORT_AVERAGING
        
        # Step 3: Price continues to drop (support breaks)
        # Trail 1.2% below support to trigger averaging
        averaging_price = support_price * 0.988  # Below the support level
        mock_market_data.set_price(symbol, averaging_price)
        await advanced_strategy.update_positions()
        
        # Should place averaging order (1.5x position size)
        orders = mock_order_manager.get_orders_for_symbol(symbol)
        assert len(orders) >= 2  # Entry + Averaging
        averaging_order = orders[1]
        assert averaging_order.side == OrderSide.BUY
        assert averaging_order.quantity == 150  # 100 * 1.5 multiplier
        
        # Step 4: Price recovers and hits profit target
        recovery_price = initial_price * 1.04  # 4% above initial
        mock_market_data.set_price(symbol, recovery_price)
        await advanced_strategy.update_positions()
        
        # Should trigger profit trailing
        assert position.phase == TradePhase.PROFIT_TRAILING
        
        print(f"✅ Long Averaging Test: Entry at ${initial_price}, Support at ${support_price}, Recovery at ${recovery_price}")


class TestShortStrategySimulation:
    """Test short strategy complete workflow simulation."""
    
    @pytest.mark.asyncio
    async def test_short_entry_and_profit_trailing(self, advanced_strategy, mock_order_manager, mock_market_data):
        """Test short entry, profit drop, trailing, and profitable cover."""
        symbol = "NVDA"
        initial_price = 300.0
        mock_market_data.set_price(symbol, initial_price)
        
        # Step 1: Create short signal
        signal = TradingSignal(
            signal_id="test_short_1",
            symbol=symbol,
            signal_type=SignalType.SELL,
            price=initial_price,
            quantity=50,
            timestamp=datetime.utcnow()
        )
        
        # Step 2: Handle signal (should place short entry order)
        result = await advanced_strategy.process_signal(signal)
        assert result is True
        
        # Verify short entry order
        orders = mock_order_manager.get_orders_for_symbol(symbol)
        assert len(orders) == 1
        entry_order = orders[0]
        assert entry_order.side == OrderSide.SELL
        assert entry_order.order_type == OrderType.LIMIT
        assert entry_order.quantity == 50
        
        # Step 3: Simulate profitable price drop
        # Price drops 4% (above 3% activation threshold)
        profit_price = initial_price * 0.96
        mock_market_data.set_price(symbol, profit_price)
        
        # Update positions to trigger trailing
        await advanced_strategy.update_positions()
        
        # Verify position is in profit trailing phase
        position = advanced_strategy.positions.get(symbol)
        assert position is not None
        assert position.phase == TradePhase.PROFIT_TRAILING
        
        # Step 4: Price continues to drop (should update trail)
        lower_price = initial_price * 0.94
        mock_market_data.set_price(symbol, lower_price)
        await advanced_strategy.update_positions()
        
        # Step 5: Price rises to trigger trail exit
        # Rises 2% from lowest (exceeds 1.5% trailing threshold)
        exit_price = lower_price * 1.02
        mock_market_data.set_price(symbol, exit_price)
        await advanced_strategy.update_positions()
        
        # Should trigger cover order
        orders = mock_order_manager.get_orders_for_symbol(symbol)
        assert len(orders) == 2  # Entry + Cover
        cover_order = orders[1]
        assert cover_order.side == OrderSide.BUY  # Buy to cover
        assert cover_order.order_type == OrderType.MARKET
        
        print(f"✅ Short Profit Test: Entry at ${initial_price}, Low at ${lower_price}, Cover at ${exit_price}")
    
    @pytest.mark.asyncio
    async def test_short_resistance_averaging_simulation(self, advanced_strategy, mock_order_manager, mock_market_data, mock_support_calculator):
        """Test short entry, price rise, resistance detection, averaging, and recovery."""
        symbol = "MSFT"
        initial_price = 400.0
        mock_market_data.set_price(symbol, initial_price)
        
        # Step 1: Create short signal and enter position
        signal = TradingSignal(
            signal_id="test_short_2",
            symbol=symbol,
            signal_type=SignalType.SELL,
            price=initial_price,
            quantity=25,
            timestamp=datetime.utcnow()
        )
        
        await advanced_strategy.process_signal(signal)
        
        # Step 2: Simulate price rise to trigger resistance averaging
        # Rise 8% to approach resistance level
        resistance_price = initial_price * 1.10  # Resistance level at 440.0
        current_price = initial_price * 1.08     # Current price at 432.0 (below resistance)
        mock_market_data.set_price(symbol, current_price)
        
        # Configure mock resistance calculation with resistance ABOVE current price
        mock_resistance_data = type('ResistanceData', (), {
            'levels': [
                type('ResistanceLevel', (), {
                    'price': resistance_price,  # 440.0 (above current price of 432.0)
                    'confidence': 0.8,
                    'method': 'technical'
                })()
            ]
        })()
        mock_support_calculator.calculate_resistance_levels.return_value = mock_resistance_data
        
        await advanced_strategy.update_positions()
        
        # Should enter resistance averaging phase
        position = advanced_strategy.positions.get(symbol)
        assert position.phase == TradePhase.RESISTANCE_AVERAGING
        
        # Step 3: Price continues to rise (resistance breaks)
        # Trail 1.2% above resistance to trigger averaging
        averaging_price = resistance_price * 1.012  # Above the resistance level
        mock_market_data.set_price(symbol, averaging_price)
        await advanced_strategy.update_positions()
        
        # Should place averaging short order (1.5x position size)
        orders = mock_order_manager.get_orders_for_symbol(symbol)
        assert len(orders) >= 2  # Entry + Averaging
        averaging_order = orders[1]
        assert averaging_order.side == OrderSide.SELL
        assert averaging_order.quantity == 37.5  # 25 * 1.5 multiplier
        
        # Step 4: Price drops and hits profit target
        recovery_price = initial_price * 0.96  # 4% below initial
        mock_market_data.set_price(symbol, recovery_price)
        await advanced_strategy.update_positions()
        
        # Should trigger profit trailing
        assert position.phase == TradePhase.PROFIT_TRAILING
        
        print(f"✅ Short Averaging Test: Entry at ${initial_price}, Resistance at ${resistance_price}, Recovery at ${recovery_price}")


class TestCompleteWorkflowSimulation:
    """Test complete trading workflows end-to-end."""
    
    @pytest.mark.asyncio
    async def test_multiple_positions_management(self, advanced_strategy, mock_order_manager, mock_market_data, mock_support_calculator):
        """Test managing multiple positions simultaneously."""
        symbols = ["AAPL", "TSLA", "NVDA"]
        initial_prices = [150.0, 250.0, 500.0]
        
        # Step 1: Create multiple long positions
        for i, (symbol, price) in enumerate(zip(symbols, initial_prices)):
            mock_market_data.set_price(symbol, price)
            
            signal = TradingSignal(
                signal_id=f"multi_{i}",
                symbol=symbol,
                signal_type=SignalType.BUY,
                price=price,
                quantity=100,
                timestamp=datetime.utcnow()
            )
            
            await advanced_strategy.process_signal(signal)
        
        # Verify all positions created
        assert len(advanced_strategy.positions) == 3
        assert len(mock_order_manager.placed_orders) == 3
        
        # Step 2: Simulate different outcomes for each position
        # AAPL: Profitable - trigger trailing
        mock_market_data.set_price("AAPL", 150.0 * 1.04)
        
        # TSLA: Loss - trigger support averaging
        tsla_current_price = 250.0 * 0.92  # 230.0
        tsla_support_price = 250.0 * 0.90  # 225.0 (below current)
        mock_market_data.set_price("TSLA", tsla_current_price)
        
        # Configure support calculator for TSLA
        mock_support_data = type('SupportData', (), {
            'levels': [
                type('SupportLevel', (), {
                    'price': tsla_support_price,
                    'confidence': 0.8,
                    'method': 'technical'
                })()
            ]
        })()
        mock_support_calculator.calculate_support_levels.return_value = mock_support_data
        
        # NVDA: Neutral - no action
        mock_market_data.set_price("NVDA", 500.0 * 1.01)
        
        # Update all positions
        await advanced_strategy.update_positions()
        
        # Step 3: Verify different states
        aapl_position = advanced_strategy.positions["AAPL"]
        tsla_position = advanced_strategy.positions["TSLA"]
        nvda_position = advanced_strategy.positions["NVDA"]
        
        assert aapl_position.phase == TradePhase.PROFIT_TRAILING
        assert tsla_position.phase == TradePhase.SUPPORT_AVERAGING
        assert nvda_position.phase == TradePhase.ENTRY
        
        print("✅ Multi-Position Test: Different strategies running simultaneously")
    
    @pytest.mark.asyncio
    async def test_position_lifecycle_complete(self, advanced_strategy, mock_order_manager, mock_market_data, mock_support_calculator):
        """Test complete position lifecycle from entry to exit."""
        symbol = "LIFECYCLE"
        initial_price = 100.0
        mock_market_data.set_price(symbol, initial_price)
        
        # Step 1: Entry
        signal = TradingSignal(
            signal_id="lifecycle_test",
            symbol=symbol,
            signal_type=SignalType.BUY,
            price=initial_price,
            quantity=100,
            timestamp=datetime.utcnow()
        )
        
        await advanced_strategy.process_signal(signal)
        assert len(mock_order_manager.placed_orders) == 1
        
        # Step 2: Initial loss and averaging
        current_price_down = initial_price * 0.92  # 92.0 (current price after loss)
        support_level = initial_price * 0.90       # 90.0 (support below current)
        mock_market_data.set_price(symbol, current_price_down)
        
        # Configure support level BELOW current price
        mock_support_data = type('SupportData', (), {
            'levels': [
                type('SupportLevel', (), {
                    'price': support_level,  # 90.0 (below current price of 92.0)
                    'confidence': 0.8,
                    'method': 'technical'
                })()
            ]
        })()
        mock_support_calculator.calculate_support_levels.return_value = mock_support_data
        
        await advanced_strategy.update_positions()
        mock_market_data.set_price(symbol, initial_price * 0.89)  # Drop below support
        await advanced_strategy.update_positions()
        
        # Should have averaging order
        assert len(mock_order_manager.placed_orders) == 2
        
        # Step 3: Recovery and profit trailing
        mock_market_data.set_price(symbol, initial_price * 1.04)
        await advanced_strategy.update_positions()
        
        position = advanced_strategy.positions[symbol]
        assert position.phase == TradePhase.PROFIT_TRAILING
        
        # Step 4: Final exit
        mock_market_data.set_price(symbol, initial_price * 1.02)  # Trigger trail exit
        await advanced_strategy.update_positions()
        
        # Should have exit order
        assert len(mock_order_manager.placed_orders) == 3
        exit_order = mock_order_manager.placed_orders[-1]
        assert exit_order.side == OrderSide.SELL
        
        print("✅ Complete Lifecycle Test: Entry → Loss → Averaging → Profit → Exit")


def run_strategy_simulation_tests():
    """Run all strategy simulation tests."""
    print("\n🧪 Running Advanced Strategy Simulation Tests...")
    print("=" * 60)
    
    # Run pytest with specific test markers
    import subprocess
    result = subprocess.run([
        "python", "-m", "pytest", 
        "tests/test_advanced_strategy_simulation.py", 
        "-v", "--tb=short"
    ], capture_output=True, text=True)
    
    print(result.stdout)
    if result.stderr:
        print("Errors:")
        print(result.stderr)
    
    return result.returncode == 0


if __name__ == "__main__":
    """Run tests directly."""
    print("🚀 Starting Advanced Strategy Simulation Tests...")
    success = run_strategy_simulation_tests()
    
    if success:
        print("\n✅ All simulation tests passed!")
        print("🎯 Advanced strategy is working as expected")
    else:
        print("\n❌ Some tests failed")
        print("🔧 Please check the output above for details")
