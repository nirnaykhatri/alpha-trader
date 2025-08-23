"""
Test configuration for webhook and integration tests.
"""

import os
from typing import Dict, Any

# Test configuration
TEST_CONFIG = {
    # Webhook test configuration
    "webhook": {
        "host": "127.0.0.1",
        "port": 8081,  # Different from production port
        "timeout": 10,
        "test_payloads": {
            "valid_buy": {
                "symbol": "AAPL",
                "action": "buy",
                "price": 150.0,
                "quantity": 100
            },
            "valid_sell": {
                "symbol": "TSLA", 
                "action": "sell",
                "price": 250.0,
                "quantity": 50
            },
            "short_sell_fail": {
                "symbol": "RGTI",
                "action": "sell",  # This will fail with "cannot be sold short"
                "price": 13.48,
                "quantity": 148
            },
            "invalid": {
                "invalid": "data"
            }
        }
    },
    
    # Performance expectations
    "performance": {
        "max_webhook_response_time": 2.0,  # seconds
        "max_concurrent_requests": 10,
        "callback_timeout": 5.0
    },
    
    # URLs for different environments
    "urls": {
        "local": "http://localhost:8080/webhook",
        "ngrok": os.getenv("WEBHOOK_URL", "https://your-ngrok-url.ngrok-free.app/webhook"),
        "test": "http://127.0.0.1:8081/webhook"
    }
}


def get_test_config(key: str = None) -> Any:
    """Get test configuration value."""
    if key is None:
        return TEST_CONFIG
    
    keys = key.split(".")
    value = TEST_CONFIG
    
    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return None
    
    return value


def get_webhook_url(environment: str = "local") -> str:
    """Get webhook URL for specified environment."""
    return TEST_CONFIG["urls"].get(environment, TEST_CONFIG["urls"]["local"])


def get_test_payload(payload_type: str = "valid_buy") -> Dict[str, Any]:
    """Get test payload by type."""
    return TEST_CONFIG["webhook"]["test_payloads"].get(payload_type, {})
