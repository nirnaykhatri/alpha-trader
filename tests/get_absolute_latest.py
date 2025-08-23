#!/usr/bin/env python3
"""
Get the absolute latest bars available from Alpaca
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

async def get_absolute_latest():
    config = ConfigurationManager("config.yaml")
    market_data = AlpacaMarketDataProvider(config)
    
    now_utc = datetime.now(timezone.utc)
    print(f"🕒 Current UTC Time: {now_utc}")
    
    # Try to get bars from just the last 30 minutes
    print(f"\n📊 Latest bars (last 30 minutes):")
    
    # Make a direct request for the most recent data
    start_time = now_utc - timedelta(minutes=30)
    
    request = StockBarsRequest(
        symbol_or_symbols=["MSFT"],
        timeframe=TimeFrame.Minute,
        start=start_time,
        limit=50  # Get up to 50 bars
    )
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, market_data._client.get_stock_bars, request)
        
        # Extract MSFT bars
        if hasattr(response, 'data') and 'MSFT' in response.data:
            bars = response.data['MSFT']
            print(f"Found {len(bars)} bars in last 30 minutes:")
            
            for bar in bars[-10:]:  # Show last 10 bars
                age = now_utc.replace(tzinfo=None) - bar.timestamp.replace(tzinfo=None)
                print(f"  {bar.timestamp} UTC: ${bar.close:.2f} (Age: {age.total_seconds()/60:.1f}m)")
        else:
            print("No bars found in last 30 minutes")
            
    except Exception as e:
        print(f"Error: {e}")
    
    # Also try with different start times
    print(f"\n📊 Latest bars (last 3 hours):")
    start_time_3h = now_utc - timedelta(hours=3)
    
    request_3h = StockBarsRequest(
        symbol_or_symbols=["MSFT"],
        timeframe=TimeFrame.Minute,
        start=start_time_3h,
        limit=200  
    )
    
    try:
        response_3h = await loop.run_in_executor(None, market_data._client.get_stock_bars, request_3h)
        
        if hasattr(response_3h, 'data') and 'MSFT' in response_3h.data:
            bars_3h = response_3h.data['MSFT']
            print(f"Found {len(bars_3h)} bars in last 3 hours:")
            
            # Show just the latest few
            for bar in bars_3h[-5:]:
                age = now_utc.replace(tzinfo=None) - bar.timestamp.replace(tzinfo=None)
                print(f"  {bar.timestamp} UTC: ${bar.close:.2f} (Age: {age.total_seconds()/60:.1f}m)")
                
            if bars_3h:
                latest_bar = bars_3h[-1]
                latest_age = now_utc.replace(tzinfo=None) - latest_bar.timestamp.replace(tzinfo=None)
                print(f"\n🎯 LATEST AVAILABLE: ${latest_bar.close:.2f} at {latest_bar.timestamp} UTC")
                print(f"   Age: {latest_age.total_seconds()/60:.1f} minutes")
        else:
            print("No bars found in last 3 hours")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(get_absolute_latest())
