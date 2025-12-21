#!/usr/bin/env python3
"""
Test to check for zero bid/ask issues that cause wrong mid-point calculations
"""

import asyncio
import sys
from pathlib import Path
import logging

# Add src to path  
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data.market_data import AlpacaMarketDataProvider
from src.core.configuration import ConfigurationManager

# Set debug logging to see detailed quote information
logging.basicConfig(level=logging.DEBUG, format='%(message)s')

async def test_zero_bid_ask():
    """Test for zero bid/ask scenarios that cause wrong pricing."""
    try:
        print("🔍 TESTING FOR ZERO BID/ASK SCENARIOS")
        print("=" * 50)
        
        config = ConfigurationManager()  # Uses config/ TOML files
        provider = AlpacaMarketDataProvider(config)
        
        # Test with TSLA specifically to investigate wide spread issue
        symbol = "TSLA"
        
        print(f"\n📊 Testing {symbol} for bid/ask validation...")
        print("-" * 40)
        
        # Get the raw quote data first
        from alpaca.data.requests import StockLatestQuoteRequest
        import asyncio
        
        request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, provider._client.get_stock_latest_quote, request)
        
        if response and symbol in response:
            quote = response[symbol]
            
            print(f"🔍 RAW QUOTE DATA for {symbol}:")
            print(f"   Raw bid_price: {quote.bid_price}")
            print(f"   Raw ask_price: {quote.ask_price}")
            print(f"   Bid size: {quote.bid_size}")
            print(f"   Ask size: {quote.ask_size}")
            print(f"   Bid exchange: {quote.bid_exchange}")
            print(f"   Ask exchange: {quote.ask_exchange}")
            print(f"   Conditions: {quote.conditions}")
            print(f"   Timestamp: {quote.timestamp}")
            
            # Check for problematic scenarios
            if quote.bid_price == 0:
                print("❌ FOUND ZERO BID PRICE!")
                print("   This would cause wrong mid-point calculation")
                
            if quote.ask_price == 0:
                print("❌ FOUND ZERO ASK PRICE!")
                print("   This would cause wrong mid-point calculation")
                
            if quote.bid_price and quote.ask_price and quote.bid_price > 0 and quote.ask_price > 0:
                spread = quote.ask_price - quote.bid_price
                spread_percentage = (spread / quote.bid_price) * 100
                
                if spread_percentage > 20:
                    print(f"⚠️ WIDE SPREAD DETECTED: {spread_percentage:.1f}%")
                    print("   This might indicate stale extended hours data")
                    
            print(f"\n🔧 PROCESSED VALUES:")
            bid_price = float(quote.bid_price) if quote.bid_price and quote.bid_price > 0 else None
            ask_price = float(quote.ask_price) if quote.ask_price and quote.ask_price > 0 else None
            
            print(f"   Processed bid: {bid_price}")
            print(f"   Processed ask: {ask_price}")
            
            if bid_price and ask_price:
                mid_price = (bid_price + ask_price) / 2.0
                print(f"   Mid-point: ${mid_price:.4f}")
            elif bid_price:
                print(f"   Using bid only: ${bid_price:.4f}")
            elif ask_price:
                print(f"   Using ask only: ${ask_price:.4f}")
            else:
                print("   ❌ No valid bid or ask!")
        
        print(f"\n📈 Now testing full price fetching with enhanced validation...")
        
        # Test the full price fetching process
        price = await provider.get_current_price(symbol)
        print(f"\n✅ Final price: ${price:.4f}")
        
        print(f"\n🧪 ANALYSIS OF WIDE SPREAD ISSUE")
        print("-" * 45)
        print("Your TSLA log showed: bid=$298.50, ask=$336.30, spread=12.7%")
        print("Trade: $336.13, Bar: $337.26")
        print("Algorithm chose: $317.40 (mid-point) - WRONG!")
        print()
        print("✅ FIXED: Added spread penalty to scoring algorithm")
        print("• Spreads >10% get -50 point penalty")
        print("• Spreads >15% get -80 point penalty")
        print("• This makes trades/bars preferred over unreliable quotes")
        print()
        print("🎯 Expected behavior: Wide spread quotes will be penalized,")
        print("   causing algorithm to prefer trade ($336.13) or bar ($337.26)")
        print("   instead of unreliable mid-point ($317.40)")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_zero_bid_ask())
