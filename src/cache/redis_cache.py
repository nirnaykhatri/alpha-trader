"""
Redis Cache Manager for Trading Bot
Provides high-performance caching with automatic fallback for market data and status information.
"""

import asyncio
import json
from typing import Optional, Any, Dict
from dataclasses import dataclass
from datetime import timedelta
from src.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CacheConfig:
    """Configuration for Redis cache."""
    enabled: bool = True
    host: str = 'localhost'
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    max_connections: int = 10
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    decode_responses: bool = True
    
    # TTL configurations (in seconds)
    price_ttl: int = 5  # Market price data expires after 5 seconds
    market_status_ttl: int = 60  # Market status expires after 1 minute
    position_ttl: int = 10  # Position data expires after 10 seconds
    default_ttl: int = 300  # Default 5 minutes


class RedisCache:
    """
    Redis-based cache manager with automatic failover and connection pooling.
    
    Features:
    - Connection pooling for high concurrency
    - Automatic fallback to direct API calls if Redis unavailable
    - Type-safe serialization/deserialization
    - TTL-based expiration for different data types
    - Health checking and auto-reconnection
    """
    
    def __init__(self, config: CacheConfig):
        """Initialize Redis cache manager."""
        self.config = config
        self._redis = None
        self._pool = None
        self._available = False
        self._lock = asyncio.Lock()
        
        # Initialize connection if enabled
        if self.config.enabled:
            asyncio.create_task(self._initialize_connection())
    
    async def _initialize_connection(self):
        """Initialize Redis connection pool."""
        try:
            import aioredis
            
            # Create connection pool
            self._pool = aioredis.ConnectionPool(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                max_connections=self.config.max_connections,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                decode_responses=self.config.decode_responses
            )
            
            # Create Redis client
            self._redis = aioredis.Redis(connection_pool=self._pool)
            
            # Test connection
            await self._redis.ping()
            self._available = True
            
            logger.info("✅ Redis cache initialized successfully")
            logger.info(f"   Host: {self.config.host}:{self.config.port}")
            logger.info(f"   Max Connections: {self.config.max_connections}")
            logger.info(f"   Price TTL: {self.config.price_ttl}s")
            
        except ImportError:
            logger.warning("⚠️  aioredis not installed, caching disabled")
            logger.warning("   Install with: pip install aioredis")
            self.config.enabled = False
            self._available = False
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Redis cache: {e}")
            logger.warning("   Caching disabled, will use direct API calls")
            self.config.enabled = False
            self._available = False
    
    async def _check_health(self) -> bool:
        """Check Redis connection health."""
        if not self.config.enabled or not self._redis:
            return False
        
        try:
            await self._redis.ping()
            if not self._available:
                self._available = True
                logger.info("✅ Redis connection restored")
            return True
        except Exception as e:
            if self._available:
                logger.warning(f"⚠️  Redis connection lost: {e}")
                self._available = False
            return False
    
    def _serialize_value(self, value: Any) -> str:
        """Serialize value to JSON string."""
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, str):
            return value
        else:
            # For complex objects, try JSON serialization
            try:
                return json.dumps(value, default=str)
            except Exception:
                return str(value)
    
    def _deserialize_value(self, value: str, value_type: type = str) -> Any:
        """Deserialize value from JSON string."""
        if value is None:
            return None
        
        try:
            if value_type == dict or value_type == list:
                return json.loads(value)
            elif value_type == int:
                return int(value)
            elif value_type == float:
                return float(value)
            else:
                return value
        except Exception as e:
            logger.debug(f"Deserialization failed: {e}, returning raw value")
            return value
    
    async def get(self, key: str, value_type: type = str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            value_type: Expected type for deserialization (dict, list, int, float, str)
        
        Returns:
            Cached value or None if not found or Redis unavailable
        """
        if not await self._check_health():
            return None
        
        try:
            value = await self._redis.get(key)
            if value is None:
                return None
            
            return self._deserialize_value(value, value_type)
            
        except Exception as e:
            logger.debug(f"Cache get failed for key '{key}': {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in cache with optional TTL.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (None = use default TTL)
        
        Returns:
            True if successful, False otherwise
        """
        if not await self._check_health():
            return False
        
        try:
            serialized = self._serialize_value(value)
            
            if ttl is not None:
                await self._redis.setex(key, ttl, serialized)
            else:
                await self._redis.setex(key, self.config.default_ttl, serialized)
            
            return True
            
        except Exception as e:
            logger.debug(f"Cache set failed for key '{key}': {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete value from cache."""
        if not await self._check_health():
            return False
        
        try:
            await self._redis.delete(key)
            return True
        except Exception as e:
            logger.debug(f"Cache delete failed for key '{key}': {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        if not await self._check_health():
            return False
        
        try:
            return await self._redis.exists(key) > 0
        except Exception as e:
            logger.debug(f"Cache exists check failed for key '{key}': {e}")
            return False
    
    async def get_price(self, symbol: str) -> Optional[float]:
        """
        Get cached price for symbol.
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Cached price or None if not found
        """
        key = f"price:{symbol}"
        return await self.get(key, value_type=float)
    
    async def set_price(self, symbol: str, price: float) -> bool:
        """
        Cache price for symbol with price_ttl.
        
        Args:
            symbol: Stock symbol
            price: Current price
        
        Returns:
            True if successful
        """
        key = f"price:{symbol}"
        return await self.set(key, price, ttl=self.config.price_ttl)
    
    async def get_market_status(self) -> Optional[Dict[str, Any]]:
        """Get cached market status."""
        return await self.get("market:status", value_type=dict)
    
    async def set_market_status(self, status: Dict[str, Any]) -> bool:
        """Cache market status with market_status_ttl."""
        return await self.set("market:status", status, ttl=self.config.market_status_ttl)
    
    async def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get cached position data."""
        key = f"position:{symbol}"
        return await self.get(key, value_type=dict)
    
    async def set_position(self, symbol: str, position_data: Dict[str, Any]) -> bool:
        """Cache position data with position_ttl."""
        key = f"position:{symbol}"
        return await self.set(key, position_data, ttl=self.config.position_ttl)
    
    async def clear_all(self) -> bool:
        """Clear all cached data (use with caution)."""
        if not await self._check_health():
            return False
        
        try:
            await self._redis.flushdb()
            logger.warning("⚠️  All cache data cleared")
            return True
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not await self._check_health():
            return {
                "available": False,
                "enabled": self.config.enabled
            }
        
        try:
            info = await self._redis.info()
            
            return {
                "available": True,
                "enabled": self.config.enabled,
                "used_memory": info.get('used_memory_human', 'N/A'),
                "connected_clients": info.get('connected_clients', 0),
                "total_keys": await self._redis.dbsize(),
                "uptime_seconds": info.get('uptime_in_seconds', 0),
                "hits": info.get('keyspace_hits', 0),
                "misses": info.get('keyspace_misses', 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get('keyspace_hits', 0),
                    info.get('keyspace_misses', 0)
                )
            }
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"available": False, "error": str(e)}
    
    def _calculate_hit_rate(self, hits: int, misses: int) -> float:
        """Calculate cache hit rate percentage."""
        total = hits + misses
        if total == 0:
            return 0.0
        return (hits / total) * 100
    
    async def close(self):
        """Close Redis connection and cleanup resources."""
        if self._redis:
            try:
                await self._redis.close()
                logger.info("Redis connection closed")
            except Exception as e:
                logger.error(f"Error closing Redis connection: {e}")
        
        if self._pool:
            try:
                await self._pool.disconnect()
                logger.info("Redis pool disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting Redis pool: {e}")
    
    def is_available(self) -> bool:
        """Check if cache is currently available."""
        return self._available and self.config.enabled
