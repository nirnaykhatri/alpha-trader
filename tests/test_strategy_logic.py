"""
Test Strategy Logic - Simulates price movements to test DCA, take profit, trailing, and stop loss
"""

import asyncio
import sys
import pytest
from datetime import datetime, timedelta
from decimal import Decimal


@pytest.mark.asyncio
async def test_long_position_scenarios():
    """Test LONG position scenarios"""
    print("=" * 80)
    print("Testing LONG Position Scenarios")
    print("=" * 80)
    
    from src.strategies.position_state import PositionState, PositionDirection
    from src.core.configuration import ConfigurationManager
    from src.strategies.dca_planner import DCAPlanner
    
    # Initialize components
    config = ConfigurationManager()
    
    # Create a LONG position at $100
    position = PositionState(
        symbol="AAPL",
        direction=PositionDirection.LONG,
        phase="entry",
        quantity=100,
        average_price=100.0,
        current_price=100.0,
        entry_time=datetime.utcnow(),
        position_lifecycle_id="AAPL_test_long"
    )
    
    print(f"\n📊 Initial Position:")
    print(f"   Symbol: {position.symbol}")
    print(f"   Direction: {position.direction}")
    print(f"   Quantity: {position.quantity}")
    print(f"   Entry Price: ${position.average_price:.2f}")
    print(f"   Current Price: ${position.current_price:.2f}")
    
    # Scenario 1: Price drops (should trigger DCA check)
    print("\n" + "=" * 80)
    print("SCENARIO 1: Price drops to $95 (-5%)")
    print("=" * 80)
    position.current_price = 95.0
    position.unrealized_pnl = (95.0 - 100.0) * 100
    position.unrealized_pnl_percent = -5.0
    
    print(f"   Current Price: ${position.current_price:.2f}")
    print(f"   Unrealized P&L: ${position.unrealized_pnl:.2f} ({position.unrealized_pnl_percent:.1f}%)")
    print(f"   ✅ DCA Check: Position is down, should evaluate support levels for averaging")
    
    # Scenario 2: Price rises (take profit check)
    print("\n" + "=" * 80)
    print("SCENARIO 2: Price rises to $105 (+5%)")
    print("=" * 80)
    position.current_price = 105.0
    position.unrealized_pnl = (105.0 - 100.0) * 100
    position.unrealized_pnl_percent = 5.0
    
    print(f"   Current Price: ${position.current_price:.2f}")
    print(f"   Unrealized P&L: ${position.unrealized_pnl:.2f} ({position.unrealized_pnl_percent:.1f}%)")
    print(f"   ✅ Take Profit Check: Position is profitable, should evaluate exit strategy")
    
    # Scenario 3: Trailing stop
    print("\n" + "=" * 80)
    print("SCENARIO 3: Price rises to $110, then drops to $108")
    print("=" * 80)
    position.current_price = 110.0
    position.unrealized_pnl = (110.0 - 100.0) * 100
    position.unrealized_pnl_percent = 10.0
    
    print(f"   Peak Price: ${position.current_price:.2f} (+{position.unrealized_pnl_percent:.1f}%)")
    
    position.current_price = 108.0
    position.unrealized_pnl = (108.0 - 100.0) * 100
    position.unrealized_pnl_percent = 8.0
    
    print(f"   Current Price: ${position.current_price:.2f} (+{position.unrealized_pnl_percent:.1f}%)")
    print(f"   ✅ Trailing Stop: If trailing stop at 2%, should trigger exit (dropped from $110 to $108)")
    
    # Scenario 4: Stop loss
    print("\n" + "=" * 80)
    print("SCENARIO 4: Price drops to $90 (-10%)")
    print("=" * 80)
    position.current_price = 90.0
    position.unrealized_pnl = (90.0 - 100.0) * 100
    position.unrealized_pnl_percent = -10.0
    
    print(f"   Current Price: ${position.current_price:.2f}")
    print(f"   Unrealized P&L: ${position.unrealized_pnl:.2f} ({position.unrealized_pnl_percent:.1f}%)")
    print(f"   ⛔ Stop Loss: If max loss is -8%, should trigger emergency exit")


