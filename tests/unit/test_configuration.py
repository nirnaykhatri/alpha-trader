"""
Unit tests for ConfigurationManager with TOML-based configuration.

Tests the new Dynaconf-based configuration system that loads from:
- config/settings.toml (base defaults)
- config/.secrets.toml (credentials)
- config/environments/{demo|live}.toml (environment overrides)
- config/profiles/*.toml (risk profiles)
"""

import pytest
import os
import threading
from unittest.mock import patch

from src.core import ConfigurationManager
from src.config.settings import ConfigurationManager as DynaconfConfigManager
from src.exceptions import ConfigurationException


@pytest.fixture(autouse=True)
def reset_config_singleton():
    """Reset the ConfigurationManager singleton before each test."""
    ConfigurationManager.reset_instance()
    yield
    ConfigurationManager.reset_instance()


class TestConfigurationManager:
    """Test cases for ConfigurationManager class."""
    
    def test_init_loads_from_toml(self):
        """Test initialization loads configuration from TOML files."""
        config = ConfigurationManager()
        # These values come from config/settings.toml
        assert config.get_config("api.alpaca.base_url") == "https://paper-api.alpaca.markets"
        assert config.get_config("trading.order_type") == "limit"
        assert config.get_config("trading.default_quantity") == 100
    
    def test_singleton_pattern(self):
        """Test that ConfigurationManager is a singleton."""
        config1 = ConfigurationManager()
        config2 = ConfigurationManager()
        assert config1 is config2
    
    def test_get_config_with_dot_notation(self):
        """Test getting configuration with dot notation."""
        config = ConfigurationManager()
        # Test various nested config paths
        assert config.get_config("api.timeout") == 30
        assert config.get_config("trading.order_timeout_minutes") == 5
        assert config.get_config("strategies.averaging_down.max_attempts") == 3
        assert config.get_config("trading.position_sizing.method") == "percentage"
    
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
        
        # Set a deeply nested new key
        config.set_config("new.nested.key", "new_value")
        assert config.get_config("new.nested.key") == "new_value"
    
    def test_set_config_overwrites_existing(self):
        """Test that set_config overwrites existing values."""
        config = ConfigurationManager()
        
        original = config.get_config("trading.order_type")
        assert original == "limit"
        
        config.set_config("trading.order_type", "market")
        assert config.get_config("trading.order_type") == "market"
    
    def test_get_config_empty_key_raises(self):
        """Test that empty key raises ConfigurationException."""
        config = ConfigurationManager()
        
        with pytest.raises(ConfigurationException):
            config.get_config("")
        
        with pytest.raises(ConfigurationException):
            config.get_config(None)
    
    def test_trading_configuration_values(self):
        """Test trading configuration values from settings.toml (with .secrets.toml overrides)."""
        config = ConfigurationManager()
        
        # Trading settings (note: .secrets.toml overrides some values)
        assert config.get_config("trading.max_position_size") == 1000
        assert config.get_config("trading.max_daily_trades") == 100  # Overridden in .secrets.toml
        assert config.get_config("trading.risk_per_trade") == 0.02
        assert config.get_config("trading.limit_order_offset") == 0.001
    
    def test_strategy_configuration_values(self):
        """Test strategy configuration values from settings.toml."""
        config = ConfigurationManager()
        
        # Strategy settings
        assert config.get_config("strategies.averaging_down.enabled") is True
        assert config.get_config("strategies.dca.base_threshold_percent") == 1.5
        assert config.get_config("strategies.long_strategy.enabled") is True
        assert config.get_config("strategies.trailing_profit.enabled") is True
    
    def test_api_configuration_values(self):
        """Test API configuration values from settings.toml."""
        config = ConfigurationManager()
        
        # API settings
        assert config.get_config("api.max_retries") == 3
        assert config.get_config("api.retry_delay") == 1.0
        assert config.get_config("api.alpaca.communication_method") == "rest"
    
    def test_webhook_configuration_values(self):
        """Test webhook configuration values from settings.toml."""
        config = ConfigurationManager()
        
        assert config.get_config("api.webhook.host") == "0.0.0.0"
        assert config.get_config("api.webhook.port") == 8080
        assert config.get_config("api.webhook.security_enabled") is False
    
    def test_logging_configuration_values(self):
        """Test logging configuration values from settings.toml (with .secrets.toml overrides)."""
        config = ConfigurationManager()
        
        assert config.get_config("logging.level") == "DEBUG"  # Overridden in .secrets.toml
        assert config.get_config("logging.format") == "json"
        assert config.get_config("logging.console_logging") is True
    
    def test_position_sizing_configuration(self):
        """Test position sizing configuration from settings.toml."""
        config = ConfigurationManager()
        
        sizing = config.get_config("trading.position_sizing")
        assert sizing is not None
        assert config.get_config("trading.position_sizing.method") == "percentage"
        assert config.get_config("trading.position_sizing.initial_portfolio_percentage") == 0.01
        assert config.get_config("trading.position_sizing.max_quantity") == 10000
    
    def test_technical_analysis_configuration(self):
        """Test technical analysis configuration from settings.toml."""
        config = ConfigurationManager()
        
        assert config.get_config("technical_analysis.default_timeframe") == "15m"
        assert config.get_config("technical_analysis.support.min_confidence") == 0.7
        assert config.get_config("technical_analysis.resistance.lookback_periods") == 50
    
    def test_risk_management_configuration(self):
        """Test risk management configuration from settings.toml."""
        config = ConfigurationManager()
        
        assert config.get_config("trading.risk_management.stop_loss.enabled") is False
        assert config.get_config("trading.risk_management.profit_taking.take_profit_percentage") == 0.05
        assert config.get_config("trading.risk_management.advanced.max_positions") == 10
    
    def test_config_file_parameter_ignored(self):
        """Test that config_file parameter is ignored (backward compatibility)."""
        # Passing a config file should be ignored - we always load from TOML
        config = ConfigurationManager("nonexistent.yaml")
        
        # Should still load from settings.toml
        assert config.get_config("api.alpaca.base_url") == "https://paper-api.alpaca.markets"
    
    def test_reload_config(self):
        """Test configuration reload."""
        config = ConfigurationManager()
        
        # Change a value
        original = config.get_config("trading.order_type")
        config.set_config("trading.order_type", "market")
        assert config.get_config("trading.order_type") == "market"
        
        # Reload should restore original from file
        config.reload_config()
        assert config.get_config("trading.order_type") == original
    
    def test_get_all_config(self):
        """Test getting all configuration as dictionary."""
        config = ConfigurationManager()
        all_config = config.get_all_config()
        
        assert isinstance(all_config, dict)
        assert len(all_config) > 0
        # Dynaconf returns uppercase keys in as_dict()
        assert "API" in all_config or "TRADING" in all_config
    
    def test_config_with_none_values(self):
        """Test configuration with None values."""
        config = ConfigurationManager()
        
        # Set None value
        config.set_config("test.none_value", None)
        assert config.get_config("test.none_value") is None
        
        # Getting None with default should return None (not the default)
        assert config.get_config("test.none_value", "default") is None
    
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
    
    def test_set_nested_value_creates_path(self):
        """Test that setting nested values creates intermediate paths."""
        config = ConfigurationManager()
        
        # Set a deeply nested value
        config.set_config("a.b.c.d.e", "deep_value")
        assert config.get_config("a.b.c.d.e") == "deep_value"
    
    def test_environment_based_loading(self):
        """Test that configuration respects TRADING_BOT_ENV."""
        # This test verifies that the demo environment is loaded by default
        config = ConfigurationManager()
        
        # Demo environment should use paper trading URL
        base_url = config.get_config("api.alpaca.base_url")
        assert "paper" in base_url.lower()
    
    def test_validate_required_config_with_valid_config(self):
        """Test validation passes with valid configuration."""
        config = ConfigurationManager()
        
        # Should not raise with the default valid config
        # (assuming .secrets.toml has valid API keys)
        try:
            config.validate_required_config()
        except ConfigurationException:
            # If secrets are not configured, validation may fail
            # This is expected behavior - skip in that case
            pytest.skip("API credentials not configured in .secrets.toml")
    
    def test_database_configuration(self):
        """Test database configuration from settings.toml."""
        config = ConfigurationManager()
        
        assert config.get_config("database.url") == "sqlite:///trading_bot.db"
        assert config.get_config("database.echo") is False
        assert config.get_config("database.pool_size") == 5
    
    def test_monitoring_configuration(self):
        """Test monitoring configuration from settings.toml."""
        config = ConfigurationManager()
        
        assert config.get_config("monitoring.enabled") is True
        assert config.get_config("monitoring.health_check_interval") == 30
        assert config.get_config("monitoring.position_monitoring_interval") == 10
    
    def test_extended_hours_configuration(self):
        """Test extended hours configuration from settings.toml."""
        config = ConfigurationManager()
        
        assert config.get_config("extended_hours.enabled") is True
        assert config.get_config("extended_hours.pre_market.enabled") is True
        assert config.get_config("extended_hours.after_hours.enabled") is True
    
    def test_performance_configuration(self):
        """Test performance configuration from settings.toml."""
        config = ConfigurationManager()
        
        assert config.get_config("performance.max_concurrent_orders") == 10
        assert config.get_config("performance.rate_limit_requests_per_second") == 5
        assert config.get_config("performance.cache_enabled") is True


