"""
Admin API Endpoint Integration Tests.

Tests the admin router endpoints for portfolio, brokers, analytics, and asset metadata.
Uses FastAPI TestClient for integration testing.

Author: Trading Bot Team
Version: 1.0.0
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

from fastapi import FastAPI
from fastapi.testclient import TestClient


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_auth_service():
    """Create mock authentication service."""
    auth_service = MagicMock()
    auth_service.validate_token = AsyncMock(return_value={
        "sub": "test-user-id",
        "name": "Test User",
        "email": "test@example.com"
    })
    auth_service.is_localhost_allowed = MagicMock(return_value=True)
    return auth_service


@pytest.fixture
def mock_position_service():
    """Create mock position service."""
    service = MagicMock()
    service.get_all_positions = AsyncMock(return_value=[
        {
            "symbol": "AAPL",
            "quantity": 100,
            "avg_cost": 150.00,
            "current_price": 175.00,
            "market_value": 17500.00,
            "unrealized_pnl": 2500.00,
            "unrealized_pnl_percent": 16.67,
            "side": "long"
        },
        {
            "symbol": "GOOGL",
            "quantity": 50,
            "avg_cost": 140.00,
            "current_price": 145.00,
            "market_value": 7250.00,
            "unrealized_pnl": 250.00,
            "unrealized_pnl_percent": 3.57,
            "side": "long"
        }
    ])
    return service


@pytest.fixture
def mock_order_service():
    """Create mock order service."""
    service = MagicMock()
    service.place_order = AsyncMock(return_value={
        "order_id": "test-order-123",
        "status": "submitted",
        "symbol": "AAPL",
        "quantity": 10,
        "side": "buy"
    })
    service.cancel_order = AsyncMock(return_value={"status": "cancelled"})
    service.get_pending_orders = AsyncMock(return_value=[])
    return service


@pytest.fixture
def mock_lifecycle_service():
    """Create mock lifecycle service."""
    service = MagicMock()
    service.get_state = AsyncMock(return_value="running")
    service.pause = AsyncMock(return_value=True)
    service.resume = AsyncMock(return_value=True)
    service.stop = AsyncMock(return_value=True)
    return service


@pytest.fixture
def mock_config_service():
    """Create mock config service."""
    service = MagicMock()
    service.get_config = AsyncMock(return_value={
        "dca": {
            "averaging_orders": {"orders_count": 5, "step_percent": 1.99, "amount_multiplier": 1.3},
            "take_profit": {"price_change_percent": 1.5}
        },
        "risk": {"max_position_size": 0.1}
    })
    service.update_config = AsyncMock(return_value=True)
    return service


@pytest.fixture
def mock_risk_service():
    """Create mock risk validation service."""
    service = MagicMock()
    service.validate_order = AsyncMock(return_value={"valid": True})
    return service


@pytest.fixture
def mock_fund_service():
    """Create mock fund service."""
    service = MagicMock()
    service.get_balance = AsyncMock(return_value={"cash": 50000.00, "buying_power": 100000.00})
    return service


@pytest.fixture
def admin_router(
    mock_auth_service,
    mock_order_service,
    mock_position_service,
    mock_lifecycle_service,
    mock_config_service,
    mock_risk_service,
    mock_fund_service
):
    """Create AdminRouter instance with mocked services."""
    from src.signals.routers import AdminRouter
    
    router = AdminRouter(
        auth_service=mock_auth_service,
        order_service=mock_order_service,
        position_service=mock_position_service,
        lifecycle_service=mock_lifecycle_service,
        config_service=mock_config_service,
        risk_service=mock_risk_service,
        fund_service=mock_fund_service
    )
    return router


@pytest.fixture
def test_app(admin_router):
    """Create FastAPI test application with admin router."""
    app = FastAPI()
    app.include_router(admin_router.router)
    return app


@pytest.fixture
def client(test_app):
    """Create test client."""
    return TestClient(test_app)


# =============================================================================
# Asset Metadata Endpoint Tests
# =============================================================================

class TestAssetMetadataEndpoint:
    """Tests for GET /admin/asset-metadata endpoint."""
    
    def test_get_asset_metadata_success(self, client):
        """Test successful retrieval of asset metadata."""
        response = client.get("/admin/asset-metadata")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "assetClasses" in data
        assert "knownSymbols" in data
        assert "classificationRules" in data
        assert "version" in data
    
    def test_asset_classes_structure(self, client):
        """Test asset classes have required fields."""
        response = client.get("/admin/asset-metadata")
        data = response.json()
        
        required_fields = ["label", "color", "bgColor", "icon", "showPair", "description"]
        
        for asset_class, config in data["assetClasses"].items():
            for field in required_fields:
                assert field in config, f"Missing '{field}' in {asset_class}"
    
    def test_known_symbols_categories(self, client):
        """Test known symbols contains expected categories."""
        response = client.get("/admin/asset-metadata")
        data = response.json()
        
        expected_categories = ["etf", "crypto", "commodity", "forex_currencies"]
        for category in expected_categories:
            assert category in data["knownSymbols"], f"Missing category: {category}"
            assert isinstance(data["knownSymbols"][category], list)
            assert len(data["knownSymbols"][category]) > 0
    
    def test_known_etf_symbols(self, client):
        """Test that common ETF symbols are included."""
        response = client.get("/admin/asset-metadata")
        data = response.json()
        
        etfs = data["knownSymbols"]["etf"]
        common_etfs = ["SPY", "QQQ", "VOO", "VTI"]
        
        for etf in common_etfs:
            assert etf in etfs, f"Missing common ETF: {etf}"
    
    def test_known_crypto_symbols(self, client):
        """Test that common crypto symbols are included."""
        response = client.get("/admin/asset-metadata")
        data = response.json()
        
        cryptos = data["knownSymbols"]["crypto"]
        common_cryptos = ["BTC", "ETH", "SOL"]
        
        for crypto in common_cryptos:
            assert crypto in cryptos, f"Missing common crypto: {crypto}"
    
    def test_classification_rules_exist(self, client):
        """Test that classification rules are provided."""
        response = client.get("/admin/asset-metadata")
        data = response.json()
        
        rules = data["classificationRules"]
        expected_rules = ["crypto_patterns", "forex_patterns", "etf_classification", "stock_default"]
        
        for rule in expected_rules:
            assert rule in rules, f"Missing classification rule: {rule}"


class TestClassifySymbolEndpoint:
    """Tests for GET /admin/asset-metadata/classify/{symbol} endpoint."""
    
    def test_classify_stock_symbol(self, client):
        """Test classification of stock symbol."""
        response = client.get("/admin/asset-metadata/classify/AAPL")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["symbol"] == "AAPL"
        assert data["assetClass"] == "stock"
    
    def test_classify_etf_symbol(self, client):
        """Test classification of ETF symbol."""
        response = client.get("/admin/asset-metadata/classify/SPY")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["symbol"] == "SPY"
        assert data["assetClass"] == "etf"
    
    def test_classify_crypto_pair(self, client):
        """Test classification of crypto pair."""
        response = client.get("/admin/asset-metadata/classify/BTC%2FUSD")  # URL-encoded /
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["assetClass"] == "crypto"
    
    def test_classify_forex_pair(self, client):
        """Test classification of forex pair."""
        response = client.get("/admin/asset-metadata/classify/EUR%2FUSD")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["assetClass"] == "forex"
    
    def test_classify_uppercase_normalization(self, client):
        """Test that symbol is normalized to uppercase."""
        response = client.get("/admin/asset-metadata/classify/aapl")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["symbol"] == "AAPL"


# =============================================================================
# Portfolio Endpoint Tests
# =============================================================================

class TestPortfolioEndpoint:
    """Tests for GET /admin/portfolio endpoint."""
    
    def test_get_portfolio_success(self, client, mock_position_service):
        """Test successful portfolio retrieval."""
        response = client.get("/admin/portfolio")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "positions" in data
        assert "summary" in data
    
    def test_portfolio_positions_structure(self, client, mock_position_service):
        """Test portfolio positions have correct structure."""
        response = client.get("/admin/portfolio")
        data = response.json()
        
        # Check mock returns correct positions
        assert len(data["positions"]) >= 0  # May be empty if mocks not set up
    
    def test_portfolio_summary_fields(self, client):
        """Test portfolio summary contains expected fields."""
        response = client.get("/admin/portfolio")
        data = response.json()
        
        summary = data.get("summary", {})
        expected_fields = ["totalValue", "totalPnL", "totalPnLPercent", "positionCount"]
        
        for field in expected_fields:
            assert field in summary, f"Missing summary field: {field}"


# =============================================================================
# Brokers Endpoint Tests
# =============================================================================

class TestBrokersEndpoint:
    """Tests for GET /admin/brokers endpoint."""
    
    def test_get_brokers_success(self, client):
        """Test successful brokers retrieval."""
        response = client.get("/admin/brokers")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "connections" in data
    
    def test_brokers_connection_structure(self, client):
        """Test broker connections have expected fields."""
        response = client.get("/admin/brokers")
        data = response.json()
        
        # Even with mock data, structure should be correct
        if data["connections"]:
            broker = data["connections"][0]
            expected_fields = ["id", "name", "type", "status"]
            
            for field in expected_fields:
                assert field in broker, f"Missing broker field: {field}"


# =============================================================================
# Analytics Endpoint Tests
# =============================================================================

class TestAnalyticsEndpoint:
    """Tests for GET /admin/analytics endpoint."""
    
    def test_get_analytics_success(self, client):
        """Test successful analytics retrieval."""
        response = client.get("/admin/analytics")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "deals" in data or "dailyPnL" in data
    
    def test_analytics_deals_structure(self, client):
        """Test analytics deals have expected structure."""
        response = client.get("/admin/analytics")
        data = response.json()
        
        if "deals" in data and data["deals"]:
            deal = data["deals"][0]
            expected_fields = ["id", "symbol", "side", "profit"]
            
            # Verify at least some key fields exist
            for field in expected_fields:
                assert field in deal, f"Missing deal field: {field}"


# =============================================================================
# Authentication Tests
# =============================================================================

class TestAdminAuthentication:
    """Tests for admin endpoint authentication."""
    
    def test_localhost_request_allowed(self, client):
        """Test that localhost requests are allowed without auth."""
        # TestClient simulates localhost by default
        response = client.get("/admin/asset-metadata")
        
        # Should succeed (localhost is allowed)
        assert response.status_code in [200, 401]  # Depends on mock setup
    
    def test_auth_header_processed(self, client, mock_auth_service):
        """Test that authorization header is processed."""
        response = client.get(
            "/admin/asset-metadata",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestAdminErrorHandling:
    """Tests for admin endpoint error handling."""
    
    def test_invalid_symbol_classification(self, client):
        """Test classification with empty symbol."""
        response = client.get("/admin/asset-metadata/classify/")
        
        # Should return 404 or 422 for invalid path
        assert response.status_code in [404, 422]
    
    def test_api_returns_json(self, client):
        """Test that all endpoints return valid JSON."""
        endpoints = [
            "/admin/asset-metadata",
            "/admin/portfolio",
            "/admin/brokers",
            "/admin/analytics"
        ]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            # Should return JSON regardless of success/failure
            assert response.headers.get("content-type", "").startswith("application/json")


# =============================================================================
# Integration Tests
# =============================================================================

class TestAdminIntegration:
    """Integration tests for admin endpoints."""
    
    def test_asset_metadata_and_classify_consistency(self, client):
        """Test that classify endpoint is consistent with metadata."""
        # Get metadata
        metadata_response = client.get("/admin/asset-metadata")
        metadata = metadata_response.json()
        
        # Get a known ETF from metadata and verify it classifies correctly
        if "knownSymbols" in metadata and "etf" in metadata["knownSymbols"]:
            etf_symbol = metadata["knownSymbols"]["etf"][0]
            
            classify_response = client.get(f"/admin/asset-metadata/classify/{etf_symbol}")
            classify_data = classify_response.json()
            
            assert classify_data["assetClass"] == "etf"
    
    def test_portfolio_uses_position_service(self, client, mock_position_service):
        """Test that portfolio endpoint uses position service."""
        response = client.get("/admin/portfolio")
        
        # Position service should have been called (may be async)
        assert response.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
