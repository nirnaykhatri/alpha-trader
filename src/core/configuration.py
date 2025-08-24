"""
Configuration management implementation.
Handles loading and managing configuration from YAML files and environment variables.
"""

import os
import yaml
from typing import Any, Dict, Optional
from pathlib import Path
from .logging_config import get_logger
from ..interfaces import IConfigurationManager
from ..exceptions import ConfigurationException


logger = get_logger(__name__)


class ConfigurationManager(IConfigurationManager):
    """
    Manages application configuration from multiple sources.
    Supports YAML files, environment variables, and runtime updates.
    """
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize configuration manager.
        
        Args:
            config_file: Path to YAML configuration file
        """
        self._config: Dict[str, Any] = {}
        self._config_file = config_file or "config.yaml"
        self._env_prefix = "TRADING_BOT_"
        
        # Load default configuration
        self._load_defaults()
        
        # Load configuration from file
        self._load_from_file()
        
        # Override with environment variables
        self._load_from_env()
        
        logger.info(f"Configuration loaded successfully, config_file={self._config_file}")
    
    def _load_defaults(self) -> None:
        """Load default configuration values."""
        self._config = {
            "api": {
                "alpaca": {
                    "base_url": "https://paper-api.alpaca.markets",
                    "api_key": "",
                    "secret_key": "",
                    "timeout": 30
                },
                "webhook": {
                    "host": "0.0.0.0",
                    "port": 8080,
                    "secret": "",
                    "security_enabled": False
                }
            },
            "trading": {
                "default_quantity": 100,
                "max_position_size": 1000,
                "max_daily_trades": 50,
                "risk_per_trade": 0.02,
                "max_portfolio_risk": 0.10
            },
            "strategies": {
                "averaging_down": {
                    "enabled": True,
                    "max_attempts": 3,
                    "step_percentage": 0.02,
                    "timeframe": "1h"
                },
                "trailing_profit": {
                    "enabled": True,
                    "activation_threshold": 0.03,
                    "trailing_percentage": 0.015,
                    "take_profit_percentage": 0.05
                }
            },
            "logging": {
                "level": "INFO",
                "format": "json",
                "file": "trading_bot.log"
            },
            "database": {
                "url": "sqlite:///trading_bot.db",
                "echo": False
            }
        }
    
    def _load_from_file(self) -> None:
        """Load configuration from YAML file."""
        try:
            config_path = Path(self._config_file)
            if config_path.exists():
                with open(config_path, 'r') as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        self._merge_config(file_config)
                        logger.info(f"Configuration loaded from file, path={str(config_path)}")
        except Exception as e:
            logger.warning(f"Failed to load configuration file, error={str(e)}, file={self._config_file}")
    
    def _load_from_env(self) -> None:
        """Load configuration from environment variables."""
        env_mappings = {
            f"{self._env_prefix}ALPACA_API_KEY": "api.alpaca.api_key",
            f"{self._env_prefix}ALPACA_SECRET_KEY": "api.alpaca.secret_key",
            f"{self._env_prefix}ALPACA_BASE_URL": "api.alpaca.base_url",
            f"{self._env_prefix}WEBHOOK_SECRET": "api.webhook.secret",
            f"{self._env_prefix}WEBHOOK_PORT": "api.webhook.port",
            f"{self._env_prefix}DATABASE_URL": "database.url",
            f"{self._env_prefix}LOG_LEVEL": "logging.level",
        }
        
        for env_var, config_key in env_mappings.items():
            value = os.getenv(env_var)
            if value:
                self._set_nested_value(config_key, value)
                logger.debug(f"Configuration loaded from environment, env_var={env_var}, config_key={config_key}")
    
    def _merge_config(self, new_config: Dict[str, Any]) -> None:
        """Merge new configuration into existing config."""
        def merge_dicts(base: Dict[str, Any], update: Dict[str, Any]) -> None:
            for key, value in update.items():
                if (key in base and isinstance(base[key], dict) 
                    and isinstance(value, dict)):
                    merge_dicts(base[key], value)
                else:
                    base[key] = value
        
        merge_dicts(self._config, new_config)
    
    def _set_nested_value(self, key: str, value: Any) -> None:
        """Set nested configuration value using dot notation."""
        if not key or not key.strip():
            raise ConfigurationException("Configuration key cannot be empty")
            
        keys = key.split('.')
        current = self._config
        
        for k in keys[:-1]:
            if not k.strip():
                raise ConfigurationException("Configuration key parts cannot be empty")
            if k not in current:
                current[k] = {}
            current = current[k]
        
        final_key = keys[-1]
        if not final_key.strip():
            raise ConfigurationException("Configuration key parts cannot be empty")
        
        # Type conversion for common cases
        if isinstance(value, str):
            if value.lower() in ('true', 'false'):
                value = value.lower() == 'true'
            elif value.isdigit():
                value = int(value)
            elif value.replace('.', '', 1).isdigit():
                value = float(value)
        
        current[final_key] = value
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by key with enhanced error handling and type safety.
        
        Args:
            key: Configuration key (supports dot notation)
            default: Default value if key not found
            
        Returns:
            Configuration value or default
            
        Raises:
            ConfigurationException: If key format is invalid
        """
        if not key or not isinstance(key, str):
            raise ConfigurationException("Configuration key must be a non-empty string")
        
        try:
            keys = key.split('.')
            current = self._config
            
            for k in keys:
                if not k.strip():
                    raise ConfigurationException(f"Empty key component in '{key}'")
                
                if isinstance(current, dict) and k in current:
                    current = current[k]
                else:
                    logger.debug(f"Configuration key not found: {key}, using default: {default}")
                    return default
            
            return current
            
        except ConfigurationException:
            raise
        except Exception as e:
            logger.error(f"Failed to get configuration, key={key}, error={str(e)}")
            return default
    
    def set_config(self, key: str, value: Any) -> None:
        """
        Set configuration value.
        
        Args:
            key: Configuration key (supports dot notation)
            value: Value to set
        """
        try:
            self._set_nested_value(key, value)
            logger.info(f"Configuration updated, key={key}, value={value}")
        except Exception as e:
            logger.error(f"Failed to set configuration, key={key}, error={str(e)}")
            raise ConfigurationException(f"Failed to set config {key}: {str(e)}")
    
    def reload_config(self) -> None:
        """Reload configuration from all sources."""
        logger.info("Reloading configuration")
        self._load_defaults()
        self._load_from_file()
        self._load_from_env()
        logger.info("Configuration reloaded successfully")
    
    def get_all_config(self) -> Dict[str, Any]:
        """Get all configuration as dictionary."""
        return self._config.copy()
    
    def validate_required_config(self) -> None:
        """Validate that all required configuration is present."""
        required_keys = [
            "api.alpaca.api_key",
            "api.alpaca.secret_key"
        ]
        
        # Only require webhook secret if security is enabled
        security_enabled = self.get_config("api.webhook.security_enabled", False)
        if security_enabled:
            required_keys.append("api.webhook.secret")
        
        missing_keys = []
        for key in required_keys:
            if not self.get_config(key):
                missing_keys.append(key)
        
        if missing_keys:
            raise ConfigurationException(
                f"Missing required configuration: {', '.join(missing_keys)}"
            )