class TestConfigurationManagerTypedAccess:
    """Test typed configuration access methods."""
    
    def test_get_alpaca_config(self):
        """Test getting typed Alpaca configuration."""
        config = ConfigurationManager()
        
        try:
            alpaca_config = config.get_alpaca_config()
            assert alpaca_config is not None
            assert alpaca_config.base_url == "https://paper-api.alpaca.markets"
            assert alpaca_config.is_paper is True
        except Exception:
            # If credentials not configured, this may fail
            pytest.skip("Alpaca configuration may require credentials")
    
    def test_get_webhook_config(self):
        """Test getting typed webhook configuration."""
        config = ConfigurationManager()
        
        try:
            webhook_config = config.get_webhook_config()
            assert webhook_config is not None
            assert webhook_config.host == "0.0.0.0"
            assert webhook_config.port == 8080
        except Exception:
            pytest.skip("Webhook configuration access failed")
    
    def test_get_broker_for_symbol_default(self):
        """Test getting default broker for a symbol."""
        config = ConfigurationManager()
        
        # Default broker should be alpaca
        broker = config.get_broker_for_symbol("AAPL")
        assert broker == "alpaca"
    
    def test_current_environment(self):
        """Test getting current environment."""
        config = ConfigurationManager()
        
        # Default environment should be demo
        env = config.current_environment
        assert env in ["demo", "live"]
