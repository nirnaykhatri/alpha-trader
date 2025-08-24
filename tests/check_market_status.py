#!/usr/bin/env python3
"""
Check market status and available data timeframes
"""
import sys
import os
import asyncio
from datetime import datetime, timezone

# Add the project root to the path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.data.market_data import AlpacaMarketDataProvider
from src.core.configuration import ConfigurationManager

async def check_market_status():
    config = ConfigurationManager("config.yaml")
    market_data = AlpacaMarketDataProvider(config)
    
    now_utc = datetime.now(timezone.utc)
    print(f"🕒 Current UTC Time: {now_utc}")
    print(f"📅 Day of Week: {now_utc.strftime('%A')} (0=Monday, 6=Sunday: {now_utc.weekday()})")
    
    # Check different timeframes to see latest available data
    timeframes = ["1Min", "5Min", "15Min", "1Hour"]
    
    for tf in timeframes:
        print(f"\n📊 {tf} bars:")
        try:
            bars = await market_data._get_recent_bars_extended("MSFT", tf, 3, hours=8)
            if bars:
                for i, bar in enumerate(bars):
                    age = now_utc.replace(tzinfo=None) - bar['timestamp'].replace(tzinfo=None)
                    print(f"  {i+1}. {bar['timestamp']} UTC: ${bar['close']:.2f} (Age: {age.total_seconds()/60:.1f}m)")
            else:
                print(f"  No {tf} bars available")
        except Exception as e:
            print(f"  Error getting {tf} bars: {e}")
    
    # Check if markets are currently open
    # US Markets: 9:30 AM - 4:00 PM ET (13:30 - 20:00 UTC) on weekdays
    # After-hours: 4:00 PM - 8:00 PM ET (20:00 - 00:00 UTC next day)
    current_hour_utc = now_utc.hour
    is_weekday = now_utc.weekday() < 5  # 0-4 = Mon-Fri
    
    print(f"\n🏪 Market Status Analysis:")
    print(f"  Weekday: {is_weekday}")
    print(f"  UTC Hour: {current_hour_utc}")
    
    if is_weekday:
        if 13 <= current_hour_utc < 20:
            print("  Status: Regular Market Hours (9:30 AM - 4:00 PM ET)")
        elif 20 <= current_hour_utc <= 23 or current_hour_utc < 4:
            print("  Status: After-Hours Trading (4:00 PM - 8:00 PM ET)")
        elif 8 <= current_hour_utc < 13:
            print("  Status: Pre-Market Trading (4:00 AM - 9:30 AM ET)")
        else:
            print("  Status: Market Closed")
    else:
        print("  Status: Weekend - Markets Closed")
    
    print(f"\n💡 Analysis:")
    print(f"  - If it's after 8 PM ET (00:00 UTC), after-hours trading has ended")
    print(f"  - Latest data from 23:06 UTC might be the last after-hours activity")
    print(f"  - 2-hour-old data could be normal if no trading activity since then")

if __name__ == "__main__":
    asyncio.run(check_market_status())
