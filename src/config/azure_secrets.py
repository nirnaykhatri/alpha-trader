"""
Azure Key Vault Secret Management.

Provides secure access to secrets stored in Azure Key Vault using
DefaultAzureCredential (Managed Identity in Azure, CLI locally).

Usage:
    secrets = AzureKeyVaultSecrets(config)
    await secrets.initialize()
    
    api_key = await secrets.get_secret("alpaca-api-key")
    all_secrets = await secrets.get_all_secrets(["alpaca-api-key", "alpaca-secret-key"])

Security:
    - Uses Azure Managed Identity (no credentials in code)
    - Secrets are cached in-memory with configurable TTL
    - Cache is cleared on hot-reload trigger
"""

import asyncio
from typing import Dict, Optional, List, Any, TYPE_CHECKING
from datetime import datetime, timedelta
from dataclasses import dataclass

# Lazy imports: Azure SDK modules are imported when first needed
# This allows tests and tools to import this module without requiring Azure SDK
if TYPE_CHECKING:
    from azure.identity.aio import DefaultAzureCredential
    from azure.keyvault.secrets.aio import SecretClient
    from azure.core.exceptions import ResourceNotFoundError, HttpResponseError

from src.interfaces import IConfigurationManager
from src.exceptions import TradingBotException
from src.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CachedSecret:
    """Represents a cached secret with expiration."""
    value: str
    cached_at: datetime
    expires_at: datetime


