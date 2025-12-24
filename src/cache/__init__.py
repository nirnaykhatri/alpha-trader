"""
Cache module for trading bot.
Provides caching layers for market data and other frequently accessed information.

Available Implementations:
- RedisCache: External Redis-based cache for distributed environments
- InMemoryCache: Lightweight in-memory cache with no dependencies
- CachedMarketDataProvider: Redis-backed market data cache
- InMemoryCachedMarketDataProvider: In-memory market data cache

Usage:
    # For local development (no Redis needed):
    from src.cache import InMemoryCachedMarketDataProvider
    cached_provider = InMemoryCachedMarketDataProvider(alpaca_provider)
    
    # For production (with Redis):
    from src.cache import CachedMarketDataProvider, RedisCache
    cache = RedisCache(config)
    cached_provider = CachedMarketDataProvider(alpaca_provider, cache)
"""

from src.cache.redis_cache import RedisCache, CacheConfig
from src.cache.cached_market_data import CachedMarketDataProvider
from src.cache.inmemory_cache import InMemoryCache, InMemoryCachedMarketDataProvider

__all__ = [
    'RedisCache', 
    'CacheConfig', 
    'CachedMarketDataProvider',
    'InMemoryCache',
    'InMemoryCachedMarketDataProvider'
]
