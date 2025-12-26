"""
Cosmos DB Base Repository - Shared Infrastructure.

This module provides the foundational Cosmos DB connectivity and utilities
shared across all Cosmos DB repositories in the application.

Architecture:
    - CosmosConnectionPool: Singleton connection pool for efficient resource usage
    - CosmosBaseRepository: Abstract base class for all Cosmos repositories

Benefits:
    - Single connection pool shared across repositories (no duplicate clients)
    - Consistent error handling and logging
    - Unified datetime serialization
    - DRY principle - no code duplication between repositories
    - Lazy imports: Azure SDK is only loaded when actually connecting

Usage:
    ```python
    class MyRepository(CosmosBaseRepository):
        async def initialize(self) -> None:
            await self._initialize_base()
            # Create your specific containers
            self._my_container = await self._create_container(
                "my_container", "/partition_key"
            )
    ```

Author: Trading Bot Team
Version: 1.2.0
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TYPE_CHECKING

# Lazy imports: Azure SDK modules are imported when first needed
# This allows tests and tools to import this module without requiring Azure SDK
if TYPE_CHECKING:
    from azure.cosmos.aio import CosmosClient
    from azure.cosmos import PartitionKey, exceptions as cosmos_exceptions
    from azure.identity.aio import DefaultAzureCredential

from src.core.logging_config import get_logger


logger = get_logger(__name__)


# System properties added by Cosmos DB that should be stripped from documents
COSMOS_SYSTEM_PROPERTIES = frozenset([
    '_rid', '_self', '_etag', '_attachments', '_ts', '_type'
])


class CosmosConnectionPool:
    """
    Singleton connection pool for Cosmos DB.
    
    Ensures a single CosmosClient is shared across all repositories
    to optimize connection usage and resource consumption.
    
    Thread-Safety:
        Uses asyncio locks to ensure thread-safe initialization.
        Once initialized, the client can be accessed concurrently.
    
    Lazy Loading:
        Azure SDK imports are deferred until initialize() is called.
        This allows tests to import this module without Azure SDK installed.
    
    Usage:
        ```python
        pool = CosmosConnectionPool.get_instance()
        await pool.initialize(endpoint, database_name)
        client = pool.client
        database = pool.database
        ```
    """
    
    _instance: Optional["CosmosConnectionPool"] = None
    _lock = asyncio.Lock()
    
    def __init__(self):
        """Private constructor - use get_instance() instead."""
        self._client: Optional[Any] = None  # CosmosClient (lazy loaded)
        self._credential: Optional[Any] = None  # DefaultAzureCredential (lazy loaded)
        self._database = None
        self._endpoint: Optional[str] = None
        self._database_name: Optional[str] = None
        self._initialized = False
    
    @classmethod
    def get_instance(cls) -> "CosmosConnectionPool":
        """
        Get the singleton instance of the connection pool.
        
        Returns:
            The singleton CosmosConnectionPool instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset(cls) -> None:
        """
        Reset the singleton instance (for testing purposes).
        
        Warning:
            This should only be used in tests. In production, the
            connection pool should persist for the application lifetime.
            
        Note:
            This method schedules an async close but does not await it.
            For proper cleanup in tests, use reset_async() instead.
        """
        if cls._instance and cls._instance._initialized:
            # Schedule close - for sync contexts only
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(cls._instance.close())
            except RuntimeError:
                # No running loop - connection will be closed on next init
                logger.debug("No event loop running, skipping async close")
        cls._instance = None
    
    @classmethod
    async def reset_async(cls) -> None:
        """
        Async reset of the singleton instance (preferred for tests).
        
        Properly awaits the close operation to prevent resource leaks.
        """
        if cls._instance and cls._instance._initialized:
            await cls._instance.close()
        cls._instance = None
    
    @property
    def client(self) -> Optional[CosmosClient]:
        """Get the Cosmos client."""
        return self._client
    
    @property
    def database(self):
        """Get the database reference."""
        return self._database
    
    @property
    def is_initialized(self) -> bool:
        """Check if the connection pool is initialized."""
        return self._initialized
    
    async def initialize(
        self,
        endpoint: str,
        database_name: str,
        credential: Optional[Any] = None
    ) -> None:
        """
        Initialize the connection pool.
        
        Uses double-checked locking pattern for thread-safe initialization.
        If already initialized with the same endpoint, this is a no-op.
        
        Azure SDK is imported lazily here, allowing this module to be
        imported without the SDK installed (e.g., for testing).
        
        Args:
            endpoint: Cosmos DB account endpoint URL
            database_name: Name of the database
            credential: Optional Azure credential (defaults to DefaultAzureCredential)
            
        Raises:
            ImportError: If Azure SDK is not installed
            Exception: If connection fails
        """
        # Quick check without lock
        if self._initialized and self._endpoint == endpoint:
            return
        
        async with self._lock:
            # Double-check inside lock
            if self._initialized and self._endpoint == endpoint:
                return
            
            # Close existing connection if endpoint changed
            if self._initialized and self._endpoint != endpoint:
                await self._close_internal()
            
            try:
                # Lazy import Azure SDK - only when actually connecting
                from azure.cosmos.aio import CosmosClient
                
                logger.info(f"Initializing Cosmos DB connection pool: {endpoint}")
                
                # Check for explicit key (required for emulator, optional for Azure)
                import os
                cosmos_key = os.environ.get("AZURE_COSMOS_KEY")
                
                # Detect if using emulator - prefer explicit flag over URL heuristics
                # AZURE_COSMOS_EMULATOR=true is the recommended way to indicate emulator usage
                is_emulator = os.environ.get("AZURE_COSMOS_EMULATOR", "").lower() == "true"
                if not is_emulator:
                    # Fallback: detect by URL (for backward compatibility)
                    # This is less reliable than explicit config but preserves existing behavior
                    is_emulator = "localhost" in endpoint.lower() or "127.0.0.1" in endpoint
                    if is_emulator:
                        logger.warning(
                            "Detected Cosmos DB Emulator via URL heuristics. "
                            "Set AZURE_COSMOS_EMULATOR=true for explicit configuration."
                        )
                
                if cosmos_key:
                    # Use key-based authentication (emulator or explicit key)
                    logger.info("Using key-based authentication for Cosmos DB")
                    self._credential = cosmos_key
                elif credential:
                    # Use provided credential
                    self._credential = credential
                else:
                    # Fall back to DefaultAzureCredential (Managed Identity)
                    from azure.identity.aio import DefaultAzureCredential
                    logger.info("Using DefaultAzureCredential for Cosmos DB")
                    self._credential = DefaultAzureCredential()
                
                # Create client with emulator-specific settings if needed
                if is_emulator:
                    logger.info("Cosmos DB Emulator mode - SSL verification disabled")
                    self._client = CosmosClient(
                        url=endpoint,
                        credential=self._credential,
                        connection_verify=False  # Disable SSL for emulator
                    )
                else:
                    self._client = CosmosClient(
                        url=endpoint,
                        credential=self._credential
                    )
                
                # Get or create database
                self._database = await self._client.create_database_if_not_exists(
                    id=database_name
                )
                
                self._endpoint = endpoint
                self._database_name = database_name
                self._initialized = True
                
                logger.info(f"Cosmos DB connection pool initialized: {database_name}")
                
            except Exception as e:
                logger.error(f"Failed to initialize Cosmos connection pool: {e}")
                await self._close_internal()
                raise
    
    async def close(self) -> None:
        """Close the connection pool."""
        async with self._lock:
            await self._close_internal()
    
    async def _close_internal(self) -> None:
        """Internal close without lock (must be called with lock held)."""
        try:
            if self._client:
                await self._client.close()
                self._client = None
            # Only close credential if it's an object with close method (not a string key)
            if self._credential and hasattr(self._credential, 'close'):
                await self._credential.close()
            self._credential = None
            self._database = None
            self._initialized = False
            logger.info("Cosmos DB connection pool closed")
        except Exception as e:
            logger.error(f"Error closing Cosmos connection pool: {e}")


