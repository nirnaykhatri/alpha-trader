"""
Broker Credential Store - Secure storage abstraction for broker API credentials.

This module provides a clean interface for storing, retrieving, and deleting
broker API credentials. The primary implementation uses Azure Key Vault for
secure, persistent storage that survives container restarts.

Architecture:
    - IBrokerCredentialStore: Interface defining credential operations
    - BrokerCredentials: Data class for credential transfer
    - AzureKeyVaultCredentialStore: Production implementation using Key Vault
    - InMemoryCredentialStore: Testing/development fallback

Secret Naming Convention (multi-user safe):
    broker-{broker_type}-{user_key}-{connection_id}-api-key
    broker-{broker_type}-{user_key}-{connection_id}-api-secret
    
    Example: broker-alpaca-user123-conn-abc12345-api-key

Security:
    - Credentials are stored in Azure Key Vault with Secrets Officer role
    - Deletion is irrecoverable (soft-delete + purge)
    - No credentials are logged or cached long-term
    - Uses managed identity for authentication (no secrets in code)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING
import asyncio
import re
import hashlib

from src.core.logging_config import get_logger
from src.exceptions import TradingBotException

if TYPE_CHECKING:
    from src.config.azure_secrets import AzureKeyVaultSecrets

logger = get_logger(__name__)


class CredentialStoreError(TradingBotException):
    """
    Domain exception for credential store operations.
    
    Raised when credential storage operations fail due to:
    - Invalid input parameters (e.g., invalid user_key format)
    - Key Vault communication errors
    - Permission/access errors
    """
    pass


@dataclass(frozen=True)
class BrokerCredentials:
    """
    Immutable container for broker API credentials.
    
    Attributes:
        api_key: The API key for broker authentication.
        api_secret: The API secret/password for broker authentication.
        is_paper: Whether these credentials are for paper/sandbox trading.
    
    Thread-Safety:
        This class is immutable (frozen=True) and safe for concurrent access.
    """
    api_key: str
    api_secret: str
    is_paper: bool = False
    
    def __repr__(self) -> str:
        """Hide sensitive data in repr."""
        return f"BrokerCredentials(api_key='***', api_secret='***', is_paper={self.is_paper})"


class IBrokerCredentialStore(ABC):
    """
    Abstract interface for broker credential storage.
    
    Implementations of this interface handle the secure storage and retrieval
    of broker API credentials. The interface supports multiple users and
    multiple broker connections per user.
    
    Naming Convention:
        Secrets follow the pattern: broker-{broker_type}-{user_key}-{connection_id}-{field}
        Where field is 'api-key' or 'api-secret'.
        
        This naming enables:
        - Multi-user isolation (user_key is unique per user)
        - Multiple connections per broker type (connection_id)
        - Easy identification of credential purpose
    
    Thread-Safety:
        Implementations MUST be async-safe for concurrent access.
    """
    
    @abstractmethod
    async def save_credentials(
        self,
        broker_type: str,
        connection_id: str,
        credentials: BrokerCredentials,
        user_key: str = "default"
    ) -> None:
        """
        Save broker credentials to secure storage.
        
        If credentials already exist for this connection, they are overwritten.
        
        Args:
            broker_type: Type of broker (e.g., 'alpaca', 'tastytrade').
            connection_id: Unique identifier for this broker connection.
            credentials: The API credentials to store.
            user_key: User-specific key for multi-tenant isolation (default: 'default').
                      Can be any string (email, UUID, etc.) - will be canonicalized.
        
        Raises:
            CredentialStoreError: If storage operation fails.
        """
        pass
    
    @abstractmethod
    async def get_credentials(
        self,
        broker_type: str,
        connection_id: str,
        user_key: str = "default"
    ) -> Optional[BrokerCredentials]:
        """
        Retrieve broker credentials from secure storage.
        
        Note:
            The returned `is_paper` flag defaults to False. Callers should
            override this value from the broker metadata stored in Cosmos DB,
            as the paper/live mode is stored alongside other connection metadata
            rather than in the credential store.
        
        Args:
            broker_type: Type of broker (e.g., 'alpaca', 'tastytrade').
            connection_id: Unique identifier for this broker connection.
            user_key: User-specific key for multi-tenant isolation (default: 'default').
                      Can be any string (email, UUID, etc.) - will be canonicalized.
        
        Returns:
            BrokerCredentials if found, None otherwise. The `is_paper` field
            defaults to False and should be overridden by the caller.
        
        Raises:
            CredentialStoreError: If retrieval operation fails (not for missing secrets).
        """
        pass
    
    @abstractmethod
    async def delete_credentials(
        self,
        broker_type: str,
        connection_id: str,
        user_key: str = "default"
    ) -> bool:
        """
        Delete broker credentials from secure storage.
        
        Deletion is irrecoverable - credentials cannot be restored after this call.
        
        Args:
            broker_type: Type of broker (e.g., 'alpaca', 'tastytrade').
            connection_id: Unique identifier for this broker connection.
            user_key: User-specific key for multi-tenant isolation (default: 'default').
                      Can be any string (email, UUID, etc.) - will be canonicalized.
        
        Returns:
            True if credentials were deleted, False if they didn't exist.
        
        Raises:
            CredentialStoreError: If deletion operation fails.
        """
        pass
    
    @abstractmethod
    async def credentials_exist(
        self,
        broker_type: str,
        connection_id: str,
        user_key: str = "default"
    ) -> bool:
        """
        Check if credentials exist without retrieving them.
        
        More efficient than get_credentials() when you only need to verify existence.
        
        Args:
            broker_type: Type of broker (e.g., 'alpaca', 'tastytrade').
            connection_id: Unique identifier for this broker connection.
            user_key: User-specific key for multi-tenant isolation (default: 'default').
        
        Returns:
            True if credentials exist, False otherwise.
        """
        pass


class AzureKeyVaultCredentialStore(IBrokerCredentialStore):
    """
    Azure Key Vault implementation of broker credential storage.
    
    This implementation stores credentials securely in Azure Key Vault using
    the naming convention: broker-{broker_type}-{user_key}-{connection_id}-{field}
    
    Security Features:
        - Uses Azure Managed Identity (no credentials in code)
        - Secrets Officer role for write/delete operations
        - Irrecoverable deletion (soft-delete + purge)
        - No long-term caching of credentials
    
    Thread-Safety:
        This class is safe for concurrent async operations.
        The underlying AzureKeyVaultSecrets handles concurrency.
    
    Attributes:
        _kv_secrets: Azure Key Vault client instance.
    """
    
    # Secret name pattern validation (alphanumeric and hyphens only)
    _SECRET_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9\-]+$')
    
    def __init__(self, kv_secrets: 'AzureKeyVaultSecrets'):
        """
        Initialize the Key Vault credential store.
        
        Args:
            kv_secrets: Configured AzureKeyVaultSecrets instance.
                       Should be initialized before first use.
        """
        self._kv_secrets = kv_secrets
    
    @staticmethod
    def _canonicalize_user_key(user_key: str) -> str:
        """
        Canonicalize a user key to a Key Vault-safe format.
        
        For the common 'default' user key (single-user mode), preserves it
        as-is for readability in Key Vault. For multi-tenant user keys,
        uses SHA-256 hash prefix for consistent, URL-safe secret names.
        
        Args:
            user_key: Any user identifier string.
        
        Returns:
            'default' if user_key is 'default', otherwise a 16-character
            lowercase hex string derived from SHA-256 hash of the user_key.
            Deterministic: same input always produces same output.
        
        Examples:
            "default" -> "default" (preserved for readability)
            "user@example.com" -> "a1b2c3d4e5f67890" (hashed)
            "550e8400-e29b-41d4-a716-446655440000" -> "f1e2d3c4b5a69870" (hashed)
        """
        # Special case: preserve "default" as-is for backward compatibility
        if user_key == "default":
            return "default"
        
        # Hash the user key to get a deterministic, safe identifier
        # Using first 16 chars of sha256 hex - collision probability is negligible
        hash_bytes = hashlib.sha256(user_key.encode('utf-8')).hexdigest()[:16]
        return hash_bytes
    
    def _sanitize_component(self, component: str, component_name: str) -> str:
        """
        Sanitize a single component for Key Vault secret naming.
        
        Args:
            component: The component value to sanitize.
            component_name: Name of the component for error messages.
        
        Returns:
            Sanitized lowercase component.
        
        Raises:
            CredentialStoreError: If component contains invalid characters after sanitization.
        """
        # Replace underscores with hyphens
        sanitized = component.replace('_', '-').lower()
        
        # Validate pattern
        if not self._SECRET_NAME_PATTERN.match(sanitized):
            raise CredentialStoreError(
                f"Invalid {component_name}: '{component}'. "
                f"After sanitization ('{sanitized}'), only alphanumeric characters "
                "and hyphens are allowed. Please use a simpler identifier."
            )
        
        return sanitized
    
    def _build_secret_name(
        self,
        broker_type: str,
        user_key: str,
        connection_id: str,
        field: str
    ) -> str:
        """
        Build a Key Vault secret name from components.
        
        Format: broker-{broker_type}-{canonical_user_key}-{connection_id}-{field}
        
        The user_key is canonicalized (hashed) to support any user identifier
        format (email, UUID, Entra object ID, etc.) while producing a safe
        Key Vault secret name.
        
        Args:
            broker_type: Type of broker (e.g., 'alpaca').
            user_key: User-specific key (any format - will be canonicalized).
            connection_id: Connection identifier.
            field: 'api-key' or 'api-secret'.
        
        Returns:
            Sanitized secret name safe for Key Vault.
        
        Raises:
            CredentialStoreError: If broker_type or connection_id contain invalid characters.
        """
        # Canonicalize user_key to handle emails, UUIDs, etc.
        canonical_user_key = self._canonicalize_user_key(user_key)
        
        # Sanitize other components (user_key is already safe after canonicalization)
        sanitized_broker = self._sanitize_component(broker_type, "broker_type")
        sanitized_connection = self._sanitize_component(connection_id, "connection_id")
        sanitized_field = self._sanitize_component(field, "field")
        
        return f"broker-{sanitized_broker}-{canonical_user_key}-{sanitized_connection}-{sanitized_field}"
    
    async def save_credentials(
        self,
        broker_type: str,
        connection_id: str,
        credentials: BrokerCredentials,
        user_key: str = "default"
    ) -> None:
        """
        Save broker credentials to Azure Key Vault.
        
        Stores API key and secret as separate Key Vault secrets.
        is_paper flag is stored as content type metadata.
        
        Args:
            broker_type: Type of broker (e.g., 'alpaca', 'tastytrade').
            connection_id: Unique identifier for this broker connection.
            credentials: The API credentials to store.
            user_key: User-specific key for multi-tenant isolation.
        """
        api_key_name = self._build_secret_name(
            broker_type, user_key, connection_id, "api-key"
        )
        api_secret_name = self._build_secret_name(
            broker_type, user_key, connection_id, "api-secret"
        )
        
        # Store paper mode in content type for metadata
        content_type = "paper" if credentials.is_paper else "live"
        
        # Save both secrets in parallel for better performance
        await asyncio.gather(
            self._kv_secrets.set_secret(
                api_key_name,
                credentials.api_key,
                content_type=content_type
            ),
            self._kv_secrets.set_secret(
                api_secret_name,
                credentials.api_secret,
                content_type=content_type
            ),
        )
        
        logger.info(
            f"Saved credentials for broker connection: "
            f"type={broker_type}, connection={connection_id}, user={user_key}"
        )
    
    async def get_credentials(
        self,
        broker_type: str,
        connection_id: str,
        user_key: str = "default"
    ) -> Optional[BrokerCredentials]:
        """
        Retrieve broker credentials from Azure Key Vault.
        
        Both API key and secret must exist for credentials to be returned.
        
        Args:
            broker_type: Type of broker (e.g., 'alpaca', 'tastytrade').
            connection_id: Unique identifier for this broker connection.
            user_key: User-specific key for multi-tenant isolation.
        
        Returns:
            BrokerCredentials if both secrets found, None otherwise.
        """
        api_key_name = self._build_secret_name(
            broker_type, user_key, connection_id, "api-key"
        )
        api_secret_name = self._build_secret_name(
            broker_type, user_key, connection_id, "api-secret"
        )
        
        # Retrieve both secrets
        api_key = await self._kv_secrets.get_secret(api_key_name, use_cache=False)
        api_secret = await self._kv_secrets.get_secret(api_secret_name, use_cache=False)
        
        # Both must exist
        if not api_key or not api_secret:
            logger.debug(
                f"Credentials not found for broker connection: "
                f"type={broker_type}, connection={connection_id}"
            )
            return None
        
        # Determine paper mode from content type (fallback to False)
        # Note: Content type isn't directly accessible via get_secret,
        # we'd need to check the secret metadata. For simplicity, we
        # store paper mode in Cosmos DB document, not Key Vault metadata.
        # The is_paper value here defaults to False and should be
        # overridden by the caller from Cosmos DB document.
        
        return BrokerCredentials(
            api_key=api_key,
            api_secret=api_secret,
            is_paper=False  # Caller should override from Cosmos DB
        )
    
    async def delete_credentials(
        self,
        broker_type: str,
        connection_id: str,
        user_key: str = "default"
    ) -> bool:
        """
        Delete broker credentials from Azure Key Vault (irrecoverable).
        
        Both API key and secret are deleted and purged.
        
        Args:
            broker_type: Type of broker (e.g., 'alpaca', 'tastytrade').
            connection_id: Unique identifier for this broker connection.
            user_key: User-specific key for multi-tenant isolation.
        
        Returns:
            True if any credentials were deleted, False if none existed.
        """
        api_key_name = self._build_secret_name(
            broker_type, user_key, connection_id, "api-key"
        )
        api_secret_name = self._build_secret_name(
            broker_type, user_key, connection_id, "api-secret"
        )
        
        # Delete both secrets (purge=True for irrecoverable deletion)
        key_deleted = await self._kv_secrets.delete_secret(api_key_name, purge=True)
        secret_deleted = await self._kv_secrets.delete_secret(api_secret_name, purge=True)
        
        any_deleted = key_deleted or secret_deleted
        
        if any_deleted:
            logger.info(
                f"Deleted credentials for broker connection: "
                f"type={broker_type}, connection={connection_id}, user={user_key}"
            )
        else:
            logger.debug(
                f"No credentials to delete for broker connection: "
                f"type={broker_type}, connection={connection_id}"
            )
        
        return any_deleted
    
    async def credentials_exist(
        self,
        broker_type: str,
        connection_id: str,
        user_key: str = "default"
    ) -> bool:
        """
        Check if complete credentials exist in Key Vault.
        
        Checks for both API key AND API secret to ensure complete credentials.
        Returns True only if both secrets are present.
        
        Args:
            broker_type: Type of broker (e.g., 'alpaca', 'tastytrade').
            connection_id: Unique identifier for this broker connection.
            user_key: User-specific key for multi-tenant isolation.
        
        Returns:
            True if both API key and secret exist, False otherwise.
        """
        api_key_name = self._build_secret_name(
            broker_type, user_key, connection_id, "api-key"
        )
        api_secret_name = self._build_secret_name(
            broker_type, user_key, connection_id, "api-secret"
        )
        
        # Check both secrets exist for complete credentials
        api_key = await self._kv_secrets.get_secret(api_key_name, use_cache=False)
        api_secret = await self._kv_secrets.get_secret(api_secret_name, use_cache=False)
        return api_key is not None and api_secret is not None


class InMemoryCredentialStore(IBrokerCredentialStore):
    """
    In-memory credential store for testing and development.
    
    Warning: Credentials are lost on process restart.
    DO NOT use in production.
    
    Thread-Safety:
        Uses asyncio.Lock for safe concurrent access in async contexts.
    """
    
    def __init__(self):
        """Initialize empty credential store with async lock."""
        self._credentials: dict[str, BrokerCredentials] = {}
        self._lock = asyncio.Lock()
    
    def _build_key(self, broker_type: str, user_key: str, connection_id: str) -> str:
        """Build storage key from components."""
        return f"{broker_type}:{user_key}:{connection_id}"
    
    async def save_credentials(
        self,
        broker_type: str,
        connection_id: str,
        credentials: BrokerCredentials,
        user_key: str = "default"
    ) -> None:
        """Save credentials to in-memory store."""
        key = self._build_key(broker_type, user_key, connection_id)
        async with self._lock:
            self._credentials[key] = credentials
        logger.debug(f"[InMemory] Saved credentials: {key}")
    
    async def get_credentials(
        self,
        broker_type: str,
        connection_id: str,
        user_key: str = "default"
    ) -> Optional[BrokerCredentials]:
        """Retrieve credentials from in-memory store."""
        key = self._build_key(broker_type, user_key, connection_id)
        async with self._lock:
            return self._credentials.get(key)
    
    async def delete_credentials(
        self,
        broker_type: str,
        connection_id: str,
        user_key: str = "default"
    ) -> bool:
        """Delete credentials from in-memory store."""
        key = self._build_key(broker_type, user_key, connection_id)
        async with self._lock:
            if key in self._credentials:
                del self._credentials[key]
                logger.debug(f"[InMemory] Deleted credentials: {key}")
                return True
            return False
    
    async def credentials_exist(
        self,
        broker_type: str,
        connection_id: str,
        user_key: str = "default"
    ) -> bool:
        """Check if credentials exist in in-memory store."""
        key = self._build_key(broker_type, user_key, connection_id)
        return key in self._credentials