class AzureKeyVaultSecrets:
    """
    Async Azure Key Vault client for secure secret retrieval.
    
    Uses DefaultAzureCredential which automatically selects the best
    authentication method based on environment:
    - In Azure: Managed Identity
    - Local dev: Azure CLI, VS Code, or environment variables
    
    Thread-Safety:
        This class is safe for concurrent async operations.
        Secret cache uses async-safe access patterns.
    
    Caching:
        Secrets are cached in-memory with configurable TTL to reduce
        Key Vault API calls and improve performance. Cache can be
        explicitly cleared for hot-reload scenarios.
    
    Attributes:
        _vault_url: Key Vault URL (https://<vault-name>.vault.azure.net/)
        _cache_ttl_minutes: Cache TTL in minutes (default: 5)
        _client: Azure SecretClient instance
        _cache: In-memory secret cache
    """
    
    # Secret name mappings (config key -> Key Vault secret name)
    SECRET_MAPPINGS = {
        # Alpaca broker secrets
        'brokers.alpaca.api_key': 'alpaca-api-key',
        'brokers.alpaca.secret_key': 'alpaca-secret-key',
        
        # Tastytrade broker secrets
        'brokers.tastytrade.client_secret': 'tastytrade-client-secret',
        'brokers.tastytrade.refresh_token': 'tastytrade-refresh-token',
        
        # Webhook security
        'api.webhook.secret': 'webhook-secret',
        
        # Database (if using external DB)
        'database.connection_string': 'database-connection-string',
    }
    
    def __init__(self, config: IConfigurationManager, cache_ttl_minutes: int = 5):
        """
        Initialize Key Vault client.
        
        Args:
            config: Configuration manager providing:
                - azure.key_vault.name: Key Vault name
                - azure.key_vault.url: Full vault URL (optional, derived from name)
            cache_ttl_minutes: How long to cache secrets (default: 5 minutes)
        """
        self._config = config
        self._cache_ttl_minutes = cache_ttl_minutes
        self._client: Optional[SecretClient] = None
        self._credential: Optional[DefaultAzureCredential] = None
        self._cache: Dict[str, CachedSecret] = {}
        self._initialized = False
        
        # Get vault URL from config
        vault_name = config.get_config("azure.key_vault.name", None)
        vault_url = config.get_config("azure.key_vault.url", None)
        
        if vault_url:
            self._vault_url = vault_url
        elif vault_name:
            self._vault_url = f"https://{vault_name}.vault.azure.net/"
        else:
            # Not configured - will fail on first secret access
            self._vault_url = None
            logger.warning(
                "Key Vault not configured. Set 'azure.key_vault.name' or "
                "'azure.key_vault.url' in configuration."
            )
        
        logger.info(f"AzureKeyVaultSecrets initialized for: {self._vault_url or 'NOT CONFIGURED'}")
    
    @property
    def is_configured(self) -> bool:
        """Check if Key Vault is configured."""
        return self._vault_url is not None
    
    async def initialize(self) -> None:
        """
        Initialize Azure Key Vault client.
        
        Creates the DefaultAzureCredential and SecretClient.
        Must be called before accessing secrets.
        
        Azure SDK is imported lazily here, allowing this module to be
        imported without the SDK installed (e.g., for testing).
        
        Raises:
            ImportError: If Azure SDK is not installed
            TradingBotException: If vault URL is not configured
        """
        if not self._vault_url:
            raise TradingBotException(
                "Key Vault URL not configured. "
                "Set 'azure.key_vault.name' or 'azure.key_vault.url' in configuration."
            )
        
        try:
            # Lazy import Azure SDK - only when actually initializing
            from azure.identity.aio import DefaultAzureCredential
            from azure.keyvault.secrets.aio import SecretClient
            
            logger.info("Initializing Azure Key Vault client...")
            
            self._credential = DefaultAzureCredential()
            self._client = SecretClient(
                vault_url=self._vault_url,
                credential=self._credential,
            )
            
            self._initialized = True
            logger.info(f"Key Vault client initialized: {self._vault_url}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Key Vault: {str(e)}")
            raise TradingBotException(f"Key Vault initialization failed: {str(e)}")
    
    async def close(self) -> None:
        """Close Key Vault client and credential."""
        try:
            if self._client:
                await self._client.close()
            if self._credential:
                await self._credential.close()
            
            self._cache.clear()
            logger.info("Key Vault client closed")
            
        except Exception as e:
            logger.error(f"Error closing Key Vault: {str(e)}")
    
    def _is_cache_valid(self, cached: CachedSecret) -> bool:
        """Check if a cached secret is still valid."""
        return datetime.utcnow() < cached.expires_at
    
    def clear_cache(self) -> None:
        """Clear the secret cache (for hot-reload scenarios)."""
        self._cache.clear()
        logger.info("Secret cache cleared")
    
    async def get_secret(
        self,
        secret_name: str,
        use_cache: bool = True
    ) -> Optional[str]:
        """
        Get a secret from Key Vault.
        
        Args:
            secret_name: Name of the secret in Key Vault
            use_cache: Whether to use cached value if available
            
        Returns:
            Secret value or None if not found
            
        Raises:
            TradingBotException: If not initialized or retrieval fails
        """
        if not self._initialized:
            await self.initialize()
        
        # Check cache first
        if use_cache and secret_name in self._cache:
            cached = self._cache[secret_name]
            if self._is_cache_valid(cached):
                logger.debug(f"Secret '{secret_name}' retrieved from cache")
                return cached.value
        
        try:
            secret = await self._client.get_secret(secret_name)
            value = secret.value
            
            # Cache the secret
            now = datetime.utcnow()
            self._cache[secret_name] = CachedSecret(
                value=value,
                cached_at=now,
                expires_at=now + timedelta(minutes=self._cache_ttl_minutes),
            )
            
            logger.debug(f"Secret '{secret_name}' retrieved from Key Vault")
            return value
            
        except Exception as e:
            # Lazy import for exception types
            from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
            
            if isinstance(e, ResourceNotFoundError):
                logger.warning(f"Secret '{secret_name}' not found in Key Vault")
                return None
            elif isinstance(e, HttpResponseError):
                logger.error(f"Key Vault error for '{secret_name}': {e.message}")
                raise TradingBotException(f"Key Vault error: {e.message}")
            else:
                raise
    
    async def get_all_secrets(
        self,
        secret_names: List[str],
        use_cache: bool = True
    ) -> Dict[str, Optional[str]]:
        """
        Get multiple secrets from Key Vault in parallel.
        
        Args:
            secret_names: List of secret names to retrieve
            use_cache: Whether to use cached values if available
            
        Returns:
            Dictionary mapping secret names to values (None if not found)
        """
        if not self._initialized:
            await self.initialize()
        
        # Fetch all secrets concurrently
        tasks = [
            self.get_secret(name, use_cache)
            for name in secret_names
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        secrets = {}
        for name, result in zip(secret_names, results):
            if isinstance(result, Exception):
                logger.error(f"Error fetching secret '{name}': {result}")
                secrets[name] = None
            else:
                secrets[name] = result
        
        return secrets
    
    async def get_config_secret(
        self,
        config_key: str,
        use_cache: bool = True
    ) -> Optional[str]:
        """
        Get a secret using its config key (automatically maps to Key Vault name).
        
        Args:
            config_key: Configuration key (e.g., 'brokers.alpaca.api_key')
            use_cache: Whether to use cached value if available
            
        Returns:
            Secret value or None if not found/mapped
        """
        secret_name = self.SECRET_MAPPINGS.get(config_key)
        
        if not secret_name:
            logger.debug(f"No Key Vault mapping for config key: {config_key}")
            return None
        
        return await self.get_secret(secret_name, use_cache)
    
    async def set_secret(
        self,
        secret_name: str,
        value: str,
        content_type: str = None
    ) -> None:
        """
        Set a secret in Key Vault.
        
        Note: This requires Key Vault Secrets Officer role.
        
        Args:
            secret_name: Name of the secret
            value: Secret value
            content_type: Optional content type (e.g., 'application/json')
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            await self._client.set_secret(
                name=secret_name,
                value=value,
                content_type=content_type,
            )
            
            # Update cache
            now = datetime.utcnow()
            self._cache[secret_name] = CachedSecret(
                value=value,
                cached_at=now,
                expires_at=now + timedelta(minutes=self._cache_ttl_minutes),
            )
            
            logger.info(f"Secret '{secret_name}' set in Key Vault")
            
        except Exception as e:
            # Lazy import for exception handling
            from azure.core.exceptions import HttpResponseError
            
            if isinstance(e, HttpResponseError):
                logger.error(f"Failed to set secret '{secret_name}': {e.message}")
                raise TradingBotException(f"Failed to set secret: {e.message}")
            raise
    
    async def delete_secret(
        self,
        secret_name: str,
        purge: bool = False
    ) -> bool:
        """
        Delete a secret from Key Vault.
        
        When purge=True, the secret is irrecoverably deleted (requires purge 
        protection to be disabled on the Key Vault). Default is False to be
        safe on purge-protected vaults; explicitly pass True when permanent
        deletion is required (e.g., UI-added broker credentials).
        
        Note: This requires Key Vault Secrets Officer role.
        
        Args:
            secret_name: Name of the secret to delete.
            purge: If True, permanently purge after soft-delete (default: False).
                   Set to True for irrecoverable deletion on non-protected vaults.
        
        Returns:
            bool: True if deletion was successful, False if secret not found.
        
        Raises:
            TradingBotException: If deletion fails due to permissions or other errors.
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            # Step 1: Begin soft-delete (required before purge)
            poller = await self._client.begin_delete_secret(secret_name)
            # Use result() for proper typing and awaiting the LRO completion
            deleted_secret = await poller.result()
            
            logger.info(f"Secret '{secret_name}' soft-deleted from Key Vault")
            
            # Remove from cache immediately
            self._cache.pop(secret_name, None)
            
            # Step 2: Purge if requested (makes deletion irrecoverable)
            if purge:
                await self.purge_deleted_secret(secret_name)
            
            return True
            
        except Exception as e:
            from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
            
            if isinstance(e, ResourceNotFoundError):
                logger.warning(f"Secret '{secret_name}' not found for deletion")
                # Remove from cache even if not found in Key Vault
                self._cache.pop(secret_name, None)
                return False
            elif isinstance(e, HttpResponseError):
                logger.error(f"Failed to delete secret '{secret_name}': {e.message}")
                raise TradingBotException(f"Failed to delete secret: {e.message}")
            raise
    
    async def purge_deleted_secret(self, secret_name: str) -> bool:
        """
        Permanently purge a soft-deleted secret (irrecoverable).
        
        This can only be called after delete_secret() and requires:
        1. Key Vault purge protection to be DISABLED
        2. Key Vault Secrets Officer role
        
        Warning: This operation is irreversible. The secret cannot be recovered.
        
        Args:
            secret_name: Name of the deleted secret to purge.
        
        Returns:
            bool: True if purge succeeded, False if secret not in deleted state.
        
        Raises:
            TradingBotException: If purge fails (e.g., purge protection enabled).
        """
        if not self._initialized:
            await self.initialize()
        
        try:
            await self._client.purge_deleted_secret(secret_name)
            logger.info(f"Secret '{secret_name}' permanently purged from Key Vault")
            return True
            
        except Exception as e:
            from azure.core.exceptions import ResourceNotFoundError, HttpResponseError
            
            if isinstance(e, ResourceNotFoundError):
                logger.warning(f"Deleted secret '{secret_name}' not found for purge")
                return False
            elif isinstance(e, HttpResponseError):
                # Common cause: purge protection is enabled
                if "purge protection" in str(e.message).lower():
                    logger.error(
                        f"Cannot purge secret '{secret_name}': "
                        "Key Vault has purge protection enabled. "
                        "Secret will be auto-deleted after retention period."
                    )
                else:
                    logger.error(f"Failed to purge secret '{secret_name}': {e.message}")
                raise TradingBotException(f"Failed to purge secret: {e.message}")
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check Key Vault connectivity.
        
        Returns:
            Health check result with status and latency.
            Never throws - returns error state in response dict.
        """
        if not self._vault_url:
            return {
                'healthy': False,
                'error': 'Key Vault not configured',
            }
        
        # Ensure client is initialized before health check
        if not self._initialized or not self._client:
            try:
                await self.initialize()
            except Exception as e:
                return {
                    'healthy': False,
                    'vault_url': self._vault_url,
                    'error': f'Initialization failed: {str(e)}',
                }
        
        start = datetime.utcnow()
        try:
            # Try to list secrets (just first one to test connectivity)
            async for _ in self._client.list_properties_of_secrets():
                break
            
            latency_ms = (datetime.utcnow() - start).total_seconds() * 1000
            
            return {
                'healthy': True,
                'vault_url': self._vault_url,
                'latency_ms': round(latency_ms, 2),
                'cache_size': len(self._cache),
            }
            
        except Exception as e:
            return {
                'healthy': False,
                'vault_url': self._vault_url,
                'error': str(e),
            }
