#!/usr/bin/env python3
"""
Emergency Position Sync Tool
Immediately syncs local database positions with Alpaca to fix zombie positions.
"""

import asyncio
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def emergency_sync():
    """Emergency sync to fix zombie positions."""
    try:
        print("🚨 EMERGENCY POSITION SYNC")
        print("=" * 50)
        print(f"Timestamp: {datetime.now()}")
        
        # Import required modules
        from src.core.configuration import ConfigurationManager
        from src.database.database_manager import DatabaseManager
        from src.position.position_manager import PositionManager
        from src.trading.alpaca_account_provider import AlpacaAccountProvider
        from src.broker.router import BrokerRouter
        from src.broker.interfaces import BrokerType
        
        # Initialize components
        print("\n📋 Initializing components...")
        config = ConfigurationManager()  # Loads from config/ directory
        db_manager = DatabaseManager(config)
        account_provider = AlpacaAccountProvider(config)
        
        # Initialize BrokerRouter with just the account provider
        broker_router = BrokerRouter(
            config=config,
            executors={},
            account_providers={BrokerType.ALPACA: account_provider},
            market_data_providers={}
        )
        
        # Initialize position manager with BrokerRouter
        position_manager = PositionManager(config, db_manager, broker_router)
        
        print("✅ Components initialized")
        
        # Get current local positions
        print("\n📊 BEFORE SYNC - Local Database Positions:")
        local_positions = await position_manager.get_all_positions()
        for pos in local_positions:
            if pos.quantity != 0:
                print(f"   {pos.symbol}: {pos.quantity:.2f} @ ${pos.avg_price:.2f}")
        
        if not any(pos.quantity != 0 for pos in local_positions):
            print("   No active positions found in local database")
        
        # Get current Alpaca positions
        print("\n🔍 ALPACA Positions:")
        try:
            # Use the provider directly or via router
            alpaca_positions = await account_provider.get_positions()
            if alpaca_positions:
                for pos in alpaca_positions:
                    print(f"   {pos.symbol}: {float(pos.quantity):.2f} @ ${float(pos.avg_price):.2f}")
            else:
                print("   No active positions found in Alpaca")
        except Exception as e:
            print(f"   ❌ Error getting Alpaca positions: {e}")
            return False
        
        # Perform sync
        print("\n🔄 PERFORMING SYNC...")
        try:
            await position_manager.sync_positions()
            print("✅ Sync completed successfully!")
        except Exception as e:
            print(f"❌ Sync failed: {e}")
            return False
        
        # Get positions after sync
        print("\n📊 AFTER SYNC - Local Database Positions:")
        synced_positions = await position_manager.get_all_positions()
        for pos in synced_positions:
            if pos.quantity != 0:
                print(f"   {pos.symbol}: {pos.quantity:.2f} @ ${pos.avg_price:.2f}")
        
        if not any(pos.quantity != 0 for pos in synced_positions):
            print("   No active positions found in local database")
        
        # Check for zombie positions that were fixed
        zombie_positions = []
        for local_pos in local_positions:
            if local_pos.quantity != 0:
                # Check if this position still exists after sync
                synced_pos = next((p for p in synced_positions if p.symbol == local_pos.symbol), None)
                if not synced_pos or synced_pos.quantity == 0:
                    zombie_positions.append(local_pos.symbol)
        
        if zombie_positions:
            print(f"\n🧟 ZOMBIE POSITIONS FIXED: {', '.join(zombie_positions)}")
            print("These positions were in the local database but not in Alpaca")
        else:
            print("\n✅ No zombie positions detected")
        
        print("\n🎯 SYNC SUMMARY:")
        print(f"   Local positions before: {len([p for p in local_positions if p.quantity != 0])}")
        print(f"   Alpaca positions: {len(alpaca_positions) if alpaca_positions else 0}")
        print(f"   Local positions after: {len([p for p in synced_positions if p.quantity != 0])}")
        print(f"   Zombie positions fixed: {len(zombie_positions)}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ EMERGENCY SYNC FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🤖 Trading Bot Emergency Position Sync")
    print("This tool fixes 'zombie positions' - positions in local DB that don't exist in Alpaca")
    
    success = asyncio.run(emergency_sync())
    
    if success:
        print("\n✅ Emergency sync completed successfully!")
        print("The bot should now stop trying to close non-existent positions.")
    else:
        print("\n❌ Emergency sync failed. Check the error messages above.")
        sys.exit(1)
