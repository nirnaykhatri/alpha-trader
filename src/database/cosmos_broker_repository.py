"""
Cosmos DB Broker Repository - Broker Connection Persistence Layer.

This module provides persistence for broker connections using Azure Cosmos DB.
It stores broker connection metadata, allowing the application to maintain
user-configured brokers across restarts.

Architecture:
- Container: 'broker_connections' - Active and disabled broker connections
- Partition Strategy: /broker_type (efficient queries by broker)

Storage Design:
    - We store connection METADATA only (id, name, status, masked API key)
    - We store a flag indicating if a broker is disabled (user deleted it)
    - Actual API credentials should be stored in Azure Key Vault (production)
    - For env-configured brokers, we only track if user disabled them

Security Note:
    API credentials are NOT stored in Cosmos DB. This repository only tracks:
    1. User-added broker metadata (with masked API key for display)
    2. Disabled state for env-configured brokers
    
    In production, actual credentials should be stored in Azure Key Vault.

Cross-Partition Query Policy:
    This repository explicitly sets enable_cross_partition_query=True for list
    operations because broker connections span multiple partition keys (broker_type).
    
    SDK 4.x Note: While the Azure Cosmos DB Python SDK 4.x defaults to allowing
    cross-partition queries, we explicitly set this flag for:
    1. Self-documenting code - makes the cross-partition intent clear
    2. Backwards compatibility with older SDK versions
    3. Explicit acknowledgment of the query cost tradeoffs
    
    This is ACCEPTABLE here because:
    1. Broker connections are a small dataset (typically <10 items)
    2. List operations are infrequent (UI load, startup sync)
    3. Single-broker queries use partition key for efficiency
    
    For repositories with large datasets, prefer partition-scoped queries.

Lazy Loading:
    Azure SDK imports are deferred until initialize() is called.
    This allows tests to import this module without Azure SDK installed.

Author: Trading Bot Team
Version: 1.1.0
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from dataclasses import dataclass, field, asdict

# Lazy imports for Azure SDK
if TYPE_CHECKING:
    from azure.cosmos import exceptions as cosmos_exceptions

from src.core.logging_config import get_logger
from src.database.cosmos_base import (
    CosmosConnectionPool,
    COSMOS_SYSTEM_PROPERTIES
)

logger = get_logger(__name__)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class BrokerConnectionDocument:
    """
    Broker connection document for Cosmos DB storage.
    
    This stores metadata about broker connections, NOT credentials.
    Actual API keys should be stored in Azure Key Vault.
    
    Attributes:
        id: Unique connection identifier (e.g., 'alpaca-abc123' or 'alpaca-env')
        broker_type: Broker identifier (e.g., 'alpaca', 'tastytrade')
        name: Display name for the connection
        status: Connection status ('connected', 'disconnected', 'error', 'disabled')
        source: Where connection was configured ('env' or 'user')
        is_disabled: True if user explicitly disabled this connection
        is_paper: True if using paper/sandbox trading
        api_key_masked: Masked API key for display (e.g., '****-****-****-ABCD')
        api_key_hash: SHA256 hash of API key for secure duplicate detection
        supported_assets: List of asset types supported
        balance: Cash balance in the account
        buying_power: Available buying power
        portfolio_value: Total portfolio value
        open_positions: Number of open positions
        error_message: Error message if status is 'error'
        logo_url: URL to broker logo image
        last_sync: Last sync timestamp (ISO format)
        created_at: Creation timestamp (ISO format)
        updated_at: Last update timestamp (ISO format)
        metadata: Additional metadata dictionary
    """
    id: str = ""
    broker_type: str = ""  # Partition key
    name: str = ""
    status: str = "connected"
    source: str = "user"  # 'env' or 'user'
    is_disabled: bool = False
    is_paper: bool = True
    api_key_masked: str = "****"
    api_key_hash: Optional[str] = None  # SHA256 hash for duplicate detection
    supported_assets: List[str] = field(default_factory=list)
    balance: float = 0.0
    buying_power: float = 0.0
    portfolio_value: float = 0.0
    open_positions: int = 0
    error_message: Optional[str] = None
    logo_url: Optional[str] = None
    last_sync: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Set timestamps if not provided."""
        now = datetime.now(timezone.utc).isoformat()
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
    
    def to_cosmos_doc(self) -> Dict[str, Any]:
        """Convert to Cosmos DB document format."""
        doc = asdict(self)
        doc['_type'] = 'broker_connection'
        return doc
    
    @classmethod
    def from_cosmos_doc(cls, doc: Dict[str, Any]) -> Optional["BrokerConnectionDocument"]:
        """Create instance from Cosmos DB document."""
        if not doc:
            return None
        
        # Remove Cosmos system properties
        for key in COSMOS_SYSTEM_PROPERTIES:
            doc.pop(key, None)
        doc.pop('_type', None)
        
        # Filter to only valid fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()} if hasattr(cls, '__dataclass_fields__') else set()
        if not valid_fields:
            # Fallback: use dataclass fields
            import dataclasses
            valid_fields = {f.name for f in dataclasses.fields(cls)}
        
        filtered_doc = {k: v for k, v in doc.items() if k in valid_fields}
        return cls(**filtered_doc)


