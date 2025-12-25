"""
Unit tests for ConfigurationManager with Azure-native configuration.

Tests the configuration system that:
- Uses Azure Key Vault for secrets
- Uses Azure App Configuration for runtime settings
- Falls back to environment variables for local development
"""

import pytest
import os
import threading
from unittest.mock import patch, MagicMock

from src.core import ConfigurationManager
from src.config.azure_config_provider import (
    AzureConfigProvider,
    ConfigKeys,
    SecretKeys,
    DEFAULT_CONFIG,
)


@pytest.fixture(autouse=True)
def reset_config_singleton():
    """Reset the ConfigurationManager singleton before each test."""
    ConfigurationManager.reset_instance()
    AzureConfigProvider.reset_instance()
    yield
    ConfigurationManager.reset_instance()
    AzureConfigProvider.reset_instance()


@pytest.fixture
def env_config():
    """Set up environment variables for testing."""
    test_env = {
        "DATABASE_URL": "cosmos://test-account.documents.azure.com/test-db",
        "LOG_LEVEL": "DEBUG",
        "ALPACA_API_KEY": "test-api-key",
        "ALPACA_SECRET_KEY": "test-secret-key",
        "WEBHOOK_PORT": "9090",
        "TRADING_ORDER_TYPE": "market",
    }
    with patch.dict(os.environ, test_env, clear=False):
        yield test_env


class TestConfigurationManager:
    """Test cases for ConfigurationManager class."""
    
    def test_singleton_pattern(self):
        """Test that ConfigurationManager is a singleton."""
        config1 = ConfigurationManager()
        config2 = ConfigurationManager()
        assert config1 is config2
    
    def test_get_config_from_environment(self, env_config):
        """Test getting configuration from environment variables."""
        ConfigurationManager.reset_instance()
        config = ConfigurationManager()
        
        assert config.get_config("database.url") == "cosmos://test-account.documents.azure.com/test-db"
        assert config.get_config("logging.level") == "DEBUG"
    
    def test_get_config_with_default(self):
        """Test getting configuration with default value."""
        config = ConfigurationManager()
        
        assert config.get_config("nonexistent.key", "default_value") == "default_value"
        assert config.get_config("api.nonexistent", None) is None
        assert config.get_config("completely.missing.path", 42) == 42
    
    def test_set_config(self):
        """Test setting configuration values at runtime."""
        config = ConfigurationManager()
        
        # Set a new value
        config.set_config("api.timeout", 60)
        assert config.get_config("api.timeout") == 60
        
        # Set another value
        config.set_config("new.key", "new_value")
        assert config.get_config("new.key") == "new_value"
    
    def test_get_secret_from_environment(self, env_config):
        """Test getting secrets from environment variables."""
        ConfigurationManager.reset_instance()
        config = ConfigurationManager()
        
        assert config.get_secret("alpaca-api-key") == "test-api-key"
        assert config.get_secret("alpaca-secret-key") == "test-secret-key"
    
    def test_get_secret_with_default(self):
        """Test getting secrets with default value."""
        config = ConfigurationManager()
        
        assert config.get_secret("nonexistent-secret", "default") == "default"
        assert config.get_secret("missing-secret") == ""
    
    def test_reload_config(self, env_config):
        """Test configuration reload."""
        ConfigurationManager.reset_instance()
        config = ConfigurationManager()
        
        # Change a value in cache
        config.set_config("database.url", "modified_value")
        assert config.get_config("database.url") == "modified_value"
        
        # Reload should restore from environment
        config.reload_config()
        assert config.get_config("database.url") == "cosmos://test-account.documents.azure.com/test-db"
    
    def test_config_thread_safety(self):
        """Test basic thread safety of configuration operations."""
        config = ConfigurationManager()
        results = []
        errors = []
        
        def worker(thread_id):
            try:
                for i in range(10):
                    key = f"thread_{thread_id}.value_{i}"
                    value = f"value_{thread_id}_{i}"
                    config.set_config(key, value)
                    read_value = config.get_config(key)
                    results.append(read_value == value)
            except Exception as e:
                errors.append(e)
        
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # No errors should occur
        assert len(errors) == 0, f"Thread errors: {errors}"
        # All operations should succeed
        assert all(results), "Some thread operations failed"
        assert len(results) == 50  # 5 threads * 10 operations each
    
    def test_current_environment_default(self):
        """Test default environment is demo."""
        config = ConfigurationManager()
        assert config.current_environment == "demo"
    
    def test_current_environment_from_env_var(self):
        """Test environment from ENVIRONMENT variable."""
        with patch.dict(os.environ, {"ENVIRONMENT": "live"}):
            ConfigurationManager.reset_instance()
            config = ConfigurationManager()
            assert config.current_environment == "live"
    
    def test_is_azure_deployment_false_by_default(self):
        """Test Azure deployment detection when not in Azure."""
        # Ensure Azure env vars are not set
        env_vars_to_remove = ["AZURE_KEYVAULT_URL", "AZURE_APP_CONFIGURATION_ENDPOINT"]
        filtered_env = {k: v for k, v in os.environ.items() if k not in env_vars_to_remove}
        
        with patch.dict(os.environ, filtered_env, clear=True):
            ConfigurationManager.reset_instance()
            config = ConfigurationManager()
            assert config.is_azure_deployment() is False
    
    def test_is_azure_deployment_with_keyvault(self):
        """Test Azure deployment detection with Key Vault configured."""
        with patch.dict(os.environ, {"AZURE_KEYVAULT_URL": "https://test.vault.azure.net"}):
            ConfigurationManager.reset_instance()
            config = ConfigurationManager()
            assert config.is_azure_deployment() is True
    
    def test_is_azure_deployment_with_app_config(self):
        """Test Azure deployment detection with App Config configured."""
        with patch.dict(os.environ, {"AZURE_APP_CONFIGURATION_ENDPOINT": "https://test.azconfig.io"}):
            ConfigurationManager.reset_instance()
            config = ConfigurationManager()
            assert config.is_azure_deployment() is True


