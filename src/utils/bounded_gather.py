"""
Bounded Concurrency Utilities

Provides utilities for executing concurrent async operations with
configurable limits to prevent overwhelming external APIs.

Key Features:
- Semaphore-based concurrency limiting
- Batch processing with configurable parallelism
- Exception handling for partial failures
- Timeout support

Usage:
    from src.utils.bounded_gather import bounded_gather, fetch_prices_bounded

    # Generic bounded gather
    results = await bounded_gather(
        [fetch_price(symbol) for symbol in symbols],
        max_concurrency=5
    )
    
    # Specialized price fetching
    prices = await fetch_prices_bounded(
        symbols=["AAPL", "TSLA", "MSFT"],
        fetch_func=market_data.get_current_price,
        max_concurrency=3
    )

Thread-Safety: All functions are stateless and safe for concurrent use.
"""

import asyncio
import logging
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    TypeVar,
    Union,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def bounded_gather(
    coros: List[Awaitable[T]],
    max_concurrency: int = 5,
    return_exceptions: bool = False,
) -> List[Union[T, Exception]]:
    """
    Execute async coroutines with bounded concurrency.
    
    Unlike asyncio.gather(), this limits how many coroutines run
    simultaneously, preventing API rate limiting.
    
    Args:
        coros: List of coroutines to execute
        max_concurrency: Maximum number of concurrent operations
        return_exceptions: If True, exceptions are returned in results.
                          If False, first exception is raised.
    
    Returns:
        List of results in the same order as input coroutines.
        If return_exceptions=True, exceptions are included in results.
    
    Raises:
        Exception: First exception encountered if return_exceptions=False
    
    Example:
        prices = await bounded_gather(
            [get_price(s) for s in symbols],
            max_concurrency=3
        )
    """
    if not coros:
        return []
    
    semaphore = asyncio.Semaphore(max_concurrency)
    results: List[Optional[Union[T, Exception]]] = [None] * len(coros)
    
    async def bounded_task(index: int, coro: Awaitable[T]) -> None:
        async with semaphore:
            try:
                results[index] = await coro
            except Exception as e:
                if return_exceptions:
                    results[index] = e
                else:
                    raise
    
    tasks = [
        asyncio.create_task(bounded_task(i, coro))
        for i, coro in enumerate(coros)
    ]
    
    try:
        await asyncio.gather(*tasks, return_exceptions=return_exceptions)
    except Exception:
        # Cancel remaining tasks on failure
        for task in tasks:
            if not task.done():
                task.cancel()
        raise
    
    return results  # type: ignore


async def fetch_prices_bounded(
    symbols: List[str],
    fetch_func: Callable[[str], Awaitable[float]],
    max_concurrency: int = 5,
    timeout_per_symbol: Optional[float] = None,
) -> Dict[str, Optional[float]]:
    """
    Fetch market prices for multiple symbols with bounded concurrency.
    
    This is a specialized wrapper for common market data fetching patterns.
    
    Args:
        symbols: List of symbols to fetch prices for
        fetch_func: Async function that takes symbol and returns price
        max_concurrency: Maximum concurrent API calls
        timeout_per_symbol: Optional timeout per symbol in seconds
    
    Returns:
        Dictionary mapping symbol to price (None if fetch failed)
    
    Example:
        prices = await fetch_prices_bounded(
            symbols=["AAPL", "TSLA", "MSFT"],
            fetch_func=market_data.get_current_price,
            max_concurrency=3
        )
        for symbol, price in prices.items():
            print(f"{symbol}: ${price}")
    """
    results: Dict[str, Optional[float]] = {}
    
    if not symbols:
        return results
    
    semaphore = asyncio.Semaphore(max_concurrency)
    
    async def fetch_with_limit(symbol: str) -> Tuple[str, Optional[float]]:
        async with semaphore:
            try:
                if timeout_per_symbol:
                    price = await asyncio.wait_for(
                        fetch_func(symbol),
                        timeout=timeout_per_symbol
                    )
                else:
                    price = await fetch_func(symbol)
                return symbol, price
            except asyncio.TimeoutError:
                logger.warning(f"Timeout fetching price for {symbol}")
                return symbol, None
            except Exception as e:
                logger.warning(f"Error fetching price for {symbol}: {e}")
                return symbol, None
    
    tasks = [fetch_with_limit(symbol) for symbol in symbols]
    completed = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in completed:
        if isinstance(result, tuple):
            symbol, price = result
            results[symbol] = price
        # Exceptions are already handled in fetch_with_limit
    
    return results


class BoundedFetcher:
    """
    Reusable bounded concurrency fetcher for repeated operations.
    
    This class maintains a semaphore that can be reused across multiple
    fetch operations, providing consistent concurrency control.
    
    Usage:
        fetcher = BoundedFetcher(max_concurrency=5)
        
        # In monitoring loop:
        prices = await fetcher.fetch_all(symbols, price_func)
    """
    
    def __init__(self, max_concurrency: int = 5) -> None:
        """
        Initialize the bounded fetcher.
        
        Args:
            max_concurrency: Maximum concurrent operations
        """
        self._max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)
    
    @property
    def max_concurrency(self) -> int:
        """Get the maximum concurrency limit."""
        return self._max_concurrency
    
    async def fetch_all(
        self,
        symbols: List[str],
        fetch_func: Callable[[str], Awaitable[T]],
        timeout: Optional[float] = None,
    ) -> Dict[str, Optional[T]]:
        """
        Fetch data for multiple symbols with bounded concurrency.
        
        Args:
            symbols: List of symbols to fetch
            fetch_func: Async function that takes symbol and returns data
            timeout: Optional timeout per fetch in seconds
        
        Returns:
            Dictionary mapping symbol to fetched data (None on failure)
        """
        results: Dict[str, Optional[T]] = {}
        
        async def fetch_one(symbol: str) -> Tuple[str, Optional[T]]:
            async with self._semaphore:
                try:
                    if timeout:
                        data = await asyncio.wait_for(
                            fetch_func(symbol),
                            timeout=timeout
                        )
                    else:
                        data = await fetch_func(symbol)
                    return symbol, data
                except Exception as e:
                    logger.debug(f"Fetch failed for {symbol}: {e}")
                    return symbol, None
        
        tasks = [fetch_one(symbol) for symbol in symbols]
        completed = await asyncio.gather(*tasks)
        
        for symbol, data in completed:
            results[symbol] = data
        
        return results
