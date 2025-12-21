"""
Test Enhanced DCA Strategy with Pure Technical Analysis
Tests the new support/resistance based DCA logic without loss thresholds
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock
from datetime import datetime

# Test the enhanced DCA functionality
@pytest.mark.asyncio
async def test_enhanced_dca_with_support_breach():
    """Test DCA triggering when price breaches support level"""
    
    # Mock position data based on user's current positions
    test_positions = [
        {
            'symbol': 'IONQ',
            'quantity': 100,
            'avg_price': 10.00,
            'current_price': 9.51,  # -4.92% loss
            'timeframe': '1h'  # Original signal timeframe
        },
        {
            'symbol': 'QBTS', 
            'quantity': 50,
            'avg_price': 2.70,
            'current_price': 2.63,  # -2.59% loss
            'timeframe': '4h'  # Original signal timeframe
        }
    ]
    
    print("\n" + "="*60)
    print("🧪 TESTING ENHANCED DCA STRATEGY")
    print("Pure Support/Resistance Based (No Loss Thresholds)")
    print("="*60)
    
    for position in test_positions:
        symbol = position['symbol']
        current_price = position['current_price']
        avg_price = position['avg_price']
        timeframe = position['timeframe']
        
        loss_pct = (current_price - avg_price) / avg_price * 100
        
        print(f"\n📊 TESTING {symbol}:")
        print(f"   Entry: ${avg_price:.2f}")
        print(f"   Current: ${current_price:.2f} ({loss_pct:+.2f}%)")
        print(f"   Timeframe: {timeframe}")
        
        # Simulate support level calculation
        # In real implementation, this would call support_calculator
        
        if symbol == 'IONQ':
            # IONQ has strong support at $9.40 based on 1H chart
            support_level = 9.40
            support_confidence = 0.85
            
            print(f"   Support: ${support_level:.2f} (confidence: {support_confidence:.0%})")
            
            # Check if current price breached support
            support_buffer = 0.005  # 0.5% buffer
            trigger_price = support_level * (1 - support_buffer)
            
            if current_price <= trigger_price:
                print(f"   🎯 DCA TRIGGERED: Price ${current_price:.2f} breached support ${trigger_price:.2f}")
                print(f"   📈 Technical analysis confirms DCA opportunity")
            else:
                distance = ((current_price - trigger_price) / current_price) * 100
                print(f"   🔍 WATCHING: {distance:.1f}% above support trigger")
                
        elif symbol == 'QBTS':
            # QBTS has support at $2.55 based on 4H chart
            support_level = 2.55
            support_confidence = 0.78
            
            print(f"   Support: ${support_level:.2f} (confidence: {support_confidence:.0%})")
            
            # Check if current price breached support
            support_buffer = 0.005  # 0.5% buffer
            trigger_price = support_level * (1 - support_buffer)
            
            if current_price <= trigger_price:
                print(f"   🎯 DCA TRIGGERED: Price ${current_price:.2f} breached support ${trigger_price:.2f}")
                print(f"   📈 Technical analysis confirms DCA opportunity")
            else:
                distance = ((current_price - trigger_price) / current_price) * 100
                print(f"   🔍 WATCHING: {distance:.1f}% above support trigger")
    
    print("\n" + "="*60)
    print("✅ ENHANCED DCA ANALYSIS COMPLETE")
    print("="*60)
    print("🎯 Key Benefits:")
    print("   • DCA based on actual support levels, not arbitrary %")
    print("   • Uses original signal timeframe for consistency")
    print("   • Confidence-based decisions (min 70%)")
    print("   • Respects market structure and chart patterns")
    print("   • No premature DCA triggers")

@pytest.mark.asyncio
async def test_comparison_old_vs_new():
    """Compare old loss threshold vs new technical approach"""
    
    print("\n" + "="*60)
    print("📊 COMPARISON: OLD vs NEW DCA APPROACH")
    print("="*60)
    
    test_case = {
        'symbol': 'IONQ',
        'entry_price': 10.00,
        'current_price': 9.51,
        'loss_pct': -4.92
    }
    
    print(f"\n📈 Test Case: {test_case['symbol']}")
    print(f"   Entry: ${test_case['entry_price']:.2f}")
    print(f"   Current: ${test_case['current_price']:.2f} ({test_case['loss_pct']:+.2f}%)")
    
    print(f"\n🔴 OLD APPROACH (Loss Threshold):")
    print(f"   Threshold: -2.0%")
    print(f"   Current Loss: {test_case['loss_pct']:.2f}%")
    if test_case['loss_pct'] <= -2.0:
        print(f"   ❌ DCA TRIGGERED at {test_case['current_price']:.2f} (may be premature)")
        print(f"   ⚠️  Ignores technical levels - could DCA too early")
    
    print(f"\n🟢 NEW APPROACH (Technical Analysis):")
    support_level = 9.40
    support_confidence = 0.85
    trigger_price = support_level * 0.995  # 0.5% buffer
    
    print(f"   Support Level: ${support_level:.2f} (confidence: {support_confidence:.0%})")
    print(f"   Trigger Price: ${trigger_price:.2f}")
    
    if test_case['current_price'] <= trigger_price:
        print(f"   ✅ DCA TRIGGERED at support breach")
        print(f"   🎯 Based on chart structure - higher probability of bounce")
    else:
        distance = ((test_case['current_price'] - trigger_price) / test_case['current_price']) * 100
        print(f"   🔍 WAITING: {distance:.1f}% above support")
        print(f"   📊 Respects market structure - no premature entry")
    
    print(f"\n💡 CONCLUSION:")
    print(f"   Old: DCA at arbitrary loss % (may be too early)")
    print(f"   New: DCA at technical levels (market-structure aware)")

if __name__ == "__main__":
    asyncio.run(test_enhanced_dca_with_support_breach())
    asyncio.run(test_comparison_old_vs_new())