class CosmosBaseRepository(ABC):
    """
    Abstract base class for Cosmos DB repositories.
    
    Provides shared functionality:
    - Connection management via shared pool
    - Container creation
    - Datetime serialization/deserialization
    - Document property cleanup
    - Retry and error handling utilities
    
    Lazy Loading:
        Azure SDK is only imported when initialize() is called.
        This allows tests to work without Azure SDK installed.
    
    Subclasses must implement:
    - initialize(): Create specific containers
    - close(): Clean up any local resources
    
    Thread-Safety:
        This class is safe for concurrent async operations.
        The connection pool handles synchronization internally.
    """
    
    def __init__(
        self,
        cosmos_endpoint: str,
        database_name: str = "trading-bot",
        credential: Optional[Any] = None
    ):
        """
        Initialize the repository.
        
        Args:
            cosmos_endpoint: Cosmos DB account endpoint URL
            database_name: Name of the database
            credential: Optional Azure credential (DefaultAzureCredential)
        """
        self._endpoint = cosmos_endpoint
        self._database_name = database_name
        self._external_credential = credential
        self._initialized = False
        
        # Get shared connection pool
        self._pool = CosmosConnectionPool.get_instance()
    
    @property
    def _database(self):
        """Get database reference from pool."""
        return self._pool.database
    
    @property
    def _client(self) -> Optional[Any]:
        """Get client reference from pool (CosmosClient when initialized)."""
        return self._pool.client
    
    async def _initialize_base(self) -> None:
        """
        Initialize the base connection.
        
        Call this at the start of your initialize() implementation.
        """
        await self._pool.initialize(
            endpoint=self._endpoint,
            database_name=self._database_name,
            credential=self._external_credential
        )
    
    async def _create_container(
        self,
        container_name: str,
        partition_key_path: str,
        default_ttl: Optional[int] = None,
        offer_throughput: Optional[int] = None
    ):
        """
        Create or get a container.
        
        Args:
            container_name: Name of the container
            partition_key_path: Partition key path (e.g., "/symbol")
            default_ttl: Optional TTL in seconds (-1 for no TTL)
            offer_throughput: Optional provisioned throughput (RU/s)
            
        Returns:
            Container reference
        """
        if not self._database:
            raise RuntimeError("Database not initialized. Call _initialize_base() first.")
        
        # Lazy import - only when actually creating containers
        from azure.cosmos import PartitionKey
        
        partition_key = PartitionKey(path=partition_key_path)
        
        kwargs = {
            "id": container_name,
            "partition_key": partition_key
        }
        
        if default_ttl is not None and default_ttl != -1:
            kwargs["default_ttl"] = default_ttl
        
        if offer_throughput:
            kwargs["offer_throughput"] = offer_throughput
        
        container = await self._database.create_container_if_not_exists(**kwargs)
        logger.debug(f"Container ready: {container_name}")
        return container
    
    async def _ensure_initialized(self) -> None:
        """Ensure the repository is initialized."""
        if not self._initialized:
            await self.initialize()
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the repository and create containers.
        
        Implementations should call _initialize_base() first,
        then create their specific containers.
        """
        pass
    
    @abstractmethod
    async def close(self) -> None:
        """
        Close the repository.
        
        Implementations should clean up any local resources.
        The connection pool is managed separately.
        """
        pass
    
    # =========================================================================
    # Serialization Utilities
    # =========================================================================
    
    @staticmethod
    def serialize_datetime(dt: Optional[datetime]) -> Optional[str]:
        """
        Serialize datetime to ISO format string.
        
        Args:
            dt: Datetime to serialize
            
        Returns:
            ISO format string or None
        """
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    
    @staticmethod
    def deserialize_datetime(dt_str: Optional[str]) -> Optional[datetime]:
        """
        Deserialize ISO format string to datetime.
        
        Args:
            dt_str: ISO format string
            
        Returns:
            Datetime or None
        """
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        except ValueError:
            logger.warning(f"Failed to parse datetime: {dt_str}")
            return None
    
    @staticmethod
    def strip_cosmos_properties(doc: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove Cosmos DB system properties from a document.
        
        Args:
            doc: Document dictionary
            
        Returns:
            Document without system properties
        """
        return {k: v for k, v in doc.items() if k not in COSMOS_SYSTEM_PROPERTIES}
    
    @staticmethod
    def now_iso() -> str:
        """Get current UTC time as ISO string."""
        return datetime.now(timezone.utc).isoformat()
    
    # =========================================================================
    # Query Utilities
    # =========================================================================
    
    async def _query_items(
        self,
        container,
        query: str,
        parameters: Optional[List[Dict[str, Any]]] = None,
        partition_key: Optional[str] = None,
        max_items: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute a query and return results as a list.
        
        Args:
            container: Container to query
            query: SQL query string
            parameters: Query parameters
            partition_key: Optional partition key for efficient query
            max_items: Maximum number of items to return
            
        Returns:
            List of documents
        """
        query_options = {}
        if parameters:
            query_options["parameters"] = parameters
        if max_items:
            query_options["max_item_count"] = max_items
        # Note: enable_cross_partition_query is deprecated in SDK 4.x+
        # Cross-partition queries are now enabled by default
        
        items = []
        async for item in container.query_items(query=query, **query_options):
            items.append(item)
            if max_items and len(items) >= max_items:
                break
        
        return items
    
    async def _point_read(
        self,
        container,
        item_id: str,
        partition_key: str
    ) -> Optional[Dict[str, Any]]:
        """
        Perform a point read (most efficient read operation).
        
        Args:
            container: Container to read from
            item_id: Document ID
            partition_key: Partition key value
            
        Returns:
            Document if found, None otherwise
        """
        # Lazy import for exception handling
        from azure.cosmos import exceptions as cosmos_exceptions
        
        try:
            return await container.read_item(
                item=item_id,
                partition_key=partition_key
            )
        except cosmos_exceptions.CosmosResourceNotFoundError:
            return None
    
    async def _upsert_item(
        self,
        container,
        document: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Upsert a document (create or update).
        
        Args:
            container: Container to upsert into
            document: Document to upsert
            
        Returns:
            Upserted document
        """
        return await container.upsert_item(body=document)
    
    async def _delete_item(
        self,
        container,
        item_id: str,
        partition_key: str
    ) -> bool:
        """
        Delete a document.
        
        Args:
            container: Container to delete from
            item_id: Document ID
            partition_key: Partition key value
            
        Returns:
            True if deleted, False if not found
        """
        # Lazy import for exception handling
        from azure.cosmos import exceptions as cosmos_exceptions
        
        try:
            await container.delete_item(
                item=item_id,
                partition_key=partition_key
            )
            return True
        except cosmos_exceptions.CosmosResourceNotFoundError:
            return False
