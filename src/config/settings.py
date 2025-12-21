"""
Configuration Management with Dynaconf and Pydantic.

This module provides a clean, layered configuration system using:
- Dynaconf for loading TOML files with environment support
- Pydantic for type-safe validation models
- Fail-fast startup validation

Environment switching:
    TRADING_BOT_ENV=demo|live (default: demo)

Risk profiles:
    Load with: settings.load_profile("conservative")
    
See docs/CONFIGURATION.md for complete documentation.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass
from enum import Enum

from dynaconf import Dynaconf, Validator
from pydantic import BaseModel, Field, field_validator, model_validator

from src.interfaces import IConfigurationManager


logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.toml"
SECRETS_FILE = CONFIG_DIR / ".secrets.toml"
ENVIRONMENTS_DIR = CONFIG_DIR / "environments"
PROFILES_DIR = CONFIG_DIR / "profiles"

VALID_ENVIRONMENTS = ["demo", "live"]
VALID_BROKERS = ["alpaca", "tastytrade"]
VALID_RISK_PROFILES = ["conservative", "moderate", "aggressive"]


# ============================================================================
# Pydantic Models for Type-Safe Config Access
# ============================================================================

class AlpacaBrokerConfig(BaseModel):
    """Alpaca broker configuration with validation."""
    
    api_key: str = Field(default="", description="Alpaca API key")
    secret_key: str = Field(default="", description="Alpaca secret key")
    base_url: str = Field(default="https://paper-api.alpaca.markets")
    timeout: int = Field(default=30, ge=1)
    max_retries: int = Field(default=3, ge=0)
    retry_delay: float = Field(default=1.0, ge=0)
    communication_method: str = Field(default="rest")
    
    @property
    def is_configured(self) -> bool:
        """Check if broker has all required credentials."""
        return bool(self.api_key and self.secret_key)
    
    @property
    def is_paper(self) -> bool:
        """Check if using paper trading endpoint."""
        return "paper" in self.base_url.lower()


class TastytradeBrokerConfig(BaseModel):
    """Tastytrade broker configuration with validation.
    
    Uses OAuth authentication (tastytrade SDK v11.x):
    - client_secret: From your OAuth application setup
    - refresh_token: Generated via OAuth grant (never expires)
    """
    
    client_secret: str = Field(default="", description="OAuth client secret")
    refresh_token: str = Field(default="", description="OAuth refresh token")
    account_id: str = Field(default="", description="Tastytrade account ID")
    is_sandbox: bool = Field(default=True)
    
    # Legacy fields (deprecated, kept for backwards compatibility)
    username: str = Field(default="", description="[DEPRECATED] Use client_secret instead")
    password: str = Field(default="", description="[DEPRECATED] Use refresh_token instead")
    
    @property
    def is_configured(self) -> bool:
        """Check if broker has all required OAuth credentials."""
        return bool(self.client_secret and self.refresh_token)


class SymbolConfig(BaseModel):
    """Per-symbol configuration."""
    
    broker: str = Field(default="alpaca")
    max_position_size: Optional[int] = None
    risk_per_trade: Optional[float] = None
    
    @field_validator("broker")
    @classmethod
    def validate_broker(cls, v: str) -> str:
        if v not in VALID_BROKERS:
            raise ValueError(f"Invalid broker '{v}'. Must be one of: {VALID_BROKERS}")
        return v


class WebhookConfig(BaseModel):
    """Webhook server configuration."""
    
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8080, ge=1024, le=65535)
    security_enabled: bool = Field(default=False)
    secret: str = Field(default="")


class PositionSizingConfig(BaseModel):
    """Position sizing configuration."""
    
    method: str = Field(default="percentage")
    initial_portfolio_percentage: float = Field(default=0.01, gt=0, le=1.0)
    risk_per_trade: float = Field(default=0.02, gt=0, le=1.0)
    min_quantity: int = Field(default=1, ge=1)
    max_quantity: int = Field(default=10000, ge=1)
    max_total_position_percentage: float = Field(default=0.15, gt=0, le=1.0)
    max_single_position_percent: float = Field(default=0.50, gt=0, le=1.0)
    max_account_risk_percent: float = Field(default=0.25, gt=0, le=1.0)
    daily_loss_limit_percent: float = Field(default=0.10, gt=0, le=1.0)
    weekly_loss_limit_percent: float = Field(default=0.20, gt=0, le=1.0)


# ============================================================================
# Validation Error Types
# ============================================================================

class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


class BrokerNotConfiguredError(ConfigValidationError):
    """Raised when a required broker is not properly configured."""
    pass


class MissingConfigFileError(ConfigValidationError):
    """Raised when a required configuration file is missing."""
    pass


@dataclass
class ValidationIssue:
    """Represents a configuration validation issue."""
    
    severity: str  # "ERROR", "WARN", "INFO"
    message: str
    path: Optional[str] = None
    
    def __str__(self) -> str:
        prefix = f"[{self.severity}]"
        if self.path:
            return f"{prefix} {self.path}: {self.message}"
        return f"{prefix} {self.message}"


# ============================================================================
# Dynaconf Settings Instance
# ============================================================================

def _get_environment() -> str:
    """Get current environment from env var, default to demo."""
    env = os.environ.get("TRADING_BOT_ENV", "demo").lower()
    if env not in VALID_ENVIRONMENTS:
        logger.warning(
            f"Invalid TRADING_BOT_ENV='{env}'. Using 'demo'. "
            f"Valid values: {VALID_ENVIRONMENTS}"
        )
        return "demo"
    return env


def _create_settings() -> Dynaconf:
    """
    Create and configure the Dynaconf settings instance.
    
    Loading Order (later files override earlier):
    1. settings.toml [default] - Base defaults
    2. .secrets.toml [default] - Shared secrets (webhook, ngrok, etc.)
    3. .secrets.toml [demo|live] - Environment-specific credentials
    4. environments/{env}.toml [default] - Environment overrides
    5. profiles/{profile}.toml [default] - Risk profile (if set)
    """
    env = _get_environment()
    
    # Build list of settings files
    settings_files = [str(SETTINGS_FILE)]
    
    # Add secrets file if it exists
    if SECRETS_FILE.exists():
        settings_files.append(str(SECRETS_FILE))
    
    # Add environment-specific file
    env_file = ENVIRONMENTS_DIR / f"{env}.toml"
    if env_file.exists():
        settings_files.append(str(env_file))
    
    # Create settings with environment support
    # Dynaconf will load [default] first, then [env] sections from all files
    settings = Dynaconf(
        envvar_prefix="TRADING_BOT",
        settings_files=settings_files,
        environments=True,  # Enable [section] parsing in TOML
        env=env,  # Load [demo] or [live] sections from secrets
        default_env="default",  # Also load [default] sections as base
        load_dotenv=False,
        merge_enabled=True,
    )
    
    return settings


# Global settings instance - created lazily
_settings: Optional[Dynaconf] = None


def get_settings() -> Dynaconf:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = _create_settings()
    return _settings


def reload_settings() -> Dynaconf:
    """Reload settings from files."""
    global _settings
    _settings = _create_settings()
    return _settings


def reset_settings() -> None:
    """
    Reset the global settings instance.
    
    This is primarily used for testing to ensure a clean state between tests.
    """
    global _settings
    _settings = None


# ============================================================================
# Configuration Manager (IConfigurationManager Implementation)
# ============================================================================

class ConfigurationManager(IConfigurationManager):
    """
    Modern configuration manager using Dynaconf.
    
    Implements IConfigurationManager interface for compatibility.
    """
    
    _instance: Optional["ConfigurationManager"] = None
    
    @classmethod
    def reset_instance(cls) -> None:
        """
        Reset the singleton instance.
        
        This is primarily used for testing to ensure a clean state between tests.
        """
        cls._instance = None
        reset_settings()
    
    @classmethod
    def _create_validated(cls) -> "ConfigurationManager":
        """
        Internal method to create a validated instance.
        
        Used by validate_and_exit_on_error() to create a properly validated config.
        DO NOT use this directly - use validate_and_exit_on_error() instead.
        
        Returns:
            ConfigurationManager instance marked as validated
        """
        instance = cls()
        instance._validated = True
        instance._allow_unvalidated = True
        return instance
    
    def __new__(cls) -> "ConfigurationManager":
        """Singleton pattern for configuration manager."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize configuration manager.
        
        WARNING: For production use, call validate_and_exit_on_error() instead
        of instantiating ConfigurationManager directly. This ensures all
        configuration is validated before starting the bot.
        
        Direct instantiation is allowed for testing but will log a warning
        in production environments.
        """
        if self._initialized:
            return
        
        self._settings = get_settings()
        self._validated = False
        self._profile: Optional[str] = None
        self._initialized = True
        self._allow_unvalidated = False
        
        # Warn if used directly without validation (except in tests)
        # Check if we're in a test environment
        import sys
        is_test = 'pytest' in sys.modules or 'unittest' in sys.modules
        
        if not is_test:
            logger.warning(
                "ConfigurationManager instantiated without validation. "
                "For production use, call validate_and_exit_on_error() instead. "
                "This ensures all configuration is valid before starting the bot."
            )
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation key.
        
        Args:
            key: Dot-notation key like "trading.position_sizing.method"
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        try:
            # Dynaconf uses uppercase for first level, so we convert
            # key like "trading.order_type" to settings.trading.order_type
            value = self._settings
            for part in key.split("."):
                if hasattr(value, part):
                    value = getattr(value, part)
                elif isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    return default
            return value
        except (AttributeError, KeyError):
            return default
    
    def set_config(self, key: str, value: Any) -> None:
        """
        Set configuration value at runtime.
        
        Note: Changes are not persisted to files.
        """
        parts = key.split(".")
        obj = self._settings
        
        for part in parts[:-1]:
            if not hasattr(obj, part):
                setattr(obj, part, {})
            obj = getattr(obj, part)
        
        if isinstance(obj, dict):
            obj[parts[-1]] = value
        else:
            setattr(obj, parts[-1], value)
    
    def reload_config(self) -> None:
        """Reload configuration from files."""
        self._settings = reload_settings()
        self._validated = False
    
    def load_profile(self, profile_name: str) -> None:
        """
        Load a risk profile to override current settings.
        
        Args:
            profile_name: One of "conservative", "moderate", "aggressive"
        """
        if profile_name not in VALID_RISK_PROFILES:
            raise ValueError(
                f"Invalid profile '{profile_name}'. "
                f"Valid profiles: {VALID_RISK_PROFILES}"
            )
        
        profile_file = PROFILES_DIR / f"{profile_name}.toml"
        if not profile_file.exists():
            raise MissingConfigFileError(f"Profile file not found: {profile_file}")
        
        # Reload settings with profile
        global _settings
        
        settings_files = [str(SETTINGS_FILE)]
        if SECRETS_FILE.exists():
            settings_files.append(str(SECRETS_FILE))
        
        env = _get_environment()
        env_file = ENVIRONMENTS_DIR / f"{env}.toml"
        if env_file.exists():
            settings_files.append(str(env_file))
        
        # Add profile last so it overrides
        settings_files.append(str(profile_file))
        
        _settings = Dynaconf(
            envvar_prefix="TRADING_BOT",
            settings_files=settings_files,
            environments=True,
            env="default",
            load_dotenv=False,
            merge_enabled=True,
        )
        
        self._settings = _settings
        self._profile = profile_name
        self._validated = False
        
        logger.info(f"Loaded risk profile: {profile_name}")
    
    @property
    def current_profile(self) -> Optional[str]:
        """Get currently loaded risk profile name."""
        return self._profile
    
    @property
    def current_environment(self) -> str:
        """Get current environment (demo/live)."""
        return _get_environment()
    
    def get_alpaca_config(self) -> AlpacaBrokerConfig:
        """Get validated Alpaca broker configuration."""
        api_config = self.get_config("api.alpaca", {})
        if isinstance(api_config, dict):
            return AlpacaBrokerConfig(**api_config)
        # Handle Dynaconf object
        return AlpacaBrokerConfig(
            api_key=getattr(api_config, "api_key", ""),
            secret_key=getattr(api_config, "secret_key", ""),
            base_url=getattr(api_config, "base_url", "https://paper-api.alpaca.markets"),
            timeout=getattr(api_config, "timeout", 30),
            max_retries=getattr(api_config, "max_retries", 3),
            retry_delay=getattr(api_config, "retry_delay", 1.0),
            communication_method=getattr(api_config, "communication_method", "rest"),
        )
    
    def get_tastytrade_config(self) -> TastytradeBrokerConfig:
        """Get validated Tastytrade broker configuration."""
        api_config = self.get_config("api.tastytrade", {})
        if isinstance(api_config, dict):
            return TastytradeBrokerConfig(**api_config)
        return TastytradeBrokerConfig(
            client_secret=getattr(api_config, "client_secret", ""),
            refresh_token=getattr(api_config, "refresh_token", ""),
            account_id=getattr(api_config, "account_id", ""),
            is_sandbox=getattr(api_config, "is_sandbox", True),
        )
    
    def get_webhook_config(self) -> WebhookConfig:
        """Get validated webhook configuration."""
        webhook = self.get_config("api.webhook", {})
        if isinstance(webhook, dict):
            return WebhookConfig(**webhook)
        return WebhookConfig(
            host=getattr(webhook, "host", "0.0.0.0"),
            port=getattr(webhook, "port", 8080),
            security_enabled=getattr(webhook, "security_enabled", False),
            secret=getattr(webhook, "secret", ""),
        )
    
    def get_broker_for_symbol(self, symbol: str) -> str:
        """
        Get the broker to use for a specific symbol.
        
        Uses symbol-specific routing if configured, otherwise uses default.
        
        Args:
            symbol: Stock symbol to route
            
        Returns:
            Broker name ("alpaca" or "tastytrade")
            
        Raises:
            ConfigValidationError: If no broker configuration exists
        """
        # Check for symbol-specific routing
        symbol_config = self.get_config(f"symbols.{symbol}", None)
        if symbol_config:
            broker = (
                symbol_config.get("broker") 
                if isinstance(symbol_config, dict) 
                else getattr(symbol_config, "broker", None)
            )
            if broker:
                return broker
        
        # Fall back to _default symbol config
        default_config = self.get_config("symbols._default", {})
        if default_config:
            broker = (
                default_config.get("broker")
                if isinstance(default_config, dict)
                else getattr(default_config, "broker", None)
            )
            if broker:
                return broker
        
        # No configuration found - raise error instead of silent fallback
        configured_brokers = self.get_configured_brokers()
        if not configured_brokers:
            raise ConfigValidationError(
                f"No broker configured for symbol '{symbol}'. "
                "Configure symbols._default.broker or add broker credentials."
            )
        
        # If we have configured brokers but no routing, use the first one with a warning
        logger.warning(
            f"No broker routing configured for '{symbol}'. "
            f"Using first configured broker: {configured_brokers[0]}. "
            "Set symbols._default.broker in config to silence this warning."
        )
        return configured_brokers[0]
    
    def get_configured_brokers(self) -> List[str]:
        """Get list of properly configured brokers."""
        configured = []
        
        if self.get_alpaca_config().is_configured:
            configured.append("alpaca")
        
        if self.get_tastytrade_config().is_configured:
            configured.append("tastytrade")
        
        return configured


# ============================================================================
# Startup Validation
# ============================================================================

def validate_config_files_exist() -> List[ValidationIssue]:
    """Check that required configuration files exist."""
    issues = []
    
    if not SETTINGS_FILE.exists():
        issues.append(ValidationIssue(
            severity="ERROR",
            message=f"Settings file not found: {SETTINGS_FILE}",
            path="config/settings.toml"
        ))
    
    if not SECRETS_FILE.exists():
        issues.append(ValidationIssue(
            severity="ERROR",
            message=(
                f"Secrets file not found: {SECRETS_FILE}. "
                f"Copy {CONFIG_DIR / '.secrets.toml.example'} to {SECRETS_FILE} "
                "and add your credentials."
            ),
            path="config/.secrets.toml"
        ))
    
    return issues


def validate_broker_configuration(config: ConfigurationManager) -> List[ValidationIssue]:
    """Validate that at least one broker is properly configured."""
    issues = []
    
    alpaca = config.get_alpaca_config()
    tastytrade = config.get_tastytrade_config()
    
    configured_brokers = []
    
    # Check Alpaca
    if alpaca.api_key or alpaca.secret_key:
        if not alpaca.is_configured:
            issues.append(ValidationIssue(
                severity="ERROR",
                message="Alpaca partially configured. Both api_key and secret_key required.",
                path="api.alpaca"
            ))
        else:
            configured_brokers.append("alpaca")
    
    # Check Tastytrade (OAuth credentials)
    if tastytrade.client_secret or tastytrade.refresh_token:
        if not tastytrade.is_configured:
            issues.append(ValidationIssue(
                severity="ERROR",
                message=(
                    "Tastytrade partially configured. Both client_secret and refresh_token required. "
                    "See https://tastyworks-api.readthedocs.io/en/latest/sessions.html for setup."
                ),
                path="api.tastytrade"
            ))
        else:
            configured_brokers.append("tastytrade")
    
    # At least one broker must be configured
    if not configured_brokers:
        issues.append(ValidationIssue(
            severity="ERROR",
            message="No brokers configured. At least one broker (alpaca or tastytrade) must be fully configured.",
        ))
    
    return issues


def validate_symbol_routing(config: ConfigurationManager) -> List[ValidationIssue]:
    """Validate symbol-to-broker routing configuration."""
    issues = []
    configured_brokers = config.get_configured_brokers()
    
    # Check _default symbol broker exists
    default_broker = config.get_broker_for_symbol("_default")
    if default_broker not in configured_brokers:
        issues.append(ValidationIssue(
            severity="ERROR",
            message=(
                f"Default symbol broker '{default_broker}' is not configured. "
                f"Configured brokers: {configured_brokers}"
            ),
            path="symbols._default.broker"
        ))
    
    # Check all symbol-specific brokers are configured
    symbols_config = config.get_config("symbols", {})
    if isinstance(symbols_config, dict):
        for symbol, sym_config in symbols_config.items():
            if symbol in ("_default", "whitelist_enabled", "default_symbols"):
                continue
            
            broker = (
                sym_config.get("broker")
                if isinstance(sym_config, dict)
                else getattr(sym_config, "broker", None)
            )
            
            if broker and broker not in configured_brokers:
                issues.append(ValidationIssue(
                    severity="ERROR",
                    message=(
                        f"Symbol '{symbol}' routes to broker '{broker}' which is not configured. "
                        f"Configured brokers: {configured_brokers}"
                    ),
                    path=f"symbols.{symbol}.broker"
                ))
    
    return issues


def validate_risk_settings(config: ConfigurationManager) -> List[ValidationIssue]:
    """Validate risk management settings."""
    issues = []
    
    # Check position sizing
    risk_per_trade = config.get_config("trading.position_sizing.risk_per_trade", 0.02)
    if risk_per_trade > 0.10:
        issues.append(ValidationIssue(
            severity="ERROR",
            message=f"Extremely high risk per trade: {risk_per_trade:.1%} (>10%)",
            path="trading.position_sizing.risk_per_trade"
        ))
    elif risk_per_trade > 0.05:
        issues.append(ValidationIssue(
            severity="WARN",
            message=f"High risk per trade: {risk_per_trade:.1%} (>5%)",
            path="trading.position_sizing.risk_per_trade"
        ))
    
    # Check DCA settings
    max_attempts = config.get_config("trading.position_sizing.averaging.max_attempts", 3)
    if max_attempts > 6:
        issues.append(ValidationIssue(
            severity="WARN",
            message=f"High DCA attempts: {max_attempts} (>6)",
            path="trading.position_sizing.averaging.max_attempts"
        ))
    
    multiplier = config.get_config("trading.position_sizing.averaging.multiplier", 1.5)
    if multiplier > 2.5:
        issues.append(ValidationIssue(
            severity="WARN",
            message=f"High DCA multiplier: {multiplier}x (>2.5)",
            path="trading.position_sizing.averaging.multiplier"
        ))
    
    return issues


def validate_live_mode(config: ConfigurationManager) -> List[ValidationIssue]:
    """Check if live mode is enabled and warn user."""
    issues = []
    
    env = config.current_environment
    if env == "live":
        # Check Alpaca is using live endpoint
        alpaca = config.get_alpaca_config()
        if alpaca.is_configured and not alpaca.is_paper:
            issues.append(ValidationIssue(
                severity="WARN",
                message="LIVE TRADING MODE ENABLED. Real money at risk!",
            ))
    
    return issues


def validate_startup() -> List[ValidationIssue]:
    """
    Run all startup validation checks.
    
    Returns:
        List of ValidationIssue objects
        
    Raises:
        ConfigValidationError: If any ERROR-level issues found
    """
    all_issues = []
    
    # Phase 1: Check files exist
    all_issues.extend(validate_config_files_exist())
    
    # If settings file doesn't exist, we can't continue
    if any(i.severity == "ERROR" and "settings.toml" in str(i) for i in all_issues):
        return all_issues
    
    # Phase 2: Load and validate configuration
    config = ConfigurationManager()
    
    all_issues.extend(validate_broker_configuration(config))
    all_issues.extend(validate_symbol_routing(config))
    all_issues.extend(validate_risk_settings(config))
    all_issues.extend(validate_live_mode(config))
    
    return all_issues


def validate_and_exit_on_error() -> ConfigurationManager:
    """
    Validate configuration and exit if errors found.
    
    This is the main entry point for bot startup validation.
    
    Returns:
        ConfigurationManager instance if validation passes
        
    Raises:
        SystemExit: If ERROR-level issues found
    """
    issues = validate_startup()
    
    errors = [i for i in issues if i.severity == "ERROR"]
    warnings = [i for i in issues if i.severity == "WARN"]
    infos = [i for i in issues if i.severity == "INFO"]
    
    # Log all issues
    for issue in infos:
        logger.info(str(issue))
    
    for issue in warnings:
        logger.warning(str(issue))
    
    for issue in errors:
        logger.error(str(issue))
    
    # Fail fast on errors
    if errors:
        logger.error(
            f"Configuration validation failed with {len(errors)} error(s). "
            "Fix the issues above and restart."
        )
        sys.exit(1)
    
    # Live mode confirmation
    config = ConfigurationManager._create_validated()  # Internal method creates validated instance
    if config.current_environment == "live":
        alpaca = config.get_alpaca_config()
        if alpaca.is_configured and not alpaca.is_paper:
            print("\n" + "="*60)
            print("⚠️  LIVE TRADING MODE DETECTED")
            print("    Real money will be used for trading.")
            print("="*60)
            
            try:
                response = input("\nType 'CONFIRM' to proceed with live trading: ")
                if response.strip() != "CONFIRM":
                    print("Live trading cancelled.")
                    sys.exit(0)
            except (EOFError, KeyboardInterrupt):
                print("\nLive trading cancelled.")
                sys.exit(0)
    
    logger.info(
        f"Configuration validated successfully. "
        f"Environment: {config.current_environment}, "
        f"Brokers: {config.get_configured_brokers()}"
    )
    
    return config


# ============================================================================
# Module-Level Convenience Access
# ============================================================================

# Create default config manager for easy import
config = ConfigurationManager()


def get_config(key: str, default: Any = None) -> Any:
    """Convenience function to get config value."""
    return config.get_config(key, default)
