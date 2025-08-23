#!/usr/bin/env python3
"""
Trading Bot Configuration Helper
Interactive script to help users configure their trading bot.
"""

import yaml
import getpass
from pathlib import Path
import secrets

def main():
    """Main configuration function."""
    print("=== Trading Bot Configuration ===")
    print("This script will help you configure your trading bot.")
    print()
    
    config_path = Path("config.yaml")
    
    # Load existing config or create new one
    if config_path.exists():
        print("Loading existing config.yaml...")
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    else:
        print("Creating new config.yaml...")
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    
    # Configure Alpaca API
    print("\n--- Alpaca API Configuration ---")
    print("You need to get API credentials from: https://alpaca.markets/")
    print("For paper trading, use: https://app.alpaca.markets/paper/dashboard/overview")
    
    api_key = input("Enter your Alpaca API Key: ").strip()
    if api_key:
        config['api']['alpaca']['api_key'] = api_key
    
    secret_key = getpass.getpass("Enter your Alpaca Secret Key: ").strip()
    if secret_key:
        config['api']['alpaca']['secret_key'] = secret_key
    
    # Choose paper or live trading
    print("\nTrading Mode:")
    print("1. Paper Trading (recommended for testing)")
    print("2. Live Trading (real money - be careful!)")
    mode = input("Choose mode (1 or 2): ").strip()
    
    if mode == "1":
        config['api']['alpaca']['base_url'] = "https://paper-api.alpaca.markets"
        print("✓ Configured for paper trading")
    elif mode == "2":
        config['api']['alpaca']['base_url'] = "https://api.alpaca.markets"
        print("⚠️  Configured for LIVE trading - please be careful!")
    
    # Configure webhook secret
    print("\n--- Webhook Configuration ---")
    print("The webhook secret is used to secure TradingView webhook calls.")
    
    generate_secret = input("Generate a new webhook secret? (y/n): ").strip().lower()
    if generate_secret in ['y', 'yes']:
        webhook_secret = secrets.token_hex(32)
        config['api']['webhook']['secret'] = webhook_secret
        print(f"✓ Generated webhook secret: {webhook_secret}")
        print("  Use this secret in your TradingView webhook configuration.")
    
    # Configure basic trading parameters
    print("\n--- Trading Configuration ---")
    
    default_quantity = input(f"Default quantity per trade [{config.get('trading', {}).get('default_quantity', 100)}]: ").strip()
    if default_quantity.isdigit():
        config['trading']['default_quantity'] = int(default_quantity)
    
    max_position = input(f"Maximum position size [{config.get('trading', {}).get('max_position_size', 1000)}]: ").strip()
    if max_position.isdigit():
        config['trading']['max_position_size'] = int(max_position)
    
    risk_per_trade = input(f"Risk per trade (%) [{config.get('trading', {}).get('risk_per_trade', 0.02)*100}]: ").strip()
    if risk_per_trade.replace('.', '').isdigit():
        config['trading']['risk_per_trade'] = float(risk_per_trade) / 100
    
    # Save configuration
    print("\n--- Saving Configuration ---")
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, indent=2)
    
    print(f"✓ Configuration saved to {config_path}")
    
    # Validation
    print("\n--- Configuration Validation ---")
    
    required_fields = [
        ('api.alpaca.api_key', config.get('api', {}).get('alpaca', {}).get('api_key')),
        ('api.alpaca.secret_key', config.get('api', {}).get('alpaca', {}).get('secret_key')),
        ('api.webhook.secret', config.get('api', {}).get('webhook', {}).get('secret'))
    ]
    
    all_valid = True
    for field_name, field_value in required_fields:
        if not field_value:
            print(f"❌ Missing: {field_name}")
            all_valid = False
        else:
            print(f"✓ Configured: {field_name}")
    
    if all_valid:
        print("\n🎉 Configuration complete! You can now run the trading bot.")
        print("Next steps:")
        print("1. Test your configuration: python setup.py")
        print("2. Start the trading bot: python run_bot.py")
        print("3. Configure TradingView webhooks with your webhook secret")
    else:
        print("\n⚠️  Configuration incomplete. Please run this script again.")
    
    return all_valid

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nConfiguration cancelled.")
    except Exception as e:
        print(f"\nError during configuration: {e}")