class TestConfigurationManagerTypedAccess:
    """Test typed configuration access methods."""
    
    def test_get_alpaca_config(self, env_config):
        """Test getting typed Alpaca configuration."""
        ConfigurationManager.reset_instance()
        config = ConfigurationManager()
        
        alpaca_config = config.get_alpaca_config()
        assert alpaca_config is not None
        assert alpaca_config.api_key == "test-api-key"
        assert alpaca_config.secret_key == "test-secret-key"
        assert alpaca_config.is_configured is True
        assert alpaca_config.is_paper is True  # Default URL is paper
    
    def test_get_alpaca_config_not_configured(self):
        """Test Alpaca config when credentials not set."""
        config = ConfigurationManager()
        
        alpaca_config = config.get_alpaca_config()
        assert alpaca_config.is_configured is False
    
    def test_get_webhook_config(self, env_config):
        """Test getting typed webhook configuration."""
        ConfigurationManager.reset_instance()
        config = ConfigurationManager()
        
        webhook_config = config.get_webhook_config()
        assert webhook_config is not None
        assert webhook_config.port == 9090  # From env var
        assert webhook_config.host == "0.0.0.0"  # Default
        assert webhook_config.security_enabled is True  # Default
    
    def test_get_database_config(self, env_config):
        """Test getting typed database configuration for Cosmos DB."""
        ConfigurationManager.reset_instance()
        config = ConfigurationManager()
        
        db_config = config.get_database_config()
        assert db_config is not None
        assert db_config.throughput_ru == 400  # Default
        assert db_config.consistency_level == "Session"  # Default
    
    def test_get_logging_config(self, env_config):
        """Test getting typed logging configuration."""
        ConfigurationManager.reset_instance()
        config = ConfigurationManager()
        
        log_config = config.get_logging_config()
        assert log_config is not None
        assert log_config.level == "DEBUG"
        assert log_config.format == "json"
    
    def test_get_configured_brokers_with_alpaca(self, env_config):
        """Test getting configured brokers when Alpaca is configured."""
        ConfigurationManager.reset_instance()
        config = ConfigurationManager()
        
        brokers = config.get_configured_brokers()
        assert "alpaca" in brokers
    
    def test_get_configured_brokers_empty(self):
        """Test getting configured brokers when none configured."""
        config = ConfigurationManager()
        
        brokers = config.get_configured_brokers()
        assert isinstance(brokers, list)
    
    def test_get_broker_for_symbol_default(self):
        """Test getting default broker for a symbol."""
        config = ConfigurationManager()
        
        # Default broker should be alpaca
        broker = config.get_broker_for_symbol("AAPL")
        assert broker == "alpaca"


class TestDefaultConfiguration:
    """Test default configuration values."""
    
    def test_default_config_keys_exist(self):
        """Test that all default config keys are defined."""
        # Cosmos DB keys (no DATABASE_URL - using COSMOS_ENDPOINT env var)
        assert ConfigKeys.DATABASE_THROUGHPUT_RU in DEFAULT_CONFIG
        assert ConfigKeys.LOG_LEVEL in DEFAULT_CONFIG
        assert ConfigKeys.WEBHOOK_PORT in DEFAULT_CONFIG
        assert ConfigKeys.TRADING_ORDER_TYPE in DEFAULT_CONFIG
    
    def test_default_config_values(self):
        """Test default configuration values."""
        assert DEFAULT_CONFIG[ConfigKeys.DATABASE_THROUGHPUT_RU] == 400  # Cosmos RU/s
        assert DEFAULT_CONFIG[ConfigKeys.LOG_LEVEL] == "INFO"
        assert DEFAULT_CONFIG[ConfigKeys.WEBHOOK_PORT] == 8080
        assert DEFAULT_CONFIG[ConfigKeys.TRADING_ORDER_TYPE] == "limit"


class TestSecretKeys:
    """Test secret key constants."""
    
    def test_secret_keys_defined(self):
        """Test that all secret keys are defined."""
        assert SecretKeys.ALPACA_API_KEY == "alpaca-api-key"
        assert SecretKeys.ALPACA_SECRET_KEY == "alpaca-secret-key"
        assert SecretKeys.WEBHOOK_SECRET == "webhook-secret"
        # Note: NGROK_AUTH_TOKEN removed - ngrok integration deprecated
