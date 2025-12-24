"""
Broker Connection Pool - Shared Broker Connections Across Bots.

The BrokerConnectionPool efficiently manages broker API connections
across multiple bots, reducing connection overhead and API rate
limit consumption.

Key Features:
- Connection pooling per broker/exchange
- Automatic connection health checking
- Rate limit aware request queuing
- Connection reuse across bots

Without Pool:
    100 bots = 100 broker connections = 100x rate limit usage

With Pool:
    100 bots = 1-5 broker connections = 1-5x rate limit usage

Author: Trading Bot Team
Version: 1.0.0
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
import uuid

from src.core.logging_config import get_logger
from src.bot_engine.interfaces import IBrokerConnectionPool
from src.bot_engine.exceptions import BrokerConnectionError

if TYPE_CHECKING:
    from alpaca.trading.client import TradingClient

logger = get_logger(__name__)


class BrokerType(str, Enum):
    """Supported broker types."""
    
    ALPACA = "alpaca"
    TASTYTRADE = "tastytrade"
    PAPER = "paper"


class ConnectionState(str, Enum):
    """Connection states."""
    
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"


@dataclass
class BrokerConnection:
    """
    Represents a single broker connection.
    
    Tracks connection state, health, and usage statistics.
    """
    
    connection_id: str
    broker_type: BrokerType
    client: Any  # Actual broker client instance
    state: ConnectionState = ConnectionState.DISCONNECTED
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used_at: Optional[datetime] = None
    last_health_check: Optional[datetime] = None
    request_count: int = 0
    error_count: int = 0
    is_primary: bool = False


@dataclass
class RateLimitConfig:
    """Rate limiting configuration for a broker."""
    
    requests_per_minute: int = 200
    requests_per_second: int = 5
    burst_limit: int = 10
    cooldown_seconds: int = 60


@dataclass
class BrokerConfig:
    """Configuration for a broker connection."""
    
    broker_type: BrokerType
    api_key: str
    api_secret: str
    paper_trading: bool = True
    base_url: Optional[str] = None
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    max_connections: int = 3
    health_check_interval: int = 30


class BrokerConnectionPool(IBrokerConnectionPool):
    """
    Pool of shared broker connections.
    
    The BrokerConnectionPool manages connections to trading brokers
    (Alpaca, TastyTrade, etc.) and efficiently shares them across
    multiple bots. This reduces connection overhead and helps stay
    within API rate limits.
    
    Pool Architecture:
    - One pool per broker type (Alpaca, TastyTrade, etc.)
    - Multiple connections per pool for redundancy
    - Request queuing when rate limited
    - Automatic connection health monitoring
    
    Thread Safety:
    - All operations are async and run in single event loop
    - Connection access is serialized via async locks
    
    Usage:
        pool = BrokerConnectionPool()
        pool.configure_broker("alpaca", api_key, api_secret)
        await pool.start()
        
        # Get a connection for trading
        async with pool.acquire_connection("alpaca") as conn:
            await conn.place_order(order)
        
        await pool.stop()
    """
    
    def __init__(self):
        """Initialize the broker connection pool."""
        # Broker configurations: broker_type -> BrokerConfig
        self._configs: Dict[BrokerType, BrokerConfig] = {}
        
        # Connection pools: broker_type -> list of BrokerConnection
        self._pools: Dict[BrokerType, List[BrokerConnection]] = {}
        
        # Connection locks: broker_type -> asyncio.Lock
        self._locks: Dict[BrokerType, asyncio.Lock] = {}
        
        # Rate limiting state: broker_type -> request timestamps
        self._request_timestamps: Dict[BrokerType, List[datetime]] = {}
        
        # Engine state
        self._is_running = False
        self._health_check_task: Optional[asyncio.Task] = None
        
        logger.info("BrokerConnectionPool initialized")
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def is_running(self) -> bool:
        """Check if the pool is running."""
        return self._is_running
    
    @property
    def configured_brokers(self) -> List[str]:
        """Get list of configured broker types."""
        return [bt.value for bt in self._configs.keys()]
    
    @property
    def total_connections(self) -> int:
        """Get total number of active connections."""
        return sum(len(conns) for conns in self._pools.values())
    
    # =========================================================================
    # Configuration
    # =========================================================================
    
    def configure_broker(
        self,
        broker_type: str,
        api_key: str,
        api_secret: str,
        paper_trading: bool = True,
        base_url: Optional[str] = None,
        max_connections: int = 3,
        rate_limit: Optional[RateLimitConfig] = None,
    ) -> None:
        """
        Configure a broker for connection pooling.
        
        Args:
            broker_type: Type of broker ("alpaca", "tastytrade", "paper")
            api_key: Broker API key
            api_secret: Broker API secret
            paper_trading: Whether to use paper trading
            base_url: Optional custom API URL
            max_connections: Maximum connections to maintain
            rate_limit: Optional custom rate limit configuration
        """
        bt = BrokerType(broker_type)
        
        config = BrokerConfig(
            broker_type=bt,
            api_key=api_key,
            api_secret=api_secret,
            paper_trading=paper_trading,
            base_url=base_url,
            max_connections=max_connections,
            rate_limit=rate_limit or RateLimitConfig(),
        )
        
        self._configs[bt] = config
        self._pools[bt] = []
        self._locks[bt] = asyncio.Lock()
        self._request_timestamps[bt] = []
        
        logger.info(
            f"Configured broker {broker_type} "
            f"(paper={paper_trading}, max_conns={max_connections})"
        )
    
    # =========================================================================
    # Lifecycle
    # =========================================================================
    
    async def start(self) -> None:
        """
        Start the connection pool.
        
        Initializes connections for all configured brokers.
        """
        if self._is_running:
            logger.warning("BrokerConnectionPool is already running")
            return
        
        logger.info("Starting BrokerConnectionPool...")
        
        # Initialize primary connection for each broker
        for broker_type, config in self._configs.items():
            try:
                await self._create_connection(broker_type, is_primary=True)
            except Exception as e:
                logger.error(f"Failed to create connection for {broker_type}: {e}")
        
        # Start health check task
        self._health_check_task = asyncio.create_task(
            self._health_check_loop(),
            name="broker_pool_health_check"
        )
        
        self._is_running = True
        logger.info("BrokerConnectionPool started successfully")
    
    async def stop(self) -> None:
        """
        Stop the connection pool.
        
        Closes all connections gracefully.
        """
        if not self._is_running:
            logger.warning("BrokerConnectionPool is not running")
            return
        
        logger.info("Stopping BrokerConnectionPool...")
        
        # Cancel health check
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        
        # Close all connections
        for broker_type in list(self._pools.keys()):
            for conn in self._pools[broker_type]:
                await self._close_connection(conn)
            self._pools[broker_type].clear()
        
        self._is_running = False
        logger.info("BrokerConnectionPool stopped")
    
    # =========================================================================
    # Connection Management
    # =========================================================================
    
    async def get_connection(self, broker_type: str) -> Any:
        """
        Get a connection for the specified broker.
        
        Args:
            broker_type: Type of broker
            
        Returns:
            Broker client instance
            
        Raises:
            BrokerConnectionError: If no connection available
        """
        if not self._is_running:
            raise BrokerConnectionError("BrokerConnectionPool is not running")
        
        bt = BrokerType(broker_type)
        
        if bt not in self._pools:
            raise BrokerConnectionError(f"Broker {broker_type} is not configured")
        
        async with self._locks[bt]:
            # Find available connection
            for conn in self._pools[bt]:
                if conn.state == ConnectionState.CONNECTED:
                    conn.last_used_at = datetime.utcnow()
                    conn.request_count += 1
                    return conn.client
            
            # No available connection, try to create one
            config = self._configs[bt]
            if len(self._pools[bt]) < config.max_connections:
                conn = await self._create_connection(bt)
                if conn and conn.state == ConnectionState.CONNECTED:
                    conn.last_used_at = datetime.utcnow()
                    conn.request_count += 1
                    return conn.client
            
            raise BrokerConnectionError(
                f"No available connection for {broker_type}"
            )
    
    async def release_connection(self, broker_type: str, client: Any) -> None:
        """
        Release a connection back to the pool.
        
        Args:
            broker_type: Type of broker
            client: Client instance to release
        """
        # Connections are shared, nothing to release
        # This method exists for interface compatibility
        pass
    
    async def _create_connection(
        self, 
        broker_type: BrokerType,
        is_primary: bool = False
    ) -> Optional[BrokerConnection]:
        """
        Create a new broker connection.
        
        Args:
            broker_type: Type of broker
            is_primary: Whether this is the primary connection
            
        Returns:
            BrokerConnection or None if failed
        """
        config = self._configs.get(broker_type)
        if not config:
            return None
        
        conn_id = str(uuid.uuid4())[:8]
        
        conn = BrokerConnection(
            connection_id=conn_id,
            broker_type=broker_type,
            client=None,
            state=ConnectionState.CONNECTING,
            is_primary=is_primary,
        )
        
        try:
            # Create broker-specific client
            client = await self._create_broker_client(config)
            conn.client = client
            conn.state = ConnectionState.CONNECTED
            conn.last_health_check = datetime.utcnow()
            
            self._pools[broker_type].append(conn)
            
            logger.info(
                f"Created {broker_type.value} connection {conn_id} "
                f"(primary={is_primary})"
            )
            
            return conn
            
        except Exception as e:
            logger.error(f"Failed to create {broker_type.value} connection: {e}")
            conn.state = ConnectionState.ERROR
            conn.error_count += 1
            return None
    
    async def _create_broker_client(self, config: BrokerConfig) -> Any:
        """
        Create a broker-specific client instance.
        
        Args:
            config: Broker configuration
            
        Returns:
            Broker client instance
        """
        if config.broker_type == BrokerType.ALPACA:
            # Import here to avoid circular dependency
            from alpaca.trading.client import TradingClient
            
            client = TradingClient(
                api_key=config.api_key,
                secret_key=config.api_secret,
                paper=config.paper_trading,
            )
            return client
        
        elif config.broker_type == BrokerType.TASTYTRADE:
            # TODO: TastyTrade Integration
            # TastyTrade client implementation pending. Requires:
            # 1. TastyTrade API library (tastytrade-api or similar)
            # 2. OAuth2 authentication flow
            # 3. Account/session management
            # See: https://developer.tastytrade.com/
            # Tracking Issue: [Add GitHub issue link when created]
            raise NotImplementedError(
                "TastyTrade client not yet implemented. "
                "See broker_connection_pool.py for integration requirements."
            )
        
        elif config.broker_type == BrokerType.PAPER:
            # Return a mock/paper client for testing
            return PaperBrokerClient()
        
        else:
            raise BrokerConnectionError(
                f"Unsupported broker type: {config.broker_type}"
            )
    
    async def _close_connection(self, conn: BrokerConnection) -> None:
        """
        Close a broker connection.
        
        Args:
            conn: Connection to close
        """
        try:
            if hasattr(conn.client, 'close'):
                await conn.client.close()
            elif hasattr(conn.client, 'disconnect'):
                await conn.client.disconnect()
            
            conn.state = ConnectionState.DISCONNECTED
            logger.debug(f"Closed connection {conn.connection_id}")
            
        except Exception as e:
            logger.error(f"Error closing connection {conn.connection_id}: {e}")
    
    # =========================================================================
    # Health Checking
    # =========================================================================
    
    async def _health_check_loop(self) -> None:
        """
        Background task that periodically checks connection health.
        """
        while self._is_running:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                await self._check_all_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {e}")
    
    async def _check_all_connections(self) -> None:
        """Check health of all connections."""
        for broker_type, connections in self._pools.items():
            for conn in connections:
                await self._check_connection_health(conn)
    
    async def _check_connection_health(self, conn: BrokerConnection) -> bool:
        """
        Check if a connection is healthy.
        
        Args:
            conn: Connection to check
            
        Returns:
            True if healthy
        """
        try:
            if hasattr(conn.client, 'ping'):
                await conn.client.ping()
            elif hasattr(conn.client, 'get_account'):
                await conn.client.get_account()
            
            conn.last_health_check = datetime.utcnow()
            conn.state = ConnectionState.CONNECTED
            return True
            
        except Exception as e:
            logger.warning(f"Connection {conn.connection_id} health check failed: {e}")
            conn.state = ConnectionState.ERROR
            conn.error_count += 1
            return False
    
    async def check_health(self, broker_type: str) -> bool:
        """
        Check health of connections for a broker type.
        
        Args:
            broker_type: Type of broker
            
        Returns:
            True if at least one connection is healthy
        """
        bt = BrokerType(broker_type)
        
        if bt not in self._pools:
            return False
        
        for conn in self._pools[bt]:
            if await self._check_connection_health(conn):
                return True
        
        return False
    
    # =========================================================================
    # Rate Limiting
    # =========================================================================
    
    async def _check_rate_limit(self, broker_type: BrokerType) -> bool:
        """
        Check if we're within rate limits.
        
        Args:
            broker_type: Type of broker
            
        Returns:
            True if request is allowed
        """
        config = self._configs.get(broker_type)
        if not config:
            return False
        
        now = datetime.utcnow()
        timestamps = self._request_timestamps[broker_type]
        
        # Clean old timestamps
        cutoff = now - timedelta(minutes=1)
        timestamps[:] = [ts for ts in timestamps if ts > cutoff]
        
        # Check per-minute limit
        if len(timestamps) >= config.rate_limit.requests_per_minute:
            return False
        
        # Check per-second limit
        second_cutoff = now - timedelta(seconds=1)
        recent = sum(1 for ts in timestamps if ts > second_cutoff)
        if recent >= config.rate_limit.requests_per_second:
            return False
        
        # Record request
        timestamps.append(now)
        return True
    
    async def wait_for_rate_limit(self, broker_type: str) -> None:
        """
        Wait until rate limit allows a request.
        
        Args:
            broker_type: Type of broker
        """
        bt = BrokerType(broker_type)
        
        while not await self._check_rate_limit(bt):
            await asyncio.sleep(0.1)
    
    # =========================================================================
    # Statistics
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get pool statistics.
        
        Returns:
            Dictionary with pool statistics
        """
        stats = {
            "is_running": self._is_running,
            "configured_brokers": self.configured_brokers,
            "total_connections": self.total_connections,
            "brokers": {},
        }
        
        for broker_type, connections in self._pools.items():
            stats["brokers"][broker_type.value] = {
                "connection_count": len(connections),
                "connections": [
                    {
                        "id": conn.connection_id,
                        "state": conn.state.value,
                        "is_primary": conn.is_primary,
                        "request_count": conn.request_count,
                        "error_count": conn.error_count,
                        "last_used": conn.last_used_at.isoformat() if conn.last_used_at else None,
                    }
                    for conn in connections
                ],
            }
        
        return stats
    
    def get_connection_count(self, broker_type: str) -> int:
        """
        Get number of connections for a broker.
        
        Args:
            broker_type: Type of broker
            
        Returns:
            Number of connections
        """
        bt = BrokerType(broker_type)
        return len(self._pools.get(bt, []))
    
    def get_healthy_connection_count(self, broker_type: str) -> int:
        """
        Get number of healthy connections for a broker.
        
        Args:
            broker_type: Type of broker
            
        Returns:
            Number of healthy connections
        """
        bt = BrokerType(broker_type)
        return sum(
            1 for conn in self._pools.get(bt, [])
            if conn.state == ConnectionState.CONNECTED
        )


