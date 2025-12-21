#!/usr/bin/env python3
"""
Test position sizing with REAL Alpaca account data.
This will show actual position sizes using your live account balance.
"""

import sys
import os
import asyncio
from datetime import datetime

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from core.configuration import ConfigurationManager
from trading.alpaca_account_provider import AlpacaAccountProvider
from risk.risk_manager import RiskManager
from position.position_manager import PositionManager
from database.database_manager import DatabaseManager
from interfaces import TradingSignal, SignalType
from alpaca.trading import TradingClient


async def test_real_position_sizing():
    """Test position sizing with real Alpaca account data."""
    
    print("=== REAL ALPACA ACCOUNT POSITION SIZING TEST ===")
    print()
    
    # Initialize configuration
    config = ConfigurationManager()  # Uses config/ TOML files
    
    # Initialize Alpaca trading client
    api_key = config.get_config("api.alpaca.api_key")
    secret_key = config.get_config("api.alpaca.secret_key")
    base_url = config.get_config("api.alpaca.base_url")
    
    print(f"🔑 API Key: {api_key[:8]}...")
    print(f"🌐 Base URL: {base_url}")
    print()
    
    trading_client = TradingClient(api_key, secret_key, paper=True)
    
    # Initialize components
    database = DatabaseManager(config)
    await database.initialize()
    
    position_manager = PositionManager(config, database)
    account_provider = AlpacaAccountProvider(trading_client)
    risk_manager = RiskManager(config, position_manager, account_provider)
    
    # Test real account data
    print("📡 Fetching REAL account data from Alpaca...")
    buying_power = await account_provider.get_buying_power()
    account_value = await account_provider.get_account_value()
    portfolio_value = await account_provider.get_portfolio_value()
    
    print(f"✅ REAL Account Data:")
    print(f"   💰 Account Value: ${account_value:,.2f}")
    print(f"   🛒 Buying Power: ${buying_power:,.2f}")
    print(f"   📈 Portfolio Value: ${portfolio_value:,.2f}")
    print()
    
    # Get configuration
    portfolio_percentage = config.get_config("trading.position_sizing.portfolio_percentage", 0.05)
    risk_per_trade = config.get_config("trading.position_sizing.risk_per_trade", 0.02)
    
    print(f"📊 Position Sizing Configuration:")
    print(f"   🎯 Portfolio Percentage: {portfolio_percentage*100:.1f}%")
    print(f"   ⚠️  Risk per Trade: {risk_per_trade*100:.1f}%")
    print()
    
    # Calculate expected position sizing
    percentage_budget = buying_power * portfolio_percentage
    risk_budget = account_value * risk_per_trade
    
    print(f"💡 Calculated Budgets:")
    print(f"   📊 Percentage Budget: ${percentage_budget:,.2f} ({portfolio_percentage*100:.1f}% of buying power)")
    print(f"   ⚠️  Risk Budget: ${risk_budget:,.2f} ({risk_per_trade*100:.1f}% of account value)")
    print()
    
    # Test symbols with various price points
    test_symbols = [
        ("AAPL", 150.00),      # Medium price
        ("GOOGL", 2500.00),    # High price
        ("F", 12.00),          # Low price
        ("NVDA", 800.00),      # High price
        ("BTC", 107000.00),    # Very high price (crypto)
    ]
    
    print("🧪 Testing Position Sizing with REAL account data:")
    print("=" * 60)
    
    for symbol, price in test_symbols:
        print(f"📈 {symbol} @ ${price:,.2f}")
        
        # Create test signal
        signal = TradingSignal(
            signal_id=f"test-{symbol}",
            symbol=symbol,
            signal_type=SignalType.BUY,
            price=price,
            timestamp=datetime.utcnow()
        )
        
        # Test percentage-based sizing
        percentage_size = await risk_manager.calculate_position_size(symbol, signal)
        percentage_cost = percentage_size * price
        
        if percentage_size > 0:
            print(f"   💰 Percentage Method: {percentage_size:,.0f} shares = ${percentage_cost:,.2f}")
            print(f"       📊 That's {percentage_cost/buying_power*100:.2f}% of buying power")
        else:
            print(f"   ❌ Percentage Method: SKIP - insufficient funds")
        
        # Test risk-based sizing  
        config.set_config("trading.position_sizing.method", "risk_based")
        risk_size = await risk_manager.calculate_position_size(symbol, signal)
        risk_cost = risk_size * price
        
        if risk_size > 0:
            print(f"   ⚠️  Risk Method: {risk_size:,.0f} shares = ${risk_cost:,.2f}")
            print(f"       📊 That's {risk_cost/account_value*100:.2f}% of account value")
        else:
            print(f"   ❌ Risk Method: SKIP - insufficient funds")
        
        # Reset to percentage method
        config.set_config("trading.position_sizing.method", "percentage")
        
        print()
    
    print("🎯 Summary:")
    print(f"   💰 Your account can afford substantial positions with ${buying_power:,.2f} buying power")
    print(f"   📊 Each position uses {portfolio_percentage*100:.1f}% = ${percentage_budget:,.2f} per trade")
    print(f"   🔢 For a $150 stock like AAPL: {int(percentage_budget/150)} shares")
    print(f"   🔢 For a $2500 stock like GOOGL: {int(percentage_budget/2500)} shares")
    print()
    
    await database.close()


if __name__ == "__main__":
    asyncio.run(test_real_position_sizing())
