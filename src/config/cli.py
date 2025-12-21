"""
Trading Bot Configuration CLI.

Commands:
    init        Copy template files to get started
    status      Show current configuration status
    validate    Validate configuration files
    switch      Switch between demo and live environments
    show-brokers Show configured brokers and their status

Usage:
    python -m src.config.cli init
    python -m src.config.cli status
    python -m src.config.cli validate
    python -m src.config.cli switch demo
    python -m src.config.cli switch live
    python -m src.config.cli show-brokers
"""

import argparse
import shutil
import sys
from pathlib import Path

from src.config.settings import (
    CONFIG_DIR,
    SETTINGS_FILE,
    SECRETS_FILE,
    ENVIRONMENTS_DIR,
    PROFILES_DIR,
    VALID_ENVIRONMENTS,
    VALID_RISK_PROFILES,
    ConfigurationManager,
    validate_startup,
    _get_environment,
)


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize configuration by copying template files."""
    print("Initializing configuration...\n")
    
    # Create directories
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    ENVIRONMENTS_DIR.mkdir(parents=True, exist_ok=True)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check what already exists
    existing = []
    missing = []
    
    files_to_check = [
        (SETTINGS_FILE, "settings.toml"),
        (SECRETS_FILE, ".secrets.toml"),
        (ENVIRONMENTS_DIR / "demo.toml", "environments/demo.toml"),
        (ENVIRONMENTS_DIR / "live.toml", "environments/live.toml"),
        (PROFILES_DIR / "conservative.toml", "profiles/conservative.toml"),
        (PROFILES_DIR / "moderate.toml", "profiles/moderate.toml"),
        (PROFILES_DIR / "aggressive.toml", "profiles/aggressive.toml"),
    ]
    
    for path, name in files_to_check:
        if path.exists():
            existing.append(name)
        else:
            missing.append((path, name))
    
    if existing:
        print("✓ Already exist:")
        for name in existing:
            print(f"    {name}")
    
    # Copy secrets template if secrets file doesn't exist
    secrets_template = CONFIG_DIR / ".secrets.toml.example"
    if not SECRETS_FILE.exists() and secrets_template.exists():
        shutil.copy(secrets_template, SECRETS_FILE)
        print(f"\n✓ Created {SECRETS_FILE.relative_to(CONFIG_DIR.parent)}")
        print("  → Edit this file to add your API credentials")
    elif not SECRETS_FILE.exists():
        print(f"\n⚠ Missing secrets template: {secrets_template}")
        print("  Run configuration setup to create template files")
    
    # Summary
    print("\n" + "="*50)
    print("Configuration Status")
    print("="*50)
    
    if SECRETS_FILE.exists():
        print(f"✓ Secrets file: {SECRETS_FILE.relative_to(CONFIG_DIR.parent)}")
    else:
        print(f"✗ Secrets file missing")
    
    print(f"\nNext steps:")
    print(f"  1. Edit config/.secrets.toml with your API credentials")
    print(f"  2. Run: trading-config validate")
    print(f"  3. Run: python run_bot.py")
    
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show current configuration status."""
    print("="*60)
    print("Trading Bot Configuration Status")
    print("="*60)
    
    # Environment
    env = _get_environment()
    print(f"\n📌 Environment: {env.upper()}")
    print(f"   Set TRADING_BOT_ENV to change (demo|live)")
    
    # Files
    print(f"\n📁 Configuration Files:")
    files = [
        (SETTINGS_FILE, "settings.toml", True),
        (SECRETS_FILE, ".secrets.toml", True),
        (ENVIRONMENTS_DIR / f"{env}.toml", f"environments/{env}.toml", False),
    ]
    
    for path, name, required in files:
        status = "✓" if path.exists() else ("✗ MISSING" if required else "○ optional")
        print(f"   {status} config/{name}")
    
    # Risk profiles
    print(f"\n📊 Risk Profiles:")
    for profile in VALID_RISK_PROFILES:
        path = PROFILES_DIR / f"{profile}.toml"
        status = "✓" if path.exists() else "○"
        print(f"   {status} {profile}")
    
    # Brokers (only if config is valid)
    try:
        config = ConfigurationManager()
        
        print(f"\n🏦 Brokers:")
        
        alpaca = config.get_alpaca_config()
        if alpaca.is_configured:
            mode = "PAPER" if alpaca.is_paper else "LIVE"
            print(f"   ✓ Alpaca ({mode})")
        else:
            print(f"   ○ Alpaca (not configured)")
        
        tastytrade = config.get_tastytrade_config()
        if tastytrade.is_configured:
            mode = "SANDBOX" if tastytrade.is_sandbox else "LIVE"
            print(f"   ✓ Tastytrade ({mode})")
        else:
            print(f"   ○ Tastytrade (not configured)")
        
        # Default broker
        configured = config.get_configured_brokers()
        if configured:
            default_broker = config.get_broker_for_symbol("_default")
            print(f"\n   Default broker: {default_broker}")
        
    except Exception as e:
        print(f"\n⚠ Could not load configuration: {e}")
    
    print()
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate configuration files."""
    print("Validating configuration...\n")
    
    issues = validate_startup()
    
    errors = [i for i in issues if i.severity == "ERROR"]
    warnings = [i for i in issues if i.severity == "WARN"]
    infos = [i for i in issues if i.severity == "INFO"]
    
    # Display issues
    for issue in infos:
        print(f"ℹ️  {issue}")
    
    for issue in warnings:
        print(f"⚠️  {issue}")
    
    for issue in errors:
        print(f"❌ {issue}")
    
    # Summary
    print()
    if errors:
        print(f"Validation FAILED with {len(errors)} error(s)")
        return 1
    elif warnings:
        print(f"Validation PASSED with {len(warnings)} warning(s)")
        return 0
    else:
        print("✅ Validation PASSED")
        return 0


def cmd_switch(args: argparse.Namespace) -> int:
    """Switch between environments."""
    target_env = args.environment.lower()
    
    if target_env not in VALID_ENVIRONMENTS:
        print(f"❌ Invalid environment: {target_env}")
        print(f"   Valid environments: {VALID_ENVIRONMENTS}")
        return 1
    
    current_env = _get_environment()
    
    if current_env == target_env:
        print(f"Already using {target_env} environment")
        return 0
    
    print(f"To switch from {current_env} to {target_env}:")
    print()
    print("  PowerShell:")
    print(f'    $env:TRADING_BOT_ENV = "{target_env}"')
    print()
    print("  Command Prompt:")
    print(f'    set TRADING_BOT_ENV={target_env}')
    print()
    print("  Bash/Zsh:")
    print(f'    export TRADING_BOT_ENV={target_env}')
    print()
    
    if target_env == "live":
        print("⚠️  WARNING: Live mode uses real money!")
        print("   Ensure your credentials point to production APIs.")
    
    return 0


def cmd_show_brokers(args: argparse.Namespace) -> int:
    """Show broker configuration status."""
    print("="*60)
    print("Broker Configuration")
    print("="*60)
    
    try:
        config = ConfigurationManager()
        
        # Alpaca
        print("\n🔸 Alpaca")
        alpaca = config.get_alpaca_config()
        if alpaca.is_configured:
            print(f"   Status: ✓ Configured")
            print(f"   Mode: {'PAPER' if alpaca.is_paper else 'LIVE'}")
            print(f"   API Key: {alpaca.api_key[:8]}..." if len(alpaca.api_key) > 8 else f"   API Key: {alpaca.api_key}")
            print(f"   Base URL: {alpaca.base_url}")
        else:
            print(f"   Status: ○ Not configured")
            if alpaca.api_key or alpaca.secret_key:
                print(f"   ⚠ Partially configured - missing fields")
        
        # Tastytrade
        print("\n🔸 Tastytrade")
        tastytrade = config.get_tastytrade_config()
        if tastytrade.is_configured:
            print(f"   Status: ✓ Configured")
            print(f"   Mode: {'SANDBOX' if tastytrade.is_sandbox else 'LIVE'}")
            print(f"   Username: {tastytrade.username}")
            print(f"   Account ID: {tastytrade.account_id}")
        else:
            print(f"   Status: ○ Not configured")
            if tastytrade.username or tastytrade.password or tastytrade.account_id:
                print(f"   ⚠ Partially configured - missing fields")
        
        # Symbol routing
        configured = config.get_configured_brokers()
        if configured:
            print("\n🔸 Symbol Routing")
            default_broker = config.get_broker_for_symbol("_default")
            print(f"   Default: {default_broker}")
            
            # Check for symbol-specific routing
            symbols_config = config.get_config("symbols", {})
            custom_routing = []
            if isinstance(symbols_config, dict):
                for symbol, sym_config in symbols_config.items():
                    if symbol in ("_default", "whitelist_enabled", "default_symbols"):
                        continue
                    broker = (
                        sym_config.get("broker")
                        if isinstance(sym_config, dict)
                        else getattr(sym_config, "broker", None)
                    )
                    if broker:
                        custom_routing.append((symbol, broker))
            
            if custom_routing:
                print("   Custom routing:")
                for symbol, broker in custom_routing:
                    print(f"     {symbol} → {broker}")
        
    except Exception as e:
        print(f"\n❌ Error loading configuration: {e}")
        return 1
    
    print()
    return 0


def main() -> int:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        prog="trading-config",
        description="Trading Bot Configuration Management",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # init command
    subparsers.add_parser("init", help="Initialize configuration files")
    
    # status command
    subparsers.add_parser("status", help="Show configuration status")
    
    # validate command
    subparsers.add_parser("validate", help="Validate configuration")
    
    # switch command
    switch_parser = subparsers.add_parser("switch", help="Switch environment")
    switch_parser.add_argument(
        "environment",
        choices=VALID_ENVIRONMENTS,
        help="Target environment (demo or live)"
    )
    
    # show-brokers command
    subparsers.add_parser("show-brokers", help="Show broker configuration")
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 0
    
    commands = {
        "init": cmd_init,
        "status": cmd_status,
        "validate": cmd_validate,
        "switch": cmd_switch,
        "show-brokers": cmd_show_brokers,
    }
    
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
