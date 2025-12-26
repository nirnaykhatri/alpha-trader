"""
Startup Validation Service

Consolidates all startup validation logic using the canonical ConfigContract.
This ensures fail-fast behavior with actionable error messages when
configuration is missing or invalid.

USAGE:
    validator = StartupValidationService()
    result = validator.validate()
    
    if result.has_errors():
        print("Startup blocked due to errors")
        sys.exit(1)

This module integrates with:
- src/core/startup_mode.py (canonical startup mode policy)
- src/config/config_contract.py (canonical field definitions)
- src/config/config_validation_service.py (validation logic)

STARTUP MODES:
    See src/core/startup_mode.py for the canonical definition.
    The bot supports two startup modes controlled by STARTUP_MODE environment variable:
    
    - "headless" (default for production):
        Requires broker credentials at startup. Fail-fast if no broker configured.
        
    - "ui-config" (default for development):
        Broker credentials are optional at startup. Users can add brokers via web UI.
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from src.core import ConfigurationManager
from src.config.config_schema import ConfigValidator, ValidationSeverity
from src.config.config_contract import ConfigContract
from src.exceptions import ConfigurationException

# Import StartupMode from its canonical location and re-export for backward compatibility
from src.core.startup_mode import StartupMode

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """Validation severity levels."""
    ERROR = "error"      # Blocks startup
    WARNING = "warning"  # Non-blocking but important
    INFO = "info"        # Informational only


@dataclass
class ValidationIssue:
    """Represents a configuration validation issue."""
    level: ValidationLevel
    message: str
    component: str = "config"
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of startup validation."""
    passed: bool
    issues: List[ValidationIssue]
    warnings_count: int = 0
    errors_count: int = 0
    
    def has_errors(self) -> bool:
        """Check if there are blocking errors."""
        return self.errors_count > 0
    
    def has_warnings(self) -> bool:
        """Check if there are warnings."""
        return self.warnings_count > 0


