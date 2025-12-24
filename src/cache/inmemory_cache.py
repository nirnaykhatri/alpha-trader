"""
In-Memory Market Data Cache
Provides a lightweight caching layer without external dependencies (Redis, etc.).
Uses TTL-based expiration for price data freshness.
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from src.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class CacheEntry:
    """
    Represents a cached value with expiration tracking.
    
    Attributes:
        value: The cached value
        expires_at: Timestamp when this entry expires
        created_at: Timestamp when this entry was created
    """
    value: Any
    expires_at: datetime
    created_at: datetime
    
    @property
    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        return datetime.utcnow() > self.expires_at


class InMemoryCache:
    """
    Thread-safe in-memory cache with TTL support.
    
    Features:
    - Configurable TTL per key type
    - Automatic cleanup of expired entries
    - Statistics tracking
    - No external dependencies
    
    Example:
        cache = InMemoryCache(default_ttl_seconds=5)
        await cache.set("AAPL_price", 150.50)
        price = await cache.get("AAPL_price")  # Returns 150.50
        await asyncio.sleep(6)
        price = await cache.get("AAPL_price")  # Returns None (expired)
    """
    
    def __init__(
        self, 
        default_ttl_seconds: float = 5.0,
        price_ttl_seconds: float = 5.0,
        market_status_ttl_seconds: float = 60.0,
        max_entries: int = 10000,
        cleanup_interval_seconds: float = 60.0
    ):
        """
        Initialize the in-memory cache.
        
        Args:
            default_ttl_seconds: Default TTL for generic cache entries
            price_ttl_seconds: TTL for price data (shorter for freshness)
            market_status_ttl_seconds: TTL for market status (longer, changes rarely)
            max_entries: Maximum number of entries before forced cleanup
            cleanup_interval_seconds: How often to run automatic cleanup
        """
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
        
        self._default_ttl = default_ttl_seconds
        self._price_ttl = price_ttl_seconds
        self._market_status_ttl = market_status_ttl_seconds
        self._max_entries = max_entries
        self._cleanup_interval = cleanup_interval_seconds
        
        # Statistics tracking
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "expirations": 0,
            "evictions": 0
        }
        
        # Background cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._is_running = False
        
        logger.info(
            f"InMemoryCache initialized: price_ttl={price_ttl_seconds}s, "
            f"market_status_ttl={market_status_ttl_seconds}s, max_entries={max_entries}"
        )
    
    async def start(self) -> None:
        """Start the background cleanup task."""
        if self._is_running:
            return
        
        self._is_running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.debug("InMemoryCache cleanup task started")
    
    async def stop(self) -> None:
        """Stop the background cleanup task."""
        self._is_running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.debug("InMemoryCache cleanup task stopped")
    
    async def _cleanup_loop(self) -> None:
        """Background task to periodically clean up expired entries."""
        while self._is_running:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cache cleanup: {e}")
    
    async def _cleanup_expired(self) -> int:
        """
        Remove all expired entries from the cache.
        
        Returns:
            Number of entries removed
        """
        async with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items() 
                if entry.is_expired
            ]
            
            for key in expired_keys:
                del self._cache[key]
                self._stats["expirations"] += 1
            
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
            
            return len(expired_keys)
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get a value from the cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        async with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._stats["misses"] += 1
                return None
            
            if entry.is_expired:
                del self._cache[key]
                self._stats["misses"] += 1
                self._stats["expirations"] += 1
                return None
            
            self._stats["hits"] += 1
            return entry.value
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl_seconds: Optional[float] = None
    ) -> None:
        """
        Set a value in the cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Optional custom TTL (uses default if None)
        """
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        now = datetime.utcnow()
        
        entry = CacheEntry(
            value=value,
            expires_at=now + timedelta(seconds=ttl),
            created_at=now
        )
        
        async with self._lock:
            # Check if we need to evict entries
            if len(self._cache) >= self._max_entries:
                await self._evict_oldest_unlocked()
            
            self._cache[key] = entry
            self._stats["sets"] += 1
    
    async def _evict_oldest_unlocked(self) -> None:
        """
        Evict the oldest entries to make room for new ones.
        Must be called with lock held.
        """
        # First remove expired entries
        expired_keys = [
            key for key, entry in self._cache.items() 
            if entry.is_expired
        ]
        
        for key in expired_keys:
            del self._cache[key]
            self._stats["expirations"] += 1
        
        # If still at capacity, remove oldest entries
        while len(self._cache) >= self._max_entries:
            oldest_key = min(
                self._cache.keys(),
                key=lambda k: self._cache[k].created_at
            )
            del self._cache[oldest_key]
            self._stats["evictions"] += 1
    
    async def delete(self, key: str) -> bool:
        """
        Delete a key from the cache.
        
        Args:
            key: Cache key to delete
            
        Returns:
            True if key was deleted, False if not found
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    async def clear(self) -> None:
        """Clear all entries from the cache."""
        async with self._lock:
            self._cache.clear()
        logger.info("InMemoryCache cleared")
    
    # Convenience methods for common data types
    
    async def get_price(self, symbol: str) -> Optional[float]:
        """
        Get cached price for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Cached price or None if not found/expired
        """
        return await self.get(f"price:{symbol.upper()}")
    
    async def set_price(self, symbol: str, price: float) -> None:
        """
        Cache a price for a symbol.
        
        Args:
            symbol: Stock symbol
            price: Current price
        """
        await self.set(f"price:{symbol.upper()}", price, self._price_ttl)
    
    async def get_market_status(self) -> Optional[Dict[str, Any]]:
        """
        Get cached market status.
        
        Returns:
            Cached market status or None if not found/expired
        """
        return await self.get("market:status")
    
    async def set_market_status(self, status: Dict[str, Any]) -> None:
        """
        Cache market status.
        
        Args:
            status: Market status dictionary
        """
        await self.set("market:status", status, self._market_status_ttl)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache performance metrics
        """
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0.0
        
        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate_percent": round(hit_rate, 2),
            "sets": self._stats["sets"],
            "expirations": self._stats["expirations"],
            "evictions": self._stats["evictions"],
            "current_entries": len(self._cache),
            "max_entries": self._max_entries,
            "price_ttl_seconds": self._price_ttl,
            "market_status_ttl_seconds": self._market_status_ttl
        }
    
    def reset_stats(self) -> None:
        """Reset statistics counters."""
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "expirations": 0,
            "evictions": 0
        }
        logger.info("InMemoryCache statistics reset")
    
    def is_available(self) -> bool:
        """
        Check if cache is available.
        
        Returns:
            Always True for in-memory cache
        """
        return True


class InMemoryCachedMarketDataProvider:
    """
    Market data provider with automatic in-memory caching.
    
    Wraps an existing IMarketDataProvider with a transparent caching layer.
    No external dependencies required.
    
    Example:
        from src.cache.inmemory_cache import InMemoryCachedMarketDataProvider
        
        alpaca_provider = AlpacaMarketDataProvider(...)
        cached_provider = InMemoryCachedMarketDataProvider(alpaca_provider)
        
        # First call hits API and caches result
        price = await cached_provider.get_current_price("AAPL")
        
        # Second call within TTL returns cached value
        price = await cached_provider.get_current_price("AAPL")  # Cache hit!
    """
    
    def __init__(
        self,
        provider,  # IMarketDataProvider
        price_ttl_seconds: float = 5.0,
        market_status_ttl_seconds: float = 60.0
    ):
        """
        Initialize cached market data provider.
        
        Args:
            provider: Underlying market data provider
            price_ttl_seconds: Cache TTL for price data (default 5s)
            market_status_ttl_seconds: Cache TTL for market status (default 60s)
        """
        self._provider = provider
        self._cache = InMemoryCache(
            price_ttl_seconds=price_ttl_seconds,
            market_status_ttl_seconds=market_status_ttl_seconds
        )
        
        # Provider statistics
        self._api_calls = 0
        
        logger.info(
            f"InMemoryCachedMarketDataProvider initialized: "
            f"price_ttl={price_ttl_seconds}s"
        )
    
    async def start(self) -> None:
        """Start the cache cleanup background task."""
        await self._cache.start()
    
    async def stop(self) -> None:
        """Stop the cache cleanup background task."""
        await self._cache.stop()
    
    async def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current price with caching.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Current price or None if unavailable
        """
        # Try cache first
        cached_price = await self._cache.get_price(symbol)
        if cached_price is not None:
            logger.debug(f"Cache HIT: {symbol} = ${cached_price:.2f}")
            return cached_price
        
        # Fetch from API
        logger.debug(f"Cache MISS: {symbol}, fetching from API")
        self._api_calls += 1
        
        try:
            price = await self._provider.get_current_price(symbol)
            
            if price is not None:
                await self._cache.set_price(symbol, price)
                logger.debug(f"Cached price for {symbol}: ${price:.2f}")
            
            return price
            
        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
            return None
    
    async def get_historical_data(
        self, 
        symbol: str, 
        timeframe: str, 
        count: int
    ):
        """
        Get historical data (passthrough, no caching).
        
        Historical data is not cached as it's typically accessed once.
        """
        return await self._provider.get_historical_data(symbol, timeframe, count)
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get combined cache and API statistics.
        
        Returns:
            Dictionary with performance metrics
        """
        cache_stats = self._cache.get_stats()
        cache_stats["api_calls"] = self._api_calls
        return cache_stats
    
    async def clear_cache(self) -> None:
        """Clear all cached data."""
        await self._cache.clear()
    
    def reset_stats(self) -> None:
        """Reset all statistics."""
        self._cache.reset_stats()
        self._api_calls = 0
