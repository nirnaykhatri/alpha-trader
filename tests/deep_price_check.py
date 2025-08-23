#!/usr/bin/env python3
"""
Get extended market data to see if we're missing something
"""
import sys
import os
import asyncio
import logging
from datetime import datetime

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.data.market_data import AlpacaMarketDataProvider
from src.core.configuration import ConfigurationManager

logging.basicConfig(level=logging.INFO, format='%(message)s')

async def deep_price_check():
    config = ConfigurationManager("config.yaml")
    market_data = AlpacaMarketDataProvider(config)
    
    print("🔍 DEEP PRICE CHECK FOR MSFT")
    print("=" * 50)
    
    symbols = ["MSFT", "AAPL"]  # Compare with another major stock
    
    for symbol in symbols:
        print(f"\n📊 {symbol} Analysis:")
        print("-" * 30)
        
        # 1. Latest quote
        try:
            quote_price = await market_data._get_latest_quote_price(symbol)
            print(f"Latest Quote: ${quote_price:.2f}")
        except Exception as e:
            print(f"Quote Error: {e}")
        
        # 2. Latest trade
        try:
            trade_price = await market_data._get_latest_trade_price(symbol)
            print(f"Latest Trade: ${trade_price:.2f}")
        except Exception as e:
            print(f"Trade Error: {e}")
        
        # 3. Current price (our method)
        try:
            current_price = await market_data.get_current_price(symbol)
            print(f"Current Price: ${current_price:.2f}")
        except Exception as e:
            print(f"Current Price Error: {e}")
        
        # 4. Very recent bars
        try:
            bars = await market_data._get_recent_bars_extended(symbol, "1Min", 3, hours=1)
            if bars:
                latest = bars[-1]
                print(f"Latest Bar: ${latest['close']:.2f} at {latest['timestamp']}")
            else:
                print("No recent bars available")
        except Exception as e:
            print(f"Bars Error: {e}")
    
    print(f"\n🕒 Timestamp: {datetime.now()}")
    
    print("\n❓ Question: What price are you seeing for MSFT, and where?")
    print("   (Please specify the platform/source showing $558)")

if __name__ == "__main__":
    asyncio.run(deep_price_check())
