"""
Cached Market Data Provider
Wraps existing market data provider with Redis caching layer for improved performance.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from src.interfaces import IMarketDataProvider
from src.core.logging_config import get_logger
from src.cache.redis_cache import RedisCache, CacheConfig

logger = get_logger(__name__)


class CachedMarketDataProvider:
    """
    Market data provider with automatic caching.
    
    Features:
    - Transparent caching of price data (5s TTL)
    - Automatic fallback to direct API calls if cache unavailable
    - Cache statistics and monitoring
    - Configurable TTL per data type
    """
    
    def __init__(self, market_data_provider: IMarketDataProvider, cache: Optional[RedisCache] = None):
        """
        Initialize cached market data provider.
        
        Args:
            market_data_provider: Underlying market data provider (Alpaca, etc.)
            cache: Optional Redis cache instance (will create default if None)
        """
        self.provider = market_data_provider
        self.cache = cache
        
        # Statistics tracking
        self._stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "api_calls": 0,
            "cache_errors": 0
        }
    
    async def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current price with caching.
        
        Flow:
        1. Check cache for recent price (5s TTL)
        2. If found, return cached price (cache hit)
        3. If not found, fetch from API
        4. Cache the result for 5 seconds
        5. Return price
        
        Args:
            symbol: Stock symbol
        
        Returns:
            Current price or None if unavailable
        """
        self._stats["total_requests"] += 1
        
        # Try cache first if available
        if self.cache and self.cache.is_available():
            try:
                cached_price = await self.cache.get_price(symbol)
                
                if cached_price is not None:
                    self._stats["cache_hits"] += 1
                    logger.debug(f"Cache HIT: {symbol} = ${cached_price:.2f}")
                    return cached_price
                else:
                    self._stats["cache_misses"] += 1
                    logger.debug(f"Cache MISS: {symbol}")
                    
            except Exception as e:
                self._stats["cache_errors"] += 1
                logger.debug(f"Cache error for {symbol}: {e}")
        
        # Fetch from API
        try:
            self._stats["api_calls"] += 1
            price = await self.provider.get_current_price(symbol)
            
            # Cache the result if cache available
            if price is not None and self.cache and self.cache.is_available():
                try:
                    await self.cache.set_price(symbol, price)
                    logger.debug(f"Cached price for {symbol}: ${price:.2f}")
                except Exception as e:
                    logger.debug(f"Failed to cache price for {symbol}: {e}")
            
            return price
            
        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
            return None
    
    async def get_historical_data(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        """
        Get historical data (passthrough to provider, no caching for historical data).
        
        Note: Historical data is typically not cached due to:
        - Large data size
        - Infrequent access patterns
        - Data doesn't change (historical)
        """
        return await self.provider.get_historical_data(symbol, timeframe, start, end)
    
    async def get_market_status(self) -> Optional[Dict[str, Any]]:
        """
        Get market status with caching (1 minute TTL).
        
        Market status changes infrequently so longer TTL is appropriate.
        """
        self._stats["total_requests"] += 1
        
        # Try cache first
        if self.cache and self.cache.is_available():
            try:
                cached_status = await self.cache.get_market_status()
                
                if cached_status is not None:
                    self._stats["cache_hits"] += 1
                    logger.debug(f"Cache HIT: market status")
                    return cached_status
                else:
                    self._stats["cache_misses"] += 1
                    logger.debug(f"Cache MISS: market status")
                    
            except Exception as e:
                self._stats["cache_errors"] += 1
                logger.debug(f"Cache error for market status: {e}")
        
        # Fetch from API
        try:
            self._stats["api_calls"] += 1
            status = await self.provider.get_market_status()
            
            # Cache the result
            if status is not None and self.cache and self.cache.is_available():
                try:
                    await self.cache.set_market_status(status)
                    logger.debug(f"Cached market status")
                except Exception as e:
                    logger.debug(f"Failed to cache market status: {e}")
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to get market status: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get caching statistics.
        
        Returns:
            Dictionary with cache performance metrics
        """
        hit_rate = 0.0
        if self._stats["total_requests"] > 0:
            hit_rate = (self._stats["cache_hits"] / self._stats["total_requests"]) * 100
        
        return {
            "total_requests": self._stats["total_requests"],
            "cache_hits": self._stats["cache_hits"],
            "cache_misses": self._stats["cache_misses"],
            "api_calls": self._stats["api_calls"],
            "cache_errors": self._stats["cache_errors"],
            "hit_rate_percent": round(hit_rate, 2),
            "cache_available": self.cache.is_available() if self.cache else False
        }
    
    async def clear_cache(self):
        """Clear all cached data."""
        if self.cache:
            await self.cache.clear_all()
            logger.info("Market data cache cleared")
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get Redis cache statistics."""
        if self.cache:
            return await self.cache.get_stats()
        return {"available": False}
    
    def reset_stats(self):
        """Reset statistics counters."""
        self._stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "api_calls": 0,
            "cache_errors": 0
        }
        logger.info("Cache statistics reset")
