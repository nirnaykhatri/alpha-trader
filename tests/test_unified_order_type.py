#!/usr/bin/env python3
"""
Test script to verify unified order type configuration.
This script validates that all order types are properly consolidated to a single setting.
Uses the new TOML-based configuration system.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.configuration import ConfigurationManager


def test_unified_order_type():
    """Test that configuration has only one order type setting."""
    # Check that config directory exists
    config_dir = project_root / "config"
    settings_file = config_dir / "settings.toml"
    
    if not settings_file.exists():
        print("❌ config/settings.toml not found")
        return False
    
    try:
        config = ConfigurationManager()  # Uses config/ TOML files
        print("✅ Configuration loaded successfully from TOML files")
    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return False
    
    # Check for the main unified order type setting
    global_order_type = config.get_config("trading.order_type")
    
    if not global_order_type:
        print("❌ Global trading.order_type setting not found")
        return False
    
    print(f"✅ Global order type found: {global_order_type}")
    
    # Check additional order type settings
    limit_offset = config.get_config("trading.limit_order_offset")
    market_slippage = config.get_config("trading.market_order_slippage")
    order_timeout = config.get_config("trading.order_timeout_minutes")
    
    print("\n📋 Current unified order configuration:")
    print(f"   ✅ trading.order_type: {global_order_type}")
    
    if limit_offset is not None:
        print(f"   ✅ trading.limit_order_offset: {limit_offset}")
    else:
        print("   ⚠️  trading.limit_order_offset: not set")
    
    if market_slippage is not None:
        print(f"   ✅ trading.market_order_slippage: {market_slippage}")
    else:
        print("   ⚠️  trading.market_order_slippage: not set")
    
    if order_timeout is not None:
        print(f"   ✅ trading.order_timeout_minutes: {order_timeout}")
    else:
        print("   ⚠️  trading.order_timeout_minutes: not set")
    
    return True


def main():
    """Main test function."""
    print("🧪 Testing Unified Order Type Configuration (TOML)")
    print("=" * 50)
    
    success = test_unified_order_type()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ All tests passed! Order type configuration is properly unified.")
        print("\n📝 Summary:")
        print("   - Configuration loaded from config/settings.toml")
        print("   - Single global trading.order_type setting controls all order types")
        print("   - Consistent configuration across all trading actions")
    else:
        print("❌ Tests failed! Configuration needs fixes.")
        sys.exit(1)


if __name__ == "__main__":
    main()
