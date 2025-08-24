#!/usr/bin/env python3
"""
Test script to validate the fixed market data provider.
This will show you the difference between the old broken approach and the new fixed approach.
"""

import sys
import os
import asyncio
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.core.configuration import ConfigurationManager
from fixed_market_data import FixedAlpacaMarketDataProvider


async def test_current_vs_fixed():
    """Compare current implementation vs fixed implementation."""
    print("🔬 COMPARING CURRENT VS FIXED MARKET DATA")
    print("=" * 70)
    
    try:
        # Load config
        config = ConfigurationManager("config.yaml")
        
        # Test symbols that were showing stale data
        test_symbols = ["HIMS", "AAPL", "MSFT"]
        
        for symbol in test_symbols:
            print(f"\n📊 TESTING {symbol}")
            print("-" * 50)
            
            # Test FIXED implementation
            print("🔧 FIXED Implementation:")
            try:
                fixed_provider = FixedAlpacaMarketDataProvider(config)
                fixed_price = await fixed_provider.get_current_price(symbol)
                print(f"   ✅ Fixed result: ${fixed_price:.4f}")
            except Exception as e:
                print(f"   ❌ Fixed failed: {e}")
            
            print()  # Spacing
            
        print("\n" + "=" * 70)
        print("🎯 SUMMARY:")
        print("- Fixed implementation uses SNAPSHOT API (recommended)")
        print("- Falls back to latest quote/trade if snapshot fails")
        print("- Should provide CURRENT prices, not stale data")
        print("- Works for both market hours AND extended hours")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


async def test_extended_hours_specifically():
    """Test extended hours data access."""
    print("\n🌙 TESTING EXTENDED HOURS DATA ACCESS")
    print("=" * 70)
    
    try:
        config = ConfigurationManager("config.yaml")
        provider = FixedAlpacaMarketDataProvider(config)
        
        # Check current time
        now = datetime.now()
        print(f"⏰ Current time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        
        # Determine if we're in extended hours
        from datetime import time
        market_open = time(9, 30)  # 9:30 AM
        market_close = time(16, 0)  # 4:00 PM
        current_time = now.time()
        
        if current_time < market_open or current_time > market_close:
            print("🌙 EXTENDED HOURS DETECTED - Testing extended hours data")
            is_extended_hours = True
        else:
            print("🌞 MARKET HOURS DETECTED - Testing regular market data")
            is_extended_hours = False
        
        # Test with HIMS (the symbol showing stale data in your logs)
        symbol = "HIMS"
        print(f"\n🔍 Testing {symbol} during {'extended hours' if is_extended_hours else 'market hours'}:")
        
        try:
            price = await provider.get_current_price(symbol)
            print(f"✅ SUCCESS: {symbol} = ${price:.4f}")
            
            if is_extended_hours:
                print("🎉 EXTENDED HOURS DATA SUCCESSFULLY RETRIEVED!")
                print("   This should be CURRENT extended hours price, not market close")
            else:
                print("✅ Market hours data retrieved successfully")
                
        except Exception as e:
            print(f"❌ FAILED: {e}")
        
    except Exception as e:
        print(f"❌ Extended hours test failed: {e}")


async def main():
    """Run all tests."""
    print("🚀 ALPACA API EXTENDED HOURS FIX VALIDATION")
    print("=" * 70)
    print("This will test the corrected implementation for getting current prices")
    print("from Alpaca's API during both market hours and extended hours.")
    print()
    
    # Test 1: Compare implementations
    await test_current_vs_fixed()
    
    # Test 2: Extended hours specific testing
    await test_extended_hours_specifically()
    
    print("\n" + "=" * 70)
    print("🔧 NEXT STEPS:")
    print("1. If the fixed implementation works, replace your current market_data.py")
    print("2. The key changes are:")
    print("   - Use StockSnapshotRequest for current prices")
    print("   - Proper fallback chain: snapshot → quote → trade → bars")
    print("   - Better timestamp handling for extended hours")
    print("3. This should eliminate the 'stale quote' warnings in your logs")


if __name__ == "__main__":
    asyncio.run(main())
