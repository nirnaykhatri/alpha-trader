#!/usr/bin/env python3
"""
Test script to verify that webhook handling is non-blocking.
This script simulates a slow callback to test that webhook responses are immediate.
"""

import asyncio
import time
import json
from typing import Dict, Any
from src.signals.signal_listener import TradingViewSignalListener
from src.interfaces import IConfigurationManager
from src import TradingSignal


class MockConfig(IConfigurationManager):
    """Mock configuration for testing."""
    
    def __init__(self):
        self._config = {
            "api.webhook.host": "127.0.0.1",
            "api.webhook.port": 8080,
            "api.webhook.secret": None,
            "api.webhook.security_enabled": False
        }
    
    def get_config(self, key: str, default=None):
        return self._config.get(key, default)
    
    def set_config(self, key: str, value):
        self._config[key] = value


class SlowCallback:
    """Mock callback that simulates slow processing."""
    
    def __init__(self, delay: float = 3.0):
        self.delay = delay
        self.call_count = 0
        self.call_times = []
    
    async def __call__(self, signal: TradingSignal):
        """Simulate slow signal processing."""
        self.call_count += 1
        start_time = time.time()
        self.call_times.append(start_time)
        
        print(f"Callback {self.call_count} started at {start_time}")
        print(f"Processing signal: {signal.symbol} {signal.signal_type.value}")
        
        # Simulate slow processing (like order placement with retries)
        await asyncio.sleep(self.delay)
        
        end_time = time.time()
        print(f"Callback {self.call_count} completed at {end_time} (took {end_time - start_time:.2f}s)")


async def test_webhook_non_blocking():
    """Test that webhook responses are immediate even with slow callbacks."""
    
    # Create mock components
    config = MockConfig()
    slow_callback = SlowCallback(delay=5.0)  # 5 second delay
    
    # Create signal listener
    listener = TradingViewSignalListener(config, slow_callback)
    
    # Start the listener in background
    print("Starting webhook listener...")
    listener_task = asyncio.create_task(listener.start_listening())
    
    # Wait for server to start
    await asyncio.sleep(1)
    
    # Test data
    test_payload = {
        "symbol": "AAPL",
        "action": "buy",
        "price": 150.0,
        "quantity": 100
    }
    
    try:
        # Simulate rapid webhook requests
        print("\nSending webhook requests...")
        
        import aiohttp
        
        async with aiohttp.ClientSession() as session:
            # Send first request
            start_time1 = time.time()
            async with session.post(
                "http://127.0.0.1:8080/webhook",
                json=test_payload,
                headers={"Content-Type": "application/json"}
            ) as response1:
                response_time1 = time.time() - start_time1
                result1 = await response1.json()
                print(f"Request 1 response time: {response_time1:.3f}s")
                print(f"Request 1 result: {result1}")
            
            # Send second request immediately
            start_time2 = time.time()
            async with session.post(
                "http://127.0.0.1:8080/webhook",
                json=test_payload,
                headers={"Content-Type": "application/json"}
            ) as response2:
                response_time2 = time.time() - start_time2
                result2 = await response2.json()
                print(f"Request 2 response time: {response_time2:.3f}s")
                print(f"Request 2 result: {result2}")
            
            # Both responses should be immediate (< 1 second)
            if response_time1 < 1.0 and response_time2 < 1.0:
                print("\n✅ SUCCESS: Both webhook responses were immediate!")
                print("The webhook handler is properly non-blocking.")
            else:
                print("\n❌ FAILURE: Webhook responses were too slow.")
                print("The webhook handler may still be blocking.")
        
        # Wait a bit for callbacks to complete
        print("\nWaiting for callbacks to complete...")
        await asyncio.sleep(6)
        
        print(f"\nCallback statistics:")
        print(f"- Total calls: {slow_callback.call_count}")
        print(f"- Call times: {[f'{t:.3f}' for t in slow_callback.call_times]}")
        
    finally:
        # Stop the listener
        print("\nStopping webhook listener...")
        await listener.stop_listening()
        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(test_webhook_non_blocking())
