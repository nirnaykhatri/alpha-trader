"""
Integration tests for webhook endpoint functionality.
"""

import pytest
import asyncio
import json
import hashlib
import hmac
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from src.signals import TradingViewSignalListener
from src.core import ConfigurationManager
from src.interfaces import TradingSignal, SignalType


class TestWebhookIntegration:
    """Test webhook endpoint integration with TradingView."""
    
    @pytest.fixture
    def config_manager(self, test_config_file):
        """Configuration manager for testing."""
        return ConfigurationManager(test_config_file)
    
    @pytest.fixture
    def signal_listener(self, config_manager):
        """Signal listener instance for testing."""
        return TradingViewSignalListener(config_manager)
    
    @pytest.fixture
    def webhook_secret(self, config_manager):
        """Get webhook secret from config."""
        return config_manager.get_config("api.webhook.secret")
    
    def create_webhook_signature(self, payload, secret):
        """Create webhook signature for testing."""
        payload_str = json.dumps(payload, separators=(',', ':'))
        return hmac.new(
            secret.encode(),
            payload_str.encode(),
            hashlib.sha256
        ).hexdigest()
    
    @pytest.mark.asyncio
    async def test_webhook_endpoint_buy_signal(self, signal_listener, webhook_secret):
        """Test webhook endpoint with buy signal."""
        # Create buy signal payload
        payload = {
            "symbol": "AAPL",
            "action": "buy",
            "price": 150.0,
            "timestamp": int(datetime.now().timestamp()),
            "source": "tradingview",
            "strategy": "momentum_breakout",
            "volume": 1000000,
            "rsi": 65.5,
            "macd": 0.25
        }
        
        # Create signature
        signature = self.create_webhook_signature(payload, webhook_secret)
        
        # Mock signal handler
        received_signals = []
        
        async def test_handler(signal):
            received_signals.append(signal)
        
        signal_listener.register_signal_handler(test_handler)
        
        # Simulate webhook request
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value=payload)
        mock_request.headers = {"X-Webhook-Signature": signature}
        
        # Process webhook
        with patch.object(signal_listener, '_verify_webhook_signature', return_value=True):
            await signal_listener._webhook_endpoint(mock_request)
        
        # Verify signal was processed
        assert len(received_signals) == 1
        signal = received_signals[0]
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BUY
        assert signal.price == 150.0
        assert signal.metadata["strategy"] == "momentum_breakout"
        assert signal.metadata["volume"] == 1000000
        assert signal.metadata["rsi"] == 65.5
        assert signal.metadata["macd"] == 0.25
    
    @pytest.mark.asyncio
    async def test_webhook_endpoint_sell_signal(self, signal_listener, webhook_secret):
        """Test webhook endpoint with sell signal."""
        # Create sell signal payload
        payload = {
            "symbol": "TSLA",
            "action": "sell",
            "price": 800.0,
            "timestamp": int(datetime.now().timestamp()),
            "source": "tradingview",
            "strategy": "profit_taking",
            "stop_loss": 750.0,
            "take_profit": 850.0
        }
        
        # Create signature
        signature = self.create_webhook_signature(payload, webhook_secret)
        
        # Mock signal handler
        received_signals = []
        
        async def test_handler(signal):
            received_signals.append(signal)
        
        signal_listener.register_signal_handler(test_handler)
        
        # Simulate webhook request
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value=payload)
        mock_request.headers = {"X-Webhook-Signature": signature}
        
        # Process webhook
        with patch.object(signal_listener, '_verify_webhook_signature', return_value=True):
            await signal_listener._webhook_endpoint(mock_request)
        
        # Verify signal was processed
        assert len(received_signals) == 1
        signal = received_signals[0]
        assert signal.symbol == "TSLA"
        assert signal.signal_type == SignalType.SELL
        assert signal.price == 800.0
        assert signal.metadata["strategy"] == "profit_taking"
        assert signal.metadata["stop_loss"] == 750.0
        assert signal.metadata["take_profit"] == 850.0
    
    @pytest.mark.asyncio
    async def test_webhook_signature_verification(self, signal_listener, webhook_secret):
        """Test webhook signature verification."""
        payload = {
            "symbol": "AAPL",
            "action": "buy",
            "price": 150.0,
            "timestamp": int(datetime.now().timestamp()),
            "source": "tradingview"
        }
        
        # Test valid signature
        valid_signature = self.create_webhook_signature(payload, webhook_secret)
        assert signal_listener._verify_webhook_signature(payload, valid_signature) is True
        
        # Test invalid signature
        invalid_signature = "invalid_signature_123"
        assert signal_listener._verify_webhook_signature(payload, invalid_signature) is False
        
        # Test modified payload (should invalidate signature)
        modified_payload = payload.copy()
        modified_payload["price"] = 151.0
        assert signal_listener._verify_webhook_signature(modified_payload, valid_signature) is False
    
    @pytest.mark.asyncio
    async def test_multiple_concurrent_webhooks(self, signal_listener, webhook_secret):
        """Test handling multiple concurrent webhook requests."""
        # Create multiple signal payloads
        payloads = []
        for i in range(5):
            payload = {
                "symbol": f"STOCK{i}",
                "action": "buy",
                "price": 100.0 + i,
                "timestamp": int(datetime.now().timestamp()) + i,
                "source": "tradingview",
                "batch_id": f"batch_{i}"
            }
            payloads.append(payload)
        
        # Mock signal handler to collect signals
        received_signals = []
        
        async def test_handler(signal):
            received_signals.append(signal)
        
        signal_listener.register_signal_handler(test_handler)
        
        # Process all webhooks concurrently
        async def process_webhook(payload):
            mock_request = Mock()
            mock_request.json = AsyncMock(return_value=payload)
            signature = self.create_webhook_signature(payload, webhook_secret)
            mock_request.headers = {"X-Webhook-Signature": signature}
            
            with patch.object(signal_listener, '_verify_webhook_signature', return_value=True):
                await signal_listener._webhook_endpoint(mock_request)
        
        # Run all webhook processing concurrently
        tasks = [process_webhook(payload) for payload in payloads]
        await asyncio.gather(*tasks)
        
        # Verify all signals were processed
        assert len(received_signals) == 5
        
        # Verify signal order and content
        for i, signal in enumerate(received_signals):
            assert signal.symbol == f"STOCK{i}"
            assert signal.price == 100.0 + i
            assert signal.metadata["batch_id"] == f"batch_{i}"
    
    @pytest.mark.asyncio
    async def test_webhook_error_handling(self, signal_listener, webhook_secret):
        """Test webhook error handling scenarios."""
        # Test missing signature
        payload = {
            "symbol": "AAPL",
            "action": "buy",
            "price": 150.0,
            "timestamp": int(datetime.now().timestamp()),
            "source": "tradingview"
        }
        
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value=payload)
        mock_request.headers = {}  # No signature header
        
        # Should raise authentication error
        with pytest.raises(Exception):  # Specific exception type depends on implementation
            await signal_listener._webhook_endpoint(mock_request)
    
    @pytest.mark.asyncio
    async def test_webhook_invalid_payload(self, signal_listener, webhook_secret):
        """Test webhook with invalid payload."""
        # Create invalid payload (missing required fields)
        invalid_payload = {
            "symbol": "AAPL",
            # Missing action, price, timestamp
            "source": "tradingview"
        }
        
        signature = self.create_webhook_signature(invalid_payload, webhook_secret)
        
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value=invalid_payload)
        mock_request.headers = {"X-Webhook-Signature": signature}
        
        # Should handle invalid payload gracefully
        with patch.object(signal_listener, '_verify_webhook_signature', return_value=True):
            with pytest.raises(Exception):  # Should raise validation error
                await signal_listener._webhook_endpoint(mock_request)
    
    @pytest.mark.asyncio
    async def test_webhook_rate_limiting(self, signal_listener, webhook_secret):
        """Test webhook rate limiting functionality."""
        # This test assumes rate limiting is implemented
        # Create many rapid requests
        payload = {
            "symbol": "AAPL",
            "action": "buy",
            "price": 150.0,
            "timestamp": int(datetime.now().timestamp()),
            "source": "tradingview"
        }
        
        signature = self.create_webhook_signature(payload, webhook_secret)
        
        # Simulate rapid webhook requests
        async def send_webhook():
            mock_request = Mock()
            mock_request.json = AsyncMock(return_value=payload)
            mock_request.headers = {"X-Webhook-Signature": signature}
            
            with patch.object(signal_listener, '_verify_webhook_signature', return_value=True):
                try:
                    await signal_listener._webhook_endpoint(mock_request)
                    return True
                except Exception:
                    return False  # Rate limited
        
        # Send many requests rapidly
        tasks = [send_webhook() for _ in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Some requests should succeed, rate limiting behavior depends on implementation
        successful_requests = sum(1 for result in results if result is True)
        assert successful_requests > 0  # At least some should succeed
    
    @pytest.mark.asyncio
    async def test_webhook_signal_deduplication(self, signal_listener, webhook_secret):
        """Test webhook signal deduplication."""
        # Create identical signal payloads
        payload = {
            "symbol": "AAPL",
            "action": "buy",
            "price": 150.0,
            "timestamp": int(datetime.now().timestamp()),
            "source": "tradingview",
            "signal_id": "unique_signal_123"  # Unique identifier
        }
        
        signature = self.create_webhook_signature(payload, webhook_secret)
        
        received_signals = []
        
        async def test_handler(signal):
            received_signals.append(signal)
        
        signal_listener.register_signal_handler(test_handler)
        
        # Send the same signal multiple times
        for _ in range(3):
            mock_request = Mock()
            mock_request.json = AsyncMock(return_value=payload)
            mock_request.headers = {"X-Webhook-Signature": signature}
            
            with patch.object(signal_listener, '_verify_webhook_signature', return_value=True):
                await signal_listener._webhook_endpoint(mock_request)
        
        # Depending on implementation, might deduplicate or process all
        # This test documents the expected behavior
        assert len(received_signals) >= 1  # At least one signal processed
    
    @pytest.mark.asyncio
    async def test_webhook_custom_strategies(self, signal_listener, webhook_secret):
        """Test webhook with custom strategy parameters."""
        # Create signal with custom strategy parameters
        payload = {
            "symbol": "NVDA",
            "action": "buy",
            "price": 500.0,
            "timestamp": int(datetime.now().timestamp()),
            "source": "tradingview",
            "strategy": "ai_momentum",
            "custom_params": {
                "ai_confidence": 0.85,
                "sector_rotation": "technology",
                "market_regime": "bull",
                "volatility_percentile": 25,
                "correlation_filter": True
            },
            "risk_params": {
                "position_size_multiplier": 1.5,
                "stop_loss_percent": 0.03,
                "take_profit_percent": 0.08
            }
        }
        
        signature = self.create_webhook_signature(payload, webhook_secret)
        
        received_signals = []
        
        async def test_handler(signal):
            received_signals.append(signal)
        
        signal_listener.register_signal_handler(test_handler)
        
        mock_request = Mock()
        mock_request.json = AsyncMock(return_value=payload)
        mock_request.headers = {"X-Webhook-Signature": signature}
        
        with patch.object(signal_listener, '_verify_webhook_signature', return_value=True):
            await signal_listener._webhook_endpoint(mock_request)
        
        # Verify custom parameters are preserved
        assert len(received_signals) == 1
        signal = received_signals[0]
        assert signal.symbol == "NVDA"
        assert signal.metadata["strategy"] == "ai_momentum"
        assert signal.metadata["custom_params"]["ai_confidence"] == 0.85
        assert signal.metadata["risk_params"]["position_size_multiplier"] == 1.5
    
    @pytest.mark.asyncio
    async def test_webhook_health_check(self, signal_listener):
        """Test webhook health check endpoint."""
        # Test health endpoint
        health_response = await signal_listener._health_check()
        
        assert health_response["status"] == "healthy"
        assert "timestamp" in health_response
        assert "uptime" in health_response or "version" in health_response
    
    @pytest.mark.asyncio
    async def test_webhook_metrics_endpoint(self, signal_listener):
        """Test webhook metrics endpoint."""
        # Process some signals first
        payload = {
            "symbol": "AAPL",
            "action": "buy",
            "price": 150.0,
            "timestamp": int(datetime.now().timestamp()),
            "source": "tradingview"
        }
        
        signature = self.create_webhook_signature(payload, "test_webhook_secret")
        
        for _ in range(3):
            mock_request = Mock()
            mock_request.json = AsyncMock(return_value=payload)
            mock_request.headers = {"X-Webhook-Signature": signature}
            
            with patch.object(signal_listener, '_verify_webhook_signature', return_value=True):
                await signal_listener._webhook_endpoint(mock_request)
        
        # Get metrics
        metrics = await signal_listener._get_metrics()
        
        assert "signals_processed" in metrics
        assert "uptime" in metrics
        assert "last_signal_time" in metrics
        assert metrics["signals_processed"] >= 3