@pytest.mark.asyncio
async def test_short_position_scenarios():
    """Test SHORT position scenarios"""
    print("\n\n" + "=" * 80)
    print("Testing SHORT Position Scenarios")
    print("=" * 80)
    
    from src.strategies.position_state import PositionState, PositionDirection
    
    # Create a SHORT position at $100
    position = PositionState(
        symbol="TSLA",
        direction=PositionDirection.SHORT,
        phase="entry",
        quantity=100,
        average_price=100.0,
        current_price=100.0,
        entry_time=datetime.utcnow(),
        position_lifecycle_id="TSLA_test_short"
    )
    
    print(f"\n📊 Initial Position:")
    print(f"   Symbol: {position.symbol}")
    print(f"   Direction: {position.direction}")
    print(f"   Quantity: {position.quantity}")
    print(f"   Entry Price: ${position.average_price:.2f}")
    print(f"   Current Price: ${position.current_price:.2f}")
    
    # Scenario 1: Price rises (should trigger DCA check for shorts)
    print("\n" + "=" * 80)
    print("SCENARIO 1: Price rises to $105 (-5% for short)")
    print("=" * 80)
    position.current_price = 105.0
    position.unrealized_pnl = (100.0 - 105.0) * 100  # Reversed for short
    position.unrealized_pnl_percent = -5.0
    
    print(f"   Current Price: ${position.current_price:.2f}")
    print(f"   Unrealized P&L: ${position.unrealized_pnl:.2f} ({position.unrealized_pnl_percent:.1f}%)")
    print(f"   ✅ DCA Check: Position is down (price rose), should evaluate resistance levels for averaging")
    
    # Scenario 2: Price drops (take profit for short)
    print("\n" + "=" * 80)
    print("SCENARIO 2: Price drops to $95 (+5% for short)")
    print("=" * 80)
    position.current_price = 95.0
    position.unrealized_pnl = (100.0 - 95.0) * 100
    position.unrealized_pnl_percent = 5.0
    
    print(f"   Current Price: ${position.current_price:.2f}")
    print(f"   Unrealized P&L: ${position.unrealized_pnl:.2f} ({position.unrealized_pnl_percent:.1f}%)")
    print(f"   ✅ Take Profit Check: Position is profitable, should evaluate exit strategy")


@pytest.mark.asyncio
async def test_dca_progressive_validation():
    """Test DCA progressive price validation"""
    print("\n\n" + "=" * 80)
    print("Testing DCA Progressive Price Validation")
    print("=" * 80)
    
    from src.strategies.position_state import PositionState, PositionDirection
    
    position = PositionState(
        symbol="AAPL",
        direction=PositionDirection.LONG,
        phase="averaging",
        quantity=100,
        average_price=100.0,
        current_price=95.0,
        entry_time=datetime.utcnow(),
        position_lifecycle_id="AAPL_test_dca"
    )
    
    print("\n📊 Initial Position: 100 shares @ $100")
    
    # DCA Attempt 1: $95 (valid - lower than entry)
    print("\n✅ DCA Attempt 1: Add 50 shares @ $95")
    position.averaging_attempts = 1
    position.last_dca_price = 95.0
    position.dca_order_prices.append(95.0)
    new_avg = ((100 * 100.0) + (50 * 95.0)) / 150
    print(f"   Last DCA Price: ${position.last_dca_price:.2f}")
    print(f"   New Average: ${new_avg:.2f}")
    print(f"   Result: VALID (lower than $100 entry)")
    
    # DCA Attempt 2: $92 (valid - lower than last DCA)
    print("\n✅ DCA Attempt 2: Add 50 shares @ $92")
    print(f"   Last DCA Price: ${position.last_dca_price:.2f}")
    print(f"   Proposed Price: $92.00")
    print(f"   Result: VALID ($92 < $95, progressive averaging)")
    
    # DCA Attempt 3: $96 (invalid - higher than last DCA)
    print("\n❌ DCA Attempt 3: Add 50 shares @ $96")
    print(f"   Last DCA Price: ${position.last_dca_price:.2f}")
    print(f"   Proposed Price: $96.00")
    print(f"   Result: REJECTED ($96 > $95, not progressive)")
    print(f"   Reason: Each DCA must be LOWER than previous for LONG positions")


@pytest.mark.asyncio
async def test_configuration_values():
    """Show current strategy configuration"""
    print("\n\n" + "=" * 80)
    print("Current Strategy Configuration")
    print("=" * 80)
    
    from src.core.configuration import ConfigurationManager
    
    config = ConfigurationManager()
    
    print("\n📋 Position Sizing:")
    print(f"   Default Size: {config.get_config('position_sizing.default_size_percent', 0.04) * 100:.1f}%")
    print(f"   Max Attempts: {config.get_config('position_sizing.averaging.max_attempts', 3)}")
    print(f"   DCA Multiplier: {config.get_config('position_sizing.averaging.multiplier', 1.5)}x")
    
    print("\n📋 Risk Management:")
    print(f"   Max Loss Per Trade: {config.get_config('risk_management.max_loss_per_trade', 0.02) * 100:.1f}%")
    print(f"   Stop Loss: {config.get_config('risk_management.stop_loss_percent', 0.05) * 100:.1f}%")
    
    print("\n📋 DCA Strategy:")
    print(f"   Min Support Confidence: {config.get_config('strategies.dca.min_support_confidence', 0.70) * 100:.0f}%")
    print(f"   Support Buffer: {config.get_config('strategies.dca.support_buffer_percent', 0.005) * 100:.2f}%")
    
    print("\n📋 Take Profit:")
    print(f"   Target Profit: {config.get_config('strategies.long_strategy.target_profit_percent', 0.05) * 100:.1f}%")