# =============================================================================
# Repository Interface
# =============================================================================

class IBrokerRepository:
    """Interface for broker connection persistence."""
    
    async def initialize(self) -> None:
        """Initialize the repository."""
        raise NotImplementedError
    
    async def get_all_connections(self) -> List[BrokerConnectionDocument]:
        """Get all broker connections."""
        raise NotImplementedError
    
    async def get_connection(self, connection_id: str) -> Optional[BrokerConnectionDocument]:
        """Get a specific broker connection by ID."""
        raise NotImplementedError
    
    async def save_connection(self, connection: BrokerConnectionDocument) -> BrokerConnectionDocument:
        """Save or update a broker connection."""
        raise NotImplementedError
    
    async def delete_connection(self, connection_id: str) -> bool:
        """Delete a broker connection."""
        raise NotImplementedError
    
    async def disable_connection(self, connection_id: str) -> bool:
        """Mark a connection as disabled (soft delete for env brokers)."""
        raise NotImplementedError
    
    async def is_connection_disabled(self, connection_id: str) -> bool:
        """Check if a connection is disabled."""
        raise NotImplementedError


# =============================================================================
# Cosmos DB Implementation
# =============================================================================

class CosmosBrokerRepository(IBrokerRepository):
    """
    Cosmos DB implementation of broker connection repository.
    
    Uses the shared CosmosConnectionPool for efficient connection management.
    Container: 'broker_connections' with partition key '/broker_type'.
    
    Architecture Note:
        This class uses composition (depends on CosmosConnectionPool) rather than
        inheritance from CosmosBaseRepository. This is because:
        1. The pool may already be initialized by other components
        2. We don't need the parent's initialization logic
        3. This provides clearer lifecycle expectations
    
    Thread-Safety:
        This class is safe for concurrent async operations.
        The shared connection pool handles synchronization internally.
    """
    
    CONTAINER_NAME = "broker_connections"
    PARTITION_KEY_PATH = "/broker_type"
    
    def __init__(
        self,
        cosmos_endpoint: str = "",
        database_name: str = "trading-bot",
    ):
        """
        Initialize the broker repository.
        
        Uses composition pattern - depends on shared CosmosConnectionPool
        rather than inheriting from CosmosBaseRepository.
        
        Args:
            cosmos_endpoint: Cosmos DB endpoint (optional if pool already initialized)
            database_name: Database name (default: trading-bot)
        """
        self._endpoint = cosmos_endpoint
        self._database_name = database_name
        self._pool = CosmosConnectionPool.get_instance()
        self._container = None
        self._initialized = False
        self._cosmos_exceptions = None
    
    async def initialize(self) -> None:
        """
        Initialize the repository and ensure container exists.
        
        Creates the container if it doesn't exist. Uses shared connection pool.
        
        Raises:
            ImportError: If Azure SDK is not installed
            Exception: If container creation fails
        """
        if self._initialized:
            return
        
        # Lazy import Azure SDK
        from azure.cosmos import PartitionKey, exceptions
        self._cosmos_exceptions = exceptions
        
        try:
            pool = CosmosConnectionPool.get_instance()
            database = pool.database
            
            if database is None:
                raise RuntimeError(
                    "CosmosConnectionPool not initialized. "
                    "Call pool.initialize() first."
                )
            
            # Create container if it doesn't exist
            try:
                self._container = database.get_container_client(self.CONTAINER_NAME)
                # Verify container exists by reading properties
                await self._container.read()
                logger.info(f"Connected to existing container: {self.CONTAINER_NAME}")
            except exceptions.CosmosResourceNotFoundError:
                logger.info(f"Creating container: {self.CONTAINER_NAME}")
                self._container = await database.create_container(
                    id=self.CONTAINER_NAME,
                    partition_key=PartitionKey(path=self.PARTITION_KEY_PATH),
                    default_ttl=-1,  # No TTL - connections persist indefinitely
                )
                logger.info(f"Created container: {self.CONTAINER_NAME}")
            
            self._initialized = True
            logger.info("CosmosBrokerRepository initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize CosmosBrokerRepository: {e}")
            raise
    
    async def close(self) -> None:
        """
        Close the repository.
        
        Cleans up local resources. The connection pool is managed separately
        and will be closed when the application shuts down.
        """
        self._container = None
        self._initialized = False
        logger.debug("CosmosBrokerRepository closed")
    
    async def _ensure_initialized(self) -> None:
        """Ensure repository is initialized before operations."""
        if not self._initialized:
            await self.initialize()
    
    async def get_all_connections(self) -> List[BrokerConnectionDocument]:
        """
        Get all broker connections.
        
        Returns:
            List of all broker connection documents
        """
        await self._ensure_initialized()
        
        try:
            query = "SELECT * FROM c WHERE c._type = 'broker_connection'"
            items = []
            
            async for item in self._container.query_items(
                query=query,
                enable_cross_partition_query=True,
            ):
                doc = BrokerConnectionDocument.from_cosmos_doc(item)
                if doc:
                    items.append(doc)
            
            logger.debug(f"Retrieved {len(items)} broker connections")
            return items
            
        except Exception as e:
            logger.error(f"Failed to get broker connections: {e}")
            return []
    
    async def get_active_connections(self) -> List[BrokerConnectionDocument]:
        """
        Get all non-disabled broker connections, deduplicated.
        
        Returns only one connection per (broker_type, is_paper) combination,
        preferring env-configured brokers and newer documents.
        
        Returns:
            List of active (not disabled) broker connections
        """
        await self._ensure_initialized()
        
        try:
            query = """
                SELECT * FROM c 
                WHERE c._type = 'broker_connection' 
                AND (c.is_disabled = false OR NOT IS_DEFINED(c.is_disabled))
            """
            raw_items = []
            
            async for item in self._container.query_items(
                query=query,
                enable_cross_partition_query=True,
            ):
                doc = BrokerConnectionDocument.from_cosmos_doc(item)
                if doc:
                    raw_items.append(doc)
            
            # Deduplicate: keep only one per (broker_type, is_paper)
            # Prefer env-configured brokers, then most recently updated
            seen: Dict[tuple, BrokerConnectionDocument] = {}
            for doc in raw_items:
                key = (doc.broker_type, doc.is_paper)
                existing = seen.get(key)
                
                if existing is None:
                    seen[key] = doc
                elif doc.source == 'env' and existing.source != 'env':
                    # Prefer env-configured
                    seen[key] = doc
                elif doc.source == existing.source:
                    # Same source - prefer newer (by updated_at)
                    if doc.updated_at > existing.updated_at:
                        seen[key] = doc
            
            items = list(seen.values())
            logger.debug(f"Retrieved {len(items)} active broker connections (deduplicated from {len(raw_items)})")
            return items
            
        except Exception as e:
            logger.error(f"Failed to get active broker connections: {e}")
            return []
    
    async def get_connection(self, connection_id: str) -> Optional[BrokerConnectionDocument]:
        """
        Get a specific broker connection by ID.
        
        Args:
            connection_id: The connection ID to retrieve
            
        Returns:
            The connection document, or None if not found
        """
        await self._ensure_initialized()
        
        try:
            # Need to query since we don't know the partition key from just ID
            query = "SELECT * FROM c WHERE c.id = @id AND c._type = 'broker_connection'"
            params = [{"name": "@id", "value": connection_id}]
            
            async for item in self._container.query_items(
                query=query,
                parameters=params,
                enable_cross_partition_query=True,
            ):
                return BrokerConnectionDocument.from_cosmos_doc(item)
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get broker connection {connection_id}: {e}")
            return None
    
    async def get_connection_by_id_and_type(
        self, 
        connection_id: str, 
        broker_type: str
    ) -> Optional[BrokerConnectionDocument]:
        """
        Get a broker connection by ID using known partition key for efficiency.
        
        Args:
            connection_id: The connection ID
            broker_type: The broker type (partition key)
            
        Returns:
            The connection document, or None if not found
        """
        await self._ensure_initialized()
        
        try:
            item = await self._container.read_item(
                item=connection_id,
                partition_key=broker_type
            )
            return BrokerConnectionDocument.from_cosmos_doc(item)
            
        except self._cosmos_exceptions.CosmosResourceNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Failed to get broker connection {connection_id}: {e}")
            return None
    
    async def save_connection(
        self, 
        connection: BrokerConnectionDocument
    ) -> BrokerConnectionDocument:
        """
        Save or update a broker connection.
        
        Uses upsert to handle both create and update operations.
        
        Args:
            connection: The connection document to save
            
        Returns:
            The saved connection document
        """
        await self._ensure_initialized()
        
        try:
            # Update timestamp
            connection.updated_at = datetime.now(timezone.utc).isoformat()
            
            doc = connection.to_cosmos_doc()
            result = await self._container.upsert_item(doc)
            
            logger.info(f"Saved broker connection: {connection.id}")
            return BrokerConnectionDocument.from_cosmos_doc(result)
            
        except Exception as e:
            logger.error(f"Failed to save broker connection {connection.id}: {e}")
            raise
    
    async def delete_connection(self, connection_id: str) -> bool:
        """
        Delete a broker connection (hard delete).
        
        For env-configured brokers, prefer disable_connection() instead.
        
        Args:
            connection_id: The connection ID to delete
            
        Returns:
            True if deleted, False if not found
        """
        await self._ensure_initialized()
        
        try:
            # First, get the connection to know the partition key
            connection = await self.get_connection(connection_id)
            if not connection:
                return False
            
            await self._container.delete_item(
                item=connection_id,
                partition_key=connection.broker_type
            )
            
            logger.info(f"Deleted broker connection: {connection_id}")
            return True
            
        except self._cosmos_exceptions.CosmosResourceNotFoundError:
            return False
        except Exception as e:
            logger.error(f"Failed to delete broker connection {connection_id}: {e}")
            raise
    
    async def disable_connection(self, connection_id: str) -> bool:
        """
        Mark a connection as disabled (soft delete).
        
        This is preferred for env-configured brokers since we need to
        remember that the user disabled them to prevent re-syncing.
        
        Args:
            connection_id: The connection ID to disable
            
        Returns:
            True if disabled, False if not found
        """
        await self._ensure_initialized()
        
        try:
            connection = await self.get_connection(connection_id)
            if not connection:
                return False
            
            connection.is_disabled = True
            connection.status = "disabled"
            await self.save_connection(connection)
            
            logger.info(f"Disabled broker connection: {connection_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to disable broker connection {connection_id}: {e}")
            return False
    
    async def is_connection_disabled(self, connection_id: str) -> bool:
        """
        Check if a connection is disabled.
        
        Args:
            connection_id: The connection ID to check
            
        Returns:
            True if disabled, False if not found or not disabled
        """
        await self._ensure_initialized()
        
        try:
            connection = await self.get_connection(connection_id)
            return connection.is_disabled if connection else False
            
        except Exception as e:
            logger.error(f"Failed to check disabled status for {connection_id}: {e}")
            return False
    
    async def get_disabled_env_brokers(self) -> set:
        """
        Get set of disabled env-configured broker IDs.
        
        This is used by BrokerRouter to know which env brokers
        should not be auto-synced.
        
        Returns:
            Set of disabled env broker connection IDs
        """
        await self._ensure_initialized()
        
        try:
            query = """
                SELECT c.id FROM c 
                WHERE c._type = 'broker_connection' 
                AND c.source = 'env'
                AND c.is_disabled = true
            """
            disabled_ids = set()
            
            async for item in self._container.query_items(
                query=query,
                enable_cross_partition_query=True,
            ):
                disabled_ids.add(item['id'])
            
            return disabled_ids
            
        except Exception as e:
            logger.error(f"Failed to get disabled env brokers: {e}")
            return set()
    
    async def connection_exists(
        self, 
        broker_type: str, 
        is_paper: bool, 
        api_key_masked: str
    ) -> bool:
        """
        Check if a connection with these parameters already exists.
        
        DEPRECATED: Use connection_exists_by_hash() instead for more reliable
        duplicate detection. Masked key comparison can have false positives
        (different keys with same last 4 chars) or false negatives.
        
        Args:
            broker_type: The broker type
            is_paper: Whether paper trading mode
            api_key_masked: The masked API key
            
        Returns:
            True if a matching connection exists
        """
        await self._ensure_initialized()
        
        try:
            query = """
                SELECT c.id FROM c 
                WHERE c._type = 'broker_connection' 
                AND c.broker_type = @broker_type
                AND c.is_paper = @is_paper
                AND c.api_key_masked = @api_key_masked
                AND (c.is_disabled = false OR NOT IS_DEFINED(c.is_disabled))
            """
            params = [
                {"name": "@broker_type", "value": broker_type},
                {"name": "@is_paper", "value": is_paper},
                {"name": "@api_key_masked", "value": api_key_masked},
            ]
            
            # Note: Using partition key filter (broker_type) so cross-partition not needed
            async for _ in self._container.query_items(
                query=query,
                parameters=params,
            ):
                return True  # Found at least one match
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to check connection existence: {e}")
            return False
    
    async def connection_exists_by_hash(
        self, 
        broker_type: str, 
        is_paper: bool, 
        api_key_hash: str
    ) -> bool:
        """
        Check if a connection with these parameters already exists using hash.
        
        Uses SHA256 hash of the API key for reliable duplicate detection.
        This is more secure and reliable than masked key comparison.
        
        Args:
            broker_type: The broker type
            is_paper: Whether paper trading mode
            api_key_hash: SHA256 hash of the API key
            
        Returns:
            True if a matching connection exists
        """
        await self._ensure_initialized()
        
        try:
            query = """
                SELECT c.id FROM c 
                WHERE c._type = 'broker_connection' 
                AND c.broker_type = @broker_type
                AND c.is_paper = @is_paper
                AND c.api_key_hash = @api_key_hash
                AND (c.is_disabled = false OR NOT IS_DEFINED(c.is_disabled))
            """
            params = [
                {"name": "@broker_type", "value": broker_type},
                {"name": "@is_paper", "value": is_paper},
                {"name": "@api_key_hash", "value": api_key_hash},
            ]
            
            # Note: Using partition key filter (broker_type) so cross-partition not needed
            async for _ in self._container.query_items(
                query=query,
                parameters=params,
            ):
                return True  # Found at least one match
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to check connection existence by hash: {e}")
            return False
