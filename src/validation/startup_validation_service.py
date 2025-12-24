"""
Startup Validation Service

Consolidates all startup validation logic to prevent duplication
between run_bot.py and trading_bot.py.
"""

import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

from src.core import ConfigurationManager
from src.config.config_schema import ConfigValidator, ValidationSeverity
from src.exceptions import ConfigurationException

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
    
    Performs all necessary validation checks before bot startup,
    consolidating logic from run_bot.py and trading_bot.py.
    
    Example:
        validator = StartupValidationService()  # Uses TOML config from config/
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
                        from config/ directory using TOML files.
        """
        if config_file is not None:
            import warnings
            warnings.warn(
                "config_file parameter is deprecated. Configuration is now loaded from "
                "config/ directory using TOML files.",
                DeprecationWarning,
                stacklevel=2
            )
        self.issues: List[ValidationIssue] = []
    
    def validate(self, verbose: bool = True) -> ValidationResult:
        """
        Perform comprehensive startup validation.
        
        Args:
            verbose: Whether to print detailed output
            
        Returns:
            ValidationResult with all issues
        """
        self.issues = []
        
        # Schema validation
        self._validate_schema()
        
        # Configuration validation
        self._validate_configuration()
        
        # API credentials validation
        self._validate_api_credentials()
        
        # Webhook security validation
        self._validate_webhook_security()
        
        # Compile results
        result = self._compile_results()
        
        # Print results if verbose
        if verbose:
            self._print_validation_results(result)
        
        return result
    
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
        """Validate API credentials."""
        try:
            config_mgr = ConfigurationManager()  # Singleton, loads from config/
            
            # Alpaca API key
            api_key = config_mgr.get_config("api.alpaca.api_key", "")
            if not api_key:
                self.issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    message="Alpaca API key is missing",
                    component="credentials",
                    suggestion="Get API keys from https://app.alpaca.markets/"
                ))
            elif len(api_key) < 10:
                self.issues.append(ValidationIssue(
                    level=ValidationLevel.WARNING,
                    message="Alpaca API key looks too short",
                    component="credentials"
                ))
            
            # Alpaca secret key
            secret_key = config_mgr.get_config("api.alpaca.secret_key", "")
            if not secret_key:
                self.issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    message="Alpaca secret key is missing",
                    component="credentials",
                    suggestion="Get API keys from https://app.alpaca.markets/"
                ))
            elif len(secret_key) < 20:
                self.issues.append(ValidationIssue(
                    level=ValidationLevel.WARNING,
                    message="Alpaca secret key looks too short",
                    component="credentials"
                ))
            
            # Check if paper trading
            base_url = config_mgr.get_config("api.alpaca.base_url", "")
            if "paper" in base_url:
                self.issues.append(ValidationIssue(
                    level=ValidationLevel.INFO,
                    message="Using paper trading environment",
                    component="credentials"
                ))
            else:
                self.issues.append(ValidationIssue(
                    level=ValidationLevel.WARNING,
                    message="Live trading mode detected - ensure you intend to use real funds",
                    component="credentials",
                    suggestion="Use paper trading for testing"
                ))
                
        except Exception as e:
            logger.debug(f"Error validating credentials: {e}")
    
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
