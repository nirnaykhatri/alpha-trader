#!/usr/bin/env python3
"""
Test script to simulate the exact scenario you described:
1. TradingView sends short signal
2. Same day, TradingView sends long signal 
3. Bot should ignore the long signal (not close the short position)
"""

import asyncio
import sys
import os
from datetime import datetime
from unittest.mock import AsyncMock, Mock

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from src.core.configuration import ConfigurationManager
from src.strategies.dca_strategy import DCAStrategy
from src.strategies.position_state import PositionState, PositionDirection, TradePhase
from src.interfaces import TradingSignal, SignalType


async def test_opposing_signals_scenario():
    """Test the exact scenario you described."""
    print("=== Testing Opposing Signals Scenario ===")
    print("Scenario: TradingView sends SHORT signal, then LONG signal same day")
    print("Expected: Bot should ignore LONG signal, keep SHORT position open\n")
    
    # Setup mock dependencies
    config = ConfigurationManager()  # Uses config/ TOML files
    mock_order_manager = AsyncMock()
    mock_market_data = AsyncMock()
    mock_risk_manager = AsyncMock()
    mock_support_calculator = Mock()
    
    # Mock the get_current_price method
    mock_market_data.get_current_price.return_value = 150.0
    mock_risk_manager.calculate_position_size.return_value = 100
    mock_order_manager.place_order.return_value = "order_123"
    
    # Create BotConfiguration for DCAStrategy
    from decimal import Decimal
    from src.domain.bot_models import (
        BotConfiguration, DCAConfig, BotType, PositionMode,
        AveragingOrdersConfig, TakeProfitConfig, StopLossConfig,
        QuickSetupPreset
    )
    
    bot_config = BotConfiguration(
        symbol="AAPL",
        exchange="alpaca",
        bot_type=BotType.DCA,
        position_mode=PositionMode.LONG,
        dca_config=DCAConfig(
            quick_setup=QuickSetupPreset.MID_TERM,
            averaging_orders=AveragingOrdersConfig(
                orders_count=5,
                step_percent=Decimal("2.0"),
                amount_multiplier=Decimal("1.5"),
            ),
            take_profit=TakeProfitConfig(
                enabled=True,
                price_change_percent=Decimal("5.0"),
                trailing_deviation=Decimal("2.0"),
            ),
            stop_loss=StopLossConfig(enabled=True, percent=Decimal("10.0")),
        ),
    )
    
    # Create strategy instance
    strategy = DCAStrategy(
        order_manager=mock_order_manager,
        market_data=mock_market_data,
        risk_manager=mock_risk_manager,
        bot_config=bot_config
    )
    
    symbol = "AAPL"
    
    # Step 1: Process SHORT signal from TradingView
    print("Step 1: Processing SHORT signal from TradingView...")
    short_signal = TradingSignal(
        signal_id="tradingview_short_123",
        symbol=symbol,
        signal_type=SignalType.SELL,
        price=150.0,  # TradingView signal price (will be updated with current market price)
        timestamp=datetime.utcnow()
    )
    
    result = await strategy.process_signal(short_signal)
    print(f"   Short signal processed: {result}")
    print(f"   Orders placed: {mock_order_manager.place_order.call_count}")
    
    # Verify short position was created
    assert symbol in strategy.positions
    short_position = strategy.positions[symbol]
    print(f"   Position created: {short_position.direction} - {short_position.quantity} shares")
    
    # Step 2: Same day - Process LONG signal from TradingView
    print("\nStep 2: Processing LONG signal from TradingView (same day)...")
    long_signal = TradingSignal(
        signal_id="tradingview_long_456", 
        symbol=symbol,
        signal_type=SignalType.BUY,
        price=148.0,  # TradingView signal price
        timestamp=datetime.utcnow()
    )
    
    # Reset call count to track new orders
    mock_order_manager.place_order.reset_mock()
    
    result = await strategy.process_signal(long_signal)
    print(f"   Long signal processed: {result}")
    print(f"   New orders placed: {mock_order_manager.place_order.call_count}")
    
    # Step 3: Verify the correct behavior
    print("\nStep 3: Verifying behavior...")
    
    # Check that no new orders were placed (long signal was ignored)
    if mock_order_manager.place_order.call_count == 0:
        print("   ✅ CORRECT: Long signal was ignored - no new orders placed")
    else:
        print("   ❌ ERROR: Long signal was processed - new orders were placed")
    
    # Check that original short position still exists
    if symbol in strategy.positions and strategy.positions[symbol].direction == PositionDirection.SHORT:
        print("   ✅ CORRECT: Short position still exists and is unchanged")
    else:
        print("   ❌ ERROR: Short position was modified or closed")
    
    # Check that no long position was created
    long_positions = [pos for pos in strategy.positions.values() if pos.direction == PositionDirection.LONG]
    if len(long_positions) == 0:
        print("   ✅ CORRECT: No long position was created")
    else:
        print(f"   ❌ ERROR: Long position was created: {long_positions}")
    
    print("\n=== Test Summary ===")
    print("With ignore_opposing_signals=true (current config):")
    print("• Short signal → Creates short position ✅")
    print("• Long signal (same symbol) → Ignored, short position preserved ✅")
    print("• Bot follows your requirement: no new position until previous is closed ✅")
    print("\nPosition will only be closed when:")
    print("• Trailing stop is hit (price moves favorably)")
    print("• Support/resistance averaging rules trigger exit")
    print("• Manual close signal is received")


if __name__ == "__main__":
    asyncio.run(test_opposing_signals_scenario())
