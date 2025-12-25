"""
Configuration Validation Service - Fail-Fast Startup Validation.

This module provides comprehensive configuration validation at startup,
ensuring the application fails fast with actionable error messages when
configuration is missing or invalid.

USAGE:
    from src.config.config_validation_service import ConfigValidationService
    
    # At application startup
    validator = ConfigValidationService()
    result = await validator.validate_all()
    
    if not result.is_valid:
        print(result.format_errors())
        sys.exit(1)
    
    # Show warnings but continue
    if result.warnings:
        for warning in result.warnings:
            logger.warning(warning)

DESIGN PRINCIPLES:
    1. FAIL FAST: Block startup for critical errors, don't silently continue
    2. ACTIONABLE ERRORS: Every error includes how to fix it
    3. SINGLE SOURCE OF TRUTH: Uses ConfigContract for field definitions
    4. LAYERED VALIDATION: Validates each config source independently
"""

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from src.config.config_contract import (
    ConfigContract,
    ConfigField,
    ConfigCategory,
    ConfigSource,
)

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severity of validation issues."""
    ERROR = "error"      # Blocks startup
    WARNING = "warning"  # Non-blocking but logged
    INFO = "info"        # Informational only


@dataclass
class ValidationIssue:
    """A single validation issue."""
    severity: ValidationSeverity
    message: str
    field_name: Optional[str] = None
    source: Optional[ConfigSource] = None
    suggestion: Optional[str] = None
    
    def __str__(self) -> str:
        parts = [f"[{self.severity.value.upper()}]"]
        if self.field_name:
            parts.append(f"[{self.field_name}]")
        parts.append(self.message)
        if self.suggestion:
            parts.append(f"💡 {self.suggestion}")
        return " ".join(parts)


@dataclass
class ValidationResult:
    """Result of configuration validation."""
    is_valid: bool
    errors: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)
    info: List[ValidationIssue] = field(default_factory=list)
    resolved_config: Dict[str, Any] = field(default_factory=dict)
    config_sources: Dict[str, ConfigSource] = field(default_factory=dict)
    
    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0
    
    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0
    
    def format_errors(self) -> str:
        """Format all errors for display."""
        if not self.errors:
            return "✅ No configuration errors"
        
        lines = [
            "",
            "=" * 70,
            "❌ CONFIGURATION VALIDATION FAILED - STARTUP BLOCKED",
            "=" * 70,
            "",
            f"Found {len(self.errors)} configuration error(s):",
            "",
        ]
        
        for i, error in enumerate(self.errors, 1):
            lines.append(f"  {i}. {error.message}")
            if error.field_name:
                field = ConfigContract.get_field(error.field_name)
                if field:
                    lines.append(f"     Environment variable: {field.get_env_var()}")
                    if field.key_vault_name:
                        lines.append(f"     Key Vault secret: {field.key_vault_name}")
            if error.suggestion:
                lines.append(f"     💡 {error.suggestion}")
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
    
    def format_summary(self) -> str:
        """Format a summary of validation results."""
        lines = [
            "",
            "📋 Configuration Validation Summary:",
            f"   ✅ Valid: {self.is_valid}",
            f"   ❌ Errors: {len(self.errors)}",
            f"   ⚠️  Warnings: {len(self.warnings)}",
            f"   ℹ️  Info: {len(self.info)}",
            "",
        ]
        
        if self.config_sources:
            lines.append("   📍 Configuration sources:")
            source_counts: Dict[ConfigSource, int] = {}
            for source in self.config_sources.values():
                source_counts[source] = source_counts.get(source, 0) + 1
            for source, count in sorted(source_counts.items(), key=lambda x: x[0].value):
                lines.append(f"      {source.name}: {count} values")
        
        return "\n".join(lines)


class ConfigValidationService:
    """
    Comprehensive configuration validation service.
    
    Validates configuration from all sources against the canonical contract,
    ensuring fail-fast behavior with actionable error messages.
    
    Thread-Safety:
        Safe for concurrent validation calls.
    """
    
    def __init__(self):
        """Initialize the validation service."""
        self._contract = ConfigContract
    
    async def validate_all(self, check_broker: bool = True) -> ValidationResult:
        """
        Perform comprehensive configuration validation.
        
        This method:
        1. Loads values from all sources (env vars, files, Azure if available)
        2. Validates all required fields are present
        3. Validates all values meet their constraints
        4. Checks cross-field dependencies (e.g., at least one broker configured)
        
        Args:
            check_broker: If True, require at least one broker to be configured
            
        Returns:
            ValidationResult with all issues and resolved configuration
        """
        errors: List[ValidationIssue] = []
        warnings: List[ValidationIssue] = []
        info: List[ValidationIssue] = []
        resolved_config: Dict[str, Any] = {}
        config_sources: Dict[str, ConfigSource] = {}
        
        # Step 1: Collect values from all sources
        source_values = await self._collect_source_values()
        
        # Step 2: Resolve each field's value by precedence
        for field_name, field_def in self._contract.get_all_fields().items():
            value, source = self._contract.resolve_value(field_name, source_values)
            
            if value is not None:
                resolved_config[field_name] = value
                config_sources[field_name] = source
        
        # Step 3: Validate required fields
        required_errors = self._validate_required_fields(resolved_config)
        errors.extend(required_errors)
        
        # Step 4: Validate field constraints
        constraint_errors = self._validate_field_constraints(resolved_config)
        errors.extend(constraint_errors)
        
        # Step 5: Cross-field validation (broker config)
        if check_broker:
            broker_errors = self._validate_broker_configuration(resolved_config)
            errors.extend(broker_errors)
        
        # Step 6: Check for configuration drift warnings
        drift_warnings = self._check_configuration_drift(source_values)
        warnings.extend(drift_warnings)
        
        # Step 7: Check for production safety warnings
        safety_warnings = self._check_production_safety(resolved_config)
        warnings.extend(safety_warnings)
        
        # Step 8: Add informational messages
        info_messages = self._generate_info_messages(resolved_config, config_sources)
        info.extend(info_messages)
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            info=info,
            resolved_config=resolved_config,
            config_sources=config_sources,
        )
    
    def validate_sync(self, check_broker: bool = True) -> ValidationResult:
        """
        Synchronous validation (environment variables and defaults only).
        
        Use this for quick validation without Azure connectivity.
        """
        errors: List[ValidationIssue] = []
        warnings: List[ValidationIssue] = []
        info: List[ValidationIssue] = []
        resolved_config: Dict[str, Any] = {}
        config_sources: Dict[str, ConfigSource] = {}
        
        # Collect from environment only
        env_values = self._collect_environment_values()
        source_values = {ConfigSource.ENVIRONMENT: env_values}
        
        # Resolve values
        for field_name, field_def in self._contract.get_all_fields().items():
            value, source = self._contract.resolve_value(field_name, source_values)
            if value is not None:
                resolved_config[field_name] = value
                config_sources[field_name] = source
        
        # Validate
        errors.extend(self._validate_required_fields(resolved_config))
        errors.extend(self._validate_field_constraints(resolved_config))
        if check_broker:
            errors.extend(self._validate_broker_configuration(resolved_config))
        warnings.extend(self._check_production_safety(resolved_config))
        info.extend(self._generate_info_messages(resolved_config, config_sources))
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            info=info,
            resolved_config=resolved_config,
            config_sources=config_sources,
        )
    
    async def _collect_source_values(self) -> Dict[ConfigSource, Dict[str, Any]]:
        """Collect configuration values from all sources."""
        sources: Dict[ConfigSource, Dict[str, Any]] = {}
        
        # Environment variables (always available)
        sources[ConfigSource.ENVIRONMENT] = self._collect_environment_values()
        
        # Azure Key Vault (if configured)
        keyvault_url = os.environ.get("AZURE_KEYVAULT_URL")
        if keyvault_url:
            try:
                sources[ConfigSource.KEY_VAULT] = await self._collect_keyvault_values()
            except Exception as e:
                logger.warning(f"Could not connect to Key Vault: {e}")
        
        # Azure App Configuration (if configured)
        app_config_url = os.environ.get("AZURE_APP_CONFIGURATION_ENDPOINT")
        if app_config_url:
            try:
                sources[ConfigSource.APP_CONFIG] = await self._collect_app_config_values()
            except Exception as e:
                logger.warning(f"Could not connect to App Configuration: {e}")
        
        return sources
    
    def _collect_environment_values(self) -> Dict[str, Any]:
        """Collect values from environment variables."""
        values = {}
        
        for field_name, field_def in self._contract.get_all_fields().items():
            env_var = field_def.get_env_var()
            value = os.environ.get(env_var)
            if value is not None:
                # Store with env var name as key
                values[env_var] = value
        
        return values
    
    async def _collect_keyvault_values(self) -> Dict[str, Any]:
        """Collect secrets from Azure Key Vault."""
        values = {}
        
        try:
            from src.config.azure_secrets import AzureKeyVaultSecrets
            
            secrets_manager = AzureKeyVaultSecrets()
            await secrets_manager.initialize()
            
            for field_def in self._contract.get_secret_fields():
                if field_def.key_vault_name:
                    try:
                        value = await secrets_manager.get_secret(field_def.key_vault_name)
                        if value:
                            values[field_def.key_vault_name] = value
                    except Exception:
                        pass  # Secret not found, will use other sources
            
        except ImportError:
            logger.debug("Azure SDK not available for Key Vault")
        except Exception as e:
            logger.warning(f"Error collecting Key Vault values: {e}")
        
        return values
    
    async def _collect_app_config_values(self) -> Dict[str, Any]:
        """Collect values from Azure App Configuration."""
        values = {}
        
        try:
            from src.config.azure_config import AzureAppConfiguration
            
            config_manager = AzureAppConfiguration()
            await config_manager.initialize()
            
            for field_name, field_def in self._contract.get_all_fields().items():
                if field_def.app_config_key:
                    try:
                        value = await config_manager.get_config(field_def.app_config_key)
                        if value is not None:
                            values[field_def.app_config_key] = value
                    except Exception:
                        pass  # Config not found, will use other sources
            
        except ImportError:
            logger.debug("Azure SDK not available for App Configuration")
        except Exception as e:
            logger.warning(f"Error collecting App Configuration values: {e}")
        
        return values
    
    def _validate_required_fields(
        self, 
        config_values: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Validate that all required fields are present."""
        issues = []
        
        for field_def in self._contract.get_required_fields():
            value = config_values.get(field_def.canonical_name)
            
            if value is None:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    message=f"Required configuration '{field_def.canonical_name}' is missing",
                    field_name=field_def.canonical_name,
                    suggestion=field_def.error_hint or f"Set {field_def.get_env_var()} environment variable",
                ))
        
        return issues
    
    def _validate_field_constraints(
        self, 
        config_values: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Validate field constraints (type, validators)."""
        issues = []
        
        for field_name, value in config_values.items():
            field_def = self._contract.get_field(field_name)
            if not field_def:
                continue
            
            error = field_def.validate_value(value)
            if error:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    message=error,
                    field_name=field_name,
                    suggestion=field_def.error_hint,
                ))
        
        return issues
    
    def _validate_broker_configuration(
        self, 
        config_values: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Validate that at least one broker is configured."""
        issues = []
        
        alpaca_configured = (
            config_values.get("alpaca_api_key") and 
            config_values.get("alpaca_secret_key")
        )
        
        tastytrade_configured = (
            config_values.get("tastytrade_client_secret") and 
            config_values.get("tastytrade_refresh_token")
        )
        
        if not alpaca_configured and not tastytrade_configured:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                message="No broker credentials configured",
                suggestion=(
                    "Configure at least one broker:\n"
                    "   • Alpaca: Set ALPACA_API_KEY and ALPACA_SECRET_KEY\n"
                    "   • Tastytrade: Set TASTYTRADE_CLIENT_SECRET and TASTYTRADE_REFRESH_TOKEN\n"
                    "   Get Alpaca keys from https://app.alpaca.markets/"
                ),
            ))
        
        return issues
    
    def _check_configuration_drift(
        self, 
        source_values: Dict[ConfigSource, Dict[str, Any]]
    ) -> List[ValidationIssue]:
        """Check for configuration drift between sources."""
        warnings = []
        
        # Check if same field has different values in different sources
        field_values: Dict[str, Dict[ConfigSource, Any]] = {}
        
        for source, values in source_values.items():
            for key, value in values.items():
                # Find the field this key belongs to
                for field_name, field_def in self._contract.get_all_fields().items():
                    if (key == field_def.get_env_var() or 
                        key == field_def.key_vault_name or 
                        key == field_def.app_config_key):
                        if field_name not in field_values:
                            field_values[field_name] = {}
                        field_values[field_name][source] = value
                        break
        
        # Report drift
        for field_name, sources in field_values.items():
            if len(sources) > 1:
                unique_values = set(str(v) for v in sources.values())
                if len(unique_values) > 1:
                    source_list = ", ".join(
                        f"{s.name}={v}" for s, v in sources.items()
                    )
                    warnings.append(ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        message=f"Configuration drift detected for '{field_name}': {source_list}",
                        field_name=field_name,
                        suggestion="Ensure all sources have the same value, or remove duplicates",
                    ))
        
        return warnings
    
    def _check_production_safety(
        self, 
        config_values: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """Check for production safety concerns."""
        warnings = []
        
        # Check if live trading with no webhook security
        alpaca_url = config_values.get("alpaca_base_url", "")
        is_live = "paper" not in alpaca_url.lower() if alpaca_url else False
        
        security_enabled = config_values.get("webhook_security_enabled", True)
        webhook_secret = config_values.get("webhook_secret", "")
        
        if is_live:
            warnings.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                message="Live trading mode detected",
                suggestion="Ensure you intend to trade with real money. Use paper trading for testing.",
            ))
            
            if not security_enabled or not webhook_secret:
                warnings.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    message="Webhook security is disabled in live trading mode",
                    suggestion="Enable webhook security and set a strong secret for production",
                ))
        
        # Check paper mode flag consistency
        paper_mode = config_values.get("trading_paper_mode", True)
        if is_live and paper_mode:
            warnings.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                message="trading_paper_mode=True but using live Alpaca URL",
                field_name="trading_paper_mode",
                suggestion="Ensure paper_mode flag matches your broker URL",
            ))
        
        return warnings
    
    def _generate_info_messages(
        self, 
        config_values: Dict[str, Any],
        config_sources: Dict[str, ConfigSource]
    ) -> List[ValidationIssue]:
        """Generate informational messages."""
        info = []
        
        # Report trading mode
        alpaca_url = config_values.get("alpaca_base_url", "")
        if "paper" in alpaca_url.lower():
            info.append(ValidationIssue(
                severity=ValidationSeverity.INFO,
                message="Paper trading mode enabled (safe for testing)",
            ))
        
        # Report Azure vs local mode
        has_azure = any(
            s in (ConfigSource.KEY_VAULT, ConfigSource.APP_CONFIG)
            for s in config_sources.values()
        )
        if has_azure:
            info.append(ValidationIssue(
                severity=ValidationSeverity.INFO,
                message="Using Azure configuration services (Key Vault / App Configuration)",
            ))
        else:
            info.append(ValidationIssue(
                severity=ValidationSeverity.INFO,
                message="Using local configuration (environment variables / TOML files)",
            ))
        
        # Report configured brokers
        brokers = []
        if config_values.get("alpaca_api_key"):
            brokers.append("Alpaca")
        if config_values.get("tastytrade_client_secret"):
            brokers.append("Tastytrade")
        
        if brokers:
            info.append(ValidationIssue(
                severity=ValidationSeverity.INFO,
                message=f"Configured brokers: {', '.join(brokers)}",
            ))
        
        return info


# =============================================================================
# Convenience Functions
# =============================================================================

async def validate_configuration(check_broker: bool = True) -> ValidationResult:
    """
    Convenience function for configuration validation.
    
    Example:
        result = await validate_configuration()
        if not result.is_valid:
            print(result.format_errors())
            sys.exit(1)
    """
    service = ConfigValidationService()
    return await service.validate_all(check_broker=check_broker)


def validate_configuration_sync(check_broker: bool = True) -> ValidationResult:
    """
    Synchronous configuration validation (environment variables only).
    """
    service = ConfigValidationService()
    return service.validate_sync(check_broker=check_broker)
