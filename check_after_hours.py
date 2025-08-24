#!/usr/bin/env python3
"""
Check for recent after-hours trading activity for MSFT
"""
import sys
import os
import asyncio
import logging
from datetime import datetime, timedelta

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.data.market_data import AlpacaMarketDataProvider
from src.core.configuration import ConfigurationManager

# Set debug logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

async def check_recent_activity():
    config = ConfigurationManager("config.yaml")
    market_data = AlpacaMarketDataProvider(config)
    
    print("🔍 Checking recent MSFT activity...")
    
    # Check very recent 1-minute bars
    print("\n📊 Recent 1-minute bars:")
    bars = await market_data._get_recent_bars_extended("MSFT", "1Min", 10, hours=6)
    if bars:
        print(f"Found {len(bars)} recent bars:")
        for i, bar in enumerate(bars[-5:]):  # Show last 5 bars
            print(f"  {i+1}. {bar['timestamp']}: ${bar['close']:.2f} (vol: {bar['volume']})")
    else:
        print("  No recent 1-minute bars found")
    
    # Check 5-minute bars
    print("\n📊 Recent 5-minute bars:")
    bars_5m = await market_data._get_recent_bars_extended("MSFT", "5Min", 10, hours=6)
    if bars_5m:
        print(f"Found {len(bars_5m)} recent 5-min bars:")
        for i, bar in enumerate(bars_5m[-3:]):  # Show last 3 bars
            print(f"  {i+1}. {bar['timestamp']}: ${bar['close']:.2f} (vol: {bar['volume']})")
    else:
        print("  No recent 5-minute bars found")
    
    # Current time reference
    now = datetime.utcnow()
    print(f"\n🕒 Current time: {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    # Check if we're in after-hours trading window
    # After-hours: 4:00 PM - 8:00 PM ET (20:00 - 00:00 UTC)
    # Pre-market: 4:00 AM - 9:30 AM ET (08:00 - 13:30 UTC)
    market_close_utc = now.replace(hour=20, minute=0, second=0, microsecond=0)  # 4 PM ET
    after_hours_end_utc = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)  # 8 PM ET (next day midnight UTC)
    
    if market_close_utc <= now <= after_hours_end_utc:
        print("🌙 Currently in after-hours trading window (4 PM - 8 PM ET)")
    else:
        print("🔒 Currently outside trading hours")

if __name__ == "__main__":
    asyncio.run(check_recent_activity())
