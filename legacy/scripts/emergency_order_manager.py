#!/usr/bin/env python3
"""
Emergency order cancellation script for trading bot.
Use this when the bot is stuck in infinite loops due to pending orders.
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.trading_bot import TradingBotOrchestrator


async def cancel_all_orders():
    """Cancel all pending orders to resolve infinite loop issues."""
    print("🚨 EMERGENCY ORDER CANCELLATION")
    print("=" * 50)
    
    try:
        # Create bot instance
        bot = TradingBotOrchestrator()
        
        # Initialize all components
        await bot._initialize_components()
        
        print("✅ Bot components initialized")
        
        # Get all open orders
        open_orders = await bot.order_manager.get_open_orders()
        
        if not open_orders:
            print("✅ No open orders found - nothing to cancel")
            return
        
        print(f"🔍 Found {len(open_orders)} open orders:")
        for order in open_orders:
            print(f"   {order.symbol}: {order.side.value} {order.quantity} @ {order.price or 'MARKET'} (ID: {order.order_id})")
        
        # Ask for confirmation
        print("\n⚠️  WARNING: This will cancel ALL open orders!")
        response = input("Continue? (yes/no): ").lower().strip()
        
        if response != 'yes':
            print("❌ Cancelled by user")
            return
        
        # Cancel all orders
        cancelled_count = 0
        failed_count = 0
        
        for order in open_orders:
            try:
                await bot.order_manager.cancel_order(order.order_id)
                print(f"✅ Cancelled: {order.symbol} {order.side.value} {order.quantity}")
                cancelled_count += 1
            except Exception as e:
                print(f"❌ Failed to cancel {order.symbol}: {e}")
                failed_count += 1
        
        print(f"\n📊 SUMMARY:")
        print(f"   ✅ Cancelled: {cancelled_count}")
        print(f"   ❌ Failed: {failed_count}")
        
        if cancelled_count > 0:
            print(f"\n🎉 Successfully cancelled {cancelled_count} orders!")
            print("💡 You can now restart the bot safely")
        
    except Exception as e:
        print(f"❌ Emergency cancellation failed: {e}")
        import traceback
        traceback.print_exc()


async def show_current_orders():
    """Show current orders without cancelling."""
    print("📋 CURRENT ORDERS STATUS")
    print("=" * 50)
    
    try:
        # Create bot instance
        bot = TradingBotOrchestrator("config.yaml")
        
        # Initialize all components
        await bot._initialize_components()
        
        # Get all open orders
        open_orders = await bot.order_manager.get_open_orders()
        
        if not open_orders:
            print("✅ No open orders found")
            return
        
        print(f"🔍 Found {len(open_orders)} open orders:")
        for order in open_orders:
            print(f"   {order.symbol}: {order.side.value} {order.quantity} @ {order.price or 'MARKET'}")
            print(f"      ID: {order.order_id}")
            print(f"      Status: {order.status}")
            print(f"      Created: {order.created_at}")
            print()
        
    except Exception as e:
        print(f"❌ Failed to check orders: {e}")


async def main():
    """Main function to handle user choice."""
    print("🔧 TRADING BOT ORDER MANAGEMENT")
    print("=" * 50)
    print("1. Show current orders")
    print("2. Cancel ALL orders (emergency)")
    print("3. Exit")
    
    choice = input("\nSelect option (1-3): ").strip()
    
    if choice == "1":
        await show_current_orders()
    elif choice == "2":
        await cancel_all_orders()
    elif choice == "3":
        print("👋 Goodbye!")
    else:
        print("❌ Invalid choice")


if __name__ == "__main__":
    print("Trading Bot Order Management Tool")
    print("Use this to resolve order conflicts and infinite loops")
    print("=" * 60)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n🛑 Interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Tool failed: {e}")
        sys.exit(1)
