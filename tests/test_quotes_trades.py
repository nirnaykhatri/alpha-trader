#!/usr/bin/env python3
"""
Test both quotes and trades to see what real-time data is available
"""
import sys
import os
import asyncio
import logging

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.data.market_data import AlpacaMarketDataProvider
from src.core.configuration import ConfigurationManager

# Set debug logging to see what's happening
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

async def test_quotes_vs_trades():
    config = ConfigurationManager()  # Uses config/ TOML files
    market_data = AlpacaMarketDataProvider(config)
    
    print("🔍 Testing MSFT quotes vs trades...")
    
    # Test quote method
    print("\n1. Latest Quote:")
    quote_price = await market_data._get_latest_quote_price("MSFT")
    print(f"Quote result: ${quote_price}")
    
    # Test trade method
    print("\n2. Latest Trade:")
    trade_price = await market_data._get_latest_trade_price("MSFT")
    print(f"Trade result: ${trade_price}")
    
    # Test full price method
    print("\n3. Full Price Method:")
    full_price = await market_data.get_current_price("MSFT")
    print(f"Full price result: ${full_price}")

if __name__ == "__main__":
    asyncio.run(test_quotes_vs_trades())
