#!/usr/bin/env python3
"""
Test Configuration Module

Provides configuration helpers for webhook and integration tests.
Reads from the Azure-native configuration system with environment variable fallback.

This module provides:
- get_webhook_url(mode): Get webhook URL for local or ngrok mode
- get_test_config(): Get complete test configuration dict
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Try to import from the project's config system
try:
    from src.core import ConfigurationManager
    HAS_CONFIG_MANAGER = True
except ImportError:
    HAS_CONFIG_MANAGER = False


def _get_config_manager() -> Optional[ConfigurationManager]:
    """Get the ConfigurationManager instance if available."""
    if not HAS_CONFIG_MANAGER:
        return None
    try:
        return ConfigurationManager()
    except Exception:
        return None


def get_webhook_url(mode: str = "local") -> str:
    """
    Get the webhook URL for testing.

    Args:
        mode: Either "local" for localhost or "ngrok" for ngrok tunnel

    Returns:
        The webhook URL string

    Examples:
        >>> get_webhook_url("local")
        'http://localhost:8080/webhook'
        >>> get_webhook_url("ngrok")
        'https://your-ngrok-url.ngrok-free.app/webhook'
    """
    # Check environment variables first (highest priority)
    env_url = os.environ.get("TEST_WEBHOOK_URL")
    if env_url:
        return env_url

    # Get port from config or default
    port = 8080
    host = "localhost"

    config_mgr = _get_config_manager()
    if config_mgr:
        try:
            port = config_mgr.get_config("api.webhook.port", 8080)
            webhook_host = config_mgr.get_config("api.webhook.host", "0.0.0.0")
            # Convert 0.0.0.0 to localhost for testing
            if webhook_host == "0.0.0.0":
                host = "localhost"
            else:
                host = webhook_host
        except Exception:
            pass

    if mode == "ngrok":
        # Check for ngrok URL in environment
        ngrok_url = os.environ.get("NGROK_URL")
        if ngrok_url:
            # Ensure it ends with /webhook
            if not ngrok_url.endswith("/webhook"):
                return f"{ngrok_url.rstrip('/')}/webhook"
            return ngrok_url

        # Try to detect running ngrok tunnel
        try:
            import requests
            response = requests.get("http://localhost:4040/api/tunnels", timeout=2)
            if response.status_code == 200:
                tunnels = response.json().get("tunnels", [])
                for tunnel in tunnels:
                    if tunnel.get("proto") == "https":
                        public_url = tunnel.get("public_url", "")
                        return f"{public_url}/webhook"
        except Exception:
            pass

        # Fallback placeholder
        return "https://your-ngrok-url.ngrok-free.app/webhook"

    # Local mode
    return f"http://{host}:{port}/webhook"


def get_test_config() -> Dict[str, Any]:
    """
    Get the complete test configuration dictionary.

    Returns:
        Dict containing test configuration values including:
        - webhook_url: The webhook URL for testing
        - webhook_port: The webhook server port
        - webhook_host: The webhook server host
        - timeout: Request timeout in seconds
        - max_retries: Maximum retry attempts
        - test_symbols: List of symbols to use in tests

    Example:
        >>> config = get_test_config()
        >>> print(config['webhook_url'])
        'http://localhost:8080/webhook'
    """
    config: Dict[str, Any] = {
        "webhook_url": get_webhook_url("local"),
        "webhook_port": 8080,
        "webhook_host": "localhost",
        "timeout": 30,
        "max_retries": 3,
        "retry_delay": 1.0,
        "test_symbols": ["AAPL", "GOOGL", "MSFT", "TSLA"],
    }

    # Try to get values from the configuration
    config_mgr = _get_config_manager()
    if config_mgr:
        try:
            webhook_config = config_mgr.get_webhook_config()
            config["webhook_port"] = webhook_config.port
            config["webhook_host"] = "localhost" if webhook_config.host == "0.0.0.0" else webhook_config.host
            config["timeout"] = config_mgr.get_config("api.timeout", 30)
            config["max_retries"] = config_mgr.get_config("api.max_retries", 3)
            config["retry_delay"] = config_mgr.get_config("api.retry_delay", 1.0)

            # Update webhook URL with correct port
            config["webhook_url"] = f"http://{config['webhook_host']}:{config['webhook_port']}/webhook"

        except Exception:
            pass

    # Override with environment variables if set
    if os.environ.get("TEST_WEBHOOK_URL"):
        config["webhook_url"] = os.environ["TEST_WEBHOOK_URL"]
    if os.environ.get("TEST_WEBHOOK_PORT"):
        config["webhook_port"] = int(os.environ["TEST_WEBHOOK_PORT"])
    if os.environ.get("TEST_TIMEOUT"):
        config["timeout"] = int(os.environ["TEST_TIMEOUT"])

    return config


def get_sample_webhook_payload(
    symbol: str = "AAPL",
    action: str = "buy",
    price: Optional[float] = None,
    quantity: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Generate a sample webhook payload for testing.

    Args:
        symbol: Stock symbol (default: AAPL)
        action: Trade action - 'buy' or 'sell' (default: buy)
        price: Optional price override
        quantity: Optional quantity override

    Returns:
        Dict containing the webhook payload

    Example:
        >>> payload = get_sample_webhook_payload("TSLA", "sell", 250.50)
        >>> print(payload)
        {'symbol': 'TSLA', 'action': 'sell', 'price': 250.50, ...}
    """
    import time

    payload: Dict[str, Any] = {
        "symbol": symbol,
        "action": action,
        "timestamp": int(time.time()),
    }

    if price is not None:
        payload["price"] = price
    if quantity is not None:
        payload["quantity"] = quantity

    return payload


# Convenience aliases for backward compatibility
def get_local_webhook_url() -> str:
    """Get the local webhook URL."""
    return get_webhook_url("local")


def get_ngrok_webhook_url() -> str:
    """Get the ngrok webhook URL."""
    return get_webhook_url("ngrok")


if __name__ == "__main__":
    # Quick test of the configuration
    print("Test Configuration Module")
    print("=" * 50)
    print(f"Local Webhook URL: {get_webhook_url('local')}")
    print(f"Ngrok Webhook URL: {get_webhook_url('ngrok')}")
    print()
    print("Full Test Config:")
    config = get_test_config()
    for key, value in config.items():
        print(f"  {key}: {value}")
