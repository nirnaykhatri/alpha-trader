#!/usr/bin/env python3
"""
Test script to verify Alpaca account data retrieval.
This will help debug why the system shows $5,000 buying power instead of real values.
"""

import asyncio
import sys
import os

# Add the src directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.insert(0, src_dir)

# Now import with absolute imports
import src.core.configuration as config_module
import src.trading.alpaca_account_provider as account_module
from alpaca.trading.client import TradingClient
import pytest


@pytest.mark.asyncio
async def test_alpaca_account():
    """Test Alpaca account data retrieval."""
    print("=== Alpaca Account Data Test ===")
    print()
    
    try:
        # Load configuration
        config = config_module.ConfigurationManager()  # Uses config/ TOML files
        
        # Get API credentials
        api_key = config.get_config("api.alpaca.api_key")
        secret_key = config.get_config("api.alpaca.secret_key")
        base_url = config.get_config("api.alpaca.base_url")
        
        print(f"🔑 API Key: {api_key[:8]}...")
        print(f"🌐 Base URL: {base_url}")
        print()
        
        # Initialize Alpaca client
        trading_client = TradingClient(api_key, secret_key, paper=True)
        
        # Test direct API call
        print("📡 Testing direct Alpaca API call...")
        account = trading_client.get_account()
        
        print(f"✅ Direct API Response:")
        print(f"   💰 Equity: ${float(account.equity):,.2f}")
        print(f"   💵 Cash: ${float(account.cash):,.2f}")
        print(f"   🛒 Buying Power: ${float(account.buying_power):,.2f}")
        print(f"   📈 Portfolio Value: ${float(account.portfolio_value):,.2f}")
        print(f"   🏦 Account ID: {account.id}")
        print(f"   📊 Account Status: {account.status}")
        print()
        
        # Test through our account provider
        print("🔧 Testing through AlpacaAccountProvider...")
        account_provider = account_module.AlpacaAccountProvider(trading_client)
        
        buying_power = await account_provider.get_buying_power()
        account_value = await account_provider.get_account_value()
        portfolio_value = await account_provider.get_portfolio_value()
        
        print(f"✅ Account Provider Response:")
        print(f"   🛒 Buying Power: ${buying_power:,.2f}")
        print(f"   💰 Account Value: ${account_value:,.2f}")
        print(f"   📈 Portfolio Value: ${portfolio_value:,.2f}")
        print()
        
        # Check if values match
        if abs(buying_power - float(account.buying_power)) < 0.01:
            print("✅ Values match - Account provider is working correctly!")
        else:
            print("❌ Values don't match - There's an issue with the account provider!")
            print(f"   Expected: ${float(account.buying_power):,.2f}")
            print(f"   Got: ${buying_power:,.2f}")
        
    except Exception as e:
        print(f"❌ Error testing Alpaca account: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_alpaca_account())
