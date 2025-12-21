"""
Pydantic-based configuration models for type-safe and validated configuration.

This module provides Pydantic models for configuration management with automatic
validation, type checking, and environment variable support.
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, validator, root_validator
from pydantic_settings import BaseSettings


class AlpacaAPISettings(BaseModel):
    """Alpaca API configuration."""
    
    api_key: str = Field(..., min_length=1, description="Alpaca API key")
    secret_key: str = Field(..., min_length=1, description="Alpaca secret key")
    base_url: str = Field(
        default="https://paper-api.alpaca.markets",
        description="Alpaca API base URL (paper or live)"
    )
    communication_method: Literal["rest", "websocket"] = Field(
        default="rest",
        description="Communication method for Alpaca API"
    )
    
    @validator("base_url")
    def validate_base_url(cls, v):
        """Validate base URL format."""
        if not v.startswith("https://"):
            raise ValueError("Base URL must start with https://")
        return v


class WebhookSettings(BaseModel):
    """Webhook configuration."""
    
    host: str = Field(default="0.0.0.0", description="Webhook server host")
    port: int = Field(default=8080, ge=1, le=65535, description="Webhook server port")
    security_enabled: bool = Field(default=True, description="Enable webhook security")
    secret: Optional[str] = Field(default=None, min_length=32, description="Webhook secret")
    
    @root_validator
    def validate_security(cls, values):
        """Validate security configuration."""
        if values.get('security_enabled') and not values.get('secret'):
            raise ValueError("Webhook secret is required when security is enabled")
        return values


class DatabaseSettings(BaseModel):
    """Database configuration."""
    
    url: str = Field(
        default="sqlite:///data/trading_bot.db",
        description="Database connection URL"
    )
    echo: bool = Field(default=False, description="Echo SQL queries")
    pool_size: int = Field(default=20, ge=1, le=100, description="Connection pool size")
    max_overflow: int = Field(default=40, ge=0, le=200, description="Max connection overflow")
    pool_timeout: int = Field(default=30, ge=1, le=300, description="Pool timeout in seconds")
    pool_recycle: int = Field(default=3600, ge=60, description="Pool recycle time in seconds")


class RiskSettings(BaseModel):
    """Risk management configuration."""
    
    max_position_size: float = Field(
        default=0.10,
        ge=0.01,
        le=1.0,
        description="Maximum position size as fraction of account"
    )
    max_total_exposure: float = Field(
        default=0.90,
        ge=0.1,
        le=1.0,
        description="Maximum total exposure as fraction of account"
    )
    default_position_size: float = Field(
        default=0.02,
        ge=0.001,
        le=0.5,
        description="Default position size as fraction of account"
    )
    
    @root_validator
    def validate_risk_limits(cls, values):
        """Validate risk limit relationships."""
        max_pos = values.get('max_position_size', 0.10)
        max_exp = values.get('max_total_exposure', 0.90)
        default_pos = values.get('default_position_size', 0.02)
        
        if default_pos > max_pos:
            raise ValueError("Default position size cannot exceed max position size")
        
        if max_pos > max_exp:
            raise ValueError("Max position size cannot exceed max total exposure")
        
        return values


class DCASettings(BaseModel):
    """Dollar Cost Averaging configuration."""
    
    enabled: bool = Field(default=True, description="Enable DCA strategy")
    max_attempts: int = Field(default=5, ge=1, le=20, description="Maximum DCA attempts")
    multiplier: float = Field(
        default=1.5,
        ge=1.0,
        le=5.0,
        description="DCA order size multiplier"
    )
    min_spacing_pct: float = Field(
        default=0.01,
        ge=0.001,
        le=0.1,
        description="Minimum spacing between DCA orders as percentage"
    )
    use_technical_analysis: bool = Field(
        default=True,
        description="Use technical analysis for DCA triggers"
    )


class StrategySettings(BaseModel):
    """Trading strategy configuration."""
    
    name: str = Field(default="advanced_dca", description="Strategy name")
    dca: DCASettings = Field(default_factory=DCASettings)
    use_trailing_stop: bool = Field(default=True, description="Enable trailing stop")
    trailing_stop_pct: float = Field(
        default=0.02,
        ge=0.001,
        le=0.2,
        description="Trailing stop percentage"
    )


class TradingBotSettings(BaseSettings):
    """
    Main trading bot configuration with validation.
    
    This can be populated from environment variables, .env file, or YAML config.
    """
    
    # API Settings
    alpaca: AlpacaAPISettings
    webhook: WebhookSettings = Field(default_factory=WebhookSettings)
    
    # Database
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    
    # Risk Management
    risk: RiskSettings = Field(default_factory=RiskSettings)
    
    # Strategy
    strategy: StrategySettings = Field(default_factory=StrategySettings)
    
    # General Settings
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Deployment environment"
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level"
    )
    
    class Config:
        """Pydantic configuration."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_nested_delimiter = "__"  # Allow nested env vars like ALPACA__API_KEY
        validate_assignment = True  # Validate on attribute assignment
        extra = "ignore"  # Ignore extra fields
        
    @root_validator
    def validate_environment_consistency(cls, values):
        """Validate environment-specific constraints."""
        env = values.get('environment')
        alpaca_url = values.get('alpaca', {}).base_url if isinstance(values.get('alpaca'), AlpacaAPISettings) else None
        
        # In production, ensure we're not using paper trading
        if env == 'production' and alpaca_url and 'paper' in alpaca_url:
            raise ValueError("Cannot use paper trading URL in production environment")
        
        return values
    
    def is_paper_trading(self) -> bool:
        """Check if configured for paper trading."""
        return 'paper' in self.alpaca.base_url.lower()
    
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.environment == 'production'


