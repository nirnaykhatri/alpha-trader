#!/usr/bin/env python3
"""
Simple test to check Alpaca account buying power.
Run this to see what the real account values are.
"""

import asyncio
from alpaca.trading.client import TradingClient
import yaml

def load_config():
    """Load configuration from config.yaml."""
    with open('config.yaml', 'r') as file:
        return yaml.safe_load(file)

async def main():
    """Test Alpaca account data."""
    print("=== Simple Alpaca Account Test ===")
    
    try:
        # Load config
        config = load_config()
        
        # Get credentials
        api_key = config['api']['alpaca']['api_key']
        secret_key = config['api']['alpaca']['secret_key']
        base_url = config['api']['alpaca']['base_url']
        
        print(f"API Key: {api_key[:8]}...")
        print(f"Base URL: {base_url}")
        print()
        
        # Create client
        is_paper = "paper" in base_url
        client = TradingClient(api_key, secret_key, paper=is_paper)
        
        # Get account data
        account = client.get_account()
        
        print("=== REAL ALPACA ACCOUNT DATA ===")
        print(f"Account ID: {account.id}")
        print(f"Cash: ${float(account.cash):,.2f}")
        print(f"Equity: ${float(account.equity):,.2f}")
        print(f"Buying Power: ${float(account.buying_power):,.2f}")
        print(f"Portfolio Value: ${float(account.portfolio_value):,.2f}")
        print(f"Status: {account.status}")
        print()
        
        # Check if it's the expected high value
        bp = float(account.buying_power)
        if bp > 10000:
            print(f"✅ Buying power looks correct: ${bp:,.2f}")
        else:
            print(f"❌ Buying power seems low: ${bp:,.2f}")
            print("This might be why the bot is rejecting trades!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
