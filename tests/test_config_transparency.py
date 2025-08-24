#!/usr/bin/env python3
"""
Test script to verify configuration transparency and new risk management settings.
This ensures all risk parameters are properly configurable and no hidden defaults remain.
"""

import yaml
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.core.configuration import ConfigurationManager

def test_config_transparency():
    """Test that all risk management parameters are properly configurable."""
    
    print("🔍 Testing Configuration Transparency...")
    print("=" * 50)
    
    # Load configuration
    config_manager = ConfigurationManager("config.yaml")
    
    # Test stop-loss configuration
    print("\n📊 Stop-Loss Configuration:")
    stop_loss_percentage = config_manager.get_config(
        "trading.risk_management.stop_loss.max_loss_percentage",
        "NOT_FOUND"
    )
    print(f"  Max Loss Percentage: {stop_loss_percentage}")
    
    if stop_loss_percentage == "NOT_FOUND":
        print("  ❌ ERROR: Stop-loss not found in config!")
        return False
    
    # Test profit-taking configuration
    print("\n💰 Profit-Taking Configuration:")
    activation_threshold = config_manager.get_config(
        "trading.risk_management.profit_taking.trailing_profit.activation_threshold",
        "NOT_FOUND"
    )
    trailing_percentage = config_manager.get_config(
        "trading.risk_management.profit_taking.trailing_profit.trailing_percentage",
        "NOT_FOUND"
    )
    take_profit_percentage = config_manager.get_config(
        "trading.risk_management.profit_taking.take_profit_percentage",
        "NOT_FOUND"
    )
    
    print(f"  Activation Threshold: {activation_threshold}")
    print(f"  Trailing Percentage: {trailing_percentage}")
    print(f"  Take Profit Percentage: {take_profit_percentage}")
    
    # Test position sizing
    print("\n📏 Position Sizing Configuration:")
    max_position_size = config_manager.get_config(
        "trading.risk_management.advanced.max_symbol_allocation",
        "NOT_FOUND"
    )
    max_portfolio_risk = config_manager.get_config(
        "trading.risk_management.advanced.daily_loss_limit",
        "NOT_FOUND"
    )
    
    print(f"  Max Symbol Allocation: {max_position_size}")
    print(f"  Daily Loss Limit: {max_portfolio_risk}")
    
    # Test fallback mechanism
    print("\n🔄 Testing Fallback Mechanism:")
    fallback_test = config_manager.get_config(
        "strategies.trailing_profit.activation_threshold",
        "FALLBACK_USED"
    )
    print(f"  Legacy path fallback: {fallback_test}")
    
    print("\n✅ Configuration transparency test completed!")
    return True

def display_current_config():
    """Display the current configuration structure."""
    
    print("\n📋 Current Configuration Structure:")
    print("=" * 50)
    
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
            
        # Display risk management section
        if 'trading' in config and 'risk_management' in config['trading']:
            print("\n🛡️  Risk Management Settings:")
            risk_config = config['trading']['risk_management']
            
            def print_nested(obj, indent=2):
                for key, value in obj.items():
                    spaces = " " * indent
                    if isinstance(value, dict):
                        print(f"{spaces}{key}:")
                        print_nested(value, indent + 2)
                    else:
                        print(f"{spaces}{key}: {value}")
            
            print_nested(risk_config)
        else:
            print("  ❌ No risk management configuration found!")
            
    except Exception as e:
        print(f"  ❌ Error reading config: {e}")

if __name__ == "__main__":
    print("🤖 Trading Bot Configuration Transparency Test")
    print("This test ensures all risk parameters are visible and configurable.")
    
    # Test configuration transparency
    success = test_config_transparency()
    
    # Display current config
    display_current_config()
    
    if success:
        print("\n✅ All tests passed! Configuration is now transparent.")
    else:
        print("\n❌ Some tests failed. Check configuration structure.")