class PaperBrokerClient:
    """
    Mock broker client for paper trading/testing.
    
    Simulates broker operations without actual API calls.
    """
    
    def __init__(self):
        """Initialize paper broker client."""
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._positions: Dict[str, Dict[str, Any]] = {}
        self._balance = Decimal("100000.00")
    
    async def ping(self) -> bool:
        """Health check."""
        return True
    
    async def get_account(self) -> Dict[str, Any]:
        """Get account info."""
        return {
            "id": "paper_account",
            "status": "active",
            "balance": str(self._balance),
            "currency": "USD",
        }
    
    async def place_order(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        order_type: str = "market",
        **kwargs
    ) -> Dict[str, Any]:
        """Place an order."""
        order_id = str(uuid.uuid4())[:8]
        
        order = {
            "id": order_id,
            "symbol": symbol,
            "side": side,
            "qty": str(qty),
            "type": order_type,
            "status": "filled",
            "filled_qty": str(qty),
            "created_at": datetime.utcnow().isoformat(),
        }
        
        self._orders[order_id] = order
        return order
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get open positions."""
        return list(self._positions.values())
    
    async def close_position(self, symbol: str) -> Dict[str, Any]:
        """Close a position."""
        position = self._positions.pop(symbol, None)
        if position:
            return {"symbol": symbol, "status": "closed"}
        return {"symbol": symbol, "status": "not_found"}