class ConfigValidator:
    """
    Helper class to validate existing configuration dictionaries.
    
    This bridges the gap between existing YAML-based config and Pydantic validation.
    """
    
    @staticmethod
    def validate_config_dict(config_dict: dict) -> TradingBotSettings:
        """
        Validate a configuration dictionary using Pydantic models.
        
        Args:
            config_dict: Configuration dictionary from YAML or other source
            
        Returns:
            Validated TradingBotSettings instance
            
        Raises:
            ValueError: If configuration is invalid
        """
        try:
            # Convert nested dict structure to match Pydantic model
            structured_config = ConfigValidator._restructure_config(config_dict)
            return TradingBotSettings(**structured_config)
        except Exception as e:
            raise ValueError(f"Configuration validation failed: {str(e)}")
    
    @staticmethod
    def _restructure_config(config_dict: dict) -> dict:
        """
        Restructure flat config dictionary to match Pydantic model structure.
        
        This helps convert YAML config like:
        api:
          alpaca:
            api_key: xxx
            
        To Pydantic structure:
        alpaca:
          api_key: xxx
        """
        structured = {}
        
        # Extract Alpaca settings
        if 'api' in config_dict and 'alpaca' in config_dict['api']:
            structured['alpaca'] = config_dict['api']['alpaca']
        
        # Extract webhook settings
        if 'api' in config_dict and 'webhook' in config_dict['api']:
            structured['webhook'] = config_dict['api']['webhook']
        
        # Extract database settings
        if 'database' in config_dict:
            structured['database'] = config_dict['database']
        
        # Extract risk settings
        if 'risk' in config_dict:
            structured['risk'] = config_dict['risk']
        
        # Extract strategy settings
        if 'strategies' in config_dict:
            structured['strategy'] = config_dict['strategies']
        
        # General settings
        structured['environment'] = config_dict.get('environment', 'development')
        structured['log_level'] = config_dict.get('logging', {}).get('level', 'INFO')
        
        return structured


# Example usage:
"""
# From environment variables
settings = TradingBotSettings()

# From dictionary (YAML config)
config_dict = yaml.load(config_file)
settings = ConfigValidator.validate_config_dict(config_dict)

# Check configuration
if settings.is_paper_trading():
    print("Using paper trading")
    
if settings.alpaca.api_key:
    print("API key configured")
"""
