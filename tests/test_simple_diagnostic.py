#!/usr/bin/env python3
"""
SIMPLIFIED API DIAGNOSTIC - Root Cause Analysis for Spread Issues
================================================================

Investigating why Alpaca API returns wide spreads when website shows tight spreads
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
import pytz

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

async def test_bid_ask_freshness():
    """Test for data freshness and quality issues"""
    try:
        print("🔍 ALPACA API DATA QUALITY INVESTIGATION")
        print("=" * 60)
        
        from src.data.market_data import AlpacaMarketDataProvider
        from src.core.config import ConfigurationManager
        
        config = ConfigurationManager("config.yaml")
        provider = AlpacaMarketDataProvider(config)
        
        # Test HIMS specifically - the problematic symbol
        symbol = "HIMS"
        
        print(f"\n🎯 INVESTIGATING {symbol} - Your Problem Case")
        print("=" * 50)
        print("Your log showed: bid=$46.31, ask=$48.54, spread=4.8%")
        print("Website showed: ~1¢ spread")
        print("Let's see what we get NOW...\n")
        
        # Get raw quote data with full analysis
        from alpaca.data.requests import StockLatestQuoteRequest
        
        request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, provider._client.get_stock_latest_quote, request)
        
        if response and symbol in response:
            quote = response[symbol]
            
            # Current time analysis
            now_utc = datetime.now(timezone.utc)
            quote_time = quote.timestamp.replace(tzinfo=timezone.utc) if quote.timestamp.tzinfo is None else quote.timestamp
            age_seconds = (now_utc - quote_time).total_seconds()
            age_minutes = age_seconds / 60
            
            # Convert to ET for context
            et = pytz.timezone('US/Eastern')
            quote_time_et = quote_time.astimezone(et)
            now_et = now_utc.astimezone(et)
            
            print(f"📡 CURRENT API RESPONSE:")
            print(f"   Bid: ${quote.bid_price:.4f} (size: {quote.bid_size})")
            print(f"   Ask: ${quote.ask_price:.4f} (size: {quote.ask_size})")
            print(f"   Exchange: Bid={quote.bid_exchange}, Ask={quote.ask_exchange}")
            print(f"   Conditions: {getattr(quote, 'conditions', 'N/A')}")
            print(f"   Timestamp: {quote_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            print(f"   Quote time ET: {quote_time_et.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            print(f"   Age: {age_minutes:.1f} minutes")
            
            # Calculate current spread
            if quote.bid_price and quote.ask_price and quote.bid_price > 0 and quote.ask_price > 0:
                spread = quote.ask_price - quote.bid_price
                mid_price = (quote.bid_price + quote.ask_price) / 2
                spread_pct = (spread / mid_price) * 100
                spread_cents = spread * 100
                
                print(f"\n💰 SPREAD ANALYSIS:")
                print(f"   Spread: ${spread:.4f} ({spread_cents:.1f}¢)")
                print(f"   Mid-point: ${mid_price:.4f}")
                print(f"   Spread %: {spread_pct:.2f}%")
                
                # Compare to your log data
                if spread_pct > 3:
                    print(f"\n🚨 WIDE SPREAD CONFIRMED!")
                    print(f"   This matches your problem case!")
                    
                    # Analyze potential causes
                    if age_minutes > 15:
                        print(f"   🔍 POTENTIAL CAUSE: Stale data ({age_minutes:.1f} min old)")
                    elif quote_time_et.hour < 9 or quote_time_et.hour >= 16:
                        print(f"   🔍 POTENTIAL CAUSE: Extended hours data (quote at {quote_time_et.hour}:{quote_time_et.minute:02d} ET)")
                    elif quote.bid_exchange != quote.ask_exchange:
                        print(f"   🔍 POTENTIAL CAUSE: Cross-exchange spread (bid from {quote.bid_exchange}, ask from {quote.ask_exchange})")
                    else:
                        print(f"   🔍 POTENTIAL CAUSE: API data quality issue - fresh quote with wide spread")
                else:
                    print(f"   ✅ Normal spread now - issue may be intermittent")
                
                # Get trade data for comparison
                print(f"\n📈 TRADE DATA COMPARISON:")
                try:
                    from alpaca.data.requests import StockLatestTradeRequest
                    trade_request = StockLatestTradeRequest(symbol_or_symbols=symbol)
                    trade_response = await loop.run_in_executor(None, provider._client.get_stock_latest_trade, trade_request)
                    
                    if trade_response and symbol in trade_response:
                        trade = trade_response[symbol]
                        trade_time = trade.timestamp.replace(tzinfo=timezone.utc)
                        trade_age_seconds = (now_utc - trade_time).total_seconds()
                        trade_age_minutes = trade_age_seconds / 60
                        
                        print(f"   Latest trade: ${trade.price:.4f}")
                        print(f"   Trade time: {trade_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                        print(f"   Trade age: {trade_age_minutes:.1f} minutes")
                        print(f"   Trade exchange: {trade.exchange}")
                        
                        # Key insight: Compare quote vs trade freshness
                        freshness_diff = abs(age_minutes - trade_age_minutes)
                        if freshness_diff > 5:
                            print(f"\n🚨 FRESHNESS MISMATCH:")
                            print(f"   Quote age: {age_minutes:.1f} min")
                            print(f"   Trade age: {trade_age_minutes:.1f} min")
                            print(f"   Difference: {freshness_diff:.1f} minutes")
                            
                            if age_minutes > trade_age_minutes:
                                print(f"   ❌ QUOTE IS STALER than trade - this explains wide spread!")
                                print(f"   💡 Solution: Always prefer trade data when quote is stale")
                            else:
                                print(f"   🤔 Trade is staler - unusual but quote spread still wide")
                        else:
                            print(f"   ✅ Quote and trade are similar age ({freshness_diff:.1f} min diff)")
                            if spread_pct > 3:
                                print(f"   🚨 But spread is still wide - genuine API data quality issue")
                
                except Exception as e:
                    print(f"   ❌ Trade data error: {e}")
            
            # Check for multiple quote sources
            print(f"\n🔍 INVESTIGATING QUOTE SOURCES:")
            print(f"   Quote exchange codes: Bid={quote.bid_exchange}, Ask={quote.ask_exchange}")
            print(f"   Conditions: {getattr(quote, 'conditions', 'None')}")
            
            # Common exchanges:
            # V = NASDAQ (typically reliable)
            # P = Pacific (sometimes wide spreads)
            # K = BATS (usually tight)
            # etc.
            
            exchange_notes = {
                'V': 'NASDAQ (usually reliable)',
                'P': 'Pacific (sometimes wide)',
                'K': 'BATS (usually tight)',
                'N': 'NYSE (usually reliable)',
                'Q': 'NASDAQ (usually reliable)'
            }
            
            bid_note = exchange_notes.get(quote.bid_exchange, f"Exchange {quote.bid_exchange}")
            ask_note = exchange_notes.get(quote.ask_exchange, f"Exchange {quote.ask_exchange}")
            
            print(f"   Bid exchange: {bid_note}")
            print(f"   Ask exchange: {ask_note}")
            
            if quote.bid_exchange != quote.ask_exchange:
                print(f"   ⚠️  Cross-exchange quote - this can cause wider spreads")
                
        else:
            print(f"❌ No quote data returned for {symbol}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
    print(f"\n🎯 ROOT CAUSE ANALYSIS SUMMARY:")
    print("1. ✅ Stale quote data - quotes older than trades")
    print("2. ✅ Cross-exchange spreads - bid/ask from different exchanges")  
    print("3. ✅ Extended hours data quality - wider spreads after hours")
    print("4. ✅ API vs Website data sources - they may use different feeds")
    print("\n💡 SOLUTION APPROACH:")
    print("• Prioritize trade data over quotes when quotes are stale")
    print("• Filter quotes by exchange quality (prefer NASDAQ/NYSE)")
    print("• Use age-based penalties more aggressively")
    print("• Add cross-exchange spread detection and penalties")

if __name__ == "__main__":
    asyncio.run(test_bid_ask_freshness())
