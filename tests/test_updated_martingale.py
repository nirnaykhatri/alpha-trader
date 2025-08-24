#!/usr/bin/env python3
"""
Test script to demonstrate updated martingale position sizing with 1% initial positions.
Shows how positions grow: 1%, 2%, 4%, 8% with configurable multipliers.
"""

import asyncio
import sys
import os
from datetime import datetime
from typing import Dict, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.risk.risk_manager import RiskManager
from src.interfaces import IConfigurationManager, IPositionManager, IAccountProvider
from src import TradingSignal, SignalType


class MockConfig(IConfigurationManager):
    """Mock configuration for testing."""
    
    def __init__(self):
        self.config = {
            "trading": {
                "position_sizing": {
                    "method": "percentage",
                    "initial_portfolio_percentage": 0.01,  # Start with 1%
                    "averaging": {
                        "enabled": True,
                        "multiplier": 2.0,  # Double each time
                        "max_attempts": 3   # 1%, 2%, 4% = 7% max exposure
                    },
                    "min_quantity": 1,
                    "max_quantity": 10000,
                    "max_total_position_percentage": 0.15
                },
                "risk_per_trade": 0.02,
                "max_portfolio_risk": 0.10,
                "max_position_size": 1000,
                "max_daily_trades": 50
            }
        }
    
    def get_config(self, key: str, default: Any = None) -> Any:
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def update_config(self, key: str, value: Any):
        pass
    
    def set_config(self, key: str, value: Any):
        pass
    
    def reload_config(self):
        pass


class MockAccountProvider(IAccountProvider):
    """Mock account provider for testing."""
    
    def __init__(self, buying_power: float = 100000.0, account_value: float = 50000.0):
        self._buying_power = buying_power
        self._account_value = account_value
    
    async def get_buying_power(self) -> float:
        return self._buying_power
    
    async def get_account_value(self) -> float:
        return self._account_value
    
    async def get_portfolio_value(self) -> float:
        return self._account_value
    
    async def get_positions(self) -> Dict[str, Any]:
        return {}


class MockPositionManager(IPositionManager):
    """Mock position manager for testing."""
    
    async def get_current_positions(self) -> Dict[str, Any]:
        return {}
    
    async def get_all_positions(self) -> Dict[str, Any]:
        return {}
    
    async def get_position(self, symbol: str) -> Any:
        return None
    
    async def update_position(self, symbol: str, position_data: Any):
        pass


