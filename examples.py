#!/usr/bin/env python3
"""
Trading Bot Examples
Shows how to use the trading bot programmatically and test various features.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.trading_bot import TradingBotOrchestrator, trading_bot_context
from src.core import ConfigurationManager
from src import TradingSignal, SignalType


async def example_basic_usage():
    """Example: Basic bot usage with context manager."""
    print("🚀 Example: Basic Trading Bot Usage")
    
    async with trading_bot_context("config.yaml") as bot:
        # Start the bot (this would normally run forever)
        print("Bot started! Press Ctrl+C to stop.")
        
        # In a real scenario, you'd let it run
        # await bot.start()


async def example_manual_signal():
    """Example: Manually send a trading signal."""
    print("📊 Example: Manual Trading Signal")
    
    bot = TradingBotOrchestrator("config.yaml")
    
    try:
        # Initialize components
        await bot._initialize_components()
        
        # Create a test signal
        test_signal = TradingSignal(
            signal_id="test_001",
            symbol="AAPL",
            signal_type=SignalType.BUY,
            price=150.25,
            quantity=100
        )
        
        print(f"Processing signal: {test_signal.symbol} {test_signal.signal_type.value}")
        
        # Process the signal
        await bot._handle_trading_signal(test_signal)
        
        print("✅ Signal processed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await bot.stop()


async def example_position_monitoring():
    """Example: Monitor positions and get status."""
    print("📈 Example: Position Monitoring")
    
    bot = TradingBotOrchestrator("config.yaml")
    
    try:
        await bot._initialize_components()
        
        # Get current status
        status = await bot.get_status()
        print(f"Bot Status: {json.dumps(status, indent=2)}")
        
        # Get positions
        positions = await bot.get_positions()
        print(f"\nCurrent Positions ({len(positions)}):")
        for pos in positions:
            print(f"  {pos.symbol}: {pos.quantity:+.0f} @ ${pos.avg_price:.2f} "
                  f"(P&L: ${pos.unrealized_pnl:+.2f})")
        
        # Get open orders
        orders = await bot.get_open_orders()
        print(f"\nOpen Orders ({len(orders)}):")
        for order in orders:
            print(f"  {order.symbol}: {order.side} {order.quantity} @ ${order.price:.2f}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await bot.stop()


async def example_manual_close():
    """Example: Manually close a position."""
    print("🛑 Example: Manual Position Close")
    
    bot = TradingBotOrchestrator("config.yaml")
    
    try:
        await bot._initialize_components()
        
        # Get positions
        positions = await bot.get_positions()
        
        if not positions:
            print("No positions to close")
            return
        
        # Close the first position
        symbol = positions[0].symbol
        print(f"Closing position: {symbol}")
        
        success = await bot.manual_close_position(symbol)
        
        if success:
            print(f"✅ Successfully closed position for {symbol}")
        else:
            print(f"❌ Failed to close position for {symbol}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await bot.stop()


async def example_config_validation():
    """Example: Validate configuration."""
    print("🔧 Example: Configuration Validation")
    
    try:
        config = ConfigurationManager("config.yaml")
        
        # Check if all required config is present
        config.validate_required_config()
        print("✅ Configuration is valid!")
        
        # Show some key settings
        print(f"\nKey Settings:")
        print(f"  Webhook Port: {config.get_config('api.webhook.port')}")
        print(f"  Default Quantity: {config.get_config('trading.default_quantity')}")
        print(f"  Risk Per Trade: {config.get_config('trading.risk_per_trade'):.1%}")
        print(f"  Trailing Enabled: {config.get_config('strategies.trailing_profit.enabled')}")
        
        # Show API configuration (without revealing secrets)
        alpaca_url = config.get_config('api.alpaca.base_url')
        print(f"  Alpaca Mode: {'Paper Trading' if 'paper' in alpaca_url else 'Live Trading'}")
        
    except Exception as e:
        print(f"❌ Configuration Error: {e}")


async def example_simulate_webhook():
    """Example: Simulate receiving a TradingView webhook."""
    print("🔗 Example: Simulate TradingView Webhook")
    
    # This is what a TradingView webhook might send
    webhook_data = {
        "ticker": "AAPL",
        "time": "2023-12-07T10:30:00Z",
        "interval": "1h",
        "signal": "buy",
        "price": 150.25,
        "quantity": 100,
        "alert_name": "AAPL Bullish Signal",
        "exchange": "NASDAQ"
    }
    
    print(f"Simulating webhook data: {json.dumps(webhook_data, indent=2)}")
    
    bot = TradingBotOrchestrator("config.yaml")
    
    try:
        await bot._initialize_components()
        
        # Process the webhook data as if it came from TradingView
        signal = await bot.signal_listener.process_signal(webhook_data)
        print(f"✅ Processed signal: {signal.signal_id}")
        
        # The signal would then be handled by the trading logic
        await bot._handle_trading_signal(signal)
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await bot.stop()


async def example_risk_check():
    """Example: Test risk management."""
    print("🛡️ Example: Risk Management Check")
    
    bot = TradingBotOrchestrator("config.yaml")
    
    try:
        await bot._initialize_components()
        
        # Test a large order that should be rejected
        large_signal = TradingSignal(
            signal_id="risk_test",
            symbol="AAPL",
            signal_type=SignalType.BUY,
            price=150.0,
            quantity=10000  # Very large quantity
        )
        
        # Check if risk manager approves this signal
        risk_approved = await bot.risk_manager.validate_signal(large_signal)
        print(f"Large order approved: {risk_approved}")
        
        # Calculate position size for a normal signal
        normal_signal = TradingSignal(
            signal_id="normal_test",
            symbol="AAPL",
            signal_type=SignalType.BUY,
            price=150.0
        )
        
        position_size = await bot.risk_manager.calculate_position_size("AAPL", normal_signal)
        print(f"Calculated position size: {position_size}")
        
        # Get risk metrics
        metrics = bot.risk_manager.get_risk_metrics()
        print(f"Risk metrics: {json.dumps(metrics, indent=2, default=str)}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await bot.stop()


async def example_tradingview_webhook_format():
    """Example: TradingView webhook format that the bot expects."""
    print("📡 Example: TradingView Webhook Format")
    
    # This is the webhook format expected from TradingView
    tradingview_webhook = {
        "ticker": "AAPL",              # {{ticker}} macro
        "time": "2023-12-07T10:30:00Z", # {{time}} macro  
        "interval": "1h",              # {{interval}} macro
        "signal": "buy",               # {{strategy.order.action}} macro
        "price": 150.25,               # Current price (optional)
        "message": "AAPL Buy Signal on 1h timeframe"  # Custom message (optional)
    }
    
    print("Expected TradingView webhook format:")
    print(json.dumps(tradingview_webhook, indent=2))
    
    print("\n" + "="*60)
    print("📋 WEBHOOK CONFIGURATION MODES")
    print("="*60)
    
    print("\n🔓 DEVELOPMENT MODE (Security Disabled):")
    print("In config.yaml:")
    print("  api:")
    print("    webhook:")
    print("      security_enabled: false")
    print("      secret: \"\"")
    print("\nWebhook URL: http://your-ngrok-url.ngrok.io/webhook")
    print("✅ No authentication required - easy for testing!")
    
    print("\n🔒 PRODUCTION MODE (Security Enabled):")
    print("In config.yaml:")
    print("  api:")
    print("    webhook:")
    print("      security_enabled: true")
    print("      secret: \"your-secret-here\"")
    print("\nWebhook URL: http://your-ngrok-url.ngrok.io/webhook/your-secret-here")
    print("🛡️  Authentication required - secure for live trading!")
    
    # The TradingView alert message template should be:
    template = '''
{
  "ticker": "{{ticker}}",
  "time": "{{time}}",
  "interval": "{{interval}}",
  "signal": "{{strategy.order.action}}",
  "price": "{{close}}",
  "message": "{{strategy.order.action}} signal for {{ticker}} on {{interval}}"
}
    '''
    
    print("\n" + "="*60)
    print("📝 TRADINGVIEW ALERT MESSAGE TEMPLATE")
    print("="*60)
    print(template.strip())
    
    print("\n" + "="*60)
    print("🔐 WEBHOOK SECURITY SETUP")
    print("="*60)
    
    print("\n📍 Option 1: Secret in URL (Recommended)")
    print("Webhook URL: https://your-ngrok-url.ngrok.io/webhook/YOUR_SECRET_HERE")
    print("Example: https://abc123.ngrok.io/webhook/a1b2c3d4e5f6789012345678")
    
    print("\n📍 Option 2: Secret in Message Body")
    print("Add secret to your TradingView alert message:")
    template_with_secret = '''
{
  "ticker": "{{ticker}}",
  "signal": "{{strategy.order.action}}",
  "secret": "YOUR_SECRET_HERE",
  "price": "{{close}}"
}'''
    print(template_with_secret)
    print("Webhook URL: https://your-ngrok-url.ngrok.io/webhook")
    
    print("\n⚠️  IMPORTANT:")
    print("- TradingView does NOT send signature headers automatically")
    print("- You must include the secret in URL path OR message body")
    print("- Generate secret with: openssl rand -hex 32")
    print("- Keep your secret secure and never share it!")


def print_menu():
    """Print example menu."""
    print("\n" + "="*60)
    print("🤖 TRADING BOT EXAMPLES")
    print("="*60)
    print("1. Basic Usage")
    print("2. Manual Signal Processing")
    print("3. Position Monitoring")
    print("4. Manual Position Close")
    print("5. Configuration Validation")
    print("6. Simulate TradingView Webhook")
    print("7. Risk Management Check")
    print("8. TradingView Webhook Format")
    print("0. Exit")
    print("="*60)


async def main():
    """Main example runner."""
    examples = {
        "1": example_basic_usage,
        "2": example_manual_signal,
        "3": example_position_monitoring,
        "4": example_manual_close,
        "5": example_config_validation,
        "6": example_simulate_webhook,
        "7": example_risk_check,
        "8": example_tradingview_webhook_format,
    }
    
    while True:
        print_menu()
        choice = input("\nSelect an example (0-8): ").strip()
        
        if choice == "0":
            print("👋 Goodbye!")
            break
        
        if choice in examples:
            print(f"\n{'='*60}")
            try:
                await examples[choice]()
            except KeyboardInterrupt:
                print("\n⏹️ Example interrupted by user")
            except Exception as e:
                print(f"\n❌ Example failed: {e}")
            
            input("\nPress Enter to continue...")
        else:
            print("❌ Invalid choice. Please select 0-8.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Examples stopped by user")
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        sys.exit(1)
