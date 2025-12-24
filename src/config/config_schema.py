""" 
Pydantic Configuration Schema Validation

Provides strong typing and validation for configuration structure.
Catches errors at startup rather than runtime.

Note: This module validates configuration structure loaded from:
- Azure App Configuration (production)
- Environment variables (local development)
The schema definitions ensure type safety regardless of the source.

Includes severity classification for validation issues.
"""

import logging
from typing import Optional, Dict, Any, List
from pathlib import Path
from enum import Enum
from pydantic import BaseModel, Field, validator, root_validator
import yaml

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severity classification for validation issues."""
    ERROR = "ERROR"      # Blocks startup
    WARN = "WARN"        # Logs warning, continues
    INFO = "INFO"        # Informational only


# API Configuration Models
class WebsocketConfig(BaseModel):
    """Websocket configuration for Alpaca."""
    enabled: bool = False
    market_data_feed: str = Field(default="iex")
    auto_reconnect: bool = True
    heartbeat_interval: int = Field(default=30, ge=1)
    max_reconnect_attempts: int = Field(default=10, ge=1)
    reconnect_delay: int = Field(default=5, ge=1)
    
    class Config:
        extra = 'allow'


class AlpacaApiConfig(BaseModel):
    """Alpaca API configuration."""
    api_key: str = Field(..., min_length=1)
    secret_key: str = Field(..., min_length=1)
    base_url: str = Field(..., pattern="^https?://")
    timeout: int = Field(default=30, ge=1)
    max_retries: int = Field(default=3, ge=0)
    retry_delay: float = Field(default=1.0, ge=0)
    communication_method: str = Field(default="rest")
    websocket: Optional[WebsocketConfig] = None
    
    class Config:
        extra = 'allow'


class WebhookApiConfig(BaseModel):
    """Webhook server configuration."""
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8080, ge=1024, le=65535)
    security_enabled: bool = False
    secret: str = Field(default="")
    
    class Config:
        extra = 'allow'


class ApiConfig(BaseModel):
    """API configuration container."""
    alpaca: AlpacaApiConfig
    webhook: WebhookApiConfig
    
    class Config:
        extra = 'allow'


# Trading Configuration Models
class OrderMonitoringConfig(BaseModel):
    """Order monitoring configuration."""
    check_interval: int = Field(default=10, ge=1)
    max_pending_time: int = Field(default=600, ge=1)
    log_pending_orders: bool = True
    
    class Config:
        extra = 'allow'


class AveragingConfig(BaseModel):
    """Position averaging configuration."""
    enabled: bool = True
    multiplier: float = Field(default=1.5, ge=1.0)
    max_multiplier: float = Field(default=4.0, ge=1.0)
    max_attempts: int = Field(default=3, ge=1)
    
    class Config:
        extra = 'allow'


class PositionSizingConfig(BaseModel):
    """Position sizing configuration."""
    method: str = Field(default="percentage")
    initial_portfolio_percentage: float = Field(default=0.01, gt=0, le=1.0)
    risk_per_trade: float = Field(default=0.02, gt=0, le=1.0)
    averaging: AveragingConfig
    min_quantity: int = Field(default=1, ge=1)
    max_quantity: int = Field(default=10000, ge=1)
    max_total_position_percentage: float = Field(default=0.15, gt=0, le=1.0)
    
    class Config:
        extra = 'allow'


class AllowedDirectionsConfig(BaseModel):
    """Trading direction filtering."""
    enabled: bool = True
    long_only: bool = False
    short_only: bool = False
    
    class Config:
        extra = 'allow'


class PositionManagementConfig(BaseModel):
    """Position management behavior."""
    ignore_opposing_signals: bool = True
    
    class Config:
        extra = 'allow'


class TradingConfig(BaseModel):
    """Trading configuration."""
    aggressive_order_timeout_minutes: int = Field(default=5, ge=1)
    max_price_adjustment_percent: float = Field(default=0.5, ge=0)
    order_monitoring: OrderMonitoringConfig
    position_sizing: PositionSizingConfig
    max_position_size: int = Field(default=1000, ge=1)
    max_daily_trades: int = Field(default=50, ge=1)
    order_type: str = Field(default="limit")
    limit_order_offset: float = Field(default=0.001, ge=0)
    market_order_slippage: float = Field(default=0.002, ge=0)
    order_timeout_minutes: int = Field(default=5, ge=1)
    allowed_directions: AllowedDirectionsConfig
    position_management: PositionManagementConfig
    max_portfolio_risk: float = Field(default=0.10, gt=0, le=1.0)
    
    class Config:
        extra = 'allow'


# Strategy Configuration Models
class TrailingProfitConfig(BaseModel):
    """Trailing profit configuration."""
    enabled: bool = True
    trailing_percentage: float = Field(default=0.015, gt=0, le=1.0)
    activation_threshold: float = Field(default=0.03, gt=0, le=1.0)
    min_profit_lock: float = Field(default=0.01, gt=0, le=1.0)
    acceleration_factor: float = Field(default=1.5, ge=1.0)
    
    class Config:
        extra = 'allow'


class StrategiesConfig(BaseModel):
    """Strategies configuration."""
    
    class Config:
        extra = 'allow'


# Logging Configuration
class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = Field(default="INFO")
    format: str = Field(default="json")
    file: str = Field(default="logs/trading_bot.log")
    max_file_size: str = Field(default="10MB")
    backup_count: int = Field(default=5, ge=0)
    console_logging: bool = True
    
    class Config:
        extra = 'allow'


# Database Configuration
class DatabaseConfig(BaseModel):
    """Database configuration."""
    url: str = Field(default="sqlite:///trading_bot.db")
    echo: bool = False
    pool_size: int = Field(default=5, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    
    class Config:
        extra = 'allow'


# Monitoring Configuration
class MonitoringConfig(BaseModel):
    """Monitoring configuration."""
    enabled: bool = True
    
    class Config:
        extra = 'allow'


# ngrok Configuration
class NgrokConfig(BaseModel):
    """ngrok configuration."""
    enabled: bool = False
    auth_token: str = Field(default="")
    
    class Config:
        extra = 'allow'


# Root Configuration
class BotConfig(BaseModel):
    """Root bot configuration schema."""
    
    api: ApiConfig
    ngrok: Optional[NgrokConfig] = None
    trading: TradingConfig
    strategies: StrategiesConfig
    logging: LoggingConfig
    database: DatabaseConfig
    monitoring: Optional[MonitoringConfig] = None
    
    class Config:
        extra = 'allow'  # Allow extra fields for extensibility


class ConfigValidator:
    """
    Configuration validator with startup checks.
    
    Example:
        validator = ConfigValidator()
        config = validator.load_and_validate()
        
        if validator.has_warnings():
            for warning in validator.get_warnings():
                print(f"⚠️ {warning}")
    """
    
    def __init__(self):
        self.warnings: List[str] = []
        self.config_dict: Optional[Dict[str, Any]] = None
        self.validated_config: Optional[BotConfig] = None
    
    def load_and_validate(self, config_path: str = None) -> BotConfig:
        """
        Load and validate configuration.
        
        Args:
            config_path: DEPRECATED - No longer used. Configuration is loaded
                        from config/ directory using TOML files via ConfigurationManager.
            
        Returns:
            Validated BotConfig instance
            
        Raises:
            ValueError: If configuration is invalid
        """
        if config_path is not None:
            import warnings
            warnings.warn(
                "config_path parameter is deprecated. Configuration is loaded from "
                "config/ directory using TOML files.",
                DeprecationWarning,
                stacklevel=2
            )
        
        # Load configuration from new TOML-based system
        from src.core import ConfigurationManager
        config_mgr = ConfigurationManager()
        
        # Get all config as a dict for Pydantic validation
        self.config_dict = self._build_config_dict(config_mgr)
        
        logger.info("Loaded configuration from config/ TOML files")
        
        # Validate with Pydantic
        try:
            self.validated_config = BotConfig(**self.config_dict)
            logger.info("✅ Configuration validation passed")
            
        except Exception as e:
            logger.error(f"❌ Configuration validation failed: {e}")
            raise ValueError(f"Invalid configuration: {e}")
        
        # Additional semantic checks
        self._check_production_settings()
        self._check_risk_settings()
        self._check_unused_keys()
        
        return self.validated_config
    
    def _build_config_dict(self, config_mgr) -> Dict[str, Any]:
        """Build a config dict from ConfigurationManager for Pydantic validation."""
        return {
            'api': {
                'alpaca': {
                    'api_key': config_mgr.get_config('api.alpaca.api_key', ''),
                    'secret_key': config_mgr.get_config('api.alpaca.secret_key', ''),
                    'base_url': config_mgr.get_config('api.alpaca.base_url', 'https://paper-api.alpaca.markets'),
                    'timeout': config_mgr.get_config('api.timeout', 30),
                    'max_retries': config_mgr.get_config('api.max_retries', 3),
                    'retry_delay': config_mgr.get_config('api.retry_delay', 1.0),
                    'communication_method': config_mgr.get_config('api.alpaca.communication_method', 'rest'),
                    'websocket': config_mgr.get_config('api.alpaca.websocket', {}),
                },
                'webhook': {
                    'host': config_mgr.get_config('api.webhook.host', '0.0.0.0'),
                    'port': config_mgr.get_config('api.webhook.port', 8080),
                    'security_enabled': config_mgr.get_config('api.webhook.security_enabled', False),
                    'secret': config_mgr.get_config('api.webhook.secret', ''),
                },
            },
            'trading': {
                'default_quantity': config_mgr.get_config('trading.default_quantity', 100),
                'order_type': config_mgr.get_config('trading.order_type', 'limit'),
                'limit_order_offset': config_mgr.get_config('trading.limit_order_offset', 0.001),
                'market_order_slippage': config_mgr.get_config('trading.market_order_slippage', 0.002),
                'order_timeout_minutes': config_mgr.get_config('trading.order_timeout_minutes', 5),
                'aggressive_order_timeout_minutes': config_mgr.get_config('trading.aggressive_order_timeout_minutes', 5),
                'max_price_adjustment_percent': config_mgr.get_config('trading.max_price_adjustment_percent', 0.5),
                'risk_per_trade': config_mgr.get_config('trading.risk_per_trade', 0.02),
                'max_position_size': config_mgr.get_config('trading.max_position_size', 1000),
                'max_daily_trades': config_mgr.get_config('trading.max_daily_trades', 50),
                'position_sizing': config_mgr.get_config('trading.position_sizing', {}),
                'order_monitoring': config_mgr.get_config('trading.order_monitoring', {}),
                'allowed_directions': config_mgr.get_config('trading.allowed_directions', {'enabled': True, 'long_only': False, 'short_only': False}),
                'position_management': config_mgr.get_config('trading.position_management', {'ignore_opposing_signals': True}),
            },
            'strategies': config_mgr.get_config('strategies', {}),
            'logging': config_mgr.get_config('logging', {}),
            'ngrok': config_mgr.get_config('ngrok', {}),
            'monitoring': config_mgr.get_config('monitoring', {}),
            'database': config_mgr.get_config('database', {}),
        }
    
    def _check_production_settings(self) -> None:
        """Warn about potentially dangerous production settings with severity classification."""
        if not self.validated_config:
            return
        
        # Check if paper trading is enabled (base_url contains "paper")
        try:
            base_url = self.validated_config.api.alpaca.base_url
            is_paper = "paper" in base_url.lower()
            
            if not is_paper:
                self.warnings.append(
                    f"[{ValidationSeverity.WARN.value}] Live trading mode detected (base_url: {base_url}) - "
                    "Ensure you intend to trade with real money"
                )
        except AttributeError:
            pass  # Skip if fields don't exist
        
        # Check position sizing if available
        try:
            sizing = self.validated_config.trading.position_sizing
            risk_per_trade = sizing.risk_per_trade
            
            # ERROR: Aggressive position sizing (>10% per trade)
            if risk_per_trade > 0.10:
                self.warnings.append(
                    f"[{ValidationSeverity.ERROR.value}] Extremely high risk per trade: "
                    f"{risk_per_trade:.1%} (>10%) - Blocks startup"
                )
            # WARN: High position sizing (5-10% per trade)
            elif risk_per_trade > 0.05:
                self.warnings.append(
                    f"[{ValidationSeverity.WARN.value}] High risk per trade: "
                    f"{risk_per_trade:.1%} (>5%)"
                )
            # INFO: Conservative position sizing (<2% per trade)
            elif risk_per_trade < 0.02:
                self.warnings.append(
                    f"[{ValidationSeverity.INFO.value}] Very conservative risk per trade: "
                    f"{risk_per_trade:.1%} (<2%)"
                )
        except AttributeError:
            pass  # Skip if fields don't exist
    
    def _check_risk_settings(self) -> None:
        """Warn about potentially unsafe risk settings with severity classification."""
        if not self.validated_config:
            return
        
        # Note: The actual config.yaml uses a different structure for risk settings
        # These checks are optional and will skip if the fields don't exist
        # The ConfigurationManager handles the actual runtime validation
        
        try:
            # Try to access risk settings from config_dict (raw YAML)
            if not self.config_dict:
                return
            
            # Check trading position sizing averaging settings
            trading_config = self.config_dict.get('trading', {})
            position_sizing = trading_config.get('position_sizing', {})
            averaging = position_sizing.get('averaging', {})
            
            max_attempts = averaging.get('max_attempts', 3)
            if max_attempts > 10:
                self.warnings.append(
                    f"[{ValidationSeverity.ERROR.value}] Excessive DCA attempts: "
                    f"{max_attempts} (>10) - High risk of runaway losses"
                )
            elif max_attempts > 7:
                self.warnings.append(
                    f"[{ValidationSeverity.WARN.value}] High DCA attempts: "
                    f"{max_attempts} (>7) - Monitor closely"
                )
            
            # Check multiplier
            multiplier = averaging.get('multiplier', 1.5)
            if multiplier > 3.0:
                self.warnings.append(
                    f"[{ValidationSeverity.ERROR.value}] Excessive DCA multiplier: "
                    f"{multiplier}x (>3.0) - Exponential position growth risk"
                )
            elif multiplier > 2.0:
                self.warnings.append(
                    f"[{ValidationSeverity.WARN.value}] High DCA multiplier: "
                    f"{multiplier}x (>2.0) - Monitor position sizes"
                )
                
        except (AttributeError, KeyError):
            pass  # Skip if fields don't exist
    
    def _check_unused_keys(self) -> None:
        """Detect unused configuration keys with severity classification."""
        if not self.config_dict or not self.validated_config:
            return
        
        # Get all keys used by schema
        schema_keys = self._collect_schema_keys(self.validated_config.dict())
        
        # Get all keys from loaded YAML
        yaml_keys = self._collect_yaml_keys(self.config_dict)
        
        # Find unused keys (in YAML but not in schema)
        unused_keys = yaml_keys - schema_keys
        
        if unused_keys:
            logger.warning(f"⚠️ Found {len(unused_keys)} unused configuration keys:")
            for key in sorted(unused_keys):
                logger.warning(f"  - {key}")
            
            # WARN: Unused keys (could be typos or deprecated settings)
            self.warnings.append(
                f"[{ValidationSeverity.WARN.value}] {len(unused_keys)} unused config keys detected "
                f"(see logs for details) - May indicate typos or deprecated settings"
            )
    
    def _collect_schema_keys(self, obj: Any, prefix: str = "") -> set:
        """Recursively collect all keys from validated schema object."""
        keys = set()
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                full_key = f"{prefix}.{key}" if prefix else key
                keys.add(full_key)
                
                if isinstance(value, (dict, list)):
                    keys.update(self._collect_schema_keys(value, full_key))
        
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, (dict, list)):
                    keys.update(self._collect_schema_keys(item, prefix))
        
        return keys
    
    def _collect_yaml_keys(self, obj: Any, prefix: str = "") -> set:
        """Recursively collect all keys from YAML dictionary."""
        keys = set()
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                full_key = f"{prefix}.{key}" if prefix else key
                keys.add(full_key)
                
                if isinstance(value, (dict, list)):
                    keys.update(self._collect_yaml_keys(value, full_key))
        
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                if isinstance(item, (dict, list)):
                    keys.update(self._collect_yaml_keys(item, prefix))
        
        return keys
    
    def has_warnings(self) -> bool:
        """Check if validation produced warnings."""
        return len(self.warnings) > 0
    
    def get_warnings(self) -> List[str]:
        """Get all validation warnings."""
        return self.warnings
    
    def has_errors(self) -> bool:
        """Check if validation produced ERROR-level warnings."""
        return any(ValidationSeverity.ERROR.value in w for w in self.warnings)
    
    def get_errors(self) -> List[str]:
        """Get ERROR-level warnings only."""
        return [w for w in self.warnings if ValidationSeverity.ERROR.value in w]
    
    def get_warnings_by_severity(self, severity: ValidationSeverity) -> List[str]:
        """Get warnings filtered by severity level."""
        return [w for w in self.warnings if severity.value in w]
    
    def log_configuration_diff(self, other_config_path: str) -> None:
        """
        Log differences between current and another config file.
        
        Useful for comparing production vs development configs.
        """
        with open(other_config_path, 'r') as f:
            other_dict = yaml.safe_load(f)
        
        if not self.config_dict:
            logger.warning("No current config loaded")
            return
        
        diffs = self._find_differences(self.config_dict, other_dict)
        
        if diffs:
            logger.info(f"Configuration differences vs {other_config_path}:")
            for diff in diffs:
                logger.info(f"  {diff}")
        else:
            logger.info(f"No differences vs {other_config_path}")
    
    def _find_differences(
        self, 
        dict1: Dict[str, Any], 
        dict2: Dict[str, Any], 
        path: str = ""
    ) -> List[str]:
        """Recursively find differences between two config dictionaries."""
        diffs = []
        
        # Keys in dict1 but not dict2
        for key in dict1:
            current_path = f"{path}.{key}" if path else key
            
            if key not in dict2:
                diffs.append(f"➕ {current_path}: {dict1[key]} (added)")
            elif isinstance(dict1[key], dict) and isinstance(dict2[key], dict):
                diffs.extend(self._find_differences(dict1[key], dict2[key], current_path))
            elif dict1[key] != dict2[key]:
                diffs.append(f"🔄 {current_path}: {dict1[key]} -> {dict2[key]} (changed)")
        
        # Keys in dict2 but not dict1
        for key in dict2:
            if key not in dict1:
                current_path = f"{path}.{key}" if path else key
                diffs.append(f"➖ {current_path}: {dict2[key]} (removed)")
        
        return diffs


def validate_config_file(config_path: str = None) -> BotConfig:
    """
    Convenience function to validate config.
    
    Note: config_path is deprecated - configuration is loaded from
    Azure App Configuration or environment variables.
    
    Example:
        try:
            config = validate_config_file()
            print("✅ Configuration valid")
        except ValueError as e:
            print(f"❌ Configuration invalid: {e}")
    """
    validator = ConfigValidator()
    config = validator.load_and_validate(config_path)
    
    if validator.has_warnings():
        logger.warning("Configuration warnings:")
        for warning in validator.get_warnings():
            logger.warning(f"  {warning}")
    
    return config