class StartupValidationService:
    """
    Centralized startup validation service.
    
    Performs all necessary validation checks before bot startup using
    the canonical ConfigContract for field definitions and validation.
    
    This service implements FAIL-FAST behavior:
    - Critical errors block startup with actionable messages
    - Warnings are logged but don't block startup
    - Info messages provide operational context
    
    Startup Modes:
        - HEADLESS: Requires broker at startup (production)
        - UI_CONFIG: Broker optional (development/demo)
    
    Example:
        validator = StartupValidationService()
        result = validator.validate()
        
        if result.has_errors():
            print("Startup blocked due to errors")
            sys.exit(1)
    """
    
    def __init__(self, config_file: str = None):
        """
        Initialize validation service.
        
        Args:
            config_file: DEPRECATED - No longer used. Configuration is loaded
                        via ConfigContract from environment/Azure.
        """
        if config_file is not None:
            import warnings
            warnings.warn(
                "config_file parameter is deprecated. Configuration is now loaded from "
                "environment variables and Azure services.",
                DeprecationWarning,
                stacklevel=2
            )
        self.issues: List[ValidationIssue] = []
        self._contract = ConfigContract
        self._startup_mode = StartupMode.from_env()
    
    def validate(self, verbose: bool = True) -> ValidationResult:
        """
        Perform comprehensive startup validation.
        
        This method validates:
        1. Required configuration fields (per ConfigContract)
        2. Configuration value constraints
        3. Broker credentials (at least one configured)
        4. Webhook security settings
        5. Production safety checks
        
        Args:
            verbose: Whether to print detailed output
            
        Returns:
            ValidationResult with all issues
        """
        self.issues = []
        
        # Contract-based validation (primary)
        self._validate_contract()
        
        # Schema validation (Pydantic models)
        self._validate_schema()
        
        # Configuration validation via ConfigurationManager
        self._validate_configuration()
        
        # API credentials validation
        self._validate_api_credentials()
        
        # Webhook security validation
        self._validate_webhook_security()
        
        # Production safety checks
        self._validate_production_safety()
        
        # Compile results
        result = self._compile_results()
        
        # Print results if verbose
        if verbose:
            self._print_validation_results(result)
        
        return result
    
    def _validate_contract(self) -> None:
        """Validate configuration against canonical contract."""
        import os
        
        # Collect values from environment using contract definitions
        config_values = {}
        
        for field_name, field_def in self._contract.get_all_fields().items():
            env_var = field_def.get_env_var()
            value = os.environ.get(env_var)
            
            if value is not None:
                config_values[field_name] = value
            elif field_def.default is not None:
                config_values[field_name] = field_def.default
        
        # Validate required fields using contract
        # Broker requirement depends on startup mode:
        #   - HEADLESS: broker required (production)
        #   - UI_CONFIG: broker optional (development)
        check_broker = self._startup_mode.requires_broker_at_startup
        errors = self._contract.validate_required(config_values, check_broker=check_broker)
        
        for error in errors:
            self.issues.append(ValidationIssue(
                level=ValidationLevel.ERROR,
                message=error,
                component="contract",
                suggestion="Check environment variables or Azure configuration"
            ))
    
    def _validate_schema(self) -> None:
        """Validate configuration schema."""
        try:
            # ConfigValidator now uses ConfigurationManager internally
            validator = ConfigValidator()
            config = validator.load_and_validate()
            
            # Check for warnings (no strict errors in relaxed schema)
            if validator.has_warnings():
                for warning in validator.get_warnings():
                    # Parse severity from warning message
                    if ValidationSeverity.ERROR.value in warning:
                        self.issues.append(ValidationIssue(
                            level=ValidationLevel.ERROR,
                            message=warning,
                            component="schema",
                            suggestion="Fix schema validation error in Azure App Configuration or environment variables"
                        ))
                    elif ValidationSeverity.WARN.value in warning:
                        self.issues.append(ValidationIssue(
                            level=ValidationLevel.WARNING,
                            message=warning,
                            component="schema"
                        ))
                    else:
                        self.issues.append(ValidationIssue(
                            level=ValidationLevel.INFO,
                            message=warning,
                            component="schema"
                        ))
                
        except Exception as e:
            self.issues.append(ValidationIssue(
                level=ValidationLevel.ERROR,
                message=f"Configuration schema validation failed: {e}",
                component="schema",
                suggestion="Check Azure App Configuration or environment variables"
            ))
    
    def _validate_configuration(self) -> None:
        """Validate basic configuration requirements."""
        try:
            config_mgr = ConfigurationManager()  # Singleton, loads from config/
            config_mgr.validate_required_config()
            
        except ConfigurationException as e:
            self.issues.append(ValidationIssue(
                level=ValidationLevel.ERROR,
                message=str(e),
                component="config",
                suggestion="Add missing required configuration"
            ))
        except Exception as e:
            self.issues.append(ValidationIssue(
                level=ValidationLevel.ERROR,
                message=f"Configuration validation error: {e}",
                component="config"
            ))
    
    def _validate_api_credentials(self) -> None:
        """
        Validate API credentials based on startup mode.
        
        In HEADLESS mode: Broker credentials are REQUIRED - blocks startup if missing.
        In UI_CONFIG mode: Broker credentials are optional - users can add via UI.
        """
        try:
            config_mgr = ConfigurationManager()  # Singleton, loads from config/
            
            # Alpaca API key
            api_key = config_mgr.get_config("api.alpaca.api_key", "")
            secret_key = config_mgr.get_config("api.alpaca.secret_key", "")
            
            # Tastytrade check
            tastytrade_token = config_mgr.get_config("api.tastytrade.refresh_token", "")
            
            has_broker = bool((api_key and secret_key) or tastytrade_token)
            
            if has_broker:
                # Alpaca is pre-configured
                if api_key and secret_key:
                    if len(api_key) < 10 or len(secret_key) < 20:
                        self.issues.append(ValidationIssue(
                            level=ValidationLevel.WARNING,
                            message="Alpaca credentials look too short - verify they are correct",
                            component="broker"
                        ))
                    else:
                        # Check if paper trading
                        base_url = config_mgr.get_config("api.alpaca.base_url", "")
                        if "paper" in base_url:
                            self.issues.append(ValidationIssue(
                                level=ValidationLevel.INFO,
                                message="Alpaca broker pre-configured (paper trading)",
                                component="broker"
                            ))
                        else:
                            self.issues.append(ValidationIssue(
                                level=ValidationLevel.WARNING,
                                message="Alpaca broker pre-configured (LIVE trading mode)",
                                component="broker",
                                suggestion="Use paper trading for testing"
                            ))
                            
                if tastytrade_token:
                    self.issues.append(ValidationIssue(
                        level=ValidationLevel.INFO,
                        message="Tastytrade broker pre-configured",
                        component="broker"
                    ))
            else:
                # No broker pre-configured
                if self._startup_mode == StartupMode.HEADLESS:
                    # HEADLESS mode: broker is required - fail-fast
                    self.issues.append(ValidationIssue(
                        level=ValidationLevel.ERROR,
                        message="No broker configured (STARTUP_MODE=headless requires broker credentials)",
                        component="broker",
                        suggestion="Set ALPACA_API_KEY and ALPACA_SECRET_KEY, or set STARTUP_MODE=ui-config"
                    ))
                else:
                    # UI_CONFIG mode: broker is optional
                    self.issues.append(ValidationIssue(
                        level=ValidationLevel.INFO,
                        message=f"No broker pre-configured (STARTUP_MODE={self._startup_mode.value}) - add brokers via web UI at /brokers",
                        component="broker"
                    ))
                
        except Exception as e:
            logger.debug(f"Error checking broker credentials: {e}")
    
    def _validate_webhook_security(self) -> None:
        """Validate webhook security configuration."""
        try:
            config_mgr = ConfigurationManager()  # Singleton, loads from config/
            
            security_enabled = config_mgr.get_config("api.webhook.security_enabled", False)
            webhook_secret = config_mgr.get_config("api.webhook.secret", "")
            
            if security_enabled:
                if not webhook_secret:
                    self.issues.append(ValidationIssue(
                        level=ValidationLevel.ERROR,
                        message="Webhook secret is missing (required when security_enabled=true)",
                        component="security",
                        suggestion="Generate secret: openssl rand -hex 32"
                    ))
                elif len(webhook_secret) < 16:
                    self.issues.append(ValidationIssue(
                        level=ValidationLevel.WARNING,
                        message="Webhook secret should be at least 16 characters",
                        component="security",
                        suggestion="Use stronger secret: openssl rand -hex 32"
                    ))
            else:
                self.issues.append(ValidationIssue(
                    level=ValidationLevel.INFO,
                    message="Webhook security is disabled (development mode)",
                    component="security",
                    suggestion="Enable security for production use"
                ))
                
        except Exception as e:
            logger.debug(f"Error validating webhook security: {e}")
    
    def _validate_production_safety(self) -> None:
        """
        Validate production safety settings.
        
        Checks for potentially dangerous configurations that could
        lead to unexpected trading behavior or security issues.
        """
        import os
        
        try:
            config_mgr = ConfigurationManager()
            
            # Check live vs paper trading consistency
            alpaca_url = config_mgr.get_config("broker.alpaca.base_url", "")
            if not alpaca_url:
                alpaca_url = os.environ.get("ALPACA_BASE_URL", "")
            
            paper_mode = config_mgr.get_config("trading_paper_mode", True)
            is_live_url = alpaca_url and "paper" not in alpaca_url.lower()
            
            if is_live_url and paper_mode:
                self.issues.append(ValidationIssue(
                    level=ValidationLevel.WARNING,
                    message="Configuration mismatch: paper_mode=True but using live Alpaca URL",
                    component="safety",
                    suggestion="Set TRADING_PAPER_MODE=false for live trading, or use paper API URL"
                ))
            
            # Check webhook security in live mode
            security_enabled = config_mgr.get_config("webhook_security_enabled", True)
            webhook_secret = config_mgr.get_secret("webhook-secret", "")
            
            if is_live_url and (not security_enabled or not webhook_secret):
                self.issues.append(ValidationIssue(
                    level=ValidationLevel.WARNING,
                    message="Webhook security disabled in live trading mode",
                    component="safety",
                    suggestion="Enable webhook security: set WEBHOOK_SECURITY_ENABLED=true and WEBHOOK_SECRET"
                ))
            
            # Check for Azure configuration in production
            is_azure = bool(
                os.environ.get("AZURE_KEYVAULT_URL") or 
                os.environ.get("AZURE_APP_CONFIGURATION_ENDPOINT")
            )
            
            if is_live_url and not is_azure:
                self.issues.append(ValidationIssue(
                    level=ValidationLevel.INFO,
                    message="Live trading without Azure configuration services",
                    component="safety",
                    suggestion="Consider using Azure Key Vault and App Configuration for production"
                ))
            
        except Exception as e:
            logger.debug(f"Error validating production safety: {e}")
    
    def _compile_results(self) -> ValidationResult:
        """Compile validation results."""
        errors_count = sum(1 for issue in self.issues if issue.level == ValidationLevel.ERROR)
        warnings_count = sum(1 for issue in self.issues if issue.level == ValidationLevel.WARNING)
        
        return ValidationResult(
            passed=errors_count == 0,
            issues=self.issues,
            errors_count=errors_count,
            warnings_count=warnings_count
        )
    
    def _print_validation_results(self, result: ValidationResult) -> None:
        """Print formatted validation results and log appropriately."""
        # Print errors
        errors = [i for i in result.issues if i.level == ValidationLevel.ERROR]
        if errors:
            logger.error("Critical configuration errors detected - startup blocked")
            print("\n🚫 CRITICAL Configuration Errors (Blocking Startup):")
            print("=" * 60)
            for issue in errors:
                logger.error(f"[{issue.component}] {issue.message}")
                print(f"   ❌ {issue.message}")
                if issue.suggestion:
                    print(f"      💡 {issue.suggestion}")
            print("=" * 60)
            print("\n❌ Startup blocked due to critical configuration errors.")
            print("💡 Fix these issues in Azure App Configuration or environment variables.")
            return
        
        # Print warnings
        warnings = [i for i in result.issues if i.level == ValidationLevel.WARNING]
        if warnings:
            logger.warning(f"Configuration validation passed with {len(warnings)} warning(s)")
            print("\n⚠️  Configuration Warnings (Non-Blocking):")
            print("=" * 60)
            for issue in warnings:
                logger.warning(f"[{issue.component}] {issue.message}")
                print(f"   ⚠️  {issue.message}")
                if issue.suggestion:
                    print(f"      💡 {issue.suggestion}")
            print("=" * 60)
            print("\n⚡ Proceeding with warnings - review these settings for production use.")
        
        # Print info messages
        infos = [i for i in result.issues if i.level == ValidationLevel.INFO]
        if infos:
            print("\nℹ️  Configuration Information:")
            for issue in infos:
                logger.info(f"[{issue.component}] {issue.message}")
                print(f"   ℹ️  {issue.message}")
        
        if result.passed and not warnings:
            logger.info("Configuration validation passed successfully")
            print("\n✅ Configuration validation passed!")
