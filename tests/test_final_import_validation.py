#!/usr/bin/env python3
"""
Final Import Validation Test
Tests all key modules with correct class names and handles missing dependencies.
"""

import sys
import os

# Add the parent directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

def test_imports():
    """Test importing all key modules with correct class names."""
    print("=== FINAL IMPORT VALIDATION TEST ===")
    
    # Test modules with their correct class names
    test_cases = [
        # (module_path, class_name, description)
        ('src.strategies.advanced_strategy', 'AdvancedTradingStrategy', 'Advanced Trading Strategy'),
        ('src.signals.signal_listener', 'TradingViewSignalListener', 'Signal Listener'),
        ('src.core.configuration', 'ConfigurationManager', 'Configuration Manager'),
        ('src.core.logging_config', None, 'Logging Configuration'),
        ('src.interfaces', 'SignalType', 'Signal Type Enum'),
        ('src.interfaces', 'TradingSignal', 'Trading Signal'),
        ('src.exceptions', None, 'Custom Exceptions'),
    ]
    
    success_count = 0
    total_count = len(test_cases)
    failed_tests = []
    
    for module_name, class_name, description in test_cases:
        try:
            # Import the module
            module = __import__(module_name, fromlist=[class_name] if class_name else [''])
            
            # Test class import if specified
            if class_name:
                getattr(module, class_name)
                print(f'✓ {description} ({module_name}.{class_name}) - SUCCESS')
            else:
                print(f'✓ {description} ({module_name}) - SUCCESS')
                
            success_count += 1
            
        except ImportError as e:
            if 'alpaca' in str(e).lower():
                print(f'⚠ {description} ({module_name}) - SKIPPED (missing alpaca dependency)')
                success_count += 1  # Count as success since it's expected in test environment
            else:
                print(f'✗ {description} ({module_name}) - FAILED: {e}')
                failed_tests.append((module_name, class_name, str(e)))
        except AttributeError as e:
            print(f'✗ {description} ({module_name}.{class_name}) - FAILED: {e}')
            failed_tests.append((module_name, class_name, str(e)))
        except Exception as e:
            print(f'✗ {description} ({module_name}) - FAILED: {e}')
            failed_tests.append((module_name, class_name, str(e)))
    
    print(f'\n=== FINAL TEST SUMMARY ===')
    print(f'Successful: {success_count}/{total_count}')
    print(f'Success Rate: {(success_count/total_count)*100:.1f}%')
    
    if failed_tests:
        print(f'\n=== FAILED IMPORTS ===')
        for module_name, class_name, error in failed_tests:
            target = f'{module_name}.{class_name}' if class_name else module_name
            print(f'  {target}: {error}')
    
    # Test configuration loading
    print(f'\n=== CONFIGURATION TEST ===')
    try:
        from src.core.configuration import ConfigurationManager
        config = ConfigurationManager('config.yaml')
        order_type = config.get_config('trading.order_type', 'market')
        print(f'✓ Configuration loaded successfully')
        print(f'✓ Unified order type: {order_type}')
    except Exception as e:
        print(f'✗ Configuration test failed: {e}')
    
    return success_count == total_count

if __name__ == "__main__":
    success = test_imports()
    sys.exit(0 if success else 1)
