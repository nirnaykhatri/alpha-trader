#!/usr/bin/env python3

"""
Test the enhanced extended hours implementation with multiple symbols
"""

import asyncio
import sys
from pathlib import Path

# Add src directory to path
current_dir = Path(__file__).parent
src_dir = current_dir.parent / "src"
sys.path.insert(0, str(src_dir))

from src.data.market_data import AlpacaMarketDataProvider
from src.core.configuration import ConfigurationManager

async def test_enhanced_extended_hours():
    """Test enhanced extended hours data access"""
    
    print("🌟 TESTING ENHANCED EXTENDED HOURS IMPLEMENTATION")
    print("=" * 60)
    
    # Initialize
    config = ConfigurationManager("config.yaml")
    provider = AlpacaMarketDataProvider(config)
    
    # Test multiple symbols to see the difference
    test_symbols = ["RGTI", "AAPL", "TSLA", "NVDA"]
    
    for symbol in test_symbols:
        print(f"\n📊 Testing {symbol}...")
        print("-" * 40)
        
        try:
            # Test all three enhanced methods individually
            
            # 1. Enhanced Quote Method
            quote_price = await provider._get_latest_quote_price(symbol)
            if quote_price:
                print(f"✅ Enhanced Quote: ${quote_price:.4f}")
            else:
                print("❌ Enhanced Quote: No data")
            
            # 2. Enhanced Trade Method  
            trade_price = await provider._get_latest_trade_price(symbol)
            if trade_price:
                print(f"✅ Enhanced Trade: ${trade_price:.4f}")
            else:
                print("❌ Enhanced Trade: No data")
            
            # 3. Enhanced Bars Method (24-hour lookback)
            bars = await provider._get_recent_bars_extended(symbol, "1Min", 100, hours=24)
            if bars:
                latest_bar = bars[-1]
                print(f"✅ Enhanced Bars (24h): ${latest_bar['close']:.4f} at {latest_bar['timestamp']}")
            else:
                print("❌ Enhanced Bars: No data")
            
            # 4. Full integrated method
            print(f"\n🎯 Full Enhanced Price Fetch for {symbol}:")
            price = await provider.get_current_price(symbol)
            print(f"💰 Final Price: ${price:.4f}")
            
        except Exception as e:
            print(f"❌ Error testing {symbol}: {e}")
    
    print(f"\n🔍 KEY IMPROVEMENTS:")
    print("1. Enhanced quote method with 8-hour tolerance")
    print("2. Enhanced trade method with better timestamp handling")
    print("3. Extended 24-hour bars lookback (vs 12-hour before)")
    print("4. Better after-hours bid/ask logic")
    print("5. Improved response handling for different API versions")

if __name__ == "__main__":
    asyncio.run(test_enhanced_extended_hours())
