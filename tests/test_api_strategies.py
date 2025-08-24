#!/usr/bin/env python3
"""
Test different API request strategies to get the absolute latest data
"""
import sys
import os
import asyncio
from datetime import datetime, timezone, timedelta

# Add the project root to the path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.data.market_data import AlpacaMarketDataProvider
from src.core.configuration import ConfigurationManager
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

async def test_api_strategies():
    config = ConfigurationManager("config.yaml")
    market_data = AlpacaMarketDataProvider(config)
    
    now_utc = datetime.now(timezone.utc)
    print(f"🕒 Current UTC Time: {now_utc}")
    
    strategies = [
        {"name": "No end time, 200 bars", "end": None, "limit": 200},
        {"name": "No end time, 500 bars", "end": None, "limit": 500},
        {"name": "End = now, 200 bars", "end": now_utc, "limit": 200},
        {"name": "End = now, 500 bars", "end": now_utc, "limit": 500},
    ]
    
    start_time = now_utc - timedelta(hours=8)  # Look back 8 hours
    
    for strategy in strategies:
        print(f"\n📊 Strategy: {strategy['name']}")
        print("-" * 40)
        
        try:
            request_params = {
                "symbol_or_symbols": ["MSFT"],
                "timeframe": TimeFrame.Minute,
                "start": start_time,
                "limit": strategy["limit"]
            }
            
            if strategy["end"]:
                request_params["end"] = strategy["end"]
            
            request = StockBarsRequest(**request_params)
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, market_data._client.get_stock_bars, request)
            
            if hasattr(response, 'data') and 'MSFT' in response.data:
                bars = response.data['MSFT']
                print(f"Found {len(bars)} bars")
                
                if bars:
                    latest_bar = bars[-1]
                    age = now_utc.replace(tzinfo=None) - latest_bar.timestamp.replace(tzinfo=None)
                    print(f"Latest: {latest_bar.timestamp} UTC = ${latest_bar.close:.2f}")
                    print(f"Age: {age.total_seconds()/60:.1f} minutes")
                    
                    # Show last few bars
                    print("Last 3 bars:")
                    for bar in bars[-3:]:
                        bar_age = now_utc.replace(tzinfo=None) - bar.timestamp.replace(tzinfo=None)
                        print(f"  {bar.timestamp}: ${bar.close:.2f} (Age: {bar_age.total_seconds()/60:.1f}m)")
            else:
                print("No data found")
                
        except Exception as e:
            print(f"Error: {e}")
    
    # Final summary
    print(f"\n🎯 SUMMARY:")
    print(f"We know from direct testing that data exists until 23:59 UTC ($555.74)")
    print(f"Let's see which strategy gets us closest to that timestamp")

if __name__ == "__main__":
    asyncio.run(test_api_strategies())
