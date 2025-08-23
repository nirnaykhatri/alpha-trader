#!/usr/bin/env python3
"""
Quick test to see detailed logging for MSFT price fetching
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

async def test_msft_detailed():
    config = ConfigurationManager("config.yaml")
    market_data = AlpacaMarketDataProvider(config)
    
    print("🔍 Testing MSFT with detailed logging...")
    
    # Test both quote and price methods
    print("\n1. Testing quote method directly:")
    quote_price = await market_data._get_latest_quote_price("MSFT")
    print(f"Quote result: {quote_price}")
    
    print("\n2. Testing full price method:")
    full_price = await market_data.get_current_price("MSFT")
    print(f"Full price result: {full_price}")

if __name__ == "__main__":
    asyncio.run(test_msft_detailed())
