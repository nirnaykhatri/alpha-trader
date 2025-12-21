"""
Test script to demonstrate the new position sizing system.
Run this to see how position sizing works with different stock prices and portfolio sizes.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core import ConfigurationManager
from src.risk.risk_manager import RiskManager
from src.interfaces import TradingSignal, SignalType
from datetime import datetime

# Mock classes for testing
class MockPositionManager:
    async def get_position(self, symbol): return None
    async def get_all_positions(self): return []
    async def update_position(self, symbol, quantity, price): pass

class MockAccountProvider:
    def __init__(self, portfolio_value=100000.0, buying_power=50000.0):
        self.portfolio_value = portfolio_value
        self.buying_power = buying_power
    
    async def get_account_value(self): 
        print(f"    📊 Account Value: ${self.portfolio_value:,.2f}")
        return self.portfolio_value
    
    async def get_buying_power(self): 
        print(f"    💰 Buying Power: ${self.buying_power:,.2f}")
        return self.buying_power
    
    async def get_portfolio_value(self): 
        return self.portfolio_value

async def test_position_sizing():
    """Test position sizing with different scenarios."""
    print("=== Trading Bot Position Sizing Test ===")
    print("ℹ️  This test simulates how position sizing works with real Alpaca account data")
    print("ℹ️  In production, buying power and account values are fetched from Alpaca API\n")
    
    # Setup components
    config = ConfigurationManager()  # Uses config/ TOML files
    position_manager = MockPositionManager()
    
    # Test scenarios with different account sizes
    scenarios = [
        ("Small Account", 10000.0, 5000.0),
        ("Medium Account", 50000.0, 25000.0),
        ("Large Account", 100000.0, 50000.0),
    ]
    
    # Test stocks with different prices
    test_stocks = [
        ("AAPL", 150.0),  # Medium price
        ("GOOGL", 2500.0),  # High price
        ("F", 12.0),  # Low price
        ("NVDA", 800.0),  # High growth stock
    ]
    
    for scenario_name, portfolio_value, buying_power in scenarios:
        print(f"\n--- {scenario_name}: ${portfolio_value:,.0f} portfolio, ${buying_power:,.0f} buying power ---")
        print(f"    ℹ️  Note: Using buying power (${buying_power:,.0f}) for position sizing, not total portfolio")
        
        account_provider = MockAccountProvider(portfolio_value, buying_power)
        risk_manager = RiskManager(config, position_manager, account_provider)
        
        for symbol, price in test_stocks:
            signal = TradingSignal(
                signal_id="test",
                symbol=symbol,
                signal_type=SignalType.BUY,
                price=price,
                timestamp=datetime.utcnow()
            )
            
            # Test different sizing methods
            for method in ["percentage", "risk_based", "fixed"]:
                # Temporarily set the method
                original_method = config.get_config("trading.position_sizing.method")
                config.set_config("trading.position_sizing.method", method)
                
                try:
                    quantity = await risk_manager.calculate_position_size(symbol, signal)
                    cost = quantity * price if quantity > 0 else 0
                    percentage = (cost / portfolio_value * 100) if cost > 0 else 0
                    
                    if quantity > 0:
                        print(f"  {symbol} @ ${price:7.2f} ({method:10s}): {quantity:4.0f} shares = ${cost:8,.0f} ({percentage:4.1f}%)")
                    else:
                        print(f"  {symbol} @ ${price:7.2f} ({method:10s}): SKIP - insufficient funds")
                    
                except Exception as e:
                    print(f"  {symbol} @ ${price:7.2f} ({method:10s}): ERROR - {str(e)}")
                
                # Restore original method
                config.set_config("trading.position_sizing.method", original_method)
    
    print("\n=== Position Sizing Configuration ===")
    print(f"Portfolio percentage: {config.get_config('trading.position_sizing.portfolio_percentage', 0.05) * 100:.1f}%")
    print(f"Risk per trade: {config.get_config('trading.position_sizing.risk_per_trade', 0.02) * 100:.1f}%")
    print(f"Default method: {config.get_config('trading.position_sizing.method', 'percentage')}")
    print(f"Min quantity: {config.get_config('trading.position_sizing.min_quantity', 1)}")
    print(f"Max quantity: {config.get_config('trading.position_sizing.max_quantity', 10000)}")
    print(f"Use Alpaca API: {config.get_config('trading.account.use_api_for_balance', True)}")
    print(f"Fallback value: ${config.get_config('trading.account.fallback_portfolio_value', 100000.0):,.0f}")
    
    print("\n=== Integration Notes ===")
    print("🔗 In production:")
    print("   • Account values are fetched from Alpaca API in real-time")
    print("   • Buying power is used for position sizing (what's actually available)")
    print("   • Account data is cached for 30 seconds to reduce API calls")
    print("   • All trades are rounded to whole shares (no fractional trading)")
    print("   • Trades are skipped if insufficient buying power")

if __name__ == "__main__":
    asyncio.run(test_position_sizing())
