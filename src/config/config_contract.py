"""
Canonical Configuration Contract (Azure-First).

This module defines the SINGLE SOURCE OF TRUTH for all configuration fields,
their canonical names, required vs optional status, and precedence rules.

CONFIGURATION STRATEGY:
All configuration should be managed via Azure for production deployments,
enabling runtime updates WITHOUT requiring redeployment.

CONFIGURATION PRECEDENCE (highest to lowest):
1. Azure Key Vault (secrets: API keys, passwords, connection strings)
2. Azure App Configuration (runtime config: feature flags, settings)
3. Environment variables (local dev overrides, container config)
4. Default values (sensible defaults for optional fields)

NOTE: Local TOML files are NOT supported. Use environment variables for local
development and Azure services for production. This ensures configuration
can be updated without redeployment.

USAGE:
    from src.config.config_contract import ConfigContract, ConfigField
    
    # Get canonical field definition
    field = ConfigContract.get_field("alpaca_api_key")
    
    # Validate all required config at startup
    errors = ConfigContract.validate_required(config_dict)
    if errors:
        raise ConfigurationException("\\n".join(errors))

ANTI-PATTERNS TO AVOID:
    - ❌ Hard-coding config keys in multiple files
    - ❌ Different env var names for the same value
    - ❌ Missing required field validation
    - ❌ Silent fallbacks to wrong values
    - ❌ Using local TOML files (requires redeployment to change)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Type, Callable, Union


class ConfigCategory(Enum):
    """Configuration categories for organization."""
    SECRETS = "secrets"          # Sensitive values (Key Vault)
    DATABASE = "database"        # Database/Cosmos settings
    BROKER = "broker"            # Broker API settings
    TRADING = "trading"          # Trading parameters
    WEBHOOK = "webhook"          # Webhook/API server
    LOGGING = "logging"          # Logging settings
    MONITORING = "monitoring"    # Monitoring/health
    FEATURE = "feature"          # Feature flags


class ConfigSource(Enum):
    """
    Configuration source with precedence.
    
    Azure-first strategy: Production deployments should use Azure Key Vault
    for secrets and Azure App Configuration for runtime settings. This allows
    configuration changes without redeployment.
    
    Local development can use environment variables directly.
    """
    KEY_VAULT = 1       # Azure Key Vault (highest for secrets)
    APP_CONFIG = 2      # Azure App Configuration (runtime config)
    ENVIRONMENT = 3     # Environment variables (local dev / container overrides)
    DEFAULT = 4         # Hard-coded defaults (lowest)


@dataclass
class ConfigField:
    """
    Canonical configuration field definition.
    
    All configuration should be managed via Azure services for production:
    - Secrets → Azure Key Vault
    - Runtime config → Azure App Configuration
    - Local dev → Environment variables
    
    Attributes:
        canonical_name: The single canonical name for this field
        category: Category for organization
        required: Whether this field is required for startup
        secret: Whether this is a sensitive value (should come from Key Vault)
        env_var: Environment variable name (standardized)
        key_vault_name: Name in Azure Key Vault (for secrets)
        app_config_key: Key in Azure App Configuration
        default: Default value if not found
        type_: Expected type for validation
        validator: Optional custom validation function
        description: Human-readable description
        error_hint: Actionable error message if missing/invalid
    """
    canonical_name: str
    category: ConfigCategory
    required: bool = False
    secret: bool = False
    env_var: Optional[str] = None
    key_vault_name: Optional[str] = None
    app_config_key: Optional[str] = None
    default: Any = None
    type_: Type = str
    validator: Optional[Callable[[Any], bool]] = None
    description: str = ""
    error_hint: str = ""
    
    def get_env_var(self) -> str:
        """Get standardized environment variable name."""
        if self.env_var:
            return self.env_var
        # Auto-generate from canonical name
        return self.canonical_name.upper().replace(".", "_").replace("-", "_")
    
    def validate_value(self, value: Any) -> Optional[str]:
        """
        Validate a configuration value.
        
        Returns:
            None if valid, error message string if invalid
        """
        if value is None:
            if self.required:
                return f"Required configuration '{self.canonical_name}' is missing. {self.error_hint}"
            return None
        
        # Type validation
        if self.type_ and not isinstance(value, self.type_):
            # Try type coercion
            try:
                if self.type_ == bool:
                    if isinstance(value, str):
                        value = value.lower() in ("true", "yes", "1")
                    else:
                        value = bool(value)
                elif self.type_ == int:
                    value = int(value)
                elif self.type_ == float:
                    value = float(value)
                elif self.type_ == str:
                    value = str(value)
            except (ValueError, TypeError):
                return (
                    f"Configuration '{self.canonical_name}' has wrong type. "
                    f"Expected {self.type_.__name__}, got {type(value).__name__}"
                )
        
        # Custom validator
        if self.validator:
            try:
                if not self.validator(value):
                    return f"Configuration '{self.canonical_name}' failed validation. {self.error_hint}"
            except Exception as e:
                return f"Configuration '{self.canonical_name}' validation error: {e}"
        
        return None


# =============================================================================
# CANONICAL CONFIGURATION FIELDS
# =============================================================================
# These are the SINGLE SOURCE OF TRUTH for all configuration field names.
# ANY new configuration must be added here first.

_FIELDS: Dict[str, ConfigField] = {}


def _register_field(field: ConfigField) -> ConfigField:
    """Register a field in the canonical registry."""
    _FIELDS[field.canonical_name] = field
    return field


# -----------------------------------------------------------------------------
# SECRETS (Azure Key Vault / Environment Variables)
# -----------------------------------------------------------------------------

ALPACA_API_KEY = _register_field(ConfigField(
    canonical_name="alpaca_api_key",
    category=ConfigCategory.SECRETS,
    required=False,  # Only required if using Alpaca
    secret=True,
    env_var="ALPACA_API_KEY",
    key_vault_name="alpaca-api-key",
    description="Alpaca API key for trading",
    error_hint="Get API keys from https://app.alpaca.markets/",
))

ALPACA_SECRET_KEY = _register_field(ConfigField(
    canonical_name="alpaca_secret_key",
    category=ConfigCategory.SECRETS,
    required=False,  # Only required if using Alpaca
    secret=True,
    env_var="ALPACA_SECRET_KEY",
    key_vault_name="alpaca-secret-key",
    description="Alpaca secret key for trading",
    error_hint="Get API keys from https://app.alpaca.markets/",
))

TASTYTRADE_CLIENT_SECRET = _register_field(ConfigField(
    canonical_name="tastytrade_client_secret",
    category=ConfigCategory.SECRETS,
    required=False,  # Only required if using Tastytrade
    secret=True,
    env_var="TASTYTRADE_CLIENT_SECRET",
    key_vault_name="tastytrade-client-secret",
    description="Tastytrade OAuth client secret",
    error_hint="Generate from Tastytrade developer portal",
))

TASTYTRADE_REFRESH_TOKEN = _register_field(ConfigField(
    canonical_name="tastytrade_refresh_token",
    category=ConfigCategory.SECRETS,
    required=False,
    secret=True,
    env_var="TASTYTRADE_REFRESH_TOKEN",
    key_vault_name="tastytrade-refresh-token",
    description="Tastytrade OAuth refresh token",
    error_hint="Generate from Tastytrade OAuth flow",
))

TASTYTRADE_ACCOUNT_ID = _register_field(ConfigField(
    canonical_name="tastytrade_account_id",
    category=ConfigCategory.SECRETS,
    required=False,
    secret=True,
    env_var="TASTYTRADE_ACCOUNT_ID",
    key_vault_name="tastytrade-account-id",
    description="Tastytrade account ID",
    error_hint="Find in Tastytrade account settings",
))

WEBHOOK_SECRET = _register_field(ConfigField(
    canonical_name="webhook_secret",
    category=ConfigCategory.SECRETS,
    required=False,  # Only required if webhook security enabled
    secret=True,
    env_var="WEBHOOK_SECRET",
    key_vault_name="webhook-secret",
    description="Webhook authentication secret",
    error_hint="Generate with: openssl rand -hex 32",
))

# -----------------------------------------------------------------------------
# DATABASE (Cosmos DB)
# -----------------------------------------------------------------------------

COSMOS_ENDPOINT = _register_field(ConfigField(
    canonical_name="cosmos_endpoint",
    category=ConfigCategory.DATABASE,
    required=True,  # Required for database operations
    secret=False,
    env_var="AZURE_COSMOS_ENDPOINT",  # Standardized name
    app_config_key="database.cosmos.endpoint",
    description="Azure Cosmos DB account endpoint",
    error_hint="Find in Azure Portal > Cosmos DB > Keys. Format: https://<account>.documents.azure.com:443/ or use emulator at https://localhost:8081",
    # Accept both Azure Cosmos DB and local emulator endpoints
    validator=lambda v: v and v.startswith("https://") and ("documents.azure.com" in v or "localhost" in v),
))

COSMOS_KEY = _register_field(ConfigField(
    canonical_name="cosmos_key",
    category=ConfigCategory.DATABASE,
    required=False,  # Optional if using Managed Identity
    secret=True,
    env_var="AZURE_COSMOS_KEY",  # Standardized name
    key_vault_name="cosmos-key",
    description="Azure Cosmos DB account key (not needed with Managed Identity)",
    error_hint="Find in Azure Portal > Cosmos DB > Keys. Consider using Managed Identity instead.",
))

COSMOS_DATABASE = _register_field(ConfigField(
    canonical_name="cosmos_database",
    category=ConfigCategory.DATABASE,
    required=True,
    secret=False,
    env_var="AZURE_COSMOS_DATABASE",  # Standardized name
    app_config_key="database.cosmos.database_name",
    default="trading_bot",
    description="Cosmos DB database name",
    error_hint="Create database in Azure Portal > Cosmos DB > Data Explorer",
))

COSMOS_THROUGHPUT_RU = _register_field(ConfigField(
    canonical_name="cosmos_throughput_ru",
    category=ConfigCategory.DATABASE,
    required=False,
    secret=False,
    env_var="COSMOS_THROUGHPUT_RU",
    app_config_key="database.throughput_ru",
    default=400,
    type_=int,
    description="Cosmos DB throughput in Request Units per second",
    error_hint="Minimum 400 RU/s for free tier. Increase for production workloads.",
    validator=lambda v: v >= 400,
))

COSMOS_CONSISTENCY = _register_field(ConfigField(
    canonical_name="cosmos_consistency",
    category=ConfigCategory.DATABASE,
    required=False,
    secret=False,
    env_var="COSMOS_CONSISTENCY_LEVEL",
    app_config_key="database.consistency_level",
    default="Session",
    description="Cosmos DB consistency level",
    error_hint="Valid values: Strong, BoundedStaleness, Session, ConsistentPrefix, Eventual",
    validator=lambda v: v in ("Strong", "BoundedStaleness", "Session", "ConsistentPrefix", "Eventual"),
))

# -----------------------------------------------------------------------------
# BROKER CONFIGURATION
# -----------------------------------------------------------------------------

ALPACA_BASE_URL = _register_field(ConfigField(
    canonical_name="alpaca_base_url",
    category=ConfigCategory.BROKER,
    required=False,
    secret=False,
    env_var="ALPACA_BASE_URL",
    app_config_key="broker.alpaca.base_url",
    default="https://paper-api.alpaca.markets",
    description="Alpaca API base URL (paper or live)",
    error_hint="Use https://paper-api.alpaca.markets for paper trading, https://api.alpaca.markets for live",
    validator=lambda v: v and v.startswith("https://"),
))

ALPACA_TIMEOUT = _register_field(ConfigField(
    canonical_name="alpaca_timeout",
    category=ConfigCategory.BROKER,
    required=False,
    secret=False,
    env_var="ALPACA_TIMEOUT",
    app_config_key="broker.alpaca.timeout",
    default=30,
    type_=int,
    description="Alpaca API timeout in seconds",
))

DEFAULT_BROKER = _register_field(ConfigField(
    canonical_name="default_broker",
    category=ConfigCategory.BROKER,
    required=False,
    secret=False,
    env_var="DEFAULT_BROKER",
    app_config_key="broker.default",
    default="alpaca",
    description="Default broker for trading",
    error_hint="Valid values: alpaca, tastytrade",
    validator=lambda v: v in ("alpaca", "tastytrade"),
))

# -----------------------------------------------------------------------------
# WEBHOOK / API SERVER
# -----------------------------------------------------------------------------

WEBHOOK_HOST = _register_field(ConfigField(
    canonical_name="webhook_host",
    category=ConfigCategory.WEBHOOK,
    required=False,
    secret=False,
    env_var="WEBHOOK_HOST",
    app_config_key="api.webhook.host",
    default="0.0.0.0",
    description="Webhook server host address",
))

WEBHOOK_PORT = _register_field(ConfigField(
    canonical_name="webhook_port",
    category=ConfigCategory.WEBHOOK,
    required=False,
    secret=False,
    env_var="WEBHOOK_PORT",
    app_config_key="api.webhook.port",
    default=8080,
    type_=int,
    description="Webhook server port",
    validator=lambda v: 1024 <= v <= 65535,
))

WEBHOOK_SECURITY_ENABLED = _register_field(ConfigField(
    canonical_name="webhook_security_enabled",
    category=ConfigCategory.WEBHOOK,
    required=False,
    secret=False,
    env_var="WEBHOOK_SECURITY_ENABLED",
    app_config_key="api.webhook.security_enabled",
    default=True,
    type_=bool,
    description="Enable webhook secret validation",
))

# -----------------------------------------------------------------------------
# LOGGING
# -----------------------------------------------------------------------------

LOG_LEVEL = _register_field(ConfigField(
    canonical_name="log_level",
    category=ConfigCategory.LOGGING,
    required=False,
    secret=False,
    env_var="LOG_LEVEL",
    app_config_key="logging.level",
    default="INFO",
    description="Logging level",
    validator=lambda v: v.upper() in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
))

LOG_FORMAT = _register_field(ConfigField(
    canonical_name="log_format",
    category=ConfigCategory.LOGGING,
    required=False,
    secret=False,
    env_var="LOG_FORMAT",
    app_config_key="logging.format",
    default="json",
    description="Logging format (json or text)",
    validator=lambda v: v.lower() in ("json", "text"),
))

# -----------------------------------------------------------------------------
# TRADING PARAMETERS
# -----------------------------------------------------------------------------

TRADING_PAPER_MODE = _register_field(ConfigField(
    canonical_name="trading_paper_mode",
    category=ConfigCategory.TRADING,
    required=False,
    secret=False,
    env_var="TRADING_PAPER_MODE",
    app_config_key="trading.paper_mode",
    default=True,
    type_=bool,
    description="Enable paper trading mode",
))

TRADING_ORDER_TYPE = _register_field(ConfigField(
    canonical_name="trading_order_type",
    category=ConfigCategory.TRADING,
    required=False,
    secret=False,
    env_var="TRADING_ORDER_TYPE",
    app_config_key="trading.order_type",
    default="limit",
    description="Default order type",
    validator=lambda v: v.lower() in ("market", "limit"),
))

TRADING_MAX_DAILY_TRADES = _register_field(ConfigField(
    canonical_name="trading_max_daily_trades",
    category=ConfigCategory.TRADING,
    required=False,
    secret=False,
    env_var="TRADING_MAX_DAILY_TRADES",
    app_config_key="trading.max_daily_trades",
    default=50,
    type_=int,
    description="Maximum trades per day",
))

# -----------------------------------------------------------------------------
# MONITORING
# -----------------------------------------------------------------------------

MONITORING_ENABLED = _register_field(ConfigField(
    canonical_name="monitoring_enabled",
    category=ConfigCategory.MONITORING,
    required=False,
    secret=False,
    env_var="MONITORING_ENABLED",
    app_config_key="monitoring.enabled",
    default=True,
    type_=bool,
    description="Enable monitoring and health checks",
))

# -----------------------------------------------------------------------------
# AZURE INFRASTRUCTURE
# -----------------------------------------------------------------------------

AZURE_KEYVAULT_URL = _register_field(ConfigField(
    canonical_name="azure_keyvault_url",
    category=ConfigCategory.SECRETS,
    required=False,  # Not required for local dev
    secret=False,
    env_var="AZURE_KEYVAULT_URL",
    description="Azure Key Vault URL for secrets",
    error_hint="Format: https://<vault-name>.vault.azure.net",
    validator=lambda v: not v or (v.startswith("https://") and ".vault.azure.net" in v),
))

AZURE_APP_CONFIG_ENDPOINT = _register_field(ConfigField(
    canonical_name="azure_app_config_endpoint",
    category=ConfigCategory.FEATURE,
    required=False,
    secret=False,
    env_var="AZURE_APP_CONFIGURATION_ENDPOINT",
    description="Azure App Configuration endpoint",
    error_hint="Format: https://<config-name>.azconfig.io",
    validator=lambda v: not v or (v.startswith("https://") and ".azconfig.io" in v),
))


# =============================================================================
# CONFIGURATION CONTRACT CLASS
# =============================================================================

class ConfigContract:
    """
    Canonical configuration contract for the trading bot.
    
    Provides a single source of truth for:
    - Field names and their canonical forms
    - Required vs optional fields
    - Source precedence
    - Validation rules
    - Error messages with actionable hints
    
    Example:
        # At startup
        errors = ConfigContract.validate_required({
            'cosmos_endpoint': os.environ.get('AZURE_COSMOS_ENDPOINT'),
            'cosmos_database': os.environ.get('AZURE_COSMOS_DATABASE'),
        })
        if errors:
            for error in errors:
                print(f"❌ {error}")
            sys.exit(1)
    """
    
    # Source precedence (higher = higher priority)
    # Azure-first: Production uses Key Vault (secrets) + App Config (settings)
    # Local dev uses environment variables
    SOURCE_PRECEDENCE = [
        ConfigSource.KEY_VAULT,      # 1 - Highest for secrets
        ConfigSource.APP_CONFIG,     # 2 - Azure App Config (runtime settings)
        ConfigSource.ENVIRONMENT,    # 3 - Environment variables (local dev)
        ConfigSource.DEFAULT,        # 4 - Default values
    ]
    
    @classmethod
    def get_field(cls, canonical_name: str) -> Optional[ConfigField]:
        """Get field definition by canonical name."""
        return _FIELDS.get(canonical_name)
    
    @classmethod
    def get_all_fields(cls) -> Dict[str, ConfigField]:
        """Get all registered fields."""
        return dict(_FIELDS)
    
    @classmethod
    def get_fields_by_category(cls, category: ConfigCategory) -> List[ConfigField]:
        """Get all fields in a category."""
        return [f for f in _FIELDS.values() if f.category == category]
    
    @classmethod
    def get_required_fields(cls) -> List[ConfigField]:
        """Get all required fields."""
        return [f for f in _FIELDS.values() if f.required]
    
    @classmethod
    def get_secret_fields(cls) -> List[ConfigField]:
        """Get all secret fields."""
        return [f for f in _FIELDS.values() if f.secret]
    
    @classmethod
    def validate_required(
        cls, 
        config_values: Dict[str, Any],
        check_broker: bool = True
    ) -> List[str]:
        """
        Validate that all required fields are present and valid.
        
        Args:
            config_values: Dict of canonical_name -> value
            check_broker: If True, validate that at least one broker is configured
            
        Returns:
            List of error messages (empty if all valid)
        """
        errors = []
        
        # Validate required fields
        for field in cls.get_required_fields():
            value = config_values.get(field.canonical_name)
            error = field.validate_value(value)
            if error:
                errors.append(error)
        
        # Validate all provided values (even if not required)
        for name, value in config_values.items():
            field = _FIELDS.get(name)
            if field and value is not None:
                error = field.validate_value(value)
                if error and error not in errors:
                    errors.append(error)
        
        # Check that at least one broker is configured
        if check_broker:
            alpaca_configured = (
                config_values.get("alpaca_api_key") and 
                config_values.get("alpaca_secret_key")
            )
            tastytrade_configured = (
                config_values.get("tastytrade_client_secret") and 
                config_values.get("tastytrade_refresh_token")
            )
            
            if not alpaca_configured and not tastytrade_configured:
                errors.append(
                    "No broker configured. Either Alpaca (api_key + secret_key) or "
                    "Tastytrade (client_secret + refresh_token) credentials are required. "
                    "Get Alpaca keys from https://app.alpaca.markets/"
                )
        
        return errors
    
    @classmethod
    def get_env_var_mapping(cls) -> Dict[str, str]:
        """
        Get mapping of canonical names to environment variable names.
        
        Useful for documentation and debugging.
        """
        return {
            name: field.get_env_var()
            for name, field in _FIELDS.items()
        }
    
    @classmethod
    def get_keyvault_mapping(cls) -> Dict[str, str]:
        """
        Get mapping of canonical names to Key Vault secret names.
        """
        return {
            name: field.key_vault_name
            for name, field in _FIELDS.items()
            if field.key_vault_name
        }
    
    @classmethod
    def resolve_value(
        cls,
        field_name: str,
        sources: Dict[ConfigSource, Dict[str, Any]]
    ) -> tuple[Any, ConfigSource]:
        """
        Resolve configuration value from sources by precedence.
        
        Args:
            field_name: Canonical field name
            sources: Dict of ConfigSource -> values dict
            
        Returns:
            Tuple of (value, source_used)
        """
        field = _FIELDS.get(field_name)
        if not field:
            return None, ConfigSource.DEFAULT
        
        # Check sources in precedence order
        for source in cls.SOURCE_PRECEDENCE:
            source_values = sources.get(source, {})
            
            # Get the appropriate key for this source
            if source == ConfigSource.KEY_VAULT and field.key_vault_name:
                value = source_values.get(field.key_vault_name)
            elif source == ConfigSource.APP_CONFIG and field.app_config_key:
                value = source_values.get(field.app_config_key)
            elif source == ConfigSource.ENVIRONMENT:
                value = source_values.get(field.get_env_var())
            else:
                continue
            
            if value is not None:
                return value, source
        
        # Return default
        return field.default, ConfigSource.DEFAULT
    
    @classmethod
    def format_validation_errors(cls, errors: List[str]) -> str:
        """
        Format validation errors for display.
        
        Returns:
            Formatted error message with header and actionable hints
        """
        if not errors:
            return ""
        
        lines = [
            "",
            "=" * 70,
            "❌ CONFIGURATION VALIDATION FAILED - STARTUP BLOCKED",
            "=" * 70,
            "",
            f"Found {len(errors)} configuration error(s):",
            "",
        ]
        
        for i, error in enumerate(errors, 1):
            lines.append(f"  {i}. {error}")
            lines.append("")
        
        lines.extend([
            "=" * 70,
            "💡 QUICK FIXES:",
            "  • For local dev: Set required environment variables",
            "  • For Azure: Add secrets to Key Vault, settings to App Configuration",
            "  • Run 'python -m src.config.config_contract --check' to validate config",
            "=" * 70,
            "",
        ])
        
        return "\n".join(lines)


# =============================================================================
# CLI for Configuration Validation
# =============================================================================

def _cli_check():
    """Command-line configuration check."""
    import os
    
    print("🔍 Checking configuration...")
    print()
    
    # Collect values from environment
    config_values = {}
    for name, field in _FIELDS.items():
        env_var = field.get_env_var()
        value = os.environ.get(env_var)
        if value:
            config_values[name] = value
            print(f"  ✅ {name}: (set via {env_var})")
        elif field.default is not None:
            config_values[name] = field.default
            print(f"  ⚪ {name}: (using default: {field.default})")
        else:
            if field.required:
                print(f"  ❌ {name}: MISSING (required)")
            else:
                print(f"  ⚪ {name}: (not set, optional)")
    
    print()
    
    # Validate
    errors = ConfigContract.validate_required(config_values)
    
    if errors:
        print(ConfigContract.format_validation_errors(errors))
        return 1
    else:
        print("✅ Configuration validation PASSED")
        return 0


if __name__ == "__main__":
    import sys
    
    if "--check" in sys.argv:
        sys.exit(_cli_check())
    else:
        print("Usage: python -m src.config.config_contract --check")
        print("       Validate current configuration against contract")
