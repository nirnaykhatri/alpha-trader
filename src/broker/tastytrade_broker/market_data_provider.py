"""
Tastytrade Market Data Provider.

Provides real-time and on-demand market data from Tastytrade's data feed.
Supports both regular and extended hours (pre-market and after-hours) data.

This implementation uses:
1. DXLinkStreamer for real-time streaming quotes (when subscribed)
2. get_market_data for one-time price fetches

Extended hours support:
- Pre-market: 4:00 AM - 9:30 AM ET
- Regular hours: 9:30 AM - 4:00 PM ET
- After-hours: 4:00 PM - 8:00 PM ET
"""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
import pytz

from tastytrade import DXLinkStreamer
from tastytrade.dxfeed import Quote
from tastytrade.market_data import get_market_data
from tastytrade.order import InstrumentType

from src.broker.interfaces import IBrokerMarketDataProvider
from src.broker.tastytrade_broker.session_manager import TastytradeSessionManager
from src.interfaces import IAsyncContextManager
from src.exceptions import MarketDataException
from src.core.logging_config import get_logger
from src.utils import run_blocking

logger = get_logger(__name__)


class TastytradeMarketDataProvider(IBrokerMarketDataProvider, IAsyncContextManager):
    """
    Market Data Provider using Tastytrade's data feed.
    
    Provides current prices and market data for symbols traded through Tastytrade.
    Supports both regular hours and extended hours (pre-market and after-hours) data.
    
    The provider uses Tastytrade's DXFeed-based streaming infrastructure which provides:
    - Real-time quotes during market hours
    - Extended hours data from pre-market (4 AM ET) through after-hours (8 PM ET)
    
    Attributes:
        _session_manager: Manages Tastytrade API sessions.
        _streamer: DXLinkStreamer for real-time quote streaming (optional).
        _price_cache: Cache for recent price data with timestamps.
        _cache_duration: How long to cache prices before refresh.
        
    Thread Safety:
        This class is designed for use with asyncio and is not thread-safe.
        All methods should be called from the same event loop.
    """
    
    def __init__(
        self, 
        session_manager: TastytradeSessionManager,
        cache_duration_seconds: int = 30,
        use_streaming: bool = False
    ):
        """
        Initialize the Tastytrade market data provider.
        
        Args:
            session_manager: Manager for Tastytrade API sessions.
            cache_duration_seconds: Duration to cache prices (default 30s).
            use_streaming: Whether to use real-time streaming (default False).
                          When True, maintains a persistent websocket connection.
                          When False, uses on-demand REST API calls.
        """
        self._session_manager = session_manager
        self._cache_duration = timedelta(seconds=cache_duration_seconds)
        self._use_streaming = use_streaming
        
        # Price cache: symbol -> {price, timestamp, source}
        self._price_cache: Dict[str, Dict] = {}
        
        # Streaming components (initialized on start if use_streaming=True)
        self._streamer: Optional[DXLinkStreamer] = None
        self._streaming_quotes: Dict[str, Quote] = {}
        self._streaming_task: Optional[asyncio.Task] = None
        self._subscribed_symbols: set = set()
        
        # Reconnection settings
        self._max_reconnect_attempts = 5
        self._reconnect_delay_base = 2  # Exponential backoff base in seconds
        self._reconnect_attempt = 0
        self._is_reconnecting = False
        
        # Market timezone
        self._market_tz = pytz.timezone('America/New_York')
        
        # Extended hours warning tracking
        self._extended_hours_warning_shown = False
        
        logger.info(
            f"TastytradeMarketDataProvider initialized - "
            f"Streaming: {use_streaming}, Cache: {cache_duration_seconds}s"
        )

    async def start(self) -> None:
        """
        Start the market data provider.
        
        If streaming is enabled, establishes a websocket connection
        to Tastytrade's DXFeed data provider.
        """
        logger.info("Starting TastytradeMarketDataProvider")
        
        if self._use_streaming:
            await self._start_streaming()
        
        logger.info("TastytradeMarketDataProvider started")

    async def stop(self) -> None:
        """
        Stop the market data provider and cleanup resources.
        
        Closes any active streaming connections and clears caches.
        """
        logger.info("Stopping TastytradeMarketDataProvider")
        
        if self._streaming_task:
            self._streaming_task.cancel()
            try:
                await self._streaming_task
            except asyncio.CancelledError:
                pass
            self._streaming_task = None
        
        if self._streamer:
            try:
                await self._streamer.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing streamer: {e}")
            self._streamer = None
        
        self._price_cache.clear()
        self._streaming_quotes.clear()
        self._subscribed_symbols.clear()
        
        logger.info("TastytradeMarketDataProvider stopped")

    async def get_current_price(self, symbol: str) -> float:
        """
        Get the current price for a symbol from Tastytrade.
        
        Uses multiple data sources in order of priority:
        1. Active streaming quote (if streaming enabled and subscribed)
        2. Cached price (if fresh)
        3. On-demand API request (get_market_data)
        
        Supports both regular hours and extended hours trading.
        
        Args:
            symbol: Trading symbol (e.g., 'AAPL', 'SPY').
            
        Returns:
            Current market price (mid-point of bid/ask, or last trade).
            
        Raises:
            MarketDataException: If price data is unavailable.
        """
        try:
            logger.debug(f"🔍 Fetching Tastytrade price for {symbol}")
            
            # Priority 1: Check streaming quote
            if self._use_streaming and symbol in self._streaming_quotes:
                quote = self._streaming_quotes[symbol]
                price = self._extract_price_from_quote(quote)
                if price:
                    logger.debug(f"📡 Using streaming quote for {symbol}: ${price:.4f}")
                    return price
            
            # Priority 2: Check cache
            cached = self._get_cached_price(symbol)
            if cached:
                logger.debug(f"📋 Using cached price for {symbol}: ${cached:.4f}")
                return cached
            
            # Priority 3: Fetch from API
            price, age = await self._fetch_price_from_api(symbol)
            
            if price is None:
                raise MarketDataException(
                    f"Unable to fetch price for {symbol} from Tastytrade"
                )
            
            # Validate price is not zero (indicates invalid data)
            if price == 0:
                raise MarketDataException(
                    f"Received zero price for {symbol} from Tastytrade - likely invalid data"
                )
            
            # Cache the result
            self._cache_price(symbol, price, "api")
            
            # Log with market status context
            market_status = self._get_market_status()
            stale_warning = self._get_staleness_warning(age, market_status)
            
            logger.info(
                f"💰 Tastytrade price: {symbol} = ${price:.4f} "
                f"(age: {age:.0f}s) [{market_status['status']}]{stale_warning}"
            )
            
            return price
            
        except MarketDataException:
            raise
        except Exception as e:
            logger.error(f"Error fetching Tastytrade price for {symbol}: {e}")
            raise MarketDataException(f"Failed to fetch price for {symbol}: {e}")

    async def get_historical_data(
        self, 
        symbol: str, 
        timeframe: str, 
        count: int
    ) -> List[Dict[str, Any]]:
        """
        Get historical data for a symbol.
        
        Note: Tastytrade's API has limited historical data capabilities.
        For comprehensive historical data, consider using Alpaca or another
        dedicated historical data provider.
        
        Args:
            symbol: Trading symbol.
            timeframe: Timeframe (e.g., '1Min', '5Min', '1Day').
            count: Number of bars to retrieve.
            
        Returns:
            List of historical bars (limited functionality).
            
        Raises:
            MarketDataException: If historical data is unavailable.
        """
        logger.warning(
            f"Tastytrade has limited historical data support. "
            f"Returning empty list for {symbol}. "
            f"Consider using Alpaca for historical data."
        )
        # Tastytrade doesn't provide traditional OHLCV historical bars
        # The DXFeed provides Trade and Candle events, but these are streaming
        # For now, return empty list and log a warning
        return []

    async def subscribe(self, symbols: List[str]) -> None:
        """
        Subscribe to real-time quotes for symbols.
        
        Only relevant when streaming mode is enabled.
        
        Args:
            symbols: List of symbols to subscribe to.
        """
        if not self._use_streaming:
            logger.debug("Streaming disabled, skipping subscribe")
            return
            
        if not self._streamer:
            await self._start_streaming()
        
        new_symbols = [s for s in symbols if s not in self._subscribed_symbols]
        if new_symbols:
            logger.info(f"Subscribing to Tastytrade quotes: {new_symbols}")
            await self._streamer.subscribe(Quote, new_symbols)
            self._subscribed_symbols.update(new_symbols)

    async def unsubscribe(self, symbols: List[str]) -> None:
        """
        Unsubscribe from real-time quotes for symbols.
        
        Args:
            symbols: List of symbols to unsubscribe from.
        """
        if not self._use_streaming or not self._streamer:
            return
            
        symbols_to_remove = [s for s in symbols if s in self._subscribed_symbols]
        if symbols_to_remove:
            logger.info(f"Unsubscribing from Tastytrade quotes: {symbols_to_remove}")
            await self._streamer.unsubscribe(Quote, symbols_to_remove)
            for s in symbols_to_remove:
                self._subscribed_symbols.discard(s)
                self._streaming_quotes.pop(s, None)

    # =========================================================================
    # Private Methods
    # =========================================================================

    async def _start_streaming(self) -> None:
        """
        Initialize and start the DXLink streamer.
        
        Creates a persistent websocket connection to Tastytrade's
        DXFeed data provider for real-time quote streaming.
        """
        try:
            session = await self._session_manager.get_session()
            self._streamer = await DXLinkStreamer(session).__aenter__()
            
            # Start background task to listen for quotes
            self._streaming_task = asyncio.create_task(self._listen_for_quotes())
            
            logger.info("Tastytrade DXLink streamer started")
        except Exception as e:
            logger.error(f"Failed to start Tastytrade streamer: {e}")
            self._streamer = None

    async def _listen_for_quotes(self) -> None:
        """
        Background task to continuously listen for streaming quotes.
        
        Updates the streaming_quotes dictionary with the latest
        quote data as it arrives. Implements automatic reconnection
        with exponential backoff on connection failures.
        """
        while True:
            try:
                if self._streamer is None:
                    logger.warning("Streamer not initialized, exiting quote listener")
                    break
                    
                async for quote in self._streamer.listen(Quote):
                    # Reset reconnection counter on successful data
                    self._reconnect_attempt = 0
                    self._streaming_quotes[quote.event_symbol] = quote
                    logger.debug(
                        f"📊 Stream update: {quote.event_symbol} "
                        f"bid=${quote.bid_price:.4f} ask=${quote.ask_price:.4f}"
                    )
            except asyncio.CancelledError:
                logger.debug("Quote listener cancelled")
                break
            except Exception as e:
                should_continue = await self._handle_stream_error(e)
                if not should_continue:
                    break

    async def _handle_stream_error(self, error: Exception) -> bool:
        """
        Handle streaming errors with exponential backoff reconnection.
        
        Implements a structured error handling flow:
        1. Log the error
        2. Check if reconnection attempts remain
        3. Calculate backoff delay
        4. Attempt reconnection
        
        Args:
            error: The exception that occurred during streaming.
            
        Returns:
            True if the listener should continue (retry), False if it should exit.
        """
        logger.error(f"Error in quote listener: {error}")
        
        # Check if we have reconnection attempts remaining
        if self._reconnect_attempt >= self._max_reconnect_attempts:
            logger.error(
                f"Max reconnection attempts ({self._max_reconnect_attempts}) "
                "reached. Streaming disabled. Falling back to REST API."
            )
            self._streamer = None
            return False
        
        # Calculate exponential backoff delay
        self._reconnect_attempt += 1
        delay = self._reconnect_delay_base ** self._reconnect_attempt
        
        logger.warning(
            f"Attempting streamer reconnection {self._reconnect_attempt}/"
            f"{self._max_reconnect_attempts} in {delay}s..."
        )
        await asyncio.sleep(delay)
        
        # Attempt reconnection
        try:
            await self._reconnect_streamer()
            return True
        except Exception as reconnect_error:
            logger.error(f"Reconnection failed: {reconnect_error}")
            return True  # Continue loop to retry

    async def _reconnect_streamer(self) -> None:
        """
        Reconnect the DXLink streamer after a connection failure.
        
        Closes the existing streamer, creates a new one, and
        re-subscribes to all previously subscribed symbols.
        """
        if self._is_reconnecting:
            return
            
        self._is_reconnecting = True
        try:
            # Close existing streamer
            if self._streamer:
                try:
                    await self._streamer.__aexit__(None, None, None)
                except Exception as e:
                    logger.debug(f"Error closing old streamer: {e}")
                self._streamer = None
            
            # Create new streamer
            session = await self._session_manager.get_session()
            self._streamer = await DXLinkStreamer(session).__aenter__()
            
            # Re-subscribe to all symbols
            if self._subscribed_symbols:
                symbols_list = list(self._subscribed_symbols)
                logger.info(f"Re-subscribing to {len(symbols_list)} symbols after reconnection")
                await self._streamer.subscribe(Quote, symbols_list)
            
            logger.info("Streamer reconnection successful")
        finally:
            self._is_reconnecting = False

    async def _fetch_price_from_api(self, symbol: str) -> Tuple[Optional[float], float]:
        """
        Fetch current price using Tastytrade's market data API.
        
        Uses the get_market_data endpoint which provides current
        bid/ask/mark prices including extended hours data.
        
        Args:
            symbol: Trading symbol to fetch.
            
        Returns:
            Tuple of (price, age_in_seconds) or (None, 0) if unavailable.
        """
        try:
            session = await self._session_manager.get_session()
            
            # Use run_blocking since get_market_data is synchronous
            market_data = await run_blocking(
                get_market_data, 
                session, 
                symbol, 
                InstrumentType.EQUITY
            )
            
            if not market_data:
                logger.warning(f"No market data returned for {symbol}")
                return None, 0
            
            # Extract price from market data
            # Priority: mark > mid of bid/ask > last
            price = None
            
            if hasattr(market_data, 'mark') and market_data.mark:
                price = float(market_data.mark)
            elif hasattr(market_data, 'bid') and hasattr(market_data, 'ask'):
                bid = float(market_data.bid) if market_data.bid else None
                ask = float(market_data.ask) if market_data.ask else None
                if bid and ask:
                    price = (bid + ask) / 2
                elif ask:
                    price = ask
                elif bid:
                    price = bid
            
            if price is None and hasattr(market_data, 'last') and market_data.last:
                price = float(market_data.last)
            
            if price is None and hasattr(market_data, 'close') and market_data.close:
                price = float(market_data.close)
            
            # Calculate age from updated_at if available
            age_seconds = 0.0
            if hasattr(market_data, 'updated_at') and market_data.updated_at:
                now_utc = datetime.now(timezone.utc)
                updated_at = market_data.updated_at
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                age_seconds = (now_utc - updated_at).total_seconds()
            
            logger.debug(
                f"📊 Tastytrade market data for {symbol}: "
                f"mark={getattr(market_data, 'mark', None)}, "
                f"bid={getattr(market_data, 'bid', None)}, "
                f"ask={getattr(market_data, 'ask', None)}"
            )
            
            return price, age_seconds
            
        except Exception as e:
            logger.error(f"Error fetching market data from Tastytrade for {symbol}: {e}")
            return None, 0

    def _extract_price_from_quote(self, quote: Quote) -> Optional[float]:
        """
        Extract a usable price from a DXFeed Quote object.
        
        Args:
            quote: DXFeed Quote object.
            
        Returns:
            Mid-point of bid/ask, or None if unavailable.
        """
        if not quote:
            return None
            
        bid = quote.bid_price if hasattr(quote, 'bid_price') else None
        ask = quote.ask_price if hasattr(quote, 'ask_price') else None
        
        if bid and ask and bid > 0 and ask > 0:
            return (bid + ask) / 2
        elif ask and ask > 0:
            return ask
        elif bid and bid > 0:
            return bid
            
        return None

    def _get_cached_price(self, symbol: str) -> Optional[float]:
        """
        Get cached price if still valid.
        
        Args:
            symbol: Trading symbol.
            
        Returns:
            Cached price if fresh, None otherwise.
        """
        cache_key = f"price_{symbol}"
        if cache_key in self._price_cache:
            entry = self._price_cache[cache_key]
            if datetime.now(timezone.utc) - entry['timestamp'] < self._cache_duration:
                return entry['price']
        return None

    def _cache_price(self, symbol: str, price: float, source: str) -> None:
        """
        Cache a price with timestamp.
        
        Args:
            symbol: Trading symbol.
            price: Price to cache.
            source: Source of the price (e.g., 'api', 'stream').
        """
        cache_key = f"price_{symbol}"
        self._price_cache[cache_key] = {
            'price': price,
            'timestamp': datetime.now(timezone.utc),
            'source': source
        }

    def _get_market_status(self) -> Dict[str, Any]:
        """
        Get current market status for intelligent data handling.
        
        Returns:
            Dictionary with market status information.
        """
        now_ny = datetime.now(self._market_tz)
        
        # Define market hours (9:30 AM - 4:00 PM ET)
        market_open = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
        
        # Define extended hours
        pre_market_start = now_ny.replace(hour=4, minute=0, second=0, microsecond=0)
        after_hours_end = now_ny.replace(hour=20, minute=0, second=0, microsecond=0)
        
        # Determine market status
        is_weekend = now_ny.weekday() >= 5
        is_regular_hours = not is_weekend and market_open <= now_ny < market_close
        is_pre_market = not is_weekend and pre_market_start <= now_ny < market_open
        is_post_market = not is_weekend and market_close <= now_ny < after_hours_end
        is_extended_hours = is_pre_market or is_post_market
        is_closed = is_weekend or not (is_regular_hours or is_extended_hours)
        
        if is_regular_hours:
            status = "REGULAR_HOURS"
        elif is_pre_market:
            status = "PRE_MARKET"
        elif is_post_market:
            status = "POST_MARKET"
        else:
            status = "CLOSED"
        
        return {
            'status': status,
            'is_regular_hours': is_regular_hours,
            'is_pre_market': is_pre_market,
            'is_post_market': is_post_market,
            'is_extended_hours': is_extended_hours,
            'is_closed': is_closed,
            'is_weekend': is_weekend,
            'current_time_ny': now_ny
        }

    def _get_staleness_warning(
        self, 
        price_age_seconds: Optional[float], 
        market_status: Dict[str, Any]
    ) -> str:
        """
        Generate staleness warning based on market status and data age.
        
        Args:
            price_age_seconds: Age of the price data in seconds.
            market_status: Current market status dictionary.
            
        Returns:
            Warning string to append to log messages.
        """
        if not price_age_seconds or price_age_seconds <= 0:
            return " ✅ (very fresh)"
        
        age_hours = price_age_seconds / 3600
        
        if market_status['is_regular_hours']:
            if price_age_seconds > 300:
                return " ⚠️ STALE DATA DURING MARKET HOURS!"
            elif price_age_seconds > 60:
                return " (note: slightly stale)"
            else:
                return " ✅ (very fresh)"
        elif market_status['is_extended_hours']:
            if price_age_seconds > 1800:
                return f" 🟡 EXTENDED HOURS DATA ({age_hours:.1f}hr old)"
            elif price_age_seconds > 300:
                return " ✅ (good extended hours data)"
            else:
                return " 🌟 (very fresh extended hours!)"
        elif market_status['is_closed']:
            if age_hours > 24:
                return f" (market closed, {age_hours:.1f}hr old)"
            elif age_hours > 8:
                return f" (market closed, {age_hours:.0f}hr old)"
            else:
                return " (normal - market closed)"
        
        return ""
