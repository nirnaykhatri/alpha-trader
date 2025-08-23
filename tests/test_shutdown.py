#!/usr/bin/env python3
"""
Simple test to verify shutdown behavior works correctly.
"""

import asyncio
import signal
import sys

async def simple_test():
    """Simple shutdown test."""
    print("🧪 Simple Shutdown Test")
    print("Press Ctrl+C to test shutdown...")
    
    shutdown_event = asyncio.Event()
    
    def signal_handler(signum, frame):
        print(f"\n📡 Signal {signum} received!")
        print("🛑 Setting shutdown event...")
        shutdown_event.set()
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        print("⏳ Waiting for signal...")
        await shutdown_event.wait()
        print("✅ Shutdown event received!")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print("🏁 Test complete")

async def main():
    await simple_test()

if __name__ == "__main__":
    try:
        asyncio.run(main())
        print("💫 Script finished - if you see this immediately after Ctrl+C, it's working!")
    except KeyboardInterrupt:
        print("\n👋 KeyboardInterrupt caught")
    except Exception as e:
        print(f"❌ Error: {e}")
