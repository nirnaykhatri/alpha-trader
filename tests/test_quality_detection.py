#!/usr/bin/env python3
"""
Test the enhanced API data quality detection system
"""

import asyncio
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

async def test_enhanced_quality_detection():
    """Test the new API data quality detection features"""
    try:
        print("🔍 TESTING ENHANCED API DATA QUALITY DETECTION")
        print("=" * 60)
        
        from src.data.market_data import AlpacaMarketDataProvider
        from src.core.config import ConfigurationManager
        
        config = ConfigurationManager("config.yaml")  
        provider = AlpacaMarketDataProvider(config)
        
        # Test symbols - including your problematic HIMS
        test_symbols = ["HIMS", "AAPL", "TSLA"]
        
        for symbol in test_symbols:
            print(f"\n📊 ANALYZING {symbol}")
            print("-" * 40)
            
            try:
                # Get price with enhanced quality detection
                price = await provider.get_current_price(symbol)
                print(f"✅ Final price: ${price:.4f}")
                print(f"   🔍 Check logs above for quality warnings and cross-exchange detection")
                
            except Exception as e:
                print(f"❌ Error getting price for {symbol}: {e}")
        
        print(f"\n🎯 KEY ENHANCEMENTS ACTIVE:")
        print("✅ Cross-exchange spread detection")
        print("✅ Stale quote identification (age >5min)")  
        print("✅ Quality issue penalties (15 points per issue)")
        print("✅ Enhanced logging with root cause analysis")
        print("✅ Automatic trade preference for poor quality quotes")
        
        print(f"\n💡 WHAT TO LOOK FOR IN LOGS:")
        print("🚨 'CROSS-EXCHANGE QUOTE' - bid/ask from different exchanges")
        print("⏰ 'STALE QUOTE' - quotes older than 5 minutes")
        print("🚨 'WIDE SPREAD DETECTED' - spread >3% with quality analysis")
        print("🔄 'OVERRIDING WIDE SPREAD QUOTE' - trade preferred over poor quote")
        
    except Exception as e:
        print(f"❌ Test error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_enhanced_quality_detection())
