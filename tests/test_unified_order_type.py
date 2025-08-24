#!/usr/bin/env python3
"""
Test script to verify unified order type configuration.
This script validates that all order types are properly consolidated to a single setting.
"""

import yaml
import sys
from pathlib import Path

def test_unified_order_type():
    """Test that configuration has only one order type setting."""
    config_path = Path(__file__).parent.parent / "config.yaml"  # Go up one level to workspace root
    
    if not config_path.exists():
        print("❌ config.yaml not found")
        return False
    
    try:
        with open(config_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        print("✅ Configuration loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load config: {e}")
        return False
    
    # Check for the main unified order type setting
    trading_config = config.get('trading', {})
    global_order_type = trading_config.get('order_type')
    
    if not global_order_type:
        print("❌ Global trading.order_type setting not found")
        return False
    
    print(f"✅ Global order type found: {global_order_type}")
    
    # Check that no old per-strategy order types exist
    old_order_type_keys = [
        'entry_order_type',
        'exit_order_type', 
        'averaging_order_type',
        'profit_exit_order_type',
        'stop_loss_order_type'
    ]
    
    issues = []
    
    # Check trading section
    for key in old_order_type_keys:
        if key in trading_config:
            issues.append(f"trading.{key}")
    
    # Check strategy sections
    strategies = config.get('strategies', {})
    for strategy_name, strategy_config in strategies.items():
        if not isinstance(strategy_config, dict):
            continue
            
        for key in old_order_type_keys:
            if key in strategy_config:
                issues.append(f"strategies.{strategy_name}.{key}")
        
        # Check nested sections in strategies
        for section_name, section_config in strategy_config.items():
            if isinstance(section_config, dict):
                for key in old_order_type_keys:
                    if key in section_config:
                        issues.append(f"strategies.{strategy_name}.{section_name}.{key}")
                
                # Check deeper nested sections
                for subsection_name, subsection_config in section_config.items():
                    if isinstance(subsection_config, dict):
                        for key in old_order_type_keys:
                            if key in subsection_config:
                                issues.append(f"strategies.{strategy_name}.{section_name}.{subsection_name}.{key}")
    
    if issues:
        print("❌ Found legacy order type settings:")
        for issue in issues:
            print(f"   - {issue}")
        return False
    
    print("✅ No legacy order type settings found")
    
    # Verify required configuration structure
    expected_structure = {
        'trading.order_type': global_order_type,
        'trading.limit_order_offset': trading_config.get('limit_order_offset'),
        'trading.market_order_slippage': trading_config.get('market_order_slippage'),
        'trading.order_timeout_minutes': trading_config.get('order_timeout_minutes')
    }
    
    print("\n📋 Current unified order configuration:")
    for key, value in expected_structure.items():
        if value is not None:
            print(f"   ✅ {key}: {value}")
        else:
            print(f"   ⚠️  {key}: not set")
    
    # Check for proper documentation comments
    with open(config_path, 'r', encoding='utf-8') as file:
        content = file.read()
    
    unified_comment_found = "applies to ALL trading actions" in content
    if unified_comment_found:
        print("✅ Found documentation comment about unified order type")
    else:
        print("⚠️  Documentation comment about unified order type not found")
    
    return True

def main():
    """Main test function."""
    print("🧪 Testing Unified Order Type Configuration")
    print("=" * 50)
    
    success = test_unified_order_type()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ All tests passed! Order type configuration is properly unified.")
        print("\n📝 Summary:")
        print("   - Single global trading.order_type setting controls all order types")
        print("   - No legacy per-strategy order type settings found")
        print("   - Consistent configuration across all trading actions")
    else:
        print("❌ Tests failed! Configuration needs fixes.")
        sys.exit(1)

if __name__ == "__main__":
    main()
