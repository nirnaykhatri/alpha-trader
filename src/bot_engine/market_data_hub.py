"""
Market Data Hub - Shared Market Data Streaming with Symbol Deduplication.

The MarketDataHub provides efficient market data distribution to multiple
bots by maintaining a single data stream per symbol, regardless of how
many bots are trading that symbol.

Key Features:
- Symbol-based stream deduplication (1 stream per symbol, not per bot)
- Automatic subscriber management
- Price callback distribution to all subscribed bots
- Memory efficient (~5KB per symbol stream)

Without MarketDataHub:
    100 bots trading BTCUSD = 100 WebSocket connections = 100x bandwidth

With MarketDataHub:
    100 bots trading BTCUSD = 1 WebSocket connection = 1x bandwidth

Author: Trading Bot Team
Version: 1.0.0
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set
import uuid

from src.core.logging_config import get_logger
from src.bot_engine.interfaces import IMarketDataHub, MarketDataSubscription
from src.bot_engine.exceptions import MarketDataError

logger = get_logger(__name__)


@dataclass
class SymbolStream:
    """
    Represents a single market data stream for a symbol.
    
    Manages WebSocket connection (or polling) and distributes
    price updates to all subscribers.
    """
    
    symbol: str
    subscribers: Set[str] = field(default_factory=set)
    last_price: Optional[Decimal] = None
    last_update: Optional[datetime] = None
    is_active: bool = False
    stream_task: Optional[asyncio.Task] = None
    callbacks: Dict[str, Callable] = field(default_factory=dict)


class MarketDataHub(IMarketDataHub):
    """
    Central hub for market data distribution with symbol deduplication.
    
    The MarketDataHub maintains one data stream per unique symbol and
    efficiently distributes price updates to all bots subscribed to
    that symbol. This dramatically reduces bandwidth and connection
    overhead when multiple bots trade the same symbol.
    
    Stream Lifecycle:
    1. First bot subscribes to BTCUSD → Stream created
    2. More bots subscribe to BTCUSD → Added to existing stream
    3. Bots unsubscribe → Removed from stream
    4. Last bot unsubscribes → Stream closed
    
    Thread Safety:
    - All operations are async and run in single event loop
    - Subscriber modifications are atomic within coroutines
    
    Usage:
        hub = MarketDataHub(market_data_provider)
        await hub.start()
        
        await hub.subscribe("BTCUSD", "bot_123", price_callback)
        # ... bot receives price updates via callback ...
        await hub.unsubscribe("BTCUSD", "bot_123")
        
        await hub.stop()
    """
    
    def __init__(
        self, 
        price_update_callback: Optional[Callable[[str, Decimal], None]] = None,
        poll_interval_seconds: float = 1.0,
    ):
        """
        Initialize the market data hub.
        
        Args:
            price_update_callback: Optional global callback for all price updates
            poll_interval_seconds: How often to poll for price updates
        """
        self._global_callback = price_update_callback
        self._poll_interval = poll_interval_seconds
        
        # Symbol streams: symbol -> SymbolStream
        self._streams: Dict[str, SymbolStream] = {}
        
        # Quick lookup: bot_id -> set of subscribed symbols
        self._bot_subscriptions: Dict[str, Set[str]] = {}
        
        # Engine state
        self._is_running = False
        self._shutdown_event = asyncio.Event()
        
        logger.info("MarketDataHub initialized")
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def is_running(self) -> bool:
        """Check if the hub is running."""
        return self._is_running
    
    @property
    def active_stream_count(self) -> int:
        """Get the number of active symbol streams."""
        return sum(1 for s in self._streams.values() if s.is_active)
    
    @property
    def total_subscribers(self) -> int:
        """Get the total number of subscriptions across all symbols."""
        return sum(len(s.subscribers) for s in self._streams.values())
    
    # =========================================================================
    # Lifecycle
    # =========================================================================
    
    async def start(self) -> None:
        """
        Start the market data hub.
        
        Initializes any existing streams and begins price polling/streaming.
        """
        if self._is_running:
            logger.warning("MarketDataHub is already running")
            return
        
        logger.info("Starting MarketDataHub...")
        self._is_running = True
        self._shutdown_event.clear()
        
        logger.info("MarketDataHub started successfully")
    
    async def stop(self) -> None:
        """
        Stop the market data hub.
        
        Closes all active streams and cleans up resources.
        """
        if not self._is_running:
            logger.warning("MarketDataHub is not running")
            return
        
        logger.info("Stopping MarketDataHub...")
        
        self._shutdown_event.set()
        
        # Stop all active streams
        for symbol, stream in list(self._streams.items()):
            if stream.stream_task and not stream.stream_task.done():
                stream.stream_task.cancel()
                try:
                    await stream.stream_task
                except asyncio.CancelledError:
                    pass
            stream.is_active = False
        
        self._streams.clear()
        self._bot_subscriptions.clear()
        self._is_running = False
        
        logger.info("MarketDataHub stopped")
    
    # =========================================================================
    # Subscription Management
    # =========================================================================
    
    async def subscribe(
        self, 
        symbol: str, 
        bot_id: str, 
        callback: Optional[Callable[[str, Decimal], None]] = None
    ) -> None:
        """
        Subscribe a bot to market data for a symbol.
        
        If this is the first subscriber for the symbol, a new stream
        is created. Otherwise, the bot is added to the existing stream.
        
        Args:
            symbol: Trading symbol (e.g., "BTCUSD")
            bot_id: Bot identifier for subscription tracking
            callback: Optional callback for price updates
        """
        if not self._is_running:
            raise MarketDataError("MarketDataHub is not running")
        
        logger.debug(f"Bot {bot_id} subscribing to {symbol}")
        
        # Get or create stream
        if symbol not in self._streams:
            self._streams[symbol] = SymbolStream(symbol=symbol)
            logger.info(f"Created new stream for {symbol}")
            # Start the stream
            await self._start_stream(symbol)
        
        stream = self._streams[symbol]
        
        # Add subscriber
        stream.subscribers.add(bot_id)
        if callback:
            stream.callbacks[bot_id] = callback
        
        # Track bot subscriptions
        if bot_id not in self._bot_subscriptions:
            self._bot_subscriptions[bot_id] = set()
        self._bot_subscriptions[bot_id].add(symbol)
        
        logger.debug(
            f"Bot {bot_id} subscribed to {symbol} "
            f"(total subscribers: {len(stream.subscribers)})"
        )
    
    async def unsubscribe(self, symbol: str, bot_id: str) -> None:
        """
        Unsubscribe a bot from market data for a symbol.
        
        If this is the last subscriber, the stream is closed.
        
        Args:
            symbol: Trading symbol
            bot_id: Bot identifier
        """
        if symbol not in self._streams:
            logger.warning(f"No stream exists for {symbol}")
            return
        
        stream = self._streams[symbol]
        
        # Remove subscriber
        stream.subscribers.discard(bot_id)
        stream.callbacks.pop(bot_id, None)
        
        # Update bot subscriptions
        if bot_id in self._bot_subscriptions:
            self._bot_subscriptions[bot_id].discard(symbol)
            if not self._bot_subscriptions[bot_id]:
                del self._bot_subscriptions[bot_id]
        
        logger.debug(
            f"Bot {bot_id} unsubscribed from {symbol} "
            f"(remaining subscribers: {len(stream.subscribers)})"
        )
        
        # Close stream if no subscribers
        if not stream.subscribers:
            await self._stop_stream(symbol)
            del self._streams[symbol]
            logger.info(f"Closed stream for {symbol} (no subscribers)")
    
    async def unsubscribe_bot(self, bot_id: str) -> None:
        """
        Unsubscribe a bot from all symbols.
        
        Args:
            bot_id: Bot identifier
        """
        symbols = list(self._bot_subscriptions.get(bot_id, set()))
        for symbol in symbols:
            await self.unsubscribe(symbol, bot_id)
    
    # =========================================================================
    # Price Data Access
    # =========================================================================
    
    def get_current_price(self, symbol: str) -> Optional[Decimal]:
        """
        Get the current price for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Current price or None if not available
        """
        stream = self._streams.get(symbol)
        if stream:
            return stream.last_price
        return None
    
    def get_all_prices(self) -> Dict[str, Decimal]:
        """
        Get current prices for all tracked symbols.
        
        Returns:
            Dictionary mapping symbol to current price
        """
        return {
            symbol: stream.last_price
            for symbol, stream in self._streams.items()
            if stream.last_price is not None
        }
    
    def get_subscription_info(self, symbol: str) -> Optional[MarketDataSubscription]:
        """
        Get subscription information for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            MarketDataSubscription or None if not subscribed
        """
        stream = self._streams.get(symbol)
        if not stream:
            return None
        
        return MarketDataSubscription(
            symbol=symbol,
            subscribers=stream.subscribers.copy(),
            last_price=stream.last_price,
            last_update=stream.last_update,
            is_streaming=stream.is_active,
        )
    
    def get_all_subscriptions(self) -> List[MarketDataSubscription]:
        """
        Get subscription information for all symbols.
        
        Returns:
            List of MarketDataSubscription for all active symbols
        """
        return [
            self.get_subscription_info(symbol)
            for symbol in self._streams.keys()
        ]
    
    def get_bot_symbols(self, bot_id: str) -> Set[str]:
        """
        Get all symbols a bot is subscribed to.
        
        Args:
            bot_id: Bot identifier
            
        Returns:
            Set of subscribed symbols
        """
        return self._bot_subscriptions.get(bot_id, set()).copy()
    
    # =========================================================================
    # Stream Management
    # =========================================================================
    
    async def _start_stream(self, symbol: str) -> None:
        """
        Start a market data stream for a symbol.
        
        Args:
            symbol: Trading symbol
        """
        stream = self._streams.get(symbol)
        if not stream:
            return
        
        if stream.is_active:
            return
        
        stream.is_active = True
        stream.stream_task = asyncio.create_task(
            self._stream_loop(symbol),
            name=f"market_data_{symbol}"
        )
        
        logger.debug(f"Started stream for {symbol}")
    
    async def _stop_stream(self, symbol: str) -> None:
        """
        Stop a market data stream for a symbol.
        
        Args:
            symbol: Trading symbol
        """
        stream = self._streams.get(symbol)
        if not stream:
            return
        
        stream.is_active = False
        
        if stream.stream_task and not stream.stream_task.done():
            stream.stream_task.cancel()
            try:
                await stream.stream_task
            except asyncio.CancelledError:
                pass
        
        logger.debug(f"Stopped stream for {symbol}")
    
    async def _stream_loop(self, symbol: str) -> None:
        """
        Main loop for a symbol's market data stream.
        
        Polls for price updates and distributes to subscribers.
        In production, this would connect to a WebSocket or use
        streaming market data APIs.
        
        Args:
            symbol: Trading symbol
        """
        stream = self._streams.get(symbol)
        if not stream:
            return
        
        logger.debug(f"Stream loop started for {symbol}")
        
        while stream.is_active and not self._shutdown_event.is_set():
            try:
                # Get latest price (placeholder - implement actual data fetching)
                price = await self._fetch_price(symbol)
                
                if price is not None:
                    await self._distribute_price(symbol, price)
                
                # Wait for next poll or shutdown
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self._poll_interval
                    )
                    break  # Shutdown signaled
                except asyncio.TimeoutError:
                    continue  # Continue polling
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Stream loop error for {symbol}: {e}")
                await asyncio.sleep(1.0)  # Brief pause on error
        
        logger.debug(f"Stream loop ended for {symbol}")
    
    async def _fetch_price(self, symbol: str) -> Optional[Decimal]:
        """
        Fetch the current price for a symbol.
        
        This is a placeholder that should be connected to actual
        market data providers (Alpaca, TastyTrade, etc.).
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Current price or None if unavailable
        """
        # TODO: Implement actual price fetching from market data provider
        # For now, return None (prices will be injected via update_price)
        return None
    
    async def _distribute_price(self, symbol: str, price: Decimal) -> None:
        """
        Distribute a price update to all subscribers.
        
        Args:
            symbol: Trading symbol
            price: New price value
        """
        stream = self._streams.get(symbol)
        if not stream:
            return
        
        # Update stream state
        stream.last_price = price
        stream.last_update = datetime.utcnow()
        
        # Call global callback
        if self._global_callback:
            try:
                self._global_callback(symbol, price)
            except Exception as e:
                logger.error(f"Global callback error for {symbol}: {e}")
        
        # Call subscriber callbacks
        for bot_id, callback in stream.callbacks.items():
            try:
                # Handle both sync and async callbacks
                if asyncio.iscoroutinefunction(callback):
                    await callback(symbol, price)
                else:
                    callback(symbol, price)
            except Exception as e:
                logger.error(
                    f"Subscriber callback error for bot {bot_id} on {symbol}: {e}"
                )
    
    # =========================================================================
    # Manual Price Updates
    # =========================================================================
    
    async def update_price(self, symbol: str, price: Decimal) -> None:
        """
        Manually update the price for a symbol.
        
        Used for injecting prices from external sources like webhooks.
        
        Args:
            symbol: Trading symbol
            price: New price value
        """
        if symbol in self._streams:
            await self._distribute_price(symbol, price)
        else:
            # Create temporary entry for tracking
            logger.debug(f"Price update for unsubscribed symbol {symbol}: {price}")
    
    async def update_prices(self, prices: Dict[str, Decimal]) -> None:
        """
        Update prices for multiple symbols.
        
        Args:
            prices: Dictionary mapping symbol to price
        """
        for symbol, price in prices.items():
            await self.update_price(symbol, price)
    
    # =========================================================================
    # Statistics
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get hub statistics.
        
        Returns:
            Dictionary with hub statistics
        """
        return {
            "is_running": self._is_running,
            "active_streams": self.active_stream_count,
            "total_streams": len(self._streams),
            "total_subscribers": self.total_subscribers,
            "unique_bots": len(self._bot_subscriptions),
            "poll_interval_seconds": self._poll_interval,
            "streams": {
                symbol: {
                    "subscribers": len(stream.subscribers),
                    "last_price": str(stream.last_price) if stream.last_price else None,
                    "last_update": stream.last_update.isoformat() if stream.last_update else None,
                    "is_active": stream.is_active,
                }
                for symbol, stream in self._streams.items()
            }
        }
