#!/usr/bin/env python3
"""
Database Recovery Utility for Trading Bot

This script helps recover your local database from Alpaca positions
in case of data loss, corruption, or when setting up on a new machine.

Usage:
    python scripts/recover_database.py [options]
    
Examples:
    # Basic recovery (preserves existing data)
    python scripts/recover_database.py
    
    # Force recovery (clears existing data first)
    python scripts/recover_database.py --force
    
    # Preview what would be recovered
    python scripts/recover_database.py --dry-run
"""

import sys
import asyncio
import argparse
from pathlib import Path
from datetime import datetime

# Add parent directory to path to import bot modules
sys.path.append(str(Path(__file__).parent.parent))

from src.core.logging_config import setup_logging, get_logger
from src.config.configuration_manager import ConfigurationManager
from src.database.database_manager import DatabaseManager
from src.position.position_manager import PositionManager


logger = get_logger(__name__)


async def main():
    """Main recovery function."""
    parser = argparse.ArgumentParser(
        description="Recover trading bot database from Alpaca positions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--force", 
        action="store_true",
        help="Clear existing local data before recovery (DESTRUCTIVE)"
    )
    
    parser.add_argument(
        "--dry-run", 
        action="store_true",
        help="Preview recovery without making changes"
    )
    
    parser.add_argument(
        "--config", 
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging()
    
    if args.force and not args.dry_run:
        print("⚠️  WARNING: --force will DELETE all existing position data!")
        response = input("Are you sure you want to continue? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Recovery cancelled.")
            return
    
    try:
        logger.info("Starting database recovery utility...")
        
        # Initialize components
        config = ConfigurationManager(args.config)
        await config.initialize()
        
        database = DatabaseManager(config)
        await database.initialize()
        
        # Initialize trading client for Alpaca access
        # Note: You may need to adjust this based on your actual trading client setup
        try:
            from src.trading.trading_client import TradingClient
            trading_client = TradingClient(config)
            await trading_client.initialize()
        except ImportError:
            logger.error("Trading client not available. Please ensure Alpaca client is properly configured.")
            return
        
        position_manager = PositionManager(config, database, trading_client)
        
        if args.dry_run:
            await preview_recovery(position_manager)
        else:
            await perform_recovery(position_manager, args.force)
            
    except Exception as e:
        logger.error(f"Recovery failed: {str(e)}")
        sys.exit(1)
    finally:
        if 'database' in locals():
            await database.close()
        if 'trading_client' in locals():
            await trading_client.close()


async def preview_recovery(position_manager: PositionManager) -> None:
    """Preview what would be recovered without making changes."""
    logger.info("🔍 DRY RUN: Previewing recovery from Alpaca...")
    
    try:
        # Get Alpaca positions
        alpaca_positions = await position_manager._get_alpaca_positions()
        
        print(f"\n📊 Recovery Preview:")
        print(f"   Alpaca positions found: {len(alpaca_positions)}")
        
        if alpaca_positions:
            print(f"\n📋 Positions that would be recovered:")
            total_value = 0
            for pos in alpaca_positions:
                position_value = float(pos.qty) * float(pos.current_price)
                total_value += abs(position_value)
                print(f"   • {pos.symbol}: {pos.qty} shares @ ${pos.current_price:.2f} "
                      f"(Avg: ${pos.avg_entry_price:.2f}, P&L: ${pos.unrealized_pl:.2f})")
            
            print(f"\n💰 Total position value: ${total_value:,.2f}")
        else:
            print("   ℹ️  No positions found in Alpaca account")
        
        # Check existing local positions
        local_positions = await position_manager.get_all_positions()
        open_local = [p for p in local_positions if p.quantity != 0]
        
        print(f"\n🏠 Current local database:")
        print(f"   Open positions: {len(open_local)}")
        if open_local:
            for pos in open_local:
                print(f"   • {pos.symbol}: {pos.quantity} shares @ ${pos.current_price:.2f}")
        
        print(f"\n✅ Run without --dry-run to perform actual recovery")
        
    except Exception as e:
        logger.error(f"Preview failed: {str(e)}")


async def perform_recovery(position_manager: PositionManager, force: bool = False) -> None:
    """Perform the actual database recovery."""
    logger.info("🔄 Starting database recovery from Alpaca...")
    
    try:
        # Perform recovery
        recovery_stats = await position_manager.recover_database_from_alpaca(force_recovery=force)
        
        # Display results
        print(f"\n✅ Database Recovery Complete!")
        print(f"   Timestamp: {recovery_stats['timestamp']}")
        print(f"   Positions recovered: {recovery_stats['recovered_positions']}")
        print(f"   Positions skipped: {recovery_stats['skipped_positions']}")
        
        if 'recovered_orders' in recovery_stats:
            print(f"   Orders recovered: {recovery_stats['recovered_orders']}")
        
        if recovery_stats['errors']:
            print(f"\n⚠️  Errors encountered:")
            for error in recovery_stats['errors']:
                print(f"   • {error}")
        
        # Show final position summary
        positions = await position_manager.get_all_positions()
        open_positions = [p for p in positions if p.quantity != 0]
        
        print(f"\n📊 Final Position Summary:")
        print(f"   Total positions in database: {len(positions)}")
        print(f"   Open positions: {len(open_positions)}")
        
        if open_positions:
            total_value = sum(abs(p.quantity * p.current_price) for p in open_positions)
            print(f"   Total position value: ${total_value:,.2f}")
            
            print(f"\n📋 Open Positions:")
            for pos in open_positions:
                print(f"   • {pos.symbol}: {pos.quantity} shares @ ${pos.current_price:.2f} "
                      f"(P&L: ${pos.unrealized_pnl:.2f})")
        
        print(f"\n🎉 Your database has been successfully recovered from Alpaca!")
        
    except Exception as e:
        logger.error(f"Recovery failed: {str(e)}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
