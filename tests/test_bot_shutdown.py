#!/usr/bin/env python3
"""
Comprehensive test that simulates the trading bot's Uvicorn server behavior.
"""

import asyncio
import signal
import sys
from typing import List

class MockUvicornServer:
    """Mock Uvicorn server that behaves like the real one."""
    
    def __init__(self):
        self.should_exit = False
        self.force_exit = False
        self._is_running = False
    
    async def serve(self):
        """Simulate Uvicorn serve method."""
        print("INFO:     Started server process")
        print("INFO:     Waiting for application startup.")
        print("INFO:     Application startup complete.")
        print("INFO:     Uvicorn running on http://0.0.0.0:8080 (Press CTRL+C to quit)")
        
        self._is_running = True
        
        # Set up signal handler that Uvicorn would normally install
        def uvicorn_signal_handler(signum, frame):
            print("INFO:     Shutting down")
            self.should_exit = True
        
        # Install Uvicorn's signal handlers
        signal.signal(signal.SIGINT, uvicorn_signal_handler)
        
        try:
            # Simulate server running
            while not self.should_exit and not self.force_exit:
                await asyncio.sleep(0.1)
        finally:
            self._is_running = False
            print("INFO:     Waiting for application shutdown.")
            print("INFO:     Application shutdown complete.")
            print("INFO:     Finished server process")

class TestBot:
    """Test bot that simulates the real trading bot."""
    
    def __init__(self):
        self.is_running = False
        self.shutdown_event = asyncio.Event()
        self.background_tasks: List[asyncio.Task] = []
        self.mock_server = MockUvicornServer()
    
    def _setup_signal_handlers(self):
        """Setup our own signal handlers."""
        def signal_handler(signum=None, frame=None):
            print(f"🤖 Bot received signal {signum}")
            print("🤖 Bot setting shutdown event...")
            if not self.shutdown_event.is_set():
                self.shutdown_event.set()
        
        try:
            # Try asyncio signal handling first
            loop = asyncio.get_running_loop()
            if hasattr(loop, 'add_signal_handler'):
                loop.add_signal_handler(signal.SIGINT, signal_handler, signal.SIGINT)
                print("🤖 Bot asyncio signal handlers registered")
            else:
                signal.signal(signal.SIGINT, signal_handler)
                print("🤖 Bot regular signal handlers registered")
        except Exception as e:
            print(f"🤖 Could not set bot signal handlers: {e}")
    
    async def _start_mock_server(self):
        """Start the mock server."""
        try:
            await self.mock_server.serve()
        finally:
            print("🤖 Mock server task completed")
    
    async def _monitor_server(self):
        """Monitor server health."""
        try:
            while self.is_running and not self.shutdown_event.is_set():
                if not self.mock_server._is_running:
                    print("🤖 Server stopped - triggering bot shutdown")
                    self.shutdown_event.set()
                    break
                
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=1.0)
                    break
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            print("🤖 Server monitor cancelled")
    
    async def start(self):
        """Start the test bot."""
        print("🤖 Starting test bot...")
        
        # Setup signal handlers FIRST
        self._setup_signal_handlers()
        
        self.is_running = True
        
        # Start background tasks
        server_task = asyncio.create_task(self._start_mock_server())
        monitor_task = asyncio.create_task(self._monitor_server())
        
        self.background_tasks.extend([server_task, monitor_task])
        
        # Main loop
        try:
            print("🤖 Main loop started...")
            
            # Wait for shutdown with periodic checking
            while self.is_running and not self.shutdown_event.is_set():
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=1.0)
                    break
                except asyncio.TimeoutError:
                    # Check if server stopped
                    if not self.mock_server._is_running:
                        print("🤖 Detected server stopped")
                        self.shutdown_event.set()
                        break
                    continue
            
            print("🤖 Shutdown detected, stopping...")
            await self.stop()
            
        except KeyboardInterrupt:
            print("🤖 KeyboardInterrupt in main loop")
            await self.stop()
    
    async def stop(self):
        """Stop the test bot."""
        if not self.is_running:
            return
        
        print("🤖 Stopping bot...")
        self.is_running = False
        
        # Stop server
        self.mock_server.should_exit = True
        self.mock_server.force_exit = True
        
        # Cancel background tasks
        for task in self.background_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self.background_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self.background_tasks, return_exceptions=True),
                    timeout=2.0
                )
                print("🤖 All tasks stopped")
            except asyncio.TimeoutError:
                print("🤖 Some tasks timed out")
        
        print("🤖 Bot stopped successfully")

async def main():
    """Main test function."""
    print("🧪 Testing Bot with Mock Uvicorn Server")
    print("Press Ctrl+C to test shutdown...")
    print("-" * 50)
    
    bot = TestBot()
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        print("\n🧪 Test KeyboardInterrupt caught")
    finally:
        print("🧪 Test complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
        print("\n💫 Test finished successfully!")
        print("✅ If you see this immediately after Ctrl+C, the fix is working!")
    except KeyboardInterrupt:
        print("\n👋 Test interrupted")
    except Exception as e:
        print(f"\n❌ Test error: {e}")
