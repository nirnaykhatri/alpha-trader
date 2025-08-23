#!/usr/bin/env python3
"""
DIAGNOSTIC TEST: Alpaca API vs Website Data Comparison
=====================================================

This investigates the root cause of spread discrepancies:
- API shows 4.8% spread (bid=$46.31, ask=$48.54) 
- Website shows 1¢ spread
- Need to identify if this is stale data or API data quality issue
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
import pytz

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.data.market_data import AlpacaMarketDataProvider
from src.core.config import ConfigurationManager

async def diagnose_bid_ask_freshness():
    """Deep diagnostic of bid/ask data quality and freshness"""
    print("🔍 ALPACA API BID/ASK DIAGNOSTIC")
    print("=" * 60)
    
    config = ConfigurationManager("config.yaml")
    provider = AlpacaMarketDataProvider(config)
    
    # Test problematic symbols
    test_symbols = ["HIMS", "TSLA", "AAPL"]  # HIMS had the issue, others for comparison
    
    for symbol in test_symbols:
        print(f"\n📊 DETAILED ANALYSIS: {symbol}")
        print("-" * 40)
        
        try:
            # Get raw quote data with full metadata
            from alpaca.data.requests import StockLatestQuoteRequest
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, provider._client.get_stock_latest_quote, request)
            
            if response and symbol in response:
                quote = response[symbol]
                
                # Extract all available metadata
                print(f"🔍 RAW API RESPONSE:")
                print(f"   Timestamp: {quote.timestamp}")
                print(f"   Bid: ${quote.bid_price:.4f} (size: {quote.bid_size})")
                print(f"   Ask: ${quote.ask_price:.4f} (size: {quote.ask_size})")
                print(f"   Bid Exchange: {quote.bid_exchange}")
                print(f"   Ask Exchange: {quote.ask_exchange}")
                if hasattr(quote, 'conditions'):
                    print(f"   Conditions: {quote.conditions}")
                if hasattr(quote, 'tape'):
                    print(f"   Tape: {quote.tape}")
                
                # Calculate freshness
                now_utc = datetime.now(timezone.utc)
                quote_time = quote.timestamp.replace(tzinfo=timezone.utc) if quote.timestamp.tzinfo is None else quote.timestamp
                age_seconds = (now_utc - quote_time).total_seconds()
                age_minutes = age_seconds / 60
                
                # Convert to ET for market context
                et = pytz.timezone('US/Eastern')
                quote_time_et = quote_time.astimezone(et)
                now_et = now_utc.astimezone(et)
                
                print(f"\n⏰ FRESHNESS ANALYSIS:")
                print(f"   Quote time (UTC): {quote_time.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"   Quote time (ET):  {quote_time_et.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                print(f"   Current time (ET): {now_et.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                print(f"   Age: {age_minutes:.1f} minutes ({age_seconds:.0f} seconds)")
                
                # Market session context
                market_hour_et = quote_time_et.hour
                is_market_hours = 9 <= market_hour_et < 16
                is_extended_hours = (4 <= market_hour_et < 9) or (16 <= market_hour_et <= 20)
                
                print(f"   Market session: ", end="")
                if is_market_hours:
                    print("REGULAR HOURS")
                elif is_extended_hours:
                    print("EXTENDED HOURS")
                else:
                    print("CLOSED/OVERNIGHT")
                
                # Spread analysis
                if quote.bid_price and quote.ask_price and quote.bid_price > 0 and quote.ask_price > 0:
                    spread = quote.ask_price - quote.bid_price
                    mid_price = (quote.bid_price + quote.ask_price) / 2
                    spread_pct = (spread / mid_price) * 100
                    
                    print(f"\n💰 SPREAD ANALYSIS:")
                    print(f"   Spread: ${spread:.4f}")
                    print(f"   Mid-point: ${mid_price:.4f}")
                    print(f"   Spread %: {spread_pct:.2f}%")
                    
                    if spread_pct > 3:
                        print(f"   🚨 WIDE SPREAD DETECTED!")
                        print(f"   🔍 This suggests potential data quality issue")
                        
                        # Check if this could be stale data
                        if age_minutes > 30:
                            print(f"   ⚠️  Quote is {age_minutes:.1f} minutes old - possibly stale")
                        elif not is_market_hours and not is_extended_hours:
                            print(f"   📅 Quote from market closed period - may be outdated")
                        else:
                            print(f"   🤔 Fresh quote with wide spread - potential API data quality issue")
                    else:
                        print(f"   ✅ Normal spread")
                
                # Get trade data for comparison
                print(f"\n📈 TRADE DATA FOR COMPARISON:")
                try:
                    from alpaca.data.requests import StockLatestTradeRequest
                    trade_request = StockLatestTradeRequest(symbol_or_symbols=symbol)
                    trade_response = await loop.run_in_executor(None, provider._client.get_stock_latest_trade, trade_request)
                    
                    if trade_response and symbol in trade_response:
                        trade = trade_response[symbol]
                        trade_time = trade.timestamp.replace(tzinfo=timezone.utc) if trade.timestamp.tzinfo is None else trade.timestamp
                        trade_age_seconds = (now_utc - trade_time).total_seconds()
                        trade_age_minutes = trade_age_seconds / 60
                        
                        print(f"   Trade price: ${trade.price:.4f}")
                        print(f"   Trade time: {trade_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                        print(f"   Trade age: {trade_age_minutes:.1f} minutes")
                        print(f"   Trade size: {trade.size}")
                        print(f"   Trade exchange: {trade.exchange}")
                        
                        # Compare quote vs trade timing
                        if abs(trade_age_minutes - age_minutes) > 5:
                            print(f"   ⚠️  Quote and trade timestamps differ by {abs(trade_age_minutes - age_minutes):.1f} minutes")
                            if age_minutes > trade_age_minutes:
                                print(f"   🔍 Quote is OLDER than trade - potentially stale quote data")
                        
                except Exception as e:
                    print(f"   ❌ Could not get trade data: {e}")
                    
            else:
                print(f"❌ No quote data returned for {symbol}")
                
        except Exception as e:
            print(f"❌ Error analyzing {symbol}: {e}")
    
    print(f"\n🔍 DIAGNOSTIC SUMMARY:")
    print("1. Check if quote timestamps are significantly older than trade timestamps")
    print("2. Verify if wide spreads occur during specific market sessions")  
    print("3. Compare exchange codes - some exchanges may have wider spreads")
    print("4. Identify if this is consistent across symbols or specific to certain stocks")
    print("\n💡 NEXT STEPS:")
    print("• If quotes are consistently stale: Prioritize trade data over quotes")
    print("• If spread is exchange-specific: Filter quotes by exchange quality")
    print("• If symbol-specific: Add symbol-specific handling for known problematic stocks")

if __name__ == "__main__":
    asyncio.run(diagnose_bid_ask_freshness())
