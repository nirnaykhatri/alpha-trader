#!/usr/bin/env python3
"""
Trading Bot Startup Script (Azure-First Configuration)

This script starts the trading bot with Azure environment configuration as the
single source of truth. Configuration is loaded from:
1. Azure Key Vault (secrets) - when AZURE_KEYVAULT_URL is set
2. Azure App Configuration (runtime settings) - when AZURE_APP_CONFIGURATION_ENDPOINT is set
3. Environment variables (local dev/overrides)
4. Default values from ConfigContract

NOTE: TOML files are NOT supported in production. For local development, use
environment variables. For testing, see tests/fixtures/ for mock configurations.
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
from src.validation import StartupValidationService


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


def check_environment_config():
    """
    Check if required environment variables are configured.
    
    Azure-First Configuration Strategy:
    - Production: Azure Key Vault + App Configuration
    - Local Dev: Environment variables (from .env or shell)
    
    Returns:
        bool: True if minimum required config is present, False otherwise.
    """
    # Check for Azure configuration (production)
    azure_keyvault = os.getenv("AZURE_KEYVAULT_URL")
    azure_app_config = os.getenv("AZURE_APP_CONFIGURATION_ENDPOINT")
    
    # Check for direct environment variables (local dev)
    alpaca_key = os.getenv("ALPACA_API_KEY")
    alpaca_secret = os.getenv("ALPACA_API_SECRET")
    
    has_azure = azure_keyvault or azure_app_config
    has_direct = alpaca_key and alpaca_secret
    
    if has_azure:
        print("✅ Azure configuration detected:")
        if azure_keyvault:
            print(f"   • Key Vault: {azure_keyvault[:50]}...")
        if azure_app_config:
            print(f"   • App Config: {azure_app_config[:50]}...")
        return True
    
    if has_direct:
        print("✅ Direct environment configuration detected:")
        print("   • ALPACA_API_KEY: [configured]")
        print("   • ALPACA_API_SECRET: [configured]")
        return True
    
    # No configuration found
    print("❌ No configuration found!")
    print("\n🔧 Configuration Options:")
    print("\n  Option 1: Azure (Recommended for Production)")
    print("  ─────────────────────────────────────────────")
    print("    Set these environment variables:")
    print("    • AZURE_KEYVAULT_URL=https://your-keyvault.vault.azure.net/")
    print("    • AZURE_APP_CONFIGURATION_ENDPOINT=https://your-config.azconfig.io")
    print("")
    print("  Option 2: Environment Variables (Local Development)")
    print("  ────────────────────────────────────────────────────")
    print("    Set these environment variables:")
    print("    • ALPACA_API_KEY=your_api_key")
    print("    • ALPACA_API_SECRET=your_api_secret")
    print("    • ALPACA_BASE_URL=https://paper-api.alpaca.markets")
    print("    • AZURE_COSMOS_ENDPOINT=https://your-cosmos.documents.azure.com:443/")
    print("    • AZURE_COSMOS_KEY=your_cosmos_key")
    print("    • AZURE_COSMOS_DATABASE=your_database_name")
    print("")
    print("  📄 Copy config/.env.example to .env and source it:")
    print("     Windows: copy config\\.env.example .env && set /p < .env")
    print("     Linux/Mac: cp config/.env.example .env && source .env")
    return False


def validate_config():
    """Validate configuration using centralized startup validation service."""
    try:
        # Use centralized validation service (uses env/Azure config)
        validator = StartupValidationService()
        result = validator.validate(verbose=True)
        
        # Return validation result
        return result.passed
        
    except Exception as e:
        print(f"❌ Unexpected error validating config: {e}")
        import traceback
        traceback.print_exc()
        return False


def show_quick_start_guide():
    """Show quick start guide for new users (Azure-first)."""
    print("\n📚 Quick Start Guide (Azure-First Configuration):")
    print("=" * 55)
    
    print("\n1. 🔑 Get Alpaca API Credentials:")
    print("   • Sign up at: https://alpaca.markets/")
    print("   • Generate paper trading API keys")
    print("   • Set environment variables:")
    print("     export ALPACA_API_KEY=your_key")
    print("     export ALPACA_API_SECRET=your_secret")
    
    print("\n2. 🗄️ Configure Azure Cosmos DB:")
    print("   • Create a Cosmos DB account in Azure")
    print("   • Set environment variables:")
    print("     export AZURE_COSMOS_ENDPOINT=https://your-account.documents.azure.com:443/")
    print("     export AZURE_COSMOS_KEY=your_key")
    print("     export AZURE_COSMOS_DATABASE=trading-bot")
    
    print("\n3. 🔐 Generate Webhook Secret:")
    print("   • Run: openssl rand -hex 32")
    print("   • Set: export WEBHOOK_SECRET=your_secret")
    
    print("\n4. 🌐 Production Configuration (Azure):")
    print("   • Store secrets in Azure Key Vault")
    print("   • Store runtime config in Azure App Configuration")
    print("   • Set AZURE_KEYVAULT_URL and AZURE_APP_CONFIGURATION_ENDPOINT")
    
    print("\n5. 📊 TradingView Setup:")
    print("   • Create alerts in TradingView")
    print("   • Use the webhook URL displayed when bot starts")
    print("   • Include timeframe data for better support calculations")
    
    print("\n6. 🎯 Signal Format:")
    print("   Your TradingView alerts should send JSON like:")
    print("   {")
    print('     "symbol": "{{ticker}}",')
    print('     "action": "{{strategy.order.action}}",')
    print('     "price": {{close}},')
    print('     "quantity": 100,')
    print('     "timeframe": "{{interval}}"')
    print("   }")
    
    print("\n7. 🌍 Environment Switching:")
    print("   • Demo (paper trading): TRADING_BOT_ENV=demo (default)")
    print("   • Live (real money):    TRADING_BOT_ENV=live")
    
    print("\n8. 🚀 Start Trading:")
    print("   • Run: python run_bot.py")
    print("   • Monitor logs for signal processing")
    print("   • Check your Alpaca account for trades")
    
    print("\n💡 Pro Tips:")
    print("   • Use paper trading first (TRADING_BOT_ENV=demo)")
    print("   • Use .env file for local development")
    print("   • Deploy to Azure Container Apps for production")
    print("   • Monitor webhook traffic at http://localhost:4040 (if ngrok enabled)")


async def main():
    """Main startup function."""
    print_banner()
    
    # Check for environment configuration (Azure-first)
    if not check_environment_config():
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
            print("\n🏠 Local Mode (ngrok disabled):")
            print("   • Running without webhook tunnel")
            print("   • Set NGROK_ENABLED=true to enable")
    except Exception:
        pass  # Don't fail if config check fails
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
