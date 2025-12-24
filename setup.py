#!/usr/bin/env python3
"""
Environment Setup Script
Helps users set up their environment and validate their configuration.
"""

import os
import sys
import subprocess
import secrets
from pathlib import Path


def print_header():
    """Print setup header."""
    print("🛠️  TRADING BOT ENVIRONMENT SETUP")
    print("=" * 50)


def check_python_version():
    """Check Python version."""
    print("🐍 Checking Python version...")
    
    version = sys.version_info
    if version.major == 3 and version.minor >= 9:
        print(f"   ✅ Python {version.major}.{version.minor}.{version.micro} (OK)")
        return True
    else:
        print(f"   ❌ Python {version.major}.{version.minor}.{version.micro} (Requires 3.9+)")
        return False


def install_dependencies():
    """Install required dependencies."""
    print("\n📦 Installing dependencies...")
    
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", "-r", "requirements.txt"
        ])
        print("   ✅ Dependencies installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Failed to install dependencies: {e}")
        return False
    except FileNotFoundError:
        print("   ❌ requirements.txt not found")
        return False


def create_directories():
    """Create necessary directories."""
    print("\n📁 Creating directories...")
    
    directories = ["data", "logs"]
    
    for directory in directories:
        path = Path(directory)
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            print(f"   ✅ Created {directory}/ directory")
        else:
            print(f"   ✅ {directory}/ directory already exists")


def generate_webhook_secret():
    """Generate a secure webhook secret."""
    print("\n🔐 Generating webhook secret...")
    
    secret = secrets.token_hex(32)
    print(f"   🔑 Generated secret: {secret}")
    print(f"   💡 Add this to config/settings.toml under api.webhook.secret")
    
    return secret


def setup_environment_file():
    """Create .env file template."""
    print("\n🌍 Setting up environment file...")
    
    env_file = Path(".env")
    
    if env_file.exists():
        print("   ✅ .env file already exists")
        return
    
    env_template = """# Trading Bot Environment Variables
# Copy this file and rename to .env, then fill in your values

# Alpaca API Credentials
# Get these from: https://app.alpaca.markets/
TRADING_BOT_ALPACA_API_KEY=
TRADING_BOT_ALPACA_SECRET_KEY=

# Webhook Security
TRADING_BOT_WEBHOOK_SECRET=

# Optional: Database URL
# TRADING_BOT_DATABASE_URL=sqlite:///data/trading_bot.db

# Optional: Logging Level
# TRADING_BOT_LOG_LEVEL=INFO
"""
    
    with open(".env.template", "w") as f:
        f.write(env_template)
    
    print("   ✅ Created .env.template file")
    print("   💡 Copy to .env and fill in your credentials")


def validate_config():
    """Validate the configuration file."""
    print("\n⚙️  Validating configuration...")
    
    config_file = Path("config/settings.toml")
    
    if not config_file.exists():
        print("   ❌ config/settings.toml not found")
        print("   💡 Make sure config/settings.toml exists")
        return False
    
    try:
        # Try to load and validate config
        sys.path.insert(0, str(Path(__file__).parent / "src"))
        from src.core import ConfigurationManager
        
        config = ConfigurationManager()
        
        # Check for required fields
        api_key = config.get_config("api.alpaca.api_key")
        secret_key = config.get_config("api.alpaca.secret_key")
        webhook_secret = config.get_config("api.webhook.secret")
        
        if not api_key:
            print("   ⚠️  Alpaca API key not set")
        else:
            print("   ✅ Alpaca API key configured")
        
        if not secret_key:
            print("   ⚠️  Alpaca secret key not set")
        else:
            print("   ✅ Alpaca secret key configured")
        
        if not webhook_secret:
            print("   ⚠️  Webhook secret not set")
        else:
            print("   ✅ Webhook secret configured")
        
        if api_key and secret_key and webhook_secret:
            print("   ✅ Configuration appears complete")
            return True
        else:
            print("   ⚠️  Configuration incomplete - see warnings above")
            return False
            
    except Exception as e:
        print(f"   ❌ Configuration error: {e}")
        return False


def show_next_steps():
    """Show next steps to user."""
    print("\n🚀 NEXT STEPS")
    print("=" * 50)
    print("1. 🔑 Get Alpaca API credentials:")
    print("   • Sign up at https://alpaca.markets/")
    print("   • Generate paper trading API keys")
    print("   • Add them to config/settings.toml or .env")
    
    print("\n2. 🔐 Set webhook secret:")
    print("   • Use the generated secret above")
    print("   • Add it to config/settings.toml under api.webhook.secret")
    
    print("\n3. 📊 Configure TradingView:")
    print("   • Create alerts with webhook notifications")
    print("   • Use URL: http://your-server:8080/webhook")
    print("   • Include your webhook secret in alerts")
    
    print("\n4. 🚀 Start the bot:")
    print("   python run_bot.py")
    
    print("\n5. 🧪 Test with examples:")
    print("   python examples.py")


def main():
    """Main setup function."""
    print_header()
    
    # Check Python version
    if not check_python_version():
        print("\n❌ Please upgrade to Python 3.9 or higher")
        return False
    
    # Install dependencies
    if not install_dependencies():
        print("\n❌ Failed to install dependencies")
        return False
    
    # Create directories
    create_directories()
    
    # Generate webhook secret
    webhook_secret = generate_webhook_secret()
    
    # Setup environment file
    setup_environment_file()
    
    # Validate configuration
    config_valid = validate_config()
    
    print("\n" + "=" * 50)
    if config_valid:
        print("✅ SETUP COMPLETE!")
        print("Your trading bot is ready to run.")
    else:
        print("⚠️  SETUP PARTIALLY COMPLETE")
        print("Please complete the configuration before running the bot.")
    
    show_next_steps()
    
    return config_valid


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⏹️  Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Setup failed: {e}")
        sys.exit(1)
