"""
Trading Bot Configuration CLI.

Commands for managing Azure-native configuration:
    status      Show current configuration status
    validate    Validate configuration (Azure or environment variables)
    show-brokers Show configured brokers and their status
    check-azure  Check Azure connectivity and configuration

Usage:
    python -m src.config.cli status
    python -m src.config.cli validate
    python -m src.config.cli show-brokers
    python -m src.config.cli check-azure
"""

import argparse
import asyncio
import os
import sys
from typing import List, Tuple

from src.core import ConfigurationManager
from src.config.azure_config_provider import (
    AzureConfigProvider,
    ConfigKeys,
    SecretKeys,
)


# Valid environments for the trading bot
VALID_ENVIRONMENTS = ("demo", "live")


def _get_environment() -> str:
    """Get current environment from ENVIRONMENT variable."""
    return os.environ.get("ENVIRONMENT", "demo").lower()


def cmd_status(args: argparse.Namespace) -> int:
    """Show current configuration status."""
    print("=" * 60)
    print("Trading Bot Configuration Status")
    print("=" * 60)
    
    # Environment
    env = _get_environment()
    print(f"\n📌 Environment: {env.upper()}")
    print(f"   Set ENVIRONMENT to change (demo|live)")
    
    # Configuration Source
    config = ConfigurationManager()
    is_azure = config.is_azure_deployment()
    
    print(f"\n📁 Configuration Source:")
    if is_azure:
        print("   ✓ Azure Key Vault + App Configuration")
        keyvault_url = os.environ.get("AZURE_KEYVAULT_URL", "Not set")
        appconfig_url = os.environ.get("AZURE_APP_CONFIGURATION_ENDPOINT", "Not set")
        print(f"   Key Vault: {keyvault_url[:50]}..." if len(keyvault_url) > 50 else f"   Key Vault: {keyvault_url}")
        print(f"   App Config: {appconfig_url[:50]}..." if len(appconfig_url) > 50 else f"   App Config: {appconfig_url}")
    else:
        print("   ○ Environment Variables (local development)")
        print("   Set AZURE_KEYVAULT_URL or AZURE_APP_CONFIGURATION_ENDPOINT to use Azure")
    
    # Database
    print(f"\n💾 Database:")
    db_config = config.get_database_config()
    if db_config.url:
        # Mask sensitive parts of connection string
        masked_url = db_config.url
        if "@" in masked_url:
            parts = masked_url.split("@")
            masked_url = parts[0].rsplit(":", 1)[0] + ":***@" + parts[-1]
        print(f"   ✓ Configured: {masked_url[:60]}...")
    else:
        print("   ○ Not configured (using default SQLite)")
    
    # Logging
    print(f"\n📝 Logging:")
    log_config = config.get_logging_config()
    print(f"   Level: {log_config.level}")
    print(f"   Format: {log_config.format}")
    
    # Brokers summary
    print(f"\n🏦 Brokers:")
    configured = config.get_configured_brokers()
    if configured:
        for broker in configured:
            print(f"   ✓ {broker}")
        default_broker = config.get_broker_for_symbol("_default")
        print(f"\n   Default broker: {default_broker}")
    else:
        print("   ○ No brokers configured")
    
    print()
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate configuration."""
    print("Validating configuration...\n")
    
    issues: List[Tuple[str, str]] = []  # (severity, message)
    
    config = ConfigurationManager()
    
    # Check database
    db_config = config.get_database_config()
    if not db_config.url:
        issues.append(("WARN", "DATABASE_URL not set, using default SQLite"))
    
    # Check brokers
    alpaca = config.get_alpaca_config()
    tastytrade = config.get_tastytrade_config()
    
    if not alpaca.is_configured and not tastytrade.is_configured:
        issues.append(("ERROR", "No broker configured - at least one broker is required"))
    
    if alpaca.api_key and not alpaca.secret_key:
        issues.append(("ERROR", "Alpaca API key set but secret key missing"))
    elif alpaca.secret_key and not alpaca.api_key:
        issues.append(("ERROR", "Alpaca secret key set but API key missing"))
    
    if alpaca.is_configured:
        if alpaca.is_paper:
            issues.append(("INFO", "Alpaca configured in PAPER mode"))
        else:
            issues.append(("WARN", "Alpaca configured in LIVE mode - real money trades!"))
    
    if tastytrade.username and not tastytrade.password:
        issues.append(("ERROR", "Tastytrade username set but password missing"))
    
    if tastytrade.is_configured:
        if tastytrade.is_sandbox:
            issues.append(("INFO", "Tastytrade configured in SANDBOX mode"))
        else:
            issues.append(("WARN", "Tastytrade configured in LIVE mode - real money trades!"))
    
    # Check webhook security
    webhook = config.get_webhook_config()
    if webhook.security_enabled and not webhook.secret:
        issues.append(("WARN", "Webhook security enabled but no secret set"))
    
    # Check Azure configuration if Azure deployment
    if config.is_azure_deployment():
        keyvault_url = os.environ.get("AZURE_KEYVAULT_URL")
        appconfig_url = os.environ.get("AZURE_APP_CONFIGURATION_ENDPOINT")
        
        if not keyvault_url:
            issues.append(("WARN", "AZURE_KEYVAULT_URL not set - secrets from environment variables"))
        if not appconfig_url:
            issues.append(("WARN", "AZURE_APP_CONFIGURATION_ENDPOINT not set - config from environment variables"))
    
    # Display issues
    errors = [i for i in issues if i[0] == "ERROR"]
    warnings = [i for i in issues if i[0] == "WARN"]
    infos = [i for i in issues if i[0] == "INFO"]
    
    for severity, message in infos:
        print(f"ℹ️  {message}")
    
    for severity, message in warnings:
        print(f"⚠️  {message}")
    
    for severity, message in errors:
        print(f"❌ {message}")
    
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
    print(f'    $env:ENVIRONMENT = "{target_env}"')
    print()
    print("  Command Prompt:")
    print(f'    set ENVIRONMENT={target_env}')
    print()
    print("  Bash/Zsh:")
    print(f'    export ENVIRONMENT={target_env}')
    print()
    print("  Azure App Service (in Azure Portal):")
    print(f'    Configuration → Application settings → ENVIRONMENT = {target_env}')
    print()
    
    if target_env == "live":
        print("⚠️  WARNING: Live mode uses real money!")
        print("   Ensure your credentials point to production APIs.")
    
    return 0


def cmd_show_brokers(args: argparse.Namespace) -> int:
    """Show broker configuration status."""
    print("=" * 60)
    print("Broker Configuration")
    print("=" * 60)
    
    config = ConfigurationManager()
    
    # Alpaca
    print("\n🔸 Alpaca")
    alpaca = config.get_alpaca_config()
    if alpaca.is_configured:
        print(f"   Status: ✓ Configured")
        print(f"   Mode: {'PAPER' if alpaca.is_paper else 'LIVE'}")
        masked_key = alpaca.api_key[:8] + "..." if len(alpaca.api_key) > 8 else alpaca.api_key
        print(f"   API Key: {masked_key}")
        print(f"   Base URL: {alpaca.base_url}")
    else:
        print(f"   Status: ○ Not configured")
        if alpaca.api_key or alpaca.secret_key:
            print(f"   ⚠ Partially configured - missing fields")
        print(f"   Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables")
    
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
        print(f"   Set TASTYTRADE_USERNAME, TASTYTRADE_PASSWORD, TASTYTRADE_ACCOUNT_ID")
    
    # Symbol routing
    configured = config.get_configured_brokers()
    if configured:
        print("\n🔸 Symbol Routing")
        default_broker = config.get_broker_for_symbol("_default")
        print(f"   Default: {default_broker}")
    
    print()
    return 0


async def _check_azure_connectivity() -> List[Tuple[str, str]]:
    """Check Azure connectivity asynchronously."""
    issues: List[Tuple[str, str]] = []
    
    keyvault_url = os.environ.get("AZURE_KEYVAULT_URL")
    appconfig_url = os.environ.get("AZURE_APP_CONFIGURATION_ENDPOINT")
    
    if not keyvault_url and not appconfig_url:
        issues.append(("INFO", "No Azure configuration set - using environment variables"))
        return issues
    
    try:
        provider = AzureConfigProvider()
        await provider.initialize()
        
        # Try to read a test value
        if keyvault_url:
            issues.append(("OK", f"Connected to Key Vault: {keyvault_url}"))
        
        if appconfig_url:
            issues.append(("OK", f"Connected to App Configuration: {appconfig_url}"))
        
    except Exception as e:
        issues.append(("ERROR", f"Azure connectivity failed: {str(e)}"))
    
    return issues


def cmd_check_azure(args: argparse.Namespace) -> int:
    """Check Azure connectivity and configuration."""
    print("=" * 60)
    print("Azure Configuration Check")
    print("=" * 60)
    
    # Environment variables
    print("\n📋 Environment Variables:")
    azure_vars = [
        "AZURE_KEYVAULT_URL",
        "AZURE_APP_CONFIGURATION_ENDPOINT",
        "AZURE_CLIENT_ID",
        "AZURE_TENANT_ID",
        "MSI_ENDPOINT",  # Managed Identity indicator
        "IDENTITY_ENDPOINT",  # Managed Identity indicator
    ]
    
    for var in azure_vars:
        value = os.environ.get(var)
        if value:
            masked = value[:30] + "..." if len(value) > 30 else value
            print(f"   ✓ {var}: {masked}")
        else:
            print(f"   ○ {var}: Not set")
    
    # Authentication method detection
    print("\n🔐 Authentication:")
    if os.environ.get("MSI_ENDPOINT") or os.environ.get("IDENTITY_ENDPOINT"):
        print("   ✓ Managed Identity detected")
    elif os.environ.get("AZURE_CLIENT_ID") and os.environ.get("AZURE_TENANT_ID"):
        print("   ✓ Service Principal credentials detected")
    elif os.environ.get("AZURE_CLIENT_ID"):
        print("   ○ Only AZURE_CLIENT_ID set - may need AZURE_TENANT_ID")
    else:
        print("   ○ No explicit credentials - DefaultAzureCredential will try multiple methods")
    
    # Connectivity check
    print("\n🔗 Connectivity Test:")
    
    config = ConfigurationManager()
    if not config.is_azure_deployment():
        print("   ℹ️ Not an Azure deployment - skipping connectivity test")
        print("   Set AZURE_KEYVAULT_URL or AZURE_APP_CONFIGURATION_ENDPOINT to enable")
        return 0
    
    try:
        issues = asyncio.run(_check_azure_connectivity())
        
        for severity, message in issues:
            if severity == "OK":
                print(f"   ✓ {message}")
            elif severity == "ERROR":
                print(f"   ❌ {message}")
            else:
                print(f"   ℹ️ {message}")
        
        if any(i[0] == "ERROR" for i in issues):
            return 1
        
    except Exception as e:
        print(f"   ❌ Connectivity test failed: {e}")
        return 1
    
    print()
    return 0


def main() -> int:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        prog="trading-config",
        description="Trading Bot Configuration Management (Azure-native)",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
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
    
    # check-azure command
    subparsers.add_parser("check-azure", help="Check Azure connectivity")
    
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 0
    
    commands = {
        "status": cmd_status,
        "validate": cmd_validate,
        "switch": cmd_switch,
        "show-brokers": cmd_show_brokers,
        "check-azure": cmd_check_azure,
    }
    
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
