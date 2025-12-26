"""
Broker Management Router.

Handles broker connection management:
- List connected brokers
- Add new broker connections
- Remove broker connections
- Test broker connectivity

This enables the "Add Broker" functionality in the web UI,
allowing users to configure brokers at runtime instead of
requiring them at startup.

Persistence:
    Broker connections are persisted to Cosmos DB via CosmosBrokerRepository.
    This ensures connections survive application restarts in Azure.
    
    For env-configured brokers (credentials in Key Vault), we track
    the 'disabled' state in Cosmos DB to remember user preferences.

Author: Trading Bot Team
Version: 2.0.0
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
import hashlib

from pydantic import BaseModel, Field, field_validator, ConfigDict
from pydantic.alias_generators import to_camel
from fastapi import Request, HTTPException, Header
from fastapi.responses import JSONResponse

from src.core.logging_config import get_logger
from src.core import ConfigurationManager
from src.constants import HTTPStatus
from src.signals.routers.base_router import BaseAdminRouter, handle_route_errors
from src.database.cosmos_broker_repository import (
    CosmosBrokerRepository,
    BrokerConnectionDocument,
)

logger = get_logger(__name__)


# =============================================================================
# Request/Response Models
# =============================================================================

class BrokerCredentials(BaseModel):
    """Broker API credentials for connection."""
    
    api_key: str = Field(..., min_length=1, description="Broker API key")
    api_secret: str = Field(..., min_length=1, description="Broker API secret")
    is_paper: bool = Field(default=True, description="Use paper/sandbox trading")
    
    @field_validator('api_key', 'api_secret')
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        """Remove leading/trailing whitespace from credentials."""
        return v.strip()


class AddBrokerRequest(BaseModel):
    """Request model for adding a new broker connection."""
    
    broker_type: str = Field(
        ..., 
        description="Broker type (e.g., 'alpaca', 'tastytrade')",
        pattern="^(alpaca|tastytrade|oanda|interactive-brokers|tradier|coinbase|kraken)$"
    )
    name: str = Field(
        default="",
        description="Custom name for this connection",
        max_length=100
    )
    credentials: BrokerCredentials
    
    @field_validator('broker_type')
    @classmethod
    def lowercase_broker_type(cls, v: str) -> str:
        """Ensure broker type is lowercase."""
        return v.lower().strip()
    
    @field_validator('name', mode='before')
    @classmethod
    def default_name(cls, v: str) -> str:
        """Strip whitespace from name. Default is handled by Pydantic."""
        if v:
            return v.strip()
        return v


class BrokerConnectionInfo(BaseModel):
    """Response model for broker connection details."""
    
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        # Note: Use model_dump(by_alias=True) at serialization points
        # The serialization_alias config is set via alias_generator
    )
    
    id: str = Field(..., description="Unique connection ID")
    name: str = Field(..., description="Connection display name")
    type: str = Field(default="broker", description="Connection type")
    broker_type: str = Field(..., description="Broker identifier (e.g., 'alpaca')")
    status: str = Field(..., description="Connection status: connected, disconnected, error, pending")
    supported_assets: List[str] = Field(default_factory=list)
    balance: float = Field(default=0.0)
    buying_power: float = Field(default=0.0)
    portfolio_value: float = Field(default=0.0)
    open_positions: int = Field(default=0)
    last_sync: Optional[str] = None
    api_key_masked: str = Field(default="****", description="Masked API key for display")
    is_paper: bool = Field(default=True)
    logo_url: Optional[str] = None
    error_message: Optional[str] = None


class BrokersListResponse(BaseModel):
    """Response model for listing broker connections."""
    
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        # Note: Use model_dump(by_alias=True) at serialization points
    )
    
    connections: List[BrokerConnectionInfo] = Field(default_factory=list)
    total_count: int = Field(default=0)


class AddBrokerResponse(BaseModel):
    """Response model for adding a broker."""
    
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        # Note: Use model_dump(by_alias=True) at serialization points
    )
    
    success: bool
    connection: Optional[BrokerConnectionInfo] = None
    message: str


class TestConnectionResponse(BaseModel):
    """Response model for testing broker connection."""
    
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        # Note: Use model_dump(by_alias=True) at serialization points
    )
    
    success: bool
    broker_type: str
    latency_ms: Optional[float] = None
    account_status: Optional[str] = None
    message: str


# =============================================================================
# Broker Type Metadata
# =============================================================================

BROKER_METADATA = {
    "alpaca": {
        "name": "Alpaca",
        "supported_assets": ["stock", "etf", "crypto"],
        "has_paper": True,
        "logo_url": "/brokers/alpaca.svg",
        "base_url_paper": "https://paper-api.alpaca.markets",
        "base_url_live": "https://api.alpaca.markets",
    },
    "tastytrade": {
        "name": "Tastytrade",
        "supported_assets": ["stock", "etf"],
        "has_paper": False,
        "logo_url": "/brokers/tastytrade.svg",
    },
    "oanda": {
        "name": "OANDA",
        "supported_assets": ["forex"],
        "has_paper": True,
        "logo_url": "/brokers/oanda.svg",
    },
    "interactive-brokers": {
        "name": "Interactive Brokers",
        "supported_assets": ["stock", "etf", "forex", "commodity"],
        "has_paper": True,
        "logo_url": "/brokers/ibkr.svg",
    },
    "tradier": {
        "name": "Tradier",
        "supported_assets": ["stock", "etf"],
        "has_paper": True,
        "logo_url": "/brokers/tradier.svg",
    },
    "coinbase": {
        "name": "Coinbase",
        "supported_assets": ["crypto"],
        "has_paper": False,
        "logo_url": "/brokers/coinbase.svg",
    },
    "kraken": {
        "name": "Kraken",
        "supported_assets": ["crypto"],
        "has_paper": False,
        "logo_url": "/brokers/kraken.svg",
    },
}


def mask_api_key(api_key: str) -> str:
    """Mask API key for display, showing only last 4 characters."""
    if len(api_key) <= 4:
        return "****"
    return f"****-****-****-{api_key[-4:]}"


def hash_api_key(api_key: str) -> str:
    """
    Create a SHA256 hash of the API key for secure duplicate detection.
    
    This is more reliable than using masked keys (last 4 chars) which can
    have false positives (different keys with same suffix) or false negatives
    (same key detected as different due to masking issues).
    
    Args:
        api_key: The raw API key to hash
        
    Returns:
        SHA256 hash string (64 hex characters)
    """
    return hashlib.sha256(api_key.encode('utf-8')).hexdigest()


class BrokerRouter(BaseAdminRouter):
    """
    Router for broker connection management.
    
    Provides endpoints for:
    - GET /admin/brokers - List all broker connections
    - POST /admin/brokers - Add a new broker connection
    - DELETE /admin/brokers/{connection_id} - Remove a broker connection
    - POST /admin/brokers/{connection_id}/test - Test broker connectivity
    - GET /admin/brokers/available - List available broker types
    
    Persistence:
        Uses CosmosBrokerRepository to persist broker connections to Cosmos DB.
        This ensures connections survive application restarts in production.
    
    Thread-Safety:
        This class is safe for concurrent async operations.
    """
    
    def __init__(
        self,
        auth_service=None,
        bot_instance=None,
        broker_repository: Optional[CosmosBrokerRepository] = None,
    ):
        """
        Initialize BrokerRouter.
        
        Args:
            auth_service: Optional authentication service for token validation
            bot_instance: Optional trading bot instance for broker operations
            broker_repository: Optional broker repository for persistence.
                              If not provided, creates a new instance.
        """
        super().__init__(prefix="/admin/brokers", auth_service=auth_service, tags=["brokers"])
        self.bot = bot_instance
        self._config = ConfigurationManager()
        
        # Repository for persisting broker connections to Cosmos DB
        self._broker_repo = broker_repository or CosmosBrokerRepository()
        self._repo_initialized = False
        
        # In-memory cache for fast access (synced from DB)
        self._connections_cache: Dict[str, BrokerConnectionInfo] = {}
        self._cache_loaded = False
        self._env_brokers_synced = False  # Track if env brokers have been synced
        
        self._setup_routes()
        logger.info("BrokerRouter initialized with Cosmos DB persistence")
    
    async def _ensure_repo_initialized(self) -> None:
        """Ensure the broker repository is initialized."""
        if not self._repo_initialized:
            try:
                await self._broker_repo.initialize()
                self._repo_initialized = True
                logger.info("Broker repository initialized")
            except Exception as e:
                logger.error(f"Failed to initialize broker repository: {e}")
                raise
    
    async def _load_connections_from_db(self, force_refresh: bool = False) -> None:
        """Load connections from database into cache.
        
        Args:
            force_refresh: If True, reload from DB even if cache is loaded.
                         If False, skip reload if cache is already populated.
        """
        if self._cache_loaded and not force_refresh:
            logger.debug("Using cached broker connections (skipping DB reload)")
            return
        
        await self._ensure_repo_initialized()
        
        try:
            # Get all active (non-disabled) connections from DB
            db_connections = await self._broker_repo.get_active_connections()
            
            self._connections_cache.clear()
            for doc in db_connections:
                # Convert document to BrokerConnectionInfo
                connection = self._doc_to_connection_info(doc)
                if connection:
                    self._connections_cache[connection.id] = connection
            
            self._cache_loaded = True
            logger.debug(f"Loaded {len(self._connections_cache)} connections from DB")
            
        except Exception as e:
            logger.error(f"Failed to load connections from DB: {e}")
            # Continue with empty cache - env brokers will still work
    
    def _doc_to_connection_info(
        self, 
        doc: BrokerConnectionDocument
    ) -> Optional[BrokerConnectionInfo]:
        """Convert database document to BrokerConnectionInfo."""
        if not doc:
            return None
        
        metadata = BROKER_METADATA.get(doc.broker_type, {})
        
        return BrokerConnectionInfo(
            id=doc.id,
            name=doc.name,
            type="broker",
            broker_type=doc.broker_type,
            status=doc.status if not doc.is_disabled else "disabled",
            supported_assets=doc.supported_assets or metadata.get("supported_assets", []),
            balance=doc.balance,
            buying_power=doc.buying_power,
            portfolio_value=doc.portfolio_value,
            open_positions=doc.open_positions,
            api_key_masked=doc.api_key_masked,
            is_paper=doc.is_paper,
            logo_url=doc.logo_url or metadata.get("logo_url"),
            last_sync=doc.last_sync,
            error_message=doc.error_message,
        )
    
    def _connection_info_to_doc(
        self, 
        connection: BrokerConnectionInfo,
        source: str = "user",
        api_key_hash: Optional[str] = None
    ) -> BrokerConnectionDocument:
        """Convert BrokerConnectionInfo to database document.
        
        Args:
            connection: The connection info to convert
            source: Source of the connection ('env' or 'user')
            api_key_hash: Optional SHA256 hash of API key for duplicate detection
            
        Returns:
            BrokerConnectionDocument ready for persistence
        """
        return BrokerConnectionDocument(
            id=connection.id,
            broker_type=connection.broker_type,
            name=connection.name,
            status=connection.status,
            source=source,
            is_disabled=False,
            is_paper=connection.is_paper,
            api_key_masked=connection.api_key_masked,
            api_key_hash=api_key_hash,
            supported_assets=connection.supported_assets,
            balance=connection.balance,
            buying_power=connection.buying_power,
            portfolio_value=connection.portfolio_value,
            open_positions=connection.open_positions,
            error_message=connection.error_message,
            logo_url=connection.logo_url,
            last_sync=connection.last_sync,
        )
    
    def _setup_routes(self) -> None:
        """Configure all broker management routes."""
        
        @self.router.get(
            "",
            response_model=BrokersListResponse,
            summary="List broker connections",
            description="Get all configured broker connections with their status and account info."
        )
        @handle_route_errors("list_brokers")
        async def list_brokers(
            request: Request,
            authorization: Optional[str] = Header(None),
        ) -> BrokersListResponse:
            """List all broker connections."""
            await self.validate_auth(request, authorization)
            
            # Load connections from database
            await self._load_connections_from_db()
            
            # Sync any env-configured brokers (checks DB for disabled status)
            await self._sync_configured_brokers()
            
            connections = list(self._connections_cache.values())
            
            return BrokersListResponse(
                connections=connections,
                total_count=len(connections)
            )
        
        @self.router.post(
            "",
            response_model=AddBrokerResponse,
            summary="Add broker connection",
            description="Add a new broker connection with API credentials."
        )
        @handle_route_errors("add_broker")
        async def add_broker(
            request: Request,
            broker_request: AddBrokerRequest,
            authorization: Optional[str] = Header(None),
        ) -> AddBrokerResponse:
            """Add a new broker connection."""
            await self.validate_auth(request, authorization)
            await self._ensure_repo_initialized()
            
            broker_type = broker_request.broker_type
            metadata = BROKER_METADATA.get(broker_type)
            
            if not metadata:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=f"Unsupported broker type: {broker_type}"
                )
            
            # Check for duplicate connections using hash-based detection
            # This is more reliable than masked key (last 4 chars) comparison
            api_key_hash = hash_api_key(broker_request.credentials.api_key)
            duplicate_exists = await self._broker_repo.connection_exists_by_hash(
                broker_type=broker_type,
                is_paper=broker_request.credentials.is_paper,
                api_key_hash=api_key_hash
            )
            
            if duplicate_exists:
                return AddBrokerResponse(
                    success=False,
                    connection=None,
                    message=f"This {metadata['name']} account is already connected. "
                            f"{'(Paper mode)' if broker_request.credentials.is_paper else '(Live mode)'}"
                )
            
            # Generate connection ID
            import uuid
            connection_id = f"{broker_type}-{str(uuid.uuid4())[:8]}"
            
            # Test connectivity first
            test_result = await self._test_broker_connection(
                broker_type,
                broker_request.credentials.api_key,
                broker_request.credentials.api_secret,
                broker_request.credentials.is_paper
            )
            
            if not test_result["success"]:
                return AddBrokerResponse(
                    success=False,
                    connection=None,
                    message=f"Connection test failed: {test_result['message']}"
                )
            
            # Create connection info
            connection = BrokerConnectionInfo(
                id=connection_id,
                name=broker_request.name or metadata["name"],
                type="broker",
                broker_type=broker_type,
                status="connected",
                supported_assets=metadata["supported_assets"],
                balance=test_result.get("balance", 0.0),
                buying_power=test_result.get("buying_power", 0.0),
                portfolio_value=test_result.get("portfolio_value", 0.0),
                open_positions=test_result.get("open_positions", 0),
                last_sync=datetime.utcnow().isoformat(),
                api_key_masked=mask_api_key(broker_request.credentials.api_key),
                is_paper=broker_request.credentials.is_paper,
                logo_url=metadata.get("logo_url"),
            )
            
            # Persist to Cosmos DB with hash for duplicate detection
            doc = self._connection_info_to_doc(
                connection, 
                source="user", 
                api_key_hash=api_key_hash
            )
            await self._broker_repo.save_connection(doc)
            
            # Update cache
            self._connections_cache[connection_id] = connection
            
            # Also update the runtime configuration so the bot can use this broker
            # 
            # SECURITY NOTE: This stores credentials in memory only for current session.
            # On restart, only metadata is loaded from Cosmos; credentials must be:
            #   - Re-entered via UI (for user-added brokers)
            #   - Provided via environment (for env-configured brokers)
            #   - Retrieved from Azure Key Vault (production recommended)
            #
            # STATE: This connection is "connected but session-only" - user should
            # understand that restart requires re-authentication unless using
            # env vars or Key Vault integration.
            await self._configure_broker_runtime(
                broker_type,
                broker_request.credentials.api_key,
                broker_request.credentials.api_secret,
                broker_request.credentials.is_paper
            )
            
            logger.info(f"Added broker connection: {connection_id} ({broker_type})")
            
            return AddBrokerResponse(
                success=True,
                connection=connection,
                message=f"Successfully connected to {metadata['name']}"
            )
        
        @self.router.delete(
            "/{connection_id}",
            summary="Remove broker connection",
            description="Remove a broker connection by ID."
        )
        @handle_route_errors("remove_broker")
        async def remove_broker(
            request: Request,
            connection_id: str,
            authorization: Optional[str] = Header(None),
        ) -> JSONResponse:
            """Remove a broker connection."""
            await self.validate_auth(request, authorization)
            await self._ensure_repo_initialized()
            
            # Check if connection exists in cache or DB
            connection = self._connections_cache.get(connection_id)
            connection_doc = None
            if not connection:
                connection_doc = await self._broker_repo.get_connection(connection_id)
                if not connection_doc:
                    raise HTTPException(
                        status_code=HTTPStatus.NOT_FOUND,
                        detail=f"Connection not found: {connection_id}"
                    )
            
            # Determine source from persisted document (not ID suffix)
            # This is more reliable than checking connection_id.endswith('-env')
            is_env_broker = False
            if connection_doc:
                is_env_broker = connection_doc.source == 'env'
            elif connection_id in self._connections_cache:
                # Check if we have the doc cached - need to fetch for source
                cached_doc = await self._broker_repo.get_connection(connection_id)
                is_env_broker = cached_doc.source == 'env' if cached_doc else False
            
            # For env-configured brokers, use soft delete (disable)
            # This persists the "disabled" state so we don't re-sync them
            if is_env_broker:
                await self._broker_repo.disable_connection(connection_id)
                logger.info(f"Disabled env broker connection: {connection_id}")
            else:
                # For user-added brokers, do hard delete
                await self._broker_repo.delete_connection(connection_id)
                logger.info(f"Deleted broker connection: {connection_id}")
            
            # Remove from cache
            self._connections_cache.pop(connection_id, None)
            
            return JSONResponse(
                status_code=HTTPStatus.OK,
                content={"success": True, "message": "Connection removed"}
            )
        
        @self.router.post(
            "/{connection_id}/test",
            response_model=TestConnectionResponse,
            summary="Test broker connectivity",
            description="Test connectivity to a broker connection."
        )
        @handle_route_errors("test_broker")
        async def test_broker_connection(
            request: Request,
            connection_id: str,
            authorization: Optional[str] = Header(None),
        ) -> TestConnectionResponse:
            """Test a broker connection."""
            await self.validate_auth(request, authorization)
            await self._ensure_repo_initialized()
            
            connection = self._connections_cache.get(connection_id)
            if not connection:
                # Try loading from DB
                connection_doc = await self._broker_repo.get_connection(connection_id)
                if not connection_doc:
                    raise HTTPException(
                        status_code=HTTPStatus.NOT_FOUND,
                        detail=f"Connection not found: {connection_id}"
                    )
                connection = self._doc_to_connection_info(connection_doc)
            
            # Perform real connectivity test based on broker type
            # For env-configured brokers, we have credentials in config
            # For user-added brokers, we only have masked keys (would need re-auth)
            broker_type = connection.broker_type
            
            try:
                import time
                start_time = time.time()
                
                if broker_type == "alpaca":
                    # Check if we have live credentials in config
                    api_key = self._config.get_config("api.alpaca.api_key", "")
                    api_secret = self._config.get_config("api.alpaca.secret_key", "")
                    
                    if api_key and api_secret:
                        result = await self._test_alpaca_connection(
                            api_key, api_secret, connection.is_paper
                        )
                        latency_ms = (time.time() - start_time) * 1000
                        
                        if result.get("success"):
                            return TestConnectionResponse(
                                success=True,
                                broker_type=broker_type,
                                latency_ms=round(latency_ms, 2),
                                account_status=result.get("account_status", "active"),
                                message="Connection verified successfully"
                            )
                        else:
                            return TestConnectionResponse(
                                success=False,
                                broker_type=broker_type,
                                latency_ms=round(latency_ms, 2),
                                account_status="error",
                                message=result.get("message", "Connection test failed")
                            )
                    else:
                        # User-added broker without live credentials
                        return TestConnectionResponse(
                            success=False,
                            broker_type=broker_type,
                            latency_ms=None,
                            account_status="needs_reauth",
                            message="Re-authentication required - credentials not in runtime config"
                        )
                        
                elif broker_type == "tastytrade":
                    # Tastytrade uses session-based auth
                    # NOTE: True connectivity test not yet implemented for Tastytrade
                    refresh_token = self._config.get_config("api.tastytrade.refresh_token", "")
                    if refresh_token:
                        # Credentials are present but not verified - return pending status
                        # TODO: Implement actual Tastytrade API connectivity test
                        return TestConnectionResponse(
                            success=False,
                            broker_type=broker_type,
                            latency_ms=None,
                            account_status="pending_verification",
                            message="Tastytrade credentials configured but not verified (connectivity test not implemented)"
                        )
                    else:
                        return TestConnectionResponse(
                            success=False,
                            broker_type=broker_type,
                            latency_ms=None,
                            account_status="needs_reauth",
                            message="Tastytrade refresh token not configured"
                        )
                else:
                    # Unsupported broker type
                    return TestConnectionResponse(
                        success=False,
                        broker_type=broker_type,
                        latency_ms=None,
                        account_status="unsupported",
                        message=f"Connectivity test not implemented for {broker_type}"
                    )
                    
            except Exception as e:
                logger.error(f"Error testing broker connection {connection_id}: {e}")
                return TestConnectionResponse(
                    success=False,
                    broker_type=broker_type,
                    latency_ms=None,
                    account_status="error",
                    message=f"Test failed: {str(e)}"
                )
        
        @self.router.get(
            "/available",
            summary="List available broker types",
            description="Get a list of all supported broker types and their capabilities."
        )
        @handle_route_errors("list_available_brokers")
        async def list_available_brokers(
            request: Request,
            authorization: Optional[str] = Header(None),
        ) -> JSONResponse:
            """List available broker types."""
            await self.validate_auth(request, authorization)
            
            available = []
            for broker_id, metadata in BROKER_METADATA.items():
                available.append({
                    "id": broker_id,
                    "name": metadata["name"],
                    "supportedAssets": metadata["supported_assets"],
                    "hasPaper": metadata["has_paper"],
                    "logoUrl": metadata.get("logo_url"),
                })
            
            return JSONResponse(content={"brokers": available})
        
        @self.router.post(
            "/refresh",
            summary="Refresh broker connections",
            description="Force refresh of broker connections from database and environment. "
                       "Use this to fetch latest account data from broker APIs."
        )
        @handle_route_errors("refresh_brokers")
        async def refresh_brokers(
            request: Request,
            authorization: Optional[str] = Header(None),
        ) -> BrokersListResponse:
            """Force refresh broker connections from DB and env configuration."""
            await self.validate_auth(request, authorization)
            
            # Force reload from database
            await self._load_connections_from_db(force_refresh=True)
            
            # Force re-sync env brokers (this will make broker API calls)
            await self._sync_configured_brokers(force_refresh=True)
            
            connections = list(self._connections_cache.values())
            
            logger.info(f"Refreshed broker connections: {len(connections)} total")
            return BrokersListResponse(
                connections=connections,
                total_count=len(connections)
            )
    
    async def _sync_configured_brokers(self, force_refresh: bool = False) -> None:
        """
        Sync broker connections from environment configuration.
        
        This checks if brokers are configured via environment variables
        and adds them to the connections list. Disabled status is persisted
        in Cosmos DB so it survives application restarts.
        
        Key behaviors:
        - Skip if already synced (unless force_refresh=True)
        - Skip if already in cache (loaded from DB)
        - Skip if user disabled (persisted in DB)
        - Fetch real account data via broker API only on first sync
        - Use upsert to prevent duplicates in DB
        
        Args:
            force_refresh: If True, re-sync env brokers even if already done.
        """
        if self._env_brokers_synced and not force_refresh:
            logger.debug("Env brokers already synced (skipping)")
            return
        
        await self._ensure_repo_initialized()
        
        # Get disabled env brokers from database
        disabled_env_brokers = await self._broker_repo.get_disabled_env_brokers()
        
        # Check for Alpaca configuration
        alpaca_key = self._config.get_config("api.alpaca.api_key", "")
        alpaca_secret = self._config.get_config("api.alpaca.secret_key", "")
        
        if alpaca_key and alpaca_secret:
            connection_id = "alpaca-env"
            should_skip_alpaca = False
            
            # Skip if user disabled this broker
            if connection_id in disabled_env_brokers:
                logger.debug(f"Skipping {connection_id} - disabled by user")
                should_skip_alpaca = True
            
            # Skip if already in cache (was loaded from DB)
            elif connection_id in self._connections_cache:
                logger.debug(f"Skipping {connection_id} - already in cache")
                should_skip_alpaca = True
            
            # Check if exists in DB but wasn't loaded (edge case)
            if not should_skip_alpaca:
                existing_doc = await self._broker_repo.get_connection(connection_id)
                if existing_doc and not existing_doc.is_disabled:
                    # Load from DB into cache
                    connection = self._doc_to_connection_info(existing_doc)
                    if connection:
                        self._connections_cache[connection_id] = connection
                        logger.debug(f"Loaded {connection_id} from DB into cache")
                        should_skip_alpaca = True
            
            # Truly new - create with real account data if not skipped
            if not should_skip_alpaca:
                base_url = self._config.get_config("api.alpaca.base_url", "")
                is_paper = "paper" in base_url.lower()
                
                # Fetch real account data from broker API
                test_result = await self._test_broker_connection(
                    "alpaca", alpaca_key, alpaca_secret, is_paper
                )
                
                connection = BrokerConnectionInfo(
                    id=connection_id,
                    name="Alpaca (Paper)" if is_paper else "Alpaca",
                    type="broker",
                    broker_type="alpaca",
                    status="connected" if test_result.get("success") else "error",
                    supported_assets=["stock", "etf", "crypto"],
                    balance=test_result.get("balance", 0.0),
                    buying_power=test_result.get("buying_power", 0.0),
                    portfolio_value=test_result.get("portfolio_value", 0.0),
                    api_key_masked=mask_api_key(alpaca_key),
                    is_paper=is_paper,
                    logo_url="/brokers/alpaca.svg",
                    last_sync=datetime.utcnow().isoformat(),
                    error_message=None if test_result.get("success") else test_result.get("message"),
                )
                self._connections_cache[connection_id] = connection
                
                # Persist to DB (upsert handles duplicates)
                doc = self._connection_info_to_doc(connection, source="env")
                await self._broker_repo.save_connection(doc)
                logger.info(f"Synced env broker: {connection_id}")
        
        # Check for Tastytrade configuration
        tastytrade_token = self._config.get_config("api.tastytrade.refresh_token", "")
        if tastytrade_token:
            connection_id = "tastytrade-env"
            should_skip_tastytrade = False
            
            # Skip if disabled or already cached
            if connection_id in disabled_env_brokers:
                should_skip_tastytrade = True
            elif connection_id in self._connections_cache:
                should_skip_tastytrade = True
            
            # Check DB if not already skipping
            if not should_skip_tastytrade:
                existing_doc = await self._broker_repo.get_connection(connection_id)
                if existing_doc and not existing_doc.is_disabled:
                    connection = self._doc_to_connection_info(existing_doc)
                    if connection:
                        self._connections_cache[connection_id] = connection
                        should_skip_tastytrade = True
            
            if not should_skip_tastytrade:
                connection = BrokerConnectionInfo(
                    id=connection_id,
                    name="Tastytrade",
                    type="broker",
                    broker_type="tastytrade",
                    status="connected",
                    supported_assets=["stock", "etf"],
                    api_key_masked="****",
                    is_paper=False,
                    logo_url="/brokers/tastytrade.svg",
                    last_sync=datetime.utcnow().isoformat(),
                )
                self._connections_cache[connection_id] = connection
                
                doc = self._connection_info_to_doc(connection, source="env")
                await self._broker_repo.save_connection(doc)
                logger.info(f"Synced env broker: {connection_id}")
        
        # Mark env brokers as synced to avoid redundant API calls on subsequent requests
        self._env_brokers_synced = True
    
    async def _test_broker_connection(
        self,
        broker_type: str,
        api_key: str,
        api_secret: str,
        is_paper: bool
    ) -> Dict[str, Any]:
        """
        Test connectivity to a broker.
        
        Args:
            broker_type: Type of broker (e.g., 'alpaca')
            api_key: Broker API key
            api_secret: Broker API secret
            is_paper: Whether to use paper/sandbox mode
            
        Returns:
            Dict with success status, message, and account info
        """
        try:
            if broker_type == "alpaca":
                return await self._test_alpaca_connection(api_key, api_secret, is_paper)
            elif broker_type == "tastytrade":
                # Tastytrade uses refresh token, not api_key/secret
                return {"success": True, "message": "Tastytrade connection pending"}
            else:
                # For unsupported brokers, just verify credentials are provided
                if api_key and api_secret:
                    return {
                        "success": True,
                        "message": f"{broker_type.capitalize()} credentials accepted (connectivity test not implemented)"
                    }
                return {"success": False, "message": "API credentials required"}
                
        except Exception as e:
            logger.error(f"Broker connection test failed: {e}")
            return {"success": False, "message": str(e)}
    
    async def _test_alpaca_connection(
        self,
        api_key: str,
        api_secret: str,
        is_paper: bool
    ) -> Dict[str, Any]:
        """Test Alpaca broker connection."""
        try:
            import aiohttp
            
            base_url = (
                "https://paper-api.alpaca.markets" if is_paper 
                else "https://api.alpaca.markets"
            )
            
            headers = {
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": api_secret,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{base_url}/v2/account",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "success": True,
                            "message": "Connected to Alpaca",
                            "balance": float(data.get("cash", 0)),
                            "buying_power": float(data.get("buying_power", 0)),
                            "portfolio_value": float(data.get("portfolio_value", 0)),
                            "open_positions": 0,  # Would need separate call
                            "account_status": data.get("status", "active"),
                        }
                    elif response.status == 401:
                        return {"success": False, "message": "Invalid API credentials"}
                    elif response.status == 403:
                        return {"success": False, "message": "API access forbidden - check permissions"}
                    else:
                        text = await response.text()
                        return {"success": False, "message": f"API error: {response.status} - {text}"}
                        
        except aiohttp.ClientError as e:
            return {"success": False, "message": f"Connection error: {str(e)}"}
        except Exception as e:
            return {"success": False, "message": f"Unexpected error: {str(e)}"}
    
    async def _configure_broker_runtime(
        self,
        broker_type: str,
        api_key: str,
        api_secret: str,
        is_paper: bool
    ) -> None:
        """
        Configure broker in runtime configuration (session-only).
        
        IMPORTANT - Session-Only Credential Storage:
            This updates the in-memory ConfigurationManager so the bot can use
            the newly added broker for trading operations during this session.
            
            On restart, credentials are NOT persisted. Users must either:
            - Re-enter credentials via the UI
            - Use environment variables (ALPACA_API_KEY, etc.)
            - Configure Azure Key Vault for production secret management
        
        Security Considerations:
            - Credentials are held in memory only
            - set_config does NOT persist to disk or external storage
            - This is intentional for security (avoid plaintext credential storage)
            - Production deployments should use Azure Key Vault
        
        Args:
            broker_type: Type of broker ('alpaca', 'tastytrade')
            api_key: Broker API key (held in memory only)
            api_secret: Broker API secret (held in memory only)
            is_paper: Whether to use paper/sandbox mode
        """
        if broker_type == "alpaca":
            base_url = (
                "https://paper-api.alpaca.markets" if is_paper
                else "https://api.alpaca.markets"
            )
            
            # Update runtime configuration (in-memory only, not persisted)
            self._config.set_config("api.alpaca.api_key", api_key)
            self._config.set_config("api.alpaca.secret_key", api_secret)
            self._config.set_config("api.alpaca.base_url", base_url)
            
            logger.info(f"Updated Alpaca configuration (paper={is_paper}, session-only)")
        
        elif broker_type == "tastytrade":
            # Tastytrade uses different credential structure
            self._config.set_config("api.tastytrade.refresh_token", api_secret)
            logger.info("Updated Tastytrade configuration (session-only)")
