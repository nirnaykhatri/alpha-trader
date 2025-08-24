#!/usr/bin/env python3
"""
Test script to verify the trailing profit manager fix.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from src.strategies.trailing_profit import ConfigurableTrailingProfitManager
    from src.core.configuration import ConfigurationManager
    
    print("✅ Successfully imported required classes")
    
    # Initialize configuration manager
    config = ConfigurationManager('config.yaml')
    print("✅ Configuration manager initialized")
    
    # Initialize trailing profit manager
    manager = ConfigurableTrailingProfitManager(config)
    print("✅ TrailingProfitManager initialized successfully")
    
    # Check if the required attributes exist
    assert hasattr(manager, '_acceleration_factor'), "Missing _acceleration_factor attribute"
    assert hasattr(manager, '_profit_steps'), "Missing _profit_steps attribute"
    
    print(f"✅ _acceleration_factor: {manager._acceleration_factor}")
    print(f"✅ _profit_steps: {manager._profit_steps}")
    
    print("\n🎉 All tests passed! The fix is working correctly.")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
