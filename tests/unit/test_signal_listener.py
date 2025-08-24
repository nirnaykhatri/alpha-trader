"""
Unit tests for TradingViewSignalListener.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
import json
import hashlib
import hmac
from datetime import datetime
try:
    from fastapi.testclient import TestClient
    from fastapi import HTTPException
except ImportError:
    # Mock FastAPI components if not available
    TestClient = Mock
    HTTPException = Mock

from src.signals.signal_listener import TradingViewSignalListener
from src.core.configuration import ConfigurationManager
from src.exceptions import SignalProcessingException, ValidationException, SignalException
from src.interfaces import TradingSignal, SignalType


class TestTradingViewSignalListener:
    """Test cases for TradingViewSignalListener class."""
    
    @pytest.fixture
    def config_manager(self, test_config_file):
        """Configuration manager for testing."""
        return ConfigurationManager(test_config_file)
    
    @pytest.fixture
    def mock_callback(self):
        """Mock callback function for testing."""
        return AsyncMock()
    
    @pytest.fixture
    def signal_listener(self, config_manager, mock_callback):
        """Signal listener instance for testing."""
        return TradingViewSignalListener(config_manager, mock_callback)
    
    @pytest.fixture
    def test_client(self, signal_listener):
        """Test client for FastAPI app."""
        return TestClient(signal_listener._app)

    def test_init(self, signal_listener):
        """Test initialization of signal listener."""
        assert signal_listener._config is not None
        assert signal_listener._app is not None
        assert signal_listener._signal_callback is not None
        assert signal_listener._secret == "test_webhook_secret"
        assert signal_listener._host == "0.0.0.0"
        assert signal_listener._port == 8080
        assert not signal_listener._is_running

    def test_verify_signature_valid(self, signal_listener):
        """Test valid webhook signature verification."""
        body = b'{"test": "data"}'
        signature = "sha256=" + hmac.new(
            "test_webhook_secret".encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        is_valid = signal_listener._verify_signature(body, signature)
        assert is_valid is True

    def test_verify_signature_invalid(self, signal_listener):
        """Test invalid webhook signature verification."""
        body = b'{"test": "data"}'
        invalid_signature = "sha256=invalid_signature"
        
        is_valid = signal_listener._verify_signature(body, invalid_signature)
        assert is_valid is False

    def test_verify_signature_missing(self, signal_listener):
        """Test missing webhook signature."""
        body = b'{"test": "data"}'
        
        is_valid = signal_listener._verify_signature(body, "")
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_process_signal_buy(self, signal_listener):
        """Test processing buy signal."""
        signal_data = {
            "ticker": "AAPL",
            "signal": "buy",
            "price": 150.0,
            "quantity": 100,
            "interval": "1h"
        }
        
        signal = await signal_listener.process_signal(signal_data)
        
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.BUY
        assert signal.price == 150.0
        assert signal.quantity == 100.0
        # Metadata should include original data plus extracted timeframe
        expected_metadata = signal_data.copy()
        expected_metadata['interval'] = '1h'  # Default interval
        assert signal.metadata == expected_metadata

    @pytest.mark.asyncio
    async def test_process_signal_sell(self, signal_listener):
        """Test processing sell signal."""
        signal_data = {
            "ticker": "TSLA",
            "signal": "sell",
            "price": 800.0,
            "interval": "4h"
        }
        
        signal = await signal_listener.process_signal(signal_data)
        
        assert signal.symbol == "TSLA"
        assert signal.signal_type == SignalType.SELL
        assert signal.price == 800.0
        assert signal.quantity is None
        # Metadata should include original data plus extracted interval
        expected_metadata = signal_data.copy()
        expected_metadata['interval'] = '4h'
        assert signal.metadata == expected_metadata
    
    @pytest.mark.asyncio
    async def test_process_signal_invalid_action(self, signal_listener):
        """Test processing signal with invalid signal."""
        signal_data = {
            "ticker": "AAPL",
            "signal": "invalid_action",
            "price": 150.0
        }
        
        with pytest.raises(SignalProcessingException) as exc_info:
            await signal_listener.process_signal(signal_data)
        
        assert "Invalid signal" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_signal_missing_fields(self, signal_listener):
        """Test processing signal with missing required fields."""
        signal_data = {
            "ticker": "AAPL",
            "signal": "buy"
            # Missing price
        }
        
        with pytest.raises(SignalProcessingException) as exc_info:
            await signal_listener.process_signal(signal_data)
        
        assert "Missing required field" in str(exc_info.value)

    def test_health_endpoint(self, test_client):
        """Test health check endpoint."""
        response = test_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_root_endpoint(self, test_client):
        """Test root endpoint."""
        response = test_client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "TradingView Signal Listener"
        assert data["version"] == "1.0.0"

    def test_webhook_endpoint_missing_signature(self, test_client):
        """Test webhook endpoint with missing signature."""
        payload = {
            "ticker": "AAPL",
            "signal": "buy",
            "price": 150.0,
            "interval": "1h"
        }
        
        response = test_client.post("/webhook", json=payload)
        
        assert response.status_code == 401
        assert "Invalid signature" in response.json()["detail"]

    def test_webhook_endpoint_invalid_signature(self, test_client):
        """Test webhook endpoint with invalid signature."""
        payload = {
            "symbol": "AAPL",
            "action": "buy",
            "price": 150.0
        }
        
        headers = {"X-Signature": "sha256=invalid_signature"}
        response = test_client.post("/webhook", json=payload, headers=headers)
        
        assert response.status_code == 401
        assert "Invalid signature" in response.json()["detail"]

    def test_webhook_endpoint_valid_signature(self, test_client, signal_listener):
        """Test webhook endpoint with valid signature."""
        payload = {
            "symbol": "AAPL",
            "action": "buy",
            "price": 150.0
        }
        
        # Create valid signature by simulating how FastAPI creates the body
        import json
        payload_json = json.dumps(payload, separators=(',', ':'))
        body = payload_json.encode()
        signature = "sha256=" + hmac.new(
            "test_webhook_secret".encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        headers = {"X-Signature": signature}
        
        with patch.object(signal_listener, '_signal_callback', new_callable=AsyncMock) as mock_callback:
            # Use the raw body in the request
            response = test_client.post("/webhook", content=body, headers={**headers, "Content-Type": "application/json"})
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert "signal_id" in data

    @pytest.mark.asyncio
    async def test_start_listening(self, signal_listener):
        """Test starting the listener."""
        with patch('uvicorn.Server') as mock_server_class:
            mock_server = Mock()
            mock_server.serve = AsyncMock()
            mock_server_class.return_value = mock_server
            
            # Start listening in background
            task = asyncio.create_task(signal_listener.start_listening())
            
            # Wait a bit for the server to start
            await asyncio.sleep(0.1)
            
            # Stop the server
            signal_listener._server.should_exit = True
            await task
            
            assert signal_listener._is_running

    @pytest.mark.asyncio
    async def test_stop_listening(self, signal_listener):
        """Test stopping the listener."""
        # Mock server
        mock_server = Mock()
        mock_server.should_exit = False
        mock_server.shutdown = AsyncMock()
        
        signal_listener._server = mock_server
        signal_listener._is_running = True
        
        await signal_listener.stop_listening()
        
        assert mock_server.should_exit is True
        mock_server.shutdown.assert_called_once()
        assert not signal_listener._is_running

    def test_is_running_property(self, signal_listener):
        """Test is_running property."""
        assert signal_listener.is_running is False
        
        signal_listener._is_running = True
        assert signal_listener.is_running is True

    def test_validate_signal_data_valid(self, signal_listener):
        """Test validation of valid signal data."""
        signal_data = {
            "symbol": "AAPL",
            "action": "buy",
            "price": 150.0,
            "quantity": 100
        }
        
        # Should not raise exception
        signal_listener._validate_signal_data(signal_data)

    def test_validate_signal_data_missing_symbol(self, signal_listener):
        """Test validation with missing symbol."""
        signal_data = {
            "action": "buy",
            "price": 150.0
        }
        
        with pytest.raises(ValidationException) as exc_info:
            signal_listener._validate_signal_data(signal_data)
        
        assert "Missing required field: symbol" in str(exc_info.value)

    def test_validate_signal_data_invalid_price(self, signal_listener):
        """Test validation with invalid price."""
        signal_data = {
            "symbol": "AAPL",
            "action": "buy",
            "price": -150.0
        }
        
        with pytest.raises(ValidationException) as exc_info:
            signal_listener._validate_signal_data(signal_data)
        
        assert "Price must be positive" in str(exc_info.value)

    def test_convert_action_to_signal_type(self, signal_listener):
        """Test conversion of action strings to signal types."""
        assert signal_listener._convert_action_to_signal_type("buy") == SignalType.BUY
        assert signal_listener._convert_action_to_signal_type("long") == SignalType.BUY
        assert signal_listener._convert_action_to_signal_type("sell") == SignalType.SELL
        assert signal_listener._convert_action_to_signal_type("short") == SignalType.SELL
        assert signal_listener._convert_action_to_signal_type("close") == SignalType.CLOSE
        assert signal_listener._convert_action_to_signal_type("exit") == SignalType.CLOSE
        assert signal_listener._convert_action_to_signal_type("unknown") == SignalType.BUY

    @pytest.mark.asyncio
    async def test_call_callback_safely_async(self, signal_listener):
        """Test calling async callback safely."""
        mock_callback = AsyncMock()
        signal_listener._signal_callback = mock_callback
        
        signal = TradingSignal(
            signal_id="test-123",
            symbol="AAPL",
            signal_type=SignalType.BUY,
            price=150.0,
            timestamp=datetime.utcnow(),
            metadata={}
        )
        
        await signal_listener._call_callback_safely(signal)
        
        mock_callback.assert_called_once_with(signal)

    @pytest.mark.asyncio
    async def test_call_callback_safely_sync(self, signal_listener):
        """Test calling sync callback safely."""
        mock_callback = Mock()
        signal_listener._signal_callback = mock_callback
        
        signal = TradingSignal(
            signal_id="test-123",
            symbol="AAPL",
            signal_type=SignalType.BUY,
            price=150.0,
            timestamp=datetime.utcnow(),
            metadata={}
        )
        
        await signal_listener._call_callback_safely(signal)
        
        mock_callback.assert_called_once_with(signal)

    @pytest.mark.asyncio
    async def test_call_callback_safely_exception(self, signal_listener):
        """Test callback exception handling."""
        mock_callback = AsyncMock(side_effect=Exception("Test error"))
        signal_listener._signal_callback = mock_callback
        
        signal = TradingSignal(
            signal_id="test-123",
            symbol="AAPL",
            signal_type=SignalType.BUY,
            price=150.0,
            timestamp=datetime.utcnow(),
            metadata={}
        )
        
        # Should not raise exception
        await signal_listener._call_callback_safely(signal)
        
        mock_callback.assert_called_once_with(signal)

    def test_webhook_endpoint_invalid_json(self, test_client):
        """Test webhook endpoint with invalid JSON."""
        # Create valid signature for invalid JSON
        body = b'{"invalid": json}'
        signature = "sha256=" + hmac.new(
            "test_webhook_secret".encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        headers = {"X-Signature": signature}
        
        response = test_client.post("/webhook", data=body, headers=headers)
        
        assert response.status_code == 400
        assert "Invalid JSON" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_process_signal_with_quantity(self, signal_listener):
        """Test processing signal with quantity."""
        signal_data = {
            "symbol": "GOOGL",
            "action": "buy",
            "price": 2500.0,
            "quantity": 50
        }
        
        signal = await signal_listener.process_signal(signal_data)
        
        assert signal.symbol == "GOOGL"
        assert signal.signal_type == SignalType.BUY
        assert signal.price == 2500.0
        assert signal.quantity == 50.0
        # Metadata should include original data plus extracted timeframe
        expected_metadata = signal_data.copy()
        expected_metadata['timeframe'] = '1h'  # Default timeframe
        assert signal.metadata == expected_metadata

    @pytest.mark.asyncio
    async def test_process_signal_close_action(self, signal_listener):
        """Test processing close signal."""
        signal_data = {
            "symbol": "MSFT",
            "action": "close",
            "price": 300.0
        }
        
        signal = await signal_listener.process_signal(signal_data)
        
        assert signal.symbol == "MSFT"
        assert signal.signal_type == SignalType.CLOSE
        assert signal.price == 300.0
        assert signal.quantity is None
        # Metadata should include original data plus extracted timeframe
        expected_metadata = signal_data.copy()
        expected_metadata['timeframe'] = '1h'  # Default timeframe
        assert signal.metadata == expected_metadata

    def test_validate_signal_data_invalid_quantity(self, signal_listener):
        """Test validation with invalid quantity."""
        signal_data = {
            "symbol": "AAPL",
            "action": "buy",
            "price": 150.0,
            "quantity": -10
        }
        
        with pytest.raises(ValidationException) as exc_info:
            signal_listener._validate_signal_data(signal_data)
        
        assert "Quantity must be positive" in str(exc_info.value)

    def test_validate_signal_data_empty_symbol(self, signal_listener):
        """Test validation with empty symbol."""
        signal_data = {
            "symbol": "",
            "action": "buy",
            "price": 150.0
        }
        
        with pytest.raises(ValidationException) as exc_info:
            signal_listener._validate_signal_data(signal_data)
        
        assert "Symbol must be a non-empty string" in str(exc_info.value)
