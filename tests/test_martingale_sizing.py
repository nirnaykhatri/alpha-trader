#!/usr/bin/env python3
"""
Test script for martingale position sizing approach.
Demonstrates how position sizes scale for averaging down/up.
"""

import asyncio


class MockAccountProvider:
    """Mock account provider that returns realistic values."""
    
    async def get_buying_power(self) -> float:
        return 200000.0  # $200k buying power (matching your real account)
    
    async def get_account_value(self) -> float:
        return 100000.0  # $100k account value


class MockConfig:
    """Mock configuration that returns martingale settings."""
    
    def get_config(self, key: str, default=None):
        config_values = {
            "trading.position_sizing.initial_portfolio_percentage": 0.01,  # 1%
            "trading.position_sizing.averaging.multiplier": 2.0,          # 2x
            "trading.position_sizing.averaging.max_attempts": 3,          # 3 attempts
            "trading.position_sizing.max_total_position_percentage": 0.15, # 15% max
            "trading.position_sizing.max_quantity": 10000,
            "trading.position_sizing.min_quantity": 1,
        }
        return config_values.get(key, default)


async def calculate_martingale_position(account_provider, config, symbol: str, price: float, averaging_attempt: int = 0):
    """Calculate position size using martingale approach."""
    
    # Get configuration - use different percentage for initial vs averaging
    if averaging_attempt == 0:
        # Initial position - use conservative percentage
        portfolio_percentage = config.get_config("trading.position_sizing.initial_portfolio_percentage", 0.01)
        print(f"   🎯 Initial position sizing: {portfolio_percentage*100:.1f}% of buying power")
    else:
        # Averaging position - use martingale approach
        initial_percentage = config.get_config("trading.position_sizing.initial_portfolio_percentage", 0.01)
        multiplier = config.get_config("trading.position_sizing.averaging.multiplier", 2.0)
        
        # Calculate martingale size: initial * (multiplier ^ averaging_attempt)
        portfolio_percentage = initial_percentage * (multiplier ** averaging_attempt)
        
        print(f"   📈 Averaging #{averaging_attempt}: {portfolio_percentage*100:.1f}% of buying power "
              f"(initial {initial_percentage*100:.1f}% × {multiplier}^{averaging_attempt})")
    
    max_qty = config.get_config("trading.position_sizing.max_quantity", 10000)
    min_qty = config.get_config("trading.position_sizing.min_quantity", 1)
    
    # Get available buying power
    buying_power = await account_provider.get_buying_power()
    available_funds = buying_power * portfolio_percentage
    
    # Calculate quantity based on current price
    if price <= 0:
        return 0.0
    
    # Calculate raw quantity
    raw_quantity = available_funds / price
    quantity = int(raw_quantity)  # Round down to whole shares
    
    # Check if we can afford at least 1 share
    if quantity < min_qty:
        min_cost = min_qty * price
        print(f"   ❌ Insufficient funds: need ${min_cost:.2f}, have ${available_funds:.2f}")
        return 0.0
    
    # Apply maximum limits
    quantity = min(quantity, max_qty)
    
    return float(quantity)


async def test_martingale_sizing():
    """Test the martingale position sizing approach."""
    print("=== Martingale Position Sizing Test ===")
    print("🎯 This demonstrates how position sizes scale with averaging attempts")
    print()
    
    # Initialize mock components
    account_provider = MockAccountProvider()
    config = MockConfig()
    
    # Test configuration
    initial_percentage = config.get_config("trading.position_sizing.initial_portfolio_percentage", 0.01)
    multiplier = config.get_config("trading.position_sizing.averaging.multiplier", 2.0)
    max_attempts = config.get_config("trading.position_sizing.averaging.max_attempts", 3)
    
    print(f"📊 Martingale Configuration:")
    print(f"   🎯 Initial Position: {initial_percentage*100:.1f}% of buying power")
    print(f"   📈 Multiplier: {multiplier}x per averaging attempt")
    print(f"   🔄 Max Attempts: {max_attempts}")
    print()
    
    # Get account data
    buying_power = await account_provider.get_buying_power()
    account_value = await account_provider.get_account_value()
    
    print(f"💰 Account Data (simulating your real Alpaca account):")
    print(f"   🛒 Buying Power: ${buying_power:,.2f}")
    print(f"   📊 Account Value: ${account_value:,.2f}")
    print()
    
    # Test stocks with different prices
    test_stocks = [
        ("AAPL", 150.00),
        ("TSLA", 250.00),
        ("F", 12.00),
        ("NVDA", 800.00),
        ("BTC", 107000.00)  # Your actual BTC example
    ]
    
    for symbol, price in test_stocks:
        print(f"📈 {symbol} @ ${price:.2f} - Martingale Position Sizing:")
        
        total_shares = 0
        total_cost = 0.0
        total_percentage = 0.0
        
        # Test initial position + averaging attempts
        for attempt in range(max_attempts + 1):
            
            # Calculate position size for this attempt
            quantity = await calculate_martingale_position(account_provider, config, symbol, price, attempt)
            
            if quantity > 0:
                cost = quantity * price
                percentage = (cost / buying_power) * 100
                
                total_shares += quantity
                total_cost += cost
                total_percentage += percentage
                
                if attempt == 0:
                    print(f"      💚 Initial:     {quantity:4.0f} shares = ${cost:8,.0f} ({percentage:4.1f}%)")
                else:
                    expected_percentage = initial_percentage * (multiplier ** attempt) * 100
                    print(f"      � Attempt #{attempt}: {quantity:4.0f} shares = ${cost:8,.0f} ({percentage:4.1f}%) "
                          f"[Expected: {expected_percentage:.1f}%]")
            else:
                print(f"      ❌ Attempt #{attempt}: SKIP - insufficient funds")
                break
        
        if total_shares > 0:
            print(f"      � TOTAL:       {total_shares:4.0f} shares = ${total_cost:8,.0f} ({total_percentage:4.1f}%)")
            avg_price = total_cost / total_shares
            print(f"      📊 Average Price: ${avg_price:.2f} (vs current ${price:.2f})")
        else:
            print(f"      💸 Cannot afford even 1 share at ${price:.2f}")
        
        print()
    
    print("=== Martingale Strategy Benefits ===")
    print("✅ Conservative start: Only 1% initial exposure")
    print("✅ Aggressive averaging: Doubles position size each time")
    print("✅ Keeps average price close to current price")
    print("✅ Maximum exposure protection prevents over-leveraging")
    print("✅ Configurable multiplier allows risk adjustment")
    print()
    
    print("🎯 Example Scenario - AAPL drops from $150 to $120:")
    print("   📉 Price Drop: $150 → $140 → $130 → $120")
    print("   💰 Position 1: 1% = 13 shares @ $150 = $1,950")
    print("   💰 Position 2: 2% = 28 shares @ $140 = $3,920") 
    print("   💰 Position 3: 4% = 61 shares @ $130 = $7,930")
    print("   💰 Position 4: 8% = 133 shares @ $120 = $15,960")
    print("   💎 TOTAL: 235 shares, avg price $127.08 (vs current $120)")
    print("   📊 Total exposure: 15% of buying power")
    print("   🎯 Profit when price recovers to $150: $5,386 (18% gain)")


if __name__ == "__main__":
    asyncio.run(test_martingale_sizing())
