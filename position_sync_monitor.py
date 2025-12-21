#!/usr/bin/env python3
"""
Position Synchronization Monitor
Checks for discrepancies between database and Alpaca positions.
"""

import asyncio
import sys
from typing import Dict, List, Tuple
from src.trading_bot import TradingBotOrchestrator
from src.core.logging_config import get_logger
from src.utils import run_blocking

logger = get_logger(__name__)

class PositionSyncMonitor:
    """Monitor for position synchronization between database and Alpaca."""
    
    def __init__(self, bot: TradingBotOrchestrator):
        self.bot = bot
        
    async def check_position_sync(self) -> Dict[str, Dict[str, float]]:
        """Check synchronization between database and Alpaca positions."""
        try:
            print("🔍 Checking Position Synchronization...")
            print("=" * 50)
            
            # Get all positions from database
            db_positions = await self.bot.position_manager.get_all_positions()
            print(f"📊 Found {len(db_positions)} positions in database")
            
            # Get all positions from Alpaca
            alpaca_positions = {}
            try:
                positions = await run_blocking(self.bot.trading_client.get_all_positions)
                
                for position in positions:
                    alpaca_positions[position.symbol] = float(position.qty)
                    
                print(f"📈 Found {len(alpaca_positions)} positions in Alpaca")
                
            except Exception as e:
                print(f"❌ Error fetching Alpaca positions: {e}")
                return {}
            
            # Compare positions
            discrepancies = {}
            all_symbols = set()
            
            # Add symbols from both sources
            for pos in db_positions:
                all_symbols.add(pos.symbol)
            all_symbols.update(alpaca_positions.keys())
            
            print(f"\n🔍 Analyzing {len(all_symbols)} unique symbols...")
            
            for symbol in all_symbols:
                # Get quantities from both sources
                db_qty = 0.0
                for pos in db_positions:
                    if pos.symbol == symbol:
                        db_qty = pos.quantity
                        break
                
                alpaca_qty = alpaca_positions.get(symbol, 0.0)
                
                # Check for discrepancies
                if abs(db_qty - alpaca_qty) > 0.001:  # Allow for small rounding differences
                    discrepancies[symbol] = {
                        'database': db_qty,
                        'alpaca': alpaca_qty,
                        'difference': abs(db_qty - alpaca_qty),
                        'critical': (db_qty > 0) != (alpaca_qty > 0) and alpaca_qty != 0  # Direction mismatch
                    }
            
            # Report results
            if discrepancies:
                print(f"\n⚠️  Found {len(discrepancies)} position discrepancies:")
                print("-" * 60)
                
                for symbol, data in discrepancies.items():
                    status = "🚨 CRITICAL" if data['critical'] else "⚠️  WARNING"
                    print(f"{status} {symbol}:")
                    print(f"   Database: {data['database']:+.2f}")
                    print(f"   Alpaca:   {data['alpaca']:+.2f}")
                    print(f"   Diff:     {data['difference']:.2f}")
                    
                    if data['critical']:
                        print(f"   Issue: Position direction mismatch!")
                    elif data['database'] != 0 and data['alpaca'] == 0:
                        print(f"   Issue: Database shows position, Alpaca shows none")
                    elif data['database'] == 0 and data['alpaca'] != 0:
                        print(f"   Issue: Alpaca shows position, Database shows none")
                    else:
                        print(f"   Issue: Quantity mismatch")
                    print()
                
                return discrepancies
            else:
                print(f"\n✅ All positions synchronized correctly!")
                return {}
                
        except Exception as e:
            print(f"❌ Error checking position sync: {e}")
            return {}
    
    async def suggest_fixes(self, discrepancies: Dict[str, Dict[str, float]]) -> None:
        """Suggest fixes for position discrepancies."""
        if not discrepancies:
            return
            
        print(f"\n💡 Suggested Actions:")
        print("=" * 30)
        
        for symbol, data in discrepancies.items():
            db_qty = data['database']
            alpaca_qty = data['alpaca']
            
            print(f"\n🔧 {symbol}:")
            
            if data['critical']:
                print(f"   🚨 CRITICAL: Manual intervention required!")
                print(f"   → Review trading history for this symbol")
                print(f"   → Verify which position is correct")
                print(f"   → Update database to match broker")
                
            elif db_qty != 0 and alpaca_qty == 0:
                print(f"   📝 Database cleanup needed")
                print(f"   → Position likely closed but not updated in database")
                print(f"   → Consider updating database position to 0")
                
            elif db_qty == 0 and alpaca_qty != 0:
                print(f"   📊 Database missing position")
                print(f"   → Alpaca shows active position")
                print(f"   → Consider adding position to database")
                
            else:
                print(f"   🔄 Quantity synchronization needed")
                print(f"   → Update database quantity to match Alpaca")
                print(f"   → Investigate cause of discrepancy")

async def main():
    """Main monitoring function."""
    try:
        print("🚀 Position Synchronization Monitor")
        print("=" * 60)
        
        # Initialize bot (lightweight init for monitoring)
        bot = TradingBotOrchestrator()
        await bot._initialize_components()
        
        # Create monitor
        monitor = PositionSyncMonitor(bot)
        
        # Check synchronization
        discrepancies = await monitor.check_position_sync()
        
        # Suggest fixes if needed
        await monitor.suggest_fixes(discrepancies)
        
        print(f"\n📋 Summary:")
        if discrepancies:
            critical_count = sum(1 for d in discrepancies.values() if d['critical'])
            warning_count = len(discrepancies) - critical_count
            
            print(f"   🚨 Critical Issues: {critical_count}")
            print(f"   ⚠️  Warnings: {warning_count}")
            print(f"   📊 Total Discrepancies: {len(discrepancies)}")
            
            if critical_count > 0:
                print(f"\n   ❗ Manual intervention required for critical issues!")
                return 1  # Exit code 1 for critical issues
        else:
            print(f"   ✅ All positions synchronized correctly")
            
        return 0
        
    except Exception as e:
        print(f"❌ Monitor failed: {e}")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
