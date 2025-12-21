#!/usr/bin/env python3
"""
Test extended hours data access for RGTI specifically.
This tests the improved multi-candidate approach for extended hours trading.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.core.configuration import ConfigurationManager
from data.market_data import AlpacaMarketDataProvider
import structlog

# Configure logging
structlog.configure(processors=[
    structlog.stdlib.add_log_level,
    structlog.stdlib.PositionalArgumentsFormatter(),
    structlog.dev.ConsoleRenderer()
])
logger = structlog.get_logger()

async def test_rgti_extended_hours():
    """Test RGTI pricing with detailed logging to see extended hours data access."""
    try:
        print("🚀 Testing RGTI Extended Hours Data Access...")
        print("=" * 60)
        
        # Load configuration
        config = ConfigurationManager()  # Uses config/ TOML files
        
        # Create market data provider
        provider = AlpacaMarketDataProvider(config)
        
        # Test RGTI specifically
        symbol = "RGTI"
        print(f"🔍 Fetching current price for {symbol}...")
        
        # Get current price with detailed logging
        price = await provider.get_current_price(symbol)
        
        print(f"\n🎯 RESULT: {symbol} = ${price:.4f}")
        print("=" * 60)
        print("✅ Extended hours data access test completed!")
        
        return price
        
    except Exception as e:
        print(f"❌ Error testing RGTI: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    asyncio.run(test_rgti_extended_hours())
