#!/usr/bin/env python3
"""
Start Trading Bot Without ngrok
Simple script to start the bot in local-only mode (no ngrok tunnel).
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def main():
    """Start the bot without ngrok."""
    print("🚫 Starting Trading Bot WITHOUT ngrok...")
    print("   • ngrok tunnel disabled")
    print("   • Running in local-only mode")
    print("   • FastAPI server on localhost:8080")
    print()
    
    # Set environment variable to disable ngrok
    os.environ["TRADING_BOT_NO_NGROK"] = "1"
    
    # Import and run the bot
    try:
        from run_bot import main as run_main
        import asyncio
        asyncio.run(run_main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
