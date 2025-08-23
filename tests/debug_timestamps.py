#!/usr/bin/env python3
"""
Debug timestamp handling and data freshness issues
"""
import sys
import os
import asyncio
import logging
from datetime import datetime, timezone

# Add the project root to the path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.data.market_data import AlpacaMarketDataProvider
from src.core.configuration import ConfigurationManager

# Set debug logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s: %(message)s')

async def debug_timestamps():
    config = ConfigurationManager("config.yaml")
    market_data = AlpacaMarketDataProvider(config)
    
    print("🕒 TIMESTAMP DEBUG FOR MSFT")
    print("=" * 50)
    
    # Current time info
    now_local = datetime.now()
    now_utc = datetime.now(timezone.utc)
    
    print(f"Current Local Time: {now_local}")
    print(f"Current UTC Time: {now_utc}")
    print(f"UTC Offset: {now_local.astimezone().strftime('%z')}")
    
    print("\n📊 Data Source Timestamps:")
    print("-" * 30)
    
    # Test each data source individually with timestamps
    from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest
    
    # 1. Quote timestamp
    try:
        request = StockLatestQuoteRequest(symbol_or_symbols="MSFT")
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, market_data._client.get_stock_latest_quote, request)
        if response and "MSFT" in response:
            quote = response["MSFT"]
            quote_time = getattr(quote, 'timestamp', None)
            if quote_time:
                age = now_utc.replace(tzinfo=None) - quote_time.replace(tzinfo=None)
                print(f"Quote: {quote_time} UTC (Age: {age.total_seconds()/60:.1f} minutes)")
                print(f"       Price: ${quote.bid_price}-${quote.ask_price}")
    except Exception as e:
        print(f"Quote Error: {e}")
    
    # 2. Trade timestamp  
    try:
        request = StockLatestTradeRequest(symbol_or_symbols="MSFT")
        response = await loop.run_in_executor(None, market_data._client.get_stock_latest_trade, request)
        if response and "MSFT" in response:
            trade = response["MSFT"]
            trade_time = getattr(trade, 'timestamp', None)
            if trade_time:
                age = now_utc.replace(tzinfo=None) - trade_time.replace(tzinfo=None)
                print(f"Trade: {trade_time} UTC (Age: {age.total_seconds()/60:.1f} minutes)")
                print(f"       Price: ${trade.price}")
    except Exception as e:
        print(f"Trade Error: {e}")
    
    # 3. Recent bars timestamp
    try:
        bars = await market_data._get_recent_bars_extended("MSFT", "1Min", 5, hours=1)
        if bars:
            latest_bar = bars[-1]
            bar_time = latest_bar['timestamp']
            age = now_utc.replace(tzinfo=None) - bar_time.replace(tzinfo=None)
            print(f"Bar:   {bar_time} UTC (Age: {age.total_seconds()/60:.1f} minutes)")
            print(f"       Price: ${latest_bar['close']}")
            
            # Show all recent bars
            print(f"\nRecent bars ({len(bars)} total):")
            for i, bar in enumerate(bars[-3:]):
                bar_age = now_utc.replace(tzinfo=None) - bar['timestamp'].replace(tzinfo=None)
                print(f"  {i+1}. {bar['timestamp']} UTC: ${bar['close']:.2f} (Age: {bar_age.total_seconds()/60:.1f}m)")
    except Exception as e:
        print(f"Bars Error: {e}")
    
    # 4. Test our current price method
    print(f"\n🔍 Current Price Method Result:")
    try:
        price = await market_data.get_current_price("MSFT")
        print(f"Result: ${price:.2f}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(debug_timestamps())
