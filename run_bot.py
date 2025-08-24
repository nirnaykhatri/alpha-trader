#!/usr/bin/env python3
"""
Trading Bot Startup Script
Simple script for users to start the trading bot with minimal configuration.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add src to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.trading_bot import run_trading_bot, TradingBotOrchestrator
from src.core import ConfigurationManager, setup_logging
from src.exceptions import ConfigurationException


def print_banner():
    """Print startup banner."""
    banner = """
    ╔══════════════════════════════════════════════════════════════╗
    ║                      TRADING BOT                             ║
    ║              Advanced Algorithmic Trading System             ║
    ║                                                              ║
    ║  Features:                                                   ║
    ║  • TradingView Webhook Integration                           ║
    ║  • Alpaca API Trading                                        ║
    ║  • Configurable Order Types (Market/Limit)                   ║
    ║  • Advanced Long/Short Strategies                            ║
    ║  • Support/Resistance Level Trading                          ║
    ║  • Intelligent Averaging (Down/Up) with Trailing             ║
    ║  • Configurable Profit Trailing                              ║
    ║  • Risk Management & Position Sizing                         ║
    ║  • Real-time Position Monitoring                             ║
    ╚══════════════════════════════════════════════════════════════╝
    """
    print(banner)


def check_config_file():
    """Check if config file exists and help user set it up."""
    config_file = "config.yaml"
    
    if not os.path.exists(config_file):
        print(f"❌ Configuration file '{config_file}' not found!")
        print("\n🔧 To get started:")
        print("1. Copy the sample config.yaml file to your working directory")
        print("2. Edit the configuration file with your settings:")
        print("   - Add your Alpaca API credentials")
        print("   - Set your webhook secret")
        print("   - Adjust trading parameters as needed")
        print("3. Run this script again")
        print(f"\n📁 Sample config location: {Path(__file__).parent / 'config.yaml'}")
        return False
    
    return True


def validate_config():
    """Validate configuration and provide helpful error messages."""
    try:
        config = ConfigurationManager()
        config.validate_required_config()
        
        # Additional checks with user-friendly messages using consolidated credentials
        credentials = config.get_broker_credentials("alpaca")
        api_key = credentials["api_key"]
        secret_key = credentials["secret_key"]
        webhook_secret = config.get_config("api.webhook.secret")
        security_enabled = config.get_config("api.webhook.security_enabled", False)
        
        issues = []
        
        if not api_key:
            issues.append("❌ Alpaca API key is missing")
        elif len(api_key) < 10:
            issues.append("⚠️  Alpaca API key looks too short")
            
        if not secret_key:
            issues.append("❌ Alpaca secret key is missing")
        elif len(secret_key) < 20:
            issues.append("⚠️  Alpaca secret key looks too short")
            
        # Only check webhook secret if security is enabled
        if security_enabled:
            if not webhook_secret:
                issues.append("❌ Webhook secret is missing (required when security_enabled=true)")
            elif len(webhook_secret) < 16:
                issues.append("⚠️  Webhook secret should be at least 16 characters")
        else:
            print("ℹ️  Webhook security is disabled (development mode)")
        
        if issues:
            print("\n🔧 Configuration Issues:")
            for issue in issues:
                print(f"   {issue}")
            print("\n💡 Tips:")
            print("   • Get Alpaca API keys from: https://app.alpaca.markets/")
            if security_enabled:
                print("   • Generate webhook secret: openssl rand -hex 32")
            else:
                print("   • Set security_enabled=true in production")
            print("   • Make sure you're using paper trading keys for testing")
            return False
        
        print("✅ Configuration validation passed!")
        return True
        
    except ConfigurationException as e:
        print(f"❌ Configuration error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error validating config: {e}")
        return False


def show_quick_start_guide():
    """Show quick start guide for new users."""
    print("\n📚 Quick Start Guide:")
    print("=" * 50)
    
    print("\n1. 🔑 Get Alpaca API Credentials:")
    print("   • Sign up at: https://alpaca.markets/")
    print("   • Generate paper trading API keys")
    print("   • Add them to config.yaml")
    
    print("\n2. 🔐 Generate Webhook Secret:")
    print("   • Run: openssl rand -hex 32")
    print("   • Add the secret to config.yaml")
    
    print("\n3. 🌐 Automated Webhook Setup (NEW!):")
    print("   • Set 'ngrok.enabled: true' in config.yaml")
    print("   • Bot will automatically download and start ngrok")
    print("   • Copy the displayed webhook URL to TradingView")
    print("   • No manual ngrok setup required!")
    
    print("\n4. 📊 TradingView Setup:")
    print("   • Create alerts in TradingView")
    print("   • Use the webhook URL displayed when bot starts")
    print("   • Include timeframe data for better support calculations")
    
    print("\n5. 🎯 Enhanced Signal Format:")
    print("   Your TradingView alerts should send JSON like:")
    print("   {")
    print('     "symbol": "{{ticker}}",')
    print('     "action": "{{strategy.order.action}}",')
    print('     "price": {{close}},')
    print('     "quantity": 100,')
    print('     "timeframe": "{{interval}}"')
    print("   }")
    print("   • The bot now supports configurable order types")
    print("   • Advanced trailing profit with support/resistance averaging")
    print("   • Separate long/short strategy configurations")
    
    print("\n6. 🚀 Start Trading:")
    print("   • Run this script to start the bot")
    print("   • ngrok tunnel will start automatically")
    print("   • Monitor logs for signal processing")
    print("   • Check your Alpaca account for trades")
    
    print("\n💡 Pro Tips:")
    print("   • Use paper trading first (default config)")
    print("   • Configure order types in config.yaml (market vs limit)")
    print("   • Adjust trailing percentages and support/resistance detection")
    print("   • Set position multipliers for averaging strategies")
    print("   • Get free ngrok token for better reliability")
    print("   • Monitor webhook traffic at http://localhost:4040")
    print("   • Free ngrok URLs change on restart - update TradingView accordingly")


async def main():
    """Main startup function."""
    print_banner()
    
    # Check for config file
    if not check_config_file():
        show_quick_start_guide()
        return
    
    # Validate configuration
    if not validate_config():
        print("\n🔧 Please fix the configuration issues and try again.")
        return
    
    print("\n🚀 Starting Trading Bot...")
    print("\n" + "="*60)
    print("🛑 IMPORTANT: Windows Shutdown Instructions")
    print("="*60)
    print("⚠️  Ctrl+C may not work reliably on Windows!")
    print("")
    print("✅ RELIABLE SHUTDOWN METHODS:")
    print("   1. 🎯 python shutdown_bot.py      (in another terminal)")
    print("   2. 🔥 stop_bot.bat               (force kill)")
    print("   3. 📊 python monitor_bot.py      (interactive)")
    print("   4. ⌨️  Ctrl+Break                (not Ctrl+C)")
    print("   5. 🪟 Close terminal window       (last resort)")
    print("="*60)
    print("")
    print("📋 Other Info:")
    print("   • Check logs: logs/trading_bot.log")
    print("   • Monitor your Alpaca account for trades")
    print("   • Health check: http://localhost:8080/health")
    
    # Check if ngrok is enabled and inform user
    try:
        from src.core import ConfigurationManager
        config = ConfigurationManager()
        
        # Check for environment variable override
        no_ngrok_env = os.getenv("TRADING_BOT_NO_NGROK", "").lower() in ("1", "true", "yes")
        ngrok_enabled = config.get_config("ngrok.enabled", False) and not no_ngrok_env
        
        if no_ngrok_env:
            print("\n🚫 ngrok Disabled (Environment Override):")
            print("   • Running in local-only mode")
            print("   • No webhook tunnel will be created")
            print("   • Use manual webhook URLs if needed")
        elif ngrok_enabled:
            print("\n🌐 ngrok Auto-Setup Enabled:")
            print("   • Bot will automatically download and configure ngrok")
            print("   • Watch for webhook URL to copy to TradingView")
            print("   • Monitor webhook traffic at: http://localhost:4040")
        else:
            print("\n🏠 Local Mode (ngrok disabled in config):")
            print("   • Running without webhook tunnel")
            print("   • Configure webhooks manually if needed")
    except Exception:
        pass  # Don't fail if config check fails
    
    try:
        # Start the trading bot
        await run_trading_bot()
        
    except KeyboardInterrupt:
        print("\n\n🛑 Trading Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Trading Bot error: {e}")
        print("\n💡 Troubleshooting tips:")
        print("   • Check your internet connection")
        print("   • Verify Alpaca API credentials")
        print("   • Check the logs for detailed error information")
        print("   • If using ngrok, ensure no other instance is running on port 4040")
    finally:
        # Ensure we give a final status message
        print("\n🏁 Bot shutdown complete")


if __name__ == "__main__":
    try:
        # Use asyncio.run with proper exception handling
        asyncio.run(main())
    except KeyboardInterrupt:
        # This handles the case where Ctrl+C is pressed before asyncio.run starts
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n💥 Fatal error: {e}")
        sys.exit(1)
    finally:
        # Ensure we always exit cleanly
        print("💫 Application terminated")
