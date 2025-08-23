#!/usr/bin/env python3
"""
Advanced webhook handler tests using async mock components.
Tests the signal listener behavior in isolation with mock callbacks.
"""

import pytest
import asyncio
import json
import time
from unittest.mock import Mock, AsyncMock
from typing import Dict, Any
from src.signals.signal_listener import TradingViewSignalListener
from src.interfaces import IConfigurationManager
from src import TradingSignal


class MockConfig(IConfigurationManager):
    """Mock configuration for testing."""
    
    def __init__(self, config_overrides: Dict[str, Any] = None):
        self._config = {
            "api.webhook.host": "127.0.0.1",
            "api.webhook.port": 8081,  # Different port for testing
            "api.webhook.secret": None,
            "api.webhook.security_enabled": False
        }
        if config_overrides:
            self._config.update(config_overrides)
    
    def get_config(self, key: str, default=None):
        return self._config.get(key, default)
    
    def set_config(self, key: str, value):
        self._config[key] = value


class SlowAsyncCallback:
    """Mock callback that simulates slow async processing."""
    
    def __init__(self, delay: float = 3.0):
        self.delay = delay
        self.call_count = 0
        self.call_times = []
        self.signals_received = []
    
    async def __call__(self, signal: TradingSignal):
        """Simulate slow signal processing."""
        self.call_count += 1
        start_time = time.time()
        self.call_times.append(start_time)
        self.signals_received.append(signal)
        
        # Simulate slow processing (like order placement with retries)
        await asyncio.sleep(self.delay)
        
        end_time = time.time()
        print(f"Callback {self.call_count} completed at {end_time} (took {end_time - start_time:.2f}s)")


class TestWebhookHandlerBehavior:
    """Test webhook handler behavior with various callback scenarios."""
    
    @pytest.fixture
    def mock_config(self):
        """Create mock configuration."""
        return MockConfig()
    
    @pytest.fixture
    def test_payload(self):
        """Standard test payload."""
        return {
            "symbol": "AAPL",
            "action": "buy",
            "price": 150.0,
            "quantity": 100
        }
    
    @pytest.mark.asyncio
    async def test_webhook_handler_fire_and_forget(self, mock_config, test_payload):
        """Test that webhook handler doesn't wait for slow callbacks."""
        # Create slow callback
        slow_callback = SlowAsyncCallback(delay=2.0)
        
        # Create signal listener
        listener = TradingViewSignalListener(mock_config, slow_callback)
        
        # Start listener in background
        listener_task = asyncio.create_task(listener.start_listening())
        await asyncio.sleep(0.5)  # Wait for server to start
        
        try:
            # Test webhook response time
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                start_time = time.time()
                
                async with session.post(
                    f"http://127.0.0.1:8081/webhook",
                    json=test_payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    response_time = time.time() - start_time
                    result = await response.json()
                
                # Webhook should respond immediately (< 1 second)
                assert response_time < 1.0, f"Webhook response too slow: {response_time:.3f}s"
                assert response.status == 200
                assert "signal_id" in result
                
                # Callback should not have completed yet
                assert slow_callback.call_count == 1, "Callback should have been called once"
                
                # Wait for callback to complete
                await asyncio.sleep(3.0)
                
                # Now callback should be done
                assert len(slow_callback.signals_received) == 1
                assert slow_callback.signals_received[0].symbol == "AAPL"
        
        finally:
            # Stop listener
            await listener.stop_listening()
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass
    
    @pytest.mark.asyncio
    async def test_webhook_concurrent_with_slow_callback(self, mock_config, test_payload):
        """Test multiple concurrent webhooks with slow callback."""
        slow_callback = SlowAsyncCallback(delay=1.5)
        listener = TradingViewSignalListener(mock_config, slow_callback)
        
        # Start listener
        listener_task = asyncio.create_task(listener.start_listening())
        await asyncio.sleep(0.5)
        
        try:
            import aiohttp
            
            # Send multiple concurrent requests
            async with aiohttp.ClientSession() as session:
                tasks = []
                start_time = time.time()
                
                for i in range(3):
                    task = session.post(
                        f"http://127.0.0.1:8081/webhook",
                        json=test_payload,
                        headers={"Content-Type": "application/json"}
                    )
                    tasks.append(task)
                
                # Wait for all responses
                responses = await asyncio.gather(*tasks)
                response_time = time.time() - start_time
                
                # All responses should be fast
                assert response_time < 2.0, f"All responses too slow: {response_time:.3f}s"
                
                # All should be successful
                for response in responses:
                    assert response.status == 200
                    result = await response.json()
                    assert "signal_id" in result
                
                # All callbacks should have been triggered
                assert slow_callback.call_count == 3
                
                # Wait for all callbacks to complete
                await asyncio.sleep(2.5)
                assert len(slow_callback.signals_received) == 3
        
        finally:
            await listener.stop_listening()
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass
    
    @pytest.mark.asyncio
    async def test_webhook_with_failing_callback(self, mock_config, test_payload):
        """Test webhook behavior when callback raises exception."""
        
        async def failing_callback(signal: TradingSignal):
            """Callback that always fails."""
            await asyncio.sleep(0.1)
            raise Exception("Simulated callback failure")
        
        listener = TradingViewSignalListener(mock_config, failing_callback)
        listener_task = asyncio.create_task(listener.start_listening())
        await asyncio.sleep(0.5)
        
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                start_time = time.time()
                
                async with session.post(
                    f"http://127.0.0.1:8081/webhook",
                    json=test_payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    response_time = time.time() - start_time
                    result = await response.json()
                
                # Webhook should still respond quickly despite callback failure
                assert response_time < 1.0, f"Webhook response too slow: {response_time:.3f}s"
                assert response.status == 200
                assert "signal_id" in result
        
        finally:
            await listener.stop_listening()
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass
    
    @pytest.mark.asyncio
    async def test_webhook_signal_processing_timeout(self, mock_config):
        """Test webhook behavior when signal processing times out."""
        # Use config that might cause processing issues
        config = MockConfig({"api.webhook.security_enabled": False})
        
        # Mock callback
        callback = AsyncMock()
        listener = TradingViewSignalListener(config, callback)
        
        # Start listener
        listener_task = asyncio.create_task(listener.start_listening())
        await asyncio.sleep(0.5)
        
        try:
            import aiohttp
            
            # Send malformed payload that might cause timeout
            invalid_payload = {"invalid": "data"}
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"http://127.0.0.1:8081/webhook",
                    json=invalid_payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    # Should get error response quickly
                    assert response.status in [400, 500]  # Bad request or internal error
        
        finally:
            await listener.stop_listening()
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    # Run tests manually
    pytest.main([__file__, "-v"])
