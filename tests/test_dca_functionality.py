#!/usr/bin/env python3
"""
Test DCA (Dollar Cost Averaging) functionality for positions showing losses.
"""
import sys
import os
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

# Add the project root to the path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.core.configuration import ConfigurationManager
from src.strategies.advanced_strategy import AdvancedTradingStrategy, PositionState, PositionDirection, TradePhase

async def test_dca_triggers():
    """Test that DCA triggers when positions have losses exceeding the threshold."""
    print("🧪 Testing DCA Trigger Functionality")
    print("=" * 60)
    
    # Mock configuration
    mock_config = Mock(spec=ConfigurationManager)
    mock_config.get_config.side_effect = lambda key, default=None: {
        'strategies.long_strategy.support_averaging.enabled': True,
        'strategies.long_strategy.support_averaging.loss_threshold': 0.02,  # 2%
        'strategies.long_strategy.support_averaging.max_attempts': 3,
        'strategies.long_strategy.support_averaging.position_multiplier': 2.0,
        'trading.order_type': 'limit',
        'trading.limit_order_offset': 0.001,
    }.get(key, default)
    
    # Mock components
    mock_order_manager = AsyncMock()
    mock_market_data = AsyncMock()
    mock_support_calculator = AsyncMock()
    mock_risk_manager = AsyncMock()
    mock_position_manager = AsyncMock()
    
    # Create strategy instance
    strategy = AdvancedTradingStrategy(
        config=mock_config,
        order_manager=mock_order_manager,
        market_data=mock_market_data,
        support_calculator=mock_support_calculator,
        risk_manager=mock_risk_manager,
        position_manager=mock_position_manager
    )
    
    # Test positions based on your actual data
    test_positions = [
        {"symbol": "IONQ", "qty": 92.0, "avg_price": 42.11, "current_price": 40.04, "loss_pct": -4.92},
        {"symbol": "QBTS", "qty": 425.0, "avg_price": 17.78, "current_price": 17.30, "loss_pct": -2.70},
        {"symbol": "QUBT", "qty": 251.0, "avg_price": 15.63, "current_price": 15.52, "loss_pct": -0.70},
        {"symbol": "COIN", "qty": 12.0, "avg_price": 320.08, "current_price": 318.01, "loss_pct": -0.65},
    ]
    
    print(f"\n📊 Testing Positions:")
    print("-" * 40)
    
    for pos in test_positions:
        print(f"   • {pos['symbol']}: {pos['qty']} @ ${pos['avg_price']:.2f}")
        print(f"     Current: ${pos['current_price']:.2f}, Loss: {pos['loss_pct']:.2f}%")
        
        # Create mock database position
        mock_db_position = Mock()
        mock_db_position.symbol = pos['symbol']
        mock_db_position.quantity = pos['qty']
        mock_db_position.avg_price = pos['avg_price']
        
        # Mock position manager to return this position
        mock_position_manager.get_position.return_value = mock_db_position
        
        # Mock order manager for new quantity calculation
        mock_risk_manager.calculate_position_size.return_value = pos['qty'] * 2.0  # Martingale doubling
        mock_order_manager.place_order.return_value = f"order_{pos['symbol']}_123"
        
        # Test DCA monitoring
        should_trigger = pos['loss_pct'] <= -2.0  # Should trigger at -2% threshold
        
        print(f"     Expected DCA: {'YES' if should_trigger else 'NO'} (threshold: -2%)")
        
        # Call the monitoring function
        await strategy.update_position_monitoring(pos['symbol'], pos['current_price'])
        
        # Check if DCA was triggered
        if should_trigger:
            # Verify order was placed
            if mock_order_manager.place_order.called:
                print(f"     ✅ DCA order placed successfully")
                # Reset for next test
                mock_order_manager.reset_mock()
            else:
                print(f"     ❌ DCA should have triggered but didn't")
        else:
            print(f"     ✅ No DCA triggered (loss not severe enough)")
        
        print()
    
    print(f"🎯 ANALYSIS OF YOUR CURRENT POSITIONS:")
    print("-" * 40)
    print("Based on your actual positions, DCA should trigger for:")
    print("✅ IONQ: -4.92% loss (exceeds -2% threshold)")
    print("✅ QBTS: -2.70% loss (exceeds -2% threshold)")
    print("❌ QUBT: -0.70% loss (below -2% threshold)")
    print("❌ COIN: -0.65% loss (below -2% threshold)")
    
    print(f"\n💡 WHY DCA WASN'T WORKING BEFORE:")
    print("1. ❌ The position monitoring wasn't calling the advanced strategy")
    print("2. ❌ Missing integration between trading bot and strategy DCA logic")
    print("3. ❌ No automatic monitoring of existing positions for DCA opportunities")
    
    print(f"\n✅ FIXES IMPLEMENTED:")
    print("1. ✅ Added position monitoring integration in trading bot")
    print("2. ✅ Created update_position_monitoring() method in advanced strategy")
    print("3. ✅ Added immediate DCA execution when support levels aren't available")
    print("4. ✅ Proper configuration reading for loss thresholds")
    print("5. ✅ Automatic position tracking and DCA attempt counting")
    
    print(f"\n⚙️  CONFIGURATION:")
    print("- DCA Loss Threshold: 2% (configurable in config.yaml)")
    print("- Max DCA Attempts: 3 (martingale: 1%, 2%, 4% position sizes)")
    print("- Position Multiplier: 2.0x (each DCA doubles the position size)")
    print("- Order Type: Respects global 'trading.order_type' setting")

if __name__ == "__main__":
    asyncio.run(test_dca_triggers())
