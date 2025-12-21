#!/usr/bin/env python3
"""
Test script to verify quote freshness detection and fallback to recent bars.
Specifically tests the fix for stale quotes during off-hours trading.
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add the project root to the path
project_root = os.path.dirname(__file__)
sys.path.insert(0, project_root)

from src.data.market_data import AlpacaMarketDataProvider
from src.core.configuration import ConfigurationManager
import logging
import pytest

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

@pytest.mark.asyncio
async def test_quote_freshness():
    """Test quote freshness detection and fallback behavior."""
    print("🧪 Testing Quote Freshness Detection & Fallback...")
    
    # Initialize config and market data provider
    config = ConfigurationManager()
    market_data = AlpacaMarketDataProvider(config)
    
    # Test symbols with different characteristics
    test_symbols = ['MSFT', 'AAPL', 'QBTS', 'HIMS']
    
    for symbol in test_symbols:
        print(f"\n📊 Testing {symbol}:")
        print("-" * 50)
        
        try:
            # Get current price (will test quote freshness internally)
            price = await market_data.get_current_price(symbol)
            print(f"✅ Current price for {symbol}: ${price:.2f}")
            
            # Also test the quote method directly to see what's happening
            quote_price = await market_data._get_latest_quote_price(symbol)
            if quote_price:
                print(f"   📈 Quote API returned: ${quote_price:.2f}")
            else:
                print(f"   ⚠️  Quote API rejected (likely stale)")
                
        except Exception as e:
            print(f"❌ Error getting price for {symbol}: {e}")
    
    print(f"\n🔍 Test completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Show what time it is and whether this is market hours
    now = datetime.now()
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    
    if market_open <= now <= market_close and now.weekday() < 5:
        print("🕒 Currently during regular market hours")
    else:
        print("🌙 Currently outside regular market hours (after-hours/pre-market)")

if __name__ == "__main__":
    asyncio.run(test_quote_freshness())
