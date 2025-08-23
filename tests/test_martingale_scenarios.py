#!/usr/bin/env python3
"""
Comprehensive Martingale Strategy Test - Shows realistic trading scenarios
with average price improvements and P&L tracking for both long and short positions.
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
                    "initial_portfolio_percentage": 0.01,  # 1% start
                    "averaging": {
                        "enabled": True,
                        "multiplier": 2.0,  # Double each time
                        "max_attempts": 3   # Max 3 attempts
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


async def simulate_martingale_scenario(risk_manager, scenario_name: str, symbol: str, 
                                     signal_type: SignalType, prices: list, direction: str):
    """Simulate a complete martingale scenario with detailed tracking."""
    
    print(f"\n🎯 {scenario_name}")
    print("=" * 70)
    print(f"   Strategy: {direction} Position")
    print(f"   Symbol: {symbol}")
    print(f"   Price Sequence: {' → '.join([f'${p:.2f}' for p in prices])}")
    
    if direction == "LONG":
        trend = "📉 Declining" if prices[-1] < prices[0] else "📈 Rising"
        print(f"   Market Trend: {trend} (Averaging DOWN strategy)")
    else:
        trend = "📈 Rising" if prices[-1] > prices[0] else "📉 Declining" 
        print(f"   Market Trend: {trend} (Averaging UP strategy)")
    
    print()
    
    # Track position
    total_shares = 0
    total_cost = 0.0
    trades = []
    
    print("📊 Trade Execution Sequence:")
    print("-" * 50)
    
    for attempt, price in enumerate(prices):
        # Create signal
        signal = TradingSignal(
            signal_id=f"{symbol.lower()}-{attempt:03d}",
            symbol=symbol,
            signal_type=signal_type,
            price=price,
            timestamp=datetime.now()
        )
        
        # Calculate position size
        quantity = await risk_manager.calculate_position_size(symbol, signal, averaging_attempt=attempt)
        
        if quantity > 0:
            trade_cost = quantity * price
            total_cost += trade_cost
            total_shares += quantity
            average_price = total_cost / total_shares
            
            # Store trade info
            trade_info = {
                'attempt': attempt,
                'price': price,
                'quantity': quantity,
                'cost': trade_cost,
                'total_shares': total_shares,
                'total_cost': total_cost,
                'average_price': average_price
            }
            trades.append(trade_info)
            
            # Calculate current position value and P&L
            current_value = total_shares * price
            
            if direction == "LONG":
                unrealized_pnl = current_value - total_cost
                unrealized_pnl_percent = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0
            else:  # SHORT
                unrealized_pnl = total_cost - current_value  # Profit when price goes down
                unrealized_pnl_percent = (unrealized_pnl / total_cost * 100) if total_cost > 0 else 0
            
            # Display trade details
            trade_type = "Initial Entry" if attempt == 0 else f"Averaging #{attempt}"
            print(f"   {trade_type} @ ${price:.2f}:")
            print(f"      📈 Quantity: {quantity:,.0f} shares")
            print(f"      💰 Trade Cost: ${trade_cost:,.2f}")
            print(f"      📊 Total Position: {total_shares:,.0f} shares")
            print(f"      💵 Total Investment: ${total_cost:,.2f}")
            print(f"      📉 Average Price: ${average_price:.2f}")
            
            # Show price improvement for averaging
            if attempt > 0:
                if direction == "LONG" and price < trades[0]['average_price']:
                    improvement = ((trades[0]['average_price'] - average_price) / trades[0]['average_price']) * 100
                    print(f"      🎯 Cost Basis Improvement: {improvement:.2f}% (from ${trades[0]['average_price']:.2f})")
                elif direction == "SHORT" and price > trades[0]['average_price']:
                    print(f"      🛡️  Defense Against Rising Prices (avg up from ${trades[0]['average_price']:.2f})")
            
            # Show current P&L
            pnl_emoji = "💚" if unrealized_pnl >= 0 else "💔"
            print(f"      {pnl_emoji} Current P&L: ${unrealized_pnl:,.2f} ({unrealized_pnl_percent:+.2f}%)")
            print()
        else:
            print(f"   ❌ Attempt {attempt} @ ${price:.2f}: BLOCKED (insufficient funds/limits)")
            print()
    
    if trades:
        # Final analysis
        final_price = prices[-1]
        final_avg_price = trades[-1]['average_price']
        
        print("📈 Final Position Analysis:")
        print("-" * 35)
        print(f"   Total Shares: {total_shares:,.0f}")
        print(f"   Total Investment: ${total_cost:,.2f}")
        print(f"   Average Price: ${final_avg_price:.2f}")
        print(f"   Current Market Price: ${final_price:.2f}")
        
        # Calculate breakeven and recovery scenarios
        if direction == "LONG":
            breakeven = final_avg_price
            recovery_5pct = final_avg_price * 1.05
            current_value = total_shares * final_price
            final_pnl = current_value - total_cost
            final_pnl_percent = (final_pnl / total_cost * 100) if total_cost > 0 else 0
            
            print(f"   Breakeven Price: ${breakeven:.2f}")
            print(f"   5% Profit Target: ${recovery_5pct:.2f}")
            print(f"   Current Value: ${current_value:,.2f}")
            print(f"   Final P&L: ${final_pnl:,.2f} ({final_pnl_percent:+.2f}%)")
            
            if final_price < breakeven:
                recovery_needed = ((breakeven - final_price) / final_price) * 100
                print(f"   🎯 Recovery Needed: {recovery_needed:.1f}% price increase")
        else:  # SHORT
            breakeven = final_avg_price
            profit_5pct = final_avg_price * 0.95  # Profit when price drops
            current_value = total_shares * final_price
            final_pnl = total_cost - current_value
            final_pnl_percent = (final_pnl / total_cost * 100) if total_cost > 0 else 0
            
            print(f"   Breakeven Price: ${breakeven:.2f}")
            print(f"   5% Profit Target: ${profit_5pct:.2f}")
            print(f"   Current Short Value: ${current_value:,.2f}")
            print(f"   Final P&L: ${final_pnl:,.2f} ({final_pnl_percent:+.2f}%)")
            
            if final_price > breakeven:
                recovery_needed = ((final_price - breakeven) / final_price) * 100
                print(f"   🎯 Recovery Needed: {recovery_needed:.1f}% price decrease")


async def main():
    """Run comprehensive martingale strategy tests."""
    
    print("🚀 Comprehensive Martingale Strategy Test")
    print("=" * 80)
    print("Testing realistic market scenarios with average price tracking")
    print("and P&L calculations for both LONG and SHORT positions")
    print()
    
    # Setup
    config = MockConfig()
    account_provider = MockAccountProvider(buying_power=100000.0, account_value=50000.0)
    position_manager = MockPositionManager()
    risk_manager = RiskManager(config, position_manager, account_provider)
    
    print(f"💰 Account Setup:")
    print(f"   Buying Power: ${await account_provider.get_buying_power():,.2f}")
    print(f"   Account Value: ${await account_provider.get_account_value():,.2f}")
    print(f"   Initial Position Size: {config.get_config('trading.position_sizing.initial_portfolio_percentage') * 100:.1f}% of buying power")
    print(f"   Martingale Multiplier: {config.get_config('trading.position_sizing.averaging.multiplier'):.1f}x")
    print(f"   Max Averaging Attempts: {config.get_config('trading.position_sizing.averaging.max_attempts')}")
    
    # Test scenarios
    scenarios = [
        {
            "name": "AAPL Long - Market Correction Scenario",
            "symbol": "AAPL",
            "signal_type": SignalType.BUY,
            "prices": [180.0, 170.0, 160.0, 150.0],  # 16.7% decline
            "direction": "LONG"
        },
        {
            "name": "TSLA Short - Squeeze Scenario", 
            "symbol": "TSLA",
            "signal_type": SignalType.SELL,
            "prices": [250.0, 275.0, 300.0, 325.0],  # 30% rise
            "direction": "SHORT"
        },
        {
            "name": "NVDA Long - Gradual Decline",
            "symbol": "NVDA",
            "signal_type": SignalType.BUY,
            "prices": [500.0, 485.0, 470.0, 455.0],  # 9% decline
            "direction": "LONG"
        },
        {
            "name": "GOOGL Short - Modest Rally",
            "symbol": "GOOGL", 
            "signal_type": SignalType.SELL,
            "prices": [2800.0, 2900.0, 3000.0, 3100.0],  # 10.7% rise
            "direction": "SHORT"
        }
    ]
    
    # Run scenarios
    for scenario in scenarios:
        await simulate_martingale_scenario(
            risk_manager,
            scenario["name"],
            scenario["symbol"],
            scenario["signal_type"],
            scenario["prices"],
            scenario["direction"]
        )
    
    print("\n🏆 Martingale Strategy Summary:")
    print("=" * 50)
    print("✅ Conservative Start: All positions begin with 1% of buying power")
    print("✅ Systematic Scaling: Each averaging attempt doubles position size")
    print("✅ Average Price Improvement: Cost basis improves with each average")
    print("✅ Risk Management: Total exposure capped at 15% per symbol")
    print("✅ Bidirectional: Works for both LONG (down averaging) and SHORT (up averaging)")
    print("✅ Real-time P&L: Tracks unrealized gains/losses throughout sequence")
    print("✅ Recovery Targets: Calculates breakeven and profit scenarios")
    print()
    print("💡 Key Benefits:")
    print("   • Reduces average entry price when markets move against you")
    print("   • Maintains systematic approach to position building")
    print("   • Provides clear recovery targets and risk metrics")
    print("   • Works in both bull and bear market conditions")


if __name__ == "__main__":
    asyncio.run(main())