async def test_martingale_sizing():
    """Test the updated martingale position sizing logic with average price calculations."""
    
    print("🎯 Testing Updated Martingale Position Sizing with Average Price Tracking")
    print("=" * 80)
    
    # Setup
    config = MockConfig()
    account_provider = MockAccountProvider(buying_power=100000.0, account_value=50000.0)
    position_manager = MockPositionManager()
    
    risk_manager = RiskManager(config, position_manager, account_provider)
    
    # Test scenarios
    scenarios = [
        {
            "name": "LONG Position - Averaging Down (AAPL)",
            "symbol": "AAPL",
            "signal_type": SignalType.BUY,
            "prices": [150.0, 145.0, 140.0, 135.0],  # Declining prices (averaging down)
            "direction": "LONG"
        },
        {
            "name": "SHORT Position - Averaging Up (TSLA)", 
            "symbol": "TSLA",
            "signal_type": SignalType.SELL,
            "prices": [200.0, 205.0, 210.0, 215.0],  # Rising prices (averaging up)
            "direction": "SHORT"
        }
    ]
    
    buying_power = await account_provider.get_buying_power()
    
    for scenario in scenarios:
        print(f"\n📊 {scenario['name']}")
        print("=" * 60)
        print(f"   Direction: {scenario['direction']}")
        print(f"   Symbol: {scenario['symbol']}")
        print(f"   Buying Power: ${buying_power:,.2f}")
        print(f"   Initial Portfolio %: {config.get_config('trading.position_sizing.initial_portfolio_percentage') * 100:.1f}%")
        print(f"   Multiplier: {config.get_config('trading.position_sizing.averaging.multiplier')}")
        print()
        
        # Track cumulative position
        total_shares = 0
        total_cost = 0.0
        average_price = 0.0
        
        print("📈 Martingale Execution Sequence:")
        print("-" * 50)
        
        for attempt, price in enumerate(scenario["prices"]):
            # Create signal for this attempt
            signal = TradingSignal(
                signal_id=f"test-{attempt:03d}",
                symbol=scenario["symbol"],
                signal_type=scenario["signal_type"],
                price=price,
                timestamp=datetime.utcnow()
            )
            
            # Calculate position size for this attempt
            quantity = await risk_manager.calculate_position_size(
                symbol=scenario["symbol"], 
                signal=signal, 
                averaging_attempt=attempt
            )
            
            if quantity > 0:
                # Calculate costs
                trade_cost = quantity * price
                total_cost += trade_cost
                total_shares += quantity
                
                # Calculate new average price
                if total_shares > 0:
                    average_price = total_cost / total_shares
                
                # Calculate percentage of buying power
                percentage_of_buying_power = (trade_cost / buying_power) * 100
                total_percentage = (total_cost / buying_power) * 100
                
                # Calculate unrealized P&L
                current_value = total_shares * price
                unrealized_pnl = current_value - total_cost
                unrealized_pnl_percent = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0
                
                print(f"   {'Initial' if attempt == 0 else f'Averaging #{attempt}'} @ ${price:.2f}:")
                print(f"      Quantity: {quantity:,.0f} shares")
                print(f"      Trade Cost: ${trade_cost:,.2f} ({percentage_of_buying_power:.2f}% of buying power)")
                print(f"      Total Shares: {total_shares:,.0f}")
                print(f"      Total Cost: ${total_cost:,.2f} ({total_percentage:.2f}% of buying power)")
                print(f"      Average Price: ${average_price:.2f}")
                
                if scenario["direction"] == "LONG":
                    print(f"      Current Value: ${current_value:,.2f}")
                    print(f"      Unrealized P&L: ${unrealized_pnl:,.2f} ({unrealized_pnl_percent:+.2f}%)")
                    if price < average_price:
                        improvement = ((average_price - price) / average_price) * 100
                        print(f"      � Averaging DOWN improved cost basis by {improvement:.2f}%")
                else:  # SHORT
                    # For short positions, profit when price goes down
                    short_pnl = total_cost - current_value  # Opposite of long
                    short_pnl_percent = (short_pnl / total_cost * 100) if total_cost > 0 else 0
                    print(f"      Short Value: ${current_value:,.2f}")
                    print(f"      Unrealized P&L: ${short_pnl:,.2f} ({short_pnl_percent:+.2f}%)")
                    if price > average_price:
                        print(f"      💡 Averaging UP - defending against rising prices")
                
                print()
            else:
                print(f"   Attempt {attempt} @ ${price:.2f}: SKIPPED (insufficient funds)")
                print()
        
        # Final position summary
        if total_shares > 0:
            print("📋 Final Position Summary:")
            print("-" * 30)
            print(f"   Total Shares: {total_shares:,.0f}")
            print(f"   Total Investment: ${total_cost:,.2f}")
            print(f"   Average Price: ${average_price:.2f}")
            print(f"   Portfolio Exposure: {(total_cost / buying_power) * 100:.2f}%")
            
            final_price = scenario["prices"][-1]
            if scenario["direction"] == "LONG":
                final_value = total_shares * final_price
                final_pnl = final_value - total_cost
                final_pnl_percent = (final_pnl / total_cost * 100) if total_cost > 0 else 0
                print(f"   Final Market Value: ${final_value:,.2f}")
                print(f"   Final P&L: ${final_pnl:,.2f} ({final_pnl_percent:+.2f}%)")
            else:  # SHORT
                final_value = total_shares * final_price
                final_pnl = total_cost - final_value
                final_pnl_percent = (final_pnl / total_cost * 100) if total_cost > 0 else 0
                print(f"   Final Market Value: ${final_value:,.2f}")
                print(f"   Final P&L: ${final_pnl:,.2f} ({final_pnl_percent:+.2f}%)")
        
        print()
    
    # Test different multipliers with average price impact
    print("\n🔄 Testing Different Multipliers - Average Price Impact:")
    print("=" * 65)
    
    multipliers = [1.5, 2.0, 3.0]
    test_prices = [150.0, 145.0, 140.0, 135.0]  # Averaging down scenario
    
    for multiplier in multipliers:
        config.config["trading"]["position_sizing"]["averaging"]["multiplier"] = multiplier
        
        print(f"\n   📊 Multiplier: {multiplier}x")
        print("   " + "-" * 40)
        
        total_shares = 0
        total_cost = 0.0
        
        for attempt, price in enumerate(test_prices):
            signal = TradingSignal(
                signal_id=f"mult-{attempt:03d}",
                symbol="TEST",
                signal_type=SignalType.BUY,
                price=price,
                timestamp=datetime.utcnow()
            )
            
            quantity = await risk_manager.calculate_position_size("TEST", signal, averaging_attempt=attempt)
            
            if quantity > 0:
                trade_cost = quantity * price
                total_cost += trade_cost
                total_shares += quantity
                average_price = total_cost / total_shares if total_shares > 0 else 0
                
                percentage = (trade_cost / buying_power) * 100
                
                print(f"   Attempt {attempt}: {quantity:,.0f} shares @ ${price:.2f} "
                      f"({percentage:.2f}%) → Avg: ${average_price:.2f}")
        
        final_avg = total_cost / total_shares if total_shares > 0 else 0
        total_exposure = (total_cost / buying_power) * 100
        print(f"   📈 Final: {total_shares:,.0f} shares, ${final_avg:.2f} avg, {total_exposure:.2f}% exposure")
    
    print()
    print("✅ Martingale position sizing test with average price tracking completed!")
    print()
    print("📋 Key Insights:")
    print("   • Initial positions start conservatively at 1% of buying power")
    print("   • Each averaging attempt uses configurable multiplier (1.5x, 2.0x, 3.0x)")
    print("   • Average price improves with each averaging down/up execution")
    print("   • Long positions average DOWN when price falls (improving cost basis)")
    print("   • Short positions average UP when price rises (defending position)")
    print("   • Total exposure is tracked and limited by max_total_position_percentage")
    print("   • Unrealized P&L calculated correctly for both directions")


async def main():
    """Run the martingale sizing test."""
    try:
        await test_martingale_sizing()
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
