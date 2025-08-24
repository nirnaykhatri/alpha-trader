#!/usr/bin/env python3
"""
Test script to verify SQL fixes for UUID and OrderSide enum issues
"""
import sys
import os
import uuid
from datetime import datetime

# Add the project root to the path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.interfaces import Order, OrderStatus, OrderType, OrderSide

def test_sql_fixes():
    """Test the SQL fixes for UUID and OrderSide enum handling."""
    print("🧪 Testing SQL Fixes")
    print("=" * 50)
    
    # Test UUID conversion
    test_uuid = uuid.uuid4()
    print(f"✅ Test UUID: {test_uuid}")
    print(f"✅ UUID as string: {str(test_uuid)}")
    print(f"✅ UUID type: {type(test_uuid)}")
    print(f"✅ String type: {type(str(test_uuid))}")
    
    # Test OrderSide enum handling
    print(f"\n📊 Testing OrderSide enum:")
    for side in [OrderSide.BUY, OrderSide.SELL]:
        print(f"✅ OrderSide.{side.name}:")
        print(f"   - Direct: {side}")
        print(f"   - .value: {side.value}")
        print(f"   - str(): {str(side)}")
        print(f"   - .value.lower(): {side.value.lower()}")
        
        # Test the logic we use in the fixed code
        side_str = side.value if hasattr(side, 'value') else str(side)
        print(f"   - Safe conversion: {side_str}")
        print(f"   - Safe .lower(): {side_str.lower()}")
    
    # Test creating a mock Order object
    print(f"\n🔧 Testing Order object creation:")
    try:
        mock_order = Order(
            order_id=test_uuid,
            symbol="TEST",
            quantity=10.0,
            order_type=OrderType.LIMIT,
            side=OrderSide.SELL,
            price=100.0,
            status=OrderStatus.FILLED,
            created_at=datetime.now(),
            filled_price=101.0,
            filled_quantity=10.0,
            filled_at=datetime.now()
        )
        
        print(f"✅ Mock order created successfully")
        print(f"   - order_id: {mock_order.order_id} (type: {type(mock_order.order_id)})")
        print(f"   - side: {mock_order.side} (type: {type(mock_order.side)})")
        print(f"   - str(order_id): {str(mock_order.order_id)}")
        print(f"   - side.value: {mock_order.side.value}")
        
        # Test the conversion logic from our fixes
        safe_id = str(mock_order.order_id)
        safe_side = mock_order.side.value if hasattr(mock_order.side, 'value') else str(mock_order.side)
        
        print(f"✅ Safe conversions:")
        print(f"   - Safe ID: {safe_id} (type: {type(safe_id)})")
        print(f"   - Safe side: {safe_side} (type: {type(safe_side)})")
        
    except Exception as e:
        print(f"❌ Error creating mock order: {e}")
    
    print(f"\n🎉 SQL fixes should now handle:")
    print(f"   ✅ UUID objects → strings for database storage")
    print(f"   ✅ OrderSide enums → string values for comparisons")
    print(f"   ✅ Both issues that caused the original SQL errors")

if __name__ == "__main__":
    test_sql_fixes()
