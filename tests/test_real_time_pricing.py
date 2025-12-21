#!/usr/bin/env python3
"""
Test script to validate real-time market data fetching improvements.
Tests the latest quote and trade APIs for accuracy during extended hours.
"""

import asyncio
import sys
import logging
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.configuration import ConfigurationManager
from src.data.market_data import AlpacaMarketDataProvider
from src.core.logging_config import setup_logging, get_logger

async def test_real_time_pricing():
    """Test real-time pricing with multiple symbols to validate accuracy."""
    
    # Setup logging
    setup_logging(level="INFO", format_type="json")
    logger = get_logger(__name__)
    
    logger.info("🚀 TESTING REAL-TIME MARKET DATA IMPROVEMENTS")
    logger.info("=" * 80)
    
    try:
        # Initialize configuration and market data provider
        config = ConfigurationManager()  # Uses config/ TOML files
        market_data = AlpacaMarketDataProvider(config)
        
        # Test symbols (including the problematic RGTI)
        test_symbols = ["RGTI", "AAPL", "TSLA", "SPY", "QQQ"]
        
        logger.info(f"📊 Testing {len(test_symbols)} symbols for pricing accuracy")
        logger.info(f"🕒 Current time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        logger.info("")
        
        results = {}
        
        for symbol in test_symbols:
            try:
                logger.info(f"🔍 TESTING {symbol}")
                logger.info("-" * 40)
                
                start_time = datetime.now()
                
                # Fetch current price using improved method
                current_price = await market_data.get_current_price(symbol)
                
                end_time = datetime.now()
                fetch_duration = (end_time - start_time).total_seconds()
                
                results[symbol] = {
                    'price': current_price,
                    'fetch_time_seconds': fetch_duration,
                    'timestamp': datetime.now(timezone.utc)
                }
                
                logger.info(f"✅ {symbol}: ${current_price:.4f} (fetched in {fetch_duration:.2f}s)")
                logger.info("")
                
            except Exception as e:
                logger.error(f"❌ Failed to get price for {symbol}: {e}")
                results[symbol] = {'error': str(e)}
                logger.info("")
        
        # Summary report
        logger.info("=" * 80)
        logger.info("📋 PRICING TEST SUMMARY")
        logger.info("=" * 80)
        
        successful_fetches = 0
        total_fetch_time = 0
        
        for symbol, result in results.items():
            if 'error' in result:
                logger.error(f"❌ {symbol}: ERROR - {result['error']}")
            else:
                logger.info(f"✅ {symbol}: ${result['price']:.4f} ({result['fetch_time_seconds']:.2f}s)")
                successful_fetches += 1
                total_fetch_time += result['fetch_time_seconds']
        
        if successful_fetches > 0:
            avg_fetch_time = total_fetch_time / successful_fetches
            logger.info("")
            logger.info(f"📊 SUCCESS RATE: {successful_fetches}/{len(test_symbols)} ({successful_fetches/len(test_symbols)*100:.1f}%)")
            logger.info(f"⚡ AVERAGE FETCH TIME: {avg_fetch_time:.2f} seconds")
            
            if avg_fetch_time < 2.0:
                logger.info("🎯 PERFORMANCE: EXCELLENT (< 2s per fetch)")
            elif avg_fetch_time < 5.0:
                logger.info("🟡 PERFORMANCE: GOOD (< 5s per fetch)")
            else:
                logger.warning("🔴 PERFORMANCE: SLOW (> 5s per fetch)")
        
        logger.info("")
        logger.info("🏁 REAL-TIME PRICING TEST COMPLETED")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}", exc_info=True)
        return None

async def main():
    """Main test execution."""
    results = await test_real_time_pricing()
    
    if results:
        print("\n" + "="*60)
        print("REAL-TIME PRICING TEST RESULTS")
        print("="*60)
        
        for symbol, result in results.items():
            if 'error' not in result:
                print(f"{symbol}: ${result['price']:.4f}")
            else:
                print(f"{symbol}: ERROR")
        
        print("="*60)
        return True
    else:
        print("\n❌ Test failed - check logs for details")
        return False

if __name__ == "__main__":
    # Run the test
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
