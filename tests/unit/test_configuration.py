"""
Unit tests for ConfigurationManager.
"""

import pytest
import os
import tempfile
import yaml
from unittest.mock import patch, mock_open
from pathlib import Path

from src.core import ConfigurationManager
from src.exceptions import ConfigurationException


class TestConfigurationManager:
    """Test cases for ConfigurationManager class."""
    
    def test_init_with_defaults(self):
        """Test initialization with default values."""
        config = ConfigurationManager()
        assert config.get_config("api.alpaca.base_url") == "https://paper-api.alpaca.markets"
        assert config.get_config("trading.default_quantity") == 100
        assert config.get_config("strategies.averaging_down.enabled") is True
    
    def test_init_with_config_file(self, test_config_file):
        """Test initialization with configuration file."""
        config = ConfigurationManager(test_config_file)
        assert config.get_config("api.alpaca.api_key") == "test_api_key"
        assert config.get_config("api.alpaca.secret_key") == "test_secret_key"
        assert config.get_config("api.webhook.secret") == "test_webhook_secret"
    
    def test_get_config_with_dot_notation(self, test_config_file):
        """Test getting configuration with dot notation."""
        config = ConfigurationManager(test_config_file)
        assert config.get_config("api.alpaca.timeout") == 30
        assert config.get_config("trading.risk_per_trade") == 0.02
        assert config.get_config("strategies.averaging_down.max_attempts") == 3
    
    def test_get_config_with_default(self, test_config_file):
        """Test getting configuration with default value."""
        config = ConfigurationManager(test_config_file)
        assert config.get_config("nonexistent.key", "default_value") == "default_value"
        assert config.get_config("api.nonexistent", None) is None
    
    def test_set_config(self, test_config_file):
        """Test setting configuration values."""
        config = ConfigurationManager(test_config_file)
        config.set_config("api.alpaca.timeout", 60)
        assert config.get_config("api.alpaca.timeout") == 60
        
        config.set_config("new.nested.key", "new_value")
        assert config.get_config("new.nested.key") == "new_value"
    
    def test_set_config_with_type_conversion(self, test_config_file):
        """Test setting configuration with automatic type conversion."""
        config = ConfigurationManager(test_config_file)
        config.set_config("test.bool_true", "true")
        config.set_config("test.bool_false", "false")
        config.set_config("test.int_value", "42")
        config.set_config("test.float_value", "3.14")
        
        assert config.get_config("test.bool_true") is True
        assert config.get_config("test.bool_false") is False
        assert config.get_config("test.int_value") == 42
        assert config.get_config("test.float_value") == 3.14
    
    def test_environment_variable_override(self, test_config_file):
        """Test environment variable override."""
        with patch.dict(os.environ, {
            "TRADING_BOT_ALPACA_API_KEY": "env_api_key",
            "TRADING_BOT_WEBHOOK_PORT": "9090",
            "TRADING_BOT_LOG_LEVEL": "DEBUG"
        }):
            config = ConfigurationManager(test_config_file)
            assert config.get_config("api.alpaca.api_key") == "env_api_key"
            assert config.get_config("api.webhook.port") == 9090
            assert config.get_config("logging.level") == "DEBUG"
    
    def test_reload_config(self, test_config_file):
        """Test configuration reload."""
        config = ConfigurationManager(test_config_file)
        original_timeout = config.get_config("api.alpaca.timeout")
        
        # Modify config
        config.set_config("api.alpaca.timeout", 120)
        assert config.get_config("api.alpaca.timeout") == 120
        
        # Reload should restore original value
        config.reload_config()
        assert config.get_config("api.alpaca.timeout") == original_timeout
    
    def test_get_all_config(self, test_config_file):
        """Test getting all configuration."""
        config = ConfigurationManager(test_config_file)
        all_config = config.get_all_config()
        
        assert isinstance(all_config, dict)
        assert "api" in all_config
        assert "trading" in all_config
        assert "strategies" in all_config
        assert all_config["api"]["alpaca"]["api_key"] == "test_api_key"
    
    def test_validate_required_config_success(self, test_config_file):
        """Test successful validation of required configuration."""
        config = ConfigurationManager(test_config_file)
        # Should not raise exception with valid config
        config.validate_required_config()
    
    def test_validate_required_config_failure(self):
        """Test validation failure with missing required configuration."""
        config = ConfigurationManager()
        with pytest.raises(ConfigurationException) as exc_info:
            config.validate_required_config()
        
        assert "Missing required configuration" in str(exc_info.value)
        assert "api.alpaca.api_key" in str(exc_info.value)
        assert "api.alpaca.secret_key" in str(exc_info.value)
        assert "api.webhook.secret" in str(exc_info.value)
    
    def test_config_file_not_found(self):
        """Test behavior when config file doesn't exist."""
        config = ConfigurationManager("nonexistent.yaml")
        # Should still work with defaults
        assert config.get_config("api.alpaca.base_url") == "https://paper-api.alpaca.markets"
    
    def test_invalid_yaml_file(self):
        """Test behavior with invalid YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            invalid_file = f.name
        
        try:
            config = ConfigurationManager(invalid_file)
            # Should still work with defaults
            assert config.get_config("api.alpaca.base_url") == "https://paper-api.alpaca.markets"
        finally:
            os.unlink(invalid_file)
    
    def test_merge_config_nested(self, test_config_file):
        """Test merging nested configuration."""
        config = ConfigurationManager(test_config_file)
        
        new_config = {
            "api": {
                "alpaca": {
                    "timeout": 90,
                    "new_setting": "test_value"
                }
            },
            "new_section": {
                "setting": "value"
            }
        }
        
        config._merge_config(new_config)
        
        assert config.get_config("api.alpaca.timeout") == 90
        assert config.get_config("api.alpaca.new_setting") == "test_value"
        assert config.get_config("api.alpaca.api_key") == "test_api_key"  # Should preserve
        assert config.get_config("new_section.setting") == "value"
    
    def test_set_nested_value_edge_cases(self, test_config_file):
        """Test setting nested values with edge cases."""
        config = ConfigurationManager(test_config_file)
        
        # Test deep nesting
        config.set_config("a.b.c.d.e", "deep_value")
        assert config.get_config("a.b.c.d.e") == "deep_value"
        
        # Test overwriting existing structure
        config.set_config("api.alpaca", "simple_value")
        assert config.get_config("api.alpaca") == "simple_value"
    
    def test_config_error_handling(self, test_config_file):
        """Test error handling in configuration operations."""
        config = ConfigurationManager(test_config_file)
        
        # Test invalid key format
        with pytest.raises(ConfigurationException):
            config.set_config("", "value")
    
    @patch('builtins.open', mock_open(read_data="corrupted yaml content: [[["))
    def test_corrupted_config_file_handling(self):
        """Test handling of corrupted configuration file."""
        with patch('pathlib.Path.exists', return_value=True):
            config = ConfigurationManager("corrupted.yaml")
            # Should fallback to defaults
            assert config.get_config("api.alpaca.base_url") == "https://paper-api.alpaca.markets"
    
    def test_config_with_none_values(self, test_config_file):
        """Test configuration with None values."""
        config = ConfigurationManager(test_config_file)
        
        # Test setting None
        config.set_config("test.none_value", None)
        assert config.get_config("test.none_value") is None
        
        # Test getting None with default
        assert config.get_config("test.none_value", "default") is None
    
    def test_config_thread_safety(self, test_config_file):
        """Test basic thread safety of configuration operations."""
        import threading
        import time
        
        config = ConfigurationManager(test_config_file)
        results = []
        
        def worker(thread_id):
            for i in range(10):
                config.set_config(f"thread_{thread_id}.value_{i}", f"value_{thread_id}_{i}")
                value = config.get_config(f"thread_{thread_id}.value_{i}")
                results.append(value == f"value_{thread_id}_{i}")
                time.sleep(0.001)
        
        threads = []
        for i in range(5):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # All operations should succeed
        assert all(results)
        assert len(results) == 50  # 5 threads * 10 operations each
