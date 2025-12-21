"""
Enhanced Market Data Provider using Alpaca API for both regular and extended hours.
Provides current and historical market data for trading decisions.
"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta, timezone
import pytz
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest, 
    StockLatestQuoteRequest, 
    StockSnapshotRequest,
    StockLatestTradeRequest,
    StockLatestBarRequest
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from src.interfaces import IMarketDataProvider, IConfigurationManager, IAsyncContextManager
from src.exceptions import MarketDataException
from src.core.logging_config import get_logger
from src.utils import run_blocking
import time

logger = get_logger(__name__)


class AlpacaMarketDataProvider(IMarketDataProvider, IAsyncContextManager):
    """
    Enhanced Market Data Provider using Alpaca API.
    Provides both regular and extended hours market data with multiple fallback methods.
    """
    
    def __init__(self, config: IConfigurationManager):
        """
        Initialize enhanced market data provider.
        
        Args:
            config: Configuration manager instance
        """
        self._config = config
        
        # Initialize Alpaca data client
        api_key = config.get_config("api.alpaca.api_key")
        secret_key = config.get_config("api.alpaca.secret_key")
        
        if not api_key or not secret_key:
            raise MarketDataException("Alpaca API credentials not configured")
        
        self._client = StockHistoricalDataClient(api_key, secret_key)
        self._price_cache: Dict[str, Dict] = {}
        
        # Enhanced Alpaca configuration with data plan awareness
        self._cache_duration = timedelta(seconds=config.get_config("data.alpaca.cache_duration", 30))
        self._use_snapshot = config.get_config("data.alpaca.use_snapshot", True)
        self._extended_hours = config.get_config("data.alpaca.extended_hours", True)
        self._fallback_to_bars = config.get_config("data.alpaca.fallback_to_bars", True)
        self._snapshot_timeout = config.get_config("data.alpaca.snapshot_timeout", 10)
        self._quote_timeout = config.get_config("data.alpaca.quote_timeout", 10)
        self._bars_timeout = config.get_config("data.alpaca.bars_timeout", 15)
        self._max_retries = config.get_config("data.alpaca.max_retries", 3)
        
        # Extended hours data limitations (IEX-only on free tier)
        self._extended_hours_warning_shown = False
        
        # Market session configuration
        self._market_tz = pytz.timezone('America/New_York')
        
        logger.info(f"Enhanced AlpacaMarketDataProvider initialized - Snapshot: {self._use_snapshot}, Extended Hours: {self._extended_hours}")
        
        # Warn about extended hours limitations on free tier
        if self._extended_hours:
            logger.warning("📊 Extended Hours Data: Free tier limited to IEX exchange only - coverage may be incomplete")
            logger.warning("📊 For full extended hours data from all exchanges, upgrade to SIP data plan")

    async def start(self) -> None:
        """Start the market data provider (IAsyncContextManager implementation)."""
        logger.info("AlpacaMarketDataProvider started")

    async def stop(self) -> None:
        """Stop the market data provider (IAsyncContextManager implementation)."""
        await self.close()

    async def get_current_price(self, symbol: str) -> float:
        """
        Get the most recent available price for a symbol using enhanced Alpaca APIs.
        Prioritizes by DATA FRESHNESS rather than API method priority.
        Handles both market hours and extended hours with multiple data sources.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Most recent available price (from freshest data source)
            
        Raises:
            MarketDataException: If price data is unavailable
        """
        try:
            logger.debug(f"🔍 Fetching current price for {symbol} (freshness-prioritized)")
            
            # Check cache first
            cached_price = self._check_price_cache(symbol)
            if cached_price:
                return cached_price
            
            # Get market status for intelligent data handling
            market_status = self._get_market_status()
            
            # Collect price data from all sources
            price_candidates = await self._collect_price_candidates(symbol, market_status)
            
            if not price_candidates:
                raise MarketDataException(f"Unable to fetch current price for {symbol} from any Alpaca source")
            
            # Select best candidate based on priority and freshness
            best_candidate = self._select_best_candidate(price_candidates)
            
            # Cache and return the selected price
            return self._cache_and_return_price(symbol, best_candidate)
            
        except MarketDataException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching price for {symbol}: {str(e)}")
            raise MarketDataException(f"Failed to fetch price for {symbol}: {str(e)}")
    
    def _check_price_cache(self, symbol: str) -> Optional[float]:
        """
        Check if a cached price exists for the symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Cached price if available and fresh, None otherwise
        """
        cache_key = f"price_{symbol}"
        cached_price = self._get_cached_price(cache_key)
        if cached_price:
            logger.debug(f"📋 Using cached price for {symbol}: ${cached_price:.4f}")
            return cached_price
        return None
    
    async def _collect_price_candidates(self, symbol: str, market_status: Dict) -> List[Dict]:
        """
        Collect price data from all available sources.
        
        Args:
            symbol: Trading symbol
            market_status: Current market status information
            
        Returns:
            List of price candidates with metadata
        """
        logger.debug(f"📊 Collecting data from all sources for freshness comparison...")
        price_candidates = []
        
        # Collect from Snapshot API (PRIORITY 1 - Best for market hours)
        if self._use_snapshot:
            candidate = await self._collect_snapshot_data(symbol)
            if candidate:
                price_candidates.append(candidate)
        
        # Collect from Latest Trade API (PRIORITY 2 - Most recent execution)
        candidate = await self._collect_trade_data(symbol)
        if candidate:
            price_candidates.append(candidate)
        
        # Collect from Latest Quote API (PRIORITY 3 - Bid/Ask data)
        candidate = await self._collect_quote_data(symbol)
        if candidate:
            price_candidates.append(candidate)
        
        # Collect from Bar APIs (PRIORITY 4 & 5 - Bar data)
        if self._fallback_to_bars:
            bar_candidates = await self._collect_bar_data(symbol, market_status)
            price_candidates.extend(bar_candidates)
        
        return price_candidates
    
    async def _collect_snapshot_data(self, symbol: str) -> Optional[Dict]:
        """Collect data from Snapshot API."""
        try:
            logger.debug(f"📸 Collecting SNAPSHOT data for {symbol}")
            price, age = await self._get_snapshot_price(symbol)
            if price and age is not None:
                logger.debug(f"📸 Snapshot: ${price:.4f} (age: {age:.0f}s)")
                return {
                    'price': price,
                    'age': age,
                    'source': 'snapshot_api',
                    'priority': 1
                }
        except Exception as e:
            logger.debug(f"❌ SNAPSHOT collection failed: {e}")
        return None
    
    async def _collect_trade_data(self, symbol: str) -> Optional[Dict]:
        """Collect data from Latest Trade API."""
        try:
            logger.debug(f"🔄 Collecting TRADE data for {symbol}")
            price, age = await self._get_latest_trade_price(symbol)
            if price and age is not None:
                logger.debug(f"🔄 Trade: ${price:.4f} (age: {age:.0f}s)")
                return {
                    'price': price,
                    'age': age,
                    'source': 'latest_trade',
                    'priority': 2
                }
        except Exception as e:
            logger.debug(f"❌ TRADE collection failed: {e}")
        return None
    
    async def _collect_quote_data(self, symbol: str) -> Optional[Dict]:
        """Collect data from Latest Quote API."""
        try:
            logger.debug(f"📡 Collecting QUOTE data for {symbol}")
            price, age = await self._get_latest_quote_price(symbol)
            if price and age is not None:
                logger.debug(f"📡 Quote: ${price:.4f} (age: {age:.0f}s)")
                return {
                    'price': price,
                    'age': age,
                    'source': 'latest_quote',
                    'priority': 3
                }
        except Exception as e:
            logger.debug(f"❌ QUOTE collection failed: {e}")
        return None
    
    async def _collect_bar_data(self, symbol: str, market_status: Dict) -> List[Dict]:
        """Collect data from Bar APIs."""
        bar_candidates = []
        try:
            logger.debug(f"📊 Collecting LATEST BAR data for {symbol}")
            price, age = await self._get_latest_bar_price(symbol)
            if price and age is not None:
                # During extended hours, bars are more valuable - reduce effective age
                effective_age = age * 0.8 if market_status['is_extended_hours'] else age
                age_note = f" (effective: {effective_age:.0f}s)" if market_status['is_extended_hours'] else ""
                logger.debug(f"📊 Latest Bar: ${price:.4f} (age: {age:.0f}s{age_note})")
                bar_candidates.append({
                    'price': price,
                    'age': effective_age,
                    'source': 'latest_bar',
                    'priority': 4,
                    'actual_age': age
                })
            else:
                # Fallback to Recent Bars API
                logger.debug(f"📊 Latest bar failed, trying RECENT BARS for {symbol}")
                price, age = await self._get_recent_bars_price(symbol)
                if price and age is not None:
                    effective_age = age * 0.8 if market_status['is_extended_hours'] else age
                    age_note = f" (effective: {effective_age:.0f}s)" if market_status['is_extended_hours'] else ""
                    logger.debug(f"📊 Recent Bars: ${price:.4f} (age: {age:.0f}s{age_note})")
                    bar_candidates.append({
                        'price': price,
                        'age': effective_age,
                        'source': 'recent_bars',
                        'priority': 5,
                        'actual_age': age
                    })
        except Exception as e:
            logger.debug(f"❌ BARS collection failed: {e}")
        return bar_candidates
    
    def _select_best_candidate(self, price_candidates: List[Dict]) -> Dict:
        """
        Select the best price candidate based on priority and freshness.
        
        Args:
            price_candidates: List of price candidates with metadata
            
        Returns:
            Best candidate dictionary
        """
        logger.debug(f"🎯 Selecting from {len(price_candidates)} candidates using priority + freshness...")
        
        # Group candidates by priority level
        priority_groups = {}
        for candidate in price_candidates:
            priority = candidate['priority']
            if priority not in priority_groups:
                priority_groups[priority] = []
            priority_groups[priority].append(candidate)
        
        # Find the best priority level
        best_priority = min(priority_groups.keys())
        best_priority_candidates = priority_groups[best_priority]
        
        # Among candidates at the best priority level, select the freshest
        if len(best_priority_candidates) == 1:
            best_candidate = best_priority_candidates[0]
        else:
            best_candidate = min(best_priority_candidates, key=lambda x: x['age'])
        
        # Apply freshness override logic if needed
        freshest_overall = min(price_candidates, key=lambda x: x['age'])
        best_candidate = self._apply_freshness_override(best_candidate, freshest_overall, price_candidates)
        
        return best_candidate
    
    def _apply_freshness_override(self, best_candidate: Dict, freshest_overall: Dict, all_candidates: List[Dict]) -> Dict:
        """
        Apply aggressive freshness override logic if fresher data is available.
        
        Args:
            best_candidate: Current best candidate based on priority
            freshest_overall: Freshest candidate across all sources
            all_candidates: All available candidates
            
        Returns:
            Final selected candidate (may override best_candidate)
        """
        if freshest_overall == best_candidate or freshest_overall['priority'] > 4:
            return best_candidate
        
        # Calculate age difference (handle negative ages)
        freshest_age = max(0, freshest_overall['age'])
        best_age = max(0, best_candidate['age'])
        age_difference = best_age - freshest_age
        
        # Determine if we should override based on staleness
        should_override, override_reason = self._should_override_for_freshness(
            best_age, freshest_age, age_difference
        )
        
        if should_override:
            logger.info(
                f"⚡ FRESHNESS OVERRIDE: {override_reason} - "
                f"Switching from {best_candidate['source']} ({best_age:.0f}s) "
                f"to {freshest_overall['source']} ({freshest_age:.0f}s)"
            )
            return freshest_overall
        
        return best_candidate
    
    def _should_override_for_freshness(self, best_age: float, freshest_age: float, age_diff: float) -> Tuple[bool, str]:
        """
        Determine if we should override priority for freshness.
        
        Returns:
            Tuple of (should_override, reason)
        """
        if best_age > 3600:  # >1 hour old
            return (age_diff > 10, f"stale data override (best is {best_age/3600:.1f}hr old)")
        elif best_age > 300:  # >5 minutes old
            return (age_diff > 30, f"moderately stale override ({best_age/60:.1f}min old)")
        elif freshest_age < 0:  # Negative age = very fresh
            return (True, "negative age override (very fresh data)")
        elif age_diff > 15:  # For relatively fresh data
            return (True, "fresh data override (>15s fresher)")
        else:
            return (age_diff > 60, "standard freshness override")
    
    def _cache_and_return_price(self, symbol: str, candidate: Dict) -> float:
        """
        Cache the selected price and return it with appropriate logging.
        
        Args:
            symbol: Trading symbol
            candidate: Selected price candidate
            
        Returns:
            Price value
        """
        price = candidate['price']
        age = candidate.get('actual_age', candidate['age'])
        source = candidate['source']
        
        # Cache the result
        cache_key = f"price_{symbol}"
        self._cache_price(cache_key, price)
        
        # Get market status for logging
        market_status = self._get_market_status()
        stale_warning = self._get_staleness_warning(age, market_status)
        
        logger.info(
            f"💰 FRESHEST PRICE: {symbol} = ${price:.4f} "
            f"(source: {source}) (age: {age:.0f}s) [{market_status['status']}]{stale_warning}"
        )
        
        return price

    async def _get_snapshot_price(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        """Get current price using Alpaca Snapshot API (includes extended hours)."""
        try:
            request = StockSnapshotRequest(symbol_or_symbols=symbol)
            loop = asyncio.get_event_loop()
            
            # Use timeout for reliability
            response = await asyncio.wait_for(
                run_blocking(self._client.get_stock_snapshot, request),
                timeout=self._snapshot_timeout
            )
            
            if response and symbol in response:
                snapshot = response[symbol]
                logger.debug(f"📸 Snapshot data for {symbol}: {snapshot}")
                
                # Get the most recent price from various sources in snapshot
                current_price = None
                price_timestamp = None
                
                # Check latest trade first (most recent actual transaction)
                if hasattr(snapshot, 'latest_trade') and snapshot.latest_trade:
                    current_price = float(snapshot.latest_trade.price)
                    price_timestamp = snapshot.latest_trade.timestamp
                    logger.debug(f"📸 Using latest trade price: ${current_price}")
                    
                    # Check if this is extended hours data by examining the timestamp
                    self._log_extended_hours_data_quality(symbol, price_timestamp, "trade")
                
                # Fallback to latest quote if no trade
                elif hasattr(snapshot, 'latest_quote') and snapshot.latest_quote:
                    quote = snapshot.latest_quote
                    if quote.ask_price and quote.ask_price > 0:
                        current_price = float(quote.ask_price)
                        price_timestamp = quote.timestamp
                        logger.debug(f"📸 Using ask price: ${current_price}")
                    elif quote.bid_price and quote.bid_price > 0:
                        current_price = float(quote.bid_price)
                        price_timestamp = quote.timestamp
                        logger.debug(f"📸 Using bid price: ${current_price}")
                    
                    if price_timestamp:
                        self._log_extended_hours_data_quality(symbol, price_timestamp, "quote")
                
                # Calculate age if we have timestamp
                price_age_seconds = None
                if price_timestamp and current_price:
                    now_utc = datetime.now(timezone.utc)
                    price_time = price_timestamp.replace(tzinfo=timezone.utc) if price_timestamp.tzinfo is None else price_timestamp
                    price_age_seconds = (now_utc - price_time).total_seconds()
                
                return current_price, price_age_seconds
                
        except asyncio.TimeoutError:
            logger.warning(f"📸 Snapshot API timeout for {symbol}")
        except Exception as e:
            logger.debug(f"📸 Snapshot API error for {symbol}: {e}")
            
        return None, None

    async def _get_latest_quote_price(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        """Get current price using Alpaca Latest Quote API."""
        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            loop = asyncio.get_event_loop()
            
            response = await asyncio.wait_for(
                run_blocking(self._client.get_stock_latest_quote, request),
                timeout=self._quote_timeout
            )
            
            if response and symbol in response:
                quote = response[symbol]
                logger.debug(f"📡 Latest quote for {symbol}: {quote}")
                
                # Calculate quote age
                now_utc = datetime.now(timezone.utc)
                quote_time = quote.timestamp.replace(tzinfo=timezone.utc) if quote.timestamp.tzinfo is None else quote.timestamp
                price_age_seconds = (now_utc - quote_time).total_seconds()
                
                # Use ask price (preferred) or bid price
                if quote.ask_price and quote.ask_price > 0:
                    return float(quote.ask_price), price_age_seconds
                elif quote.bid_price and quote.bid_price > 0:
                    return float(quote.bid_price), price_age_seconds
                    
        except asyncio.TimeoutError:
            logger.warning(f"📡 Quote API timeout for {symbol}")
        except Exception as e:
            logger.debug(f"📡 Quote API error for {symbol}: {e}")
            
        return None, None

    async def _get_latest_trade_price(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        """Get current price using Alpaca Latest Trade API."""
        try:
            request = StockLatestTradeRequest(symbol_or_symbols=symbol)
            loop = asyncio.get_event_loop()
            
            response = await asyncio.wait_for(
                run_blocking(self._client.get_stock_latest_trade, request),
                timeout=self._quote_timeout
            )
            
            if response and symbol in response:
                trade = response[symbol]
                logger.debug(f"🔄 Latest trade for {symbol}: {trade}")
                
                # Calculate trade age
                now_utc = datetime.now(timezone.utc)
                trade_time = trade.timestamp.replace(tzinfo=timezone.utc) if trade.timestamp.tzinfo is None else trade.timestamp
                price_age_seconds = (now_utc - trade_time).total_seconds()
                
                return float(trade.price), price_age_seconds
                    
        except asyncio.TimeoutError:
            logger.warning(f"🔄 Trade API timeout for {symbol}")
        except Exception as e:
            logger.debug(f"🔄 Trade API error for {symbol}: {e}")
            
        return None, None

    async def _get_latest_bar_price(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        """Get current price using latest bar endpoint - most recent 1-minute bar."""
        try:
            request = StockLatestBarRequest(
                symbol_or_symbols=[symbol],
                feed='iex'  # Use IEX feed for free tier
            )
            
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                run_blocking(self._client.get_stock_latest_bar, request),
                timeout=self._bars_timeout
            )
            
            if response and symbol in response:
                latest_bar = response[symbol]
                ny_tz = pytz.timezone('America/New_York')
                
                logger.debug(f"📊 Latest bar for {symbol}: {latest_bar.timestamp} - ${float(latest_bar.close):.4f}")
                
                # Check if this is extended hours data
                bar_time_ny = latest_bar.timestamp.astimezone(ny_tz)
                is_extended_hours_bar = self._is_extended_hours_time(bar_time_ny)
                
                if is_extended_hours_bar:
                    logger.info(f"🌅 Latest bar IS extended hours: {bar_time_ny} (${float(latest_bar.close):.4f})")
                else:
                    logger.debug(f"🕐 Latest bar is regular hours: {bar_time_ny} (${float(latest_bar.close):.4f})")
                
                # Calculate bar age
                now_utc = datetime.now(timezone.utc)
                bar_time_utc = latest_bar.timestamp.replace(tzinfo=timezone.utc) if latest_bar.timestamp.tzinfo is None else latest_bar.timestamp
                price_age_seconds = (now_utc - bar_time_utc).total_seconds()
                
                # Log extended hours data quality for latest bar
                self._log_extended_hours_data_quality(symbol, latest_bar.timestamp, "latest_bar")
                
                # Use close price from the latest bar
                return float(latest_bar.close), price_age_seconds
                    
        except asyncio.TimeoutError:
            logger.warning(f"📊 Latest Bar API timeout for {symbol}")
        except Exception as e:
            logger.debug(f"📊 Latest Bar API error for {symbol}: {e}")
            
        return None, None

    async def _get_recent_bars_price(self, symbol: str) -> Tuple[Optional[float], Optional[float]]:
        """Get current price using recent bars including extended hours data."""
        try:
            # Get market status to determine time range for extended hours bars
            market_status = self._get_market_status()
            ny_tz = pytz.timezone('America/New_York')
            now_ny = datetime.now(ny_tz)
            
            # For extended hours, we need to look back further to capture pre/post market bars
            if market_status['is_extended_hours'] or market_status['is_closed']:
                # Look back 24 hours to ensure we capture any extended hours activity
                start_time = now_ny - timedelta(hours=24)
                logger.debug(f"📊 Extended hours: Looking for bars from {start_time} for {symbol}")
            else:
                # Regular hours - look back 2 hours
                start_time = now_ny - timedelta(hours=2)
                logger.debug(f"📊 Regular hours: Looking for bars from {start_time} for {symbol}")
            
            # Request bars with extended hours data included
            request = StockBarsRequest(
                symbol_or_symbols=[symbol],  # Use list format like working test
                timeframe=TimeFrame.Minute,
                start=start_time,
                end=now_ny,
                limit=100,  # Get more bars to find the most recent one
                asof=None,
                feed='iex'  # Explicitly specify IEX feed for extended hours data
            )
            
            loop = asyncio.get_event_loop()
            response = await asyncio.wait_for(
                run_blocking(self._client.get_stock_bars, request),
                timeout=self._bars_timeout
            )
            
            # Fix: BarSet doesn't support 'in' operator, use response.data to check
            if response and symbol in response.data and len(response[symbol]) > 0:
                # Get all bars and find the most recent one
                all_bars = list(response[symbol])
                latest_bar = all_bars[-1]  # Most recent bar
                
                logger.debug(f"📊 Found {len(all_bars)} bars for {symbol}, latest: {latest_bar.timestamp}")
                
                # Check if this is extended hours data
                bar_time_ny = latest_bar.timestamp.astimezone(ny_tz)
                is_extended_hours_bar = self._is_extended_hours_time(bar_time_ny)
                
                # Count extended hours vs regular hours bars for intelligence
                extended_count = sum(1 for bar in all_bars 
                                   if self._is_extended_hours_time(bar.timestamp.astimezone(ny_tz)))
                regular_count = len(all_bars) - extended_count
                
                if is_extended_hours_bar:
                    logger.info(f"🌅 Latest bar IS extended hours: {bar_time_ny} (${float(latest_bar.close):.4f})")
                else:
                    logger.debug(f"� Latest bar is regular hours: {bar_time_ny} (${float(latest_bar.close):.4f})")
                
                logger.info(f"📊 Recent bars for {symbol}: {len(all_bars)} total ({regular_count} regular, {extended_count} extended hours)")
                
                # Special handling for extended hours periods
                current_market_status = self._get_market_status()
                if current_market_status['is_extended_hours'] and not is_extended_hours_bar:
                    logger.warning(f"⚠️ Using regular hours bar (${float(latest_bar.close):.4f}) during extended hours period")
                    logger.warning(f"💡 This may be stale data - IEX limited extended hours coverage on free tier")
                elif current_market_status['is_extended_hours'] and is_extended_hours_bar:
                    logger.info(f"✅ Perfect! Using fresh extended hours bar during extended hours period")
                
                # Calculate bar age
                now_utc = datetime.now(timezone.utc)
                bar_time_utc = latest_bar.timestamp.replace(tzinfo=timezone.utc) if latest_bar.timestamp.tzinfo is None else latest_bar.timestamp
                price_age_seconds = (now_utc - bar_time_utc).total_seconds()
                
                # Log extended hours data quality for bars
                self._log_extended_hours_data_quality(symbol, latest_bar.timestamp, "bar")
                
                # Use close price from the most recent bar
                return float(latest_bar.close), price_age_seconds
                    
        except asyncio.TimeoutError:
            logger.warning(f"📊 Bars API timeout for {symbol}")
        except Exception as e:
            logger.debug(f"📊 Bars API error for {symbol}: {e}")
            
        return None, None

    def _is_extended_hours_time(self, timestamp_ny: datetime) -> bool:
        """Check if a given timestamp is during extended hours."""
        hour = timestamp_ny.hour
        minute = timestamp_ny.minute
        
        # Pre-market: 4:00 AM - 9:30 AM
        if (hour == 4 and minute >= 0) or (5 <= hour <= 8) or (hour == 9 and minute < 30):
            return True
        
        # After-hours: 4:00 PM - 8:00 PM  
        if (hour == 16 and minute >= 0) or (17 <= hour <= 19) or (hour == 20 and minute == 0):
            return True
            
        return False

    def _log_extended_hours_data_quality(self, symbol: str, timestamp: datetime, data_type: str):
        """Log warnings about extended hours data quality and limitations."""
        if not self._extended_hours or not timestamp:
            return
            
        # Get current market status
        market_status = self._get_market_status()
        
        # Calculate data age
        now_utc = datetime.now(timezone.utc)
        data_time = timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp
        age_seconds = (now_utc - data_time).total_seconds()
        age_hours = age_seconds / 3600
        
        # Determine if we're in extended hours but getting stale regular hours data
        if market_status['is_extended_hours'] and age_hours > 2:
            # We're in extended hours but data is more than 2 hours old
            if not self._extended_hours_warning_shown:
                logger.warning(f"🟡 Extended Hours Data Limitation: {symbol} {data_type} is {age_hours:.1f}hr old during {market_status['status']}")
                logger.warning(f"🟡 Free Tier Limitation: Extended hours data limited to IEX exchange only")
                logger.warning(f"🟡 Solution: Upgrade to SIP data plan for full extended hours coverage from all exchanges")
                self._extended_hours_warning_shown = True
            else:
                logger.debug(f"🟡 {symbol}: Using stale {data_type} data ({age_hours:.1f}hr old) - extended hours coverage limited on free tier")
                
        elif market_status['is_extended_hours'] and age_seconds < 1800:  # < 30 minutes
            # We have relatively fresh data during extended hours - this is good!
            logger.info(f"✅ {symbol}: Fresh extended hours {data_type} available ({age_seconds:.0f}s old)")

    def _get_market_status(self) -> Dict[str, Any]:
        """Get current market status for intelligent data handling."""
        ny_tz = pytz.timezone('America/New_York')
        now_ny = datetime.now(ny_tz)
        
        # Define market hours (9:30 AM - 4:00 PM ET)
        market_open = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now_ny.replace(hour=16, minute=0, second=0, microsecond=0)
        
        # Define extended hours
        pre_market_start = now_ny.replace(hour=4, minute=0, second=0, microsecond=0)
        after_hours_end = now_ny.replace(hour=20, minute=0, second=0, microsecond=0)
        
        # Determine market status
        is_weekend = now_ny.weekday() >= 5  # Saturday = 5, Sunday = 6
        is_regular_hours = not is_weekend and market_open <= now_ny < market_close
        is_pre_market = not is_weekend and pre_market_start <= now_ny < market_open
        is_post_market = not is_weekend and market_close <= now_ny < after_hours_end
        is_extended_hours = is_pre_market or is_post_market
        is_closed = is_weekend or not (is_regular_hours or is_extended_hours)
        
        # Determine status text
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

    def _get_staleness_warning(self, price_age_seconds: Optional[float], market_status: Dict[str, Any]) -> str:
        """Generate appropriate staleness warning based on market status and freshness."""
        if not price_age_seconds:
            return ""
        
        age_hours = price_age_seconds / 3600
        
        if market_status['is_regular_hours']:
            if price_age_seconds > 300:  # > 5 minutes during market hours is concerning
                return " ⚠️ STALE DATA DURING MARKET HOURS!"
            elif price_age_seconds > 60:  # > 1 minute is noteworthy
                return " (note: slightly stale)"
            else:
                return " ✅ (very fresh)"
        elif market_status['is_extended_hours']:
            if price_age_seconds > 1800:  # > 30 minutes during extended hours
                return f" 🟡 EXTENDED HOURS LIMITED (Free tier IEX-only, {age_hours:.1f}hr old)"
            elif price_age_seconds > 300:  # > 5 minutes but < 30 minutes
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

    def _get_cached_price(self, cache_key: str) -> Optional[float]:
        """Get cached price if still valid."""
        if cache_key in self._price_cache:
            cache_entry = self._price_cache[cache_key]
            cache_time = cache_entry['timestamp']
            if datetime.now(timezone.utc) - cache_time < self._cache_duration:
                return cache_entry['price']
        return None

    def _cache_price(self, cache_key: str, price: float):
        """Cache price with timestamp."""
        self._price_cache[cache_key] = {
            'price': price,
            'timestamp': datetime.now(timezone.utc)
        }

    async def get_historical_data(self, symbol: str, timeframe: str, count: int) -> List[Dict[str, Any]]:
        """
        Get historical market data (interface compatibility method).
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe (1Min, 5Min, 15Min, 1Hour, 1Day)
            count: Number of bars to fetch
            
        Returns:
            List of historical bars
        """
        return await self.get_historical_bars(symbol, timeframe, count)

    async def get_historical_bars(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get historical bars for a symbol.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe (1Min, 5Min, 15Min, 1Hour, 1Day)
            limit: Number of bars to fetch
            start_date: Start date for historical data
            end_date: End date for historical data
            
        Returns:
            List of historical bars
        """
        try:
            # Map timeframe string to Alpaca TimeFrame
            timeframe_map = {
                '1Min': TimeFrame.Minute,
                '5Min': TimeFrame(5, TimeFrameUnit.Minute),
                '15Min': TimeFrame(15, TimeFrameUnit.Minute),
                '1Hour': TimeFrame.Hour,
                '1Day': TimeFrame.Day
            }
            
            alpaca_timeframe = timeframe_map.get(timeframe, TimeFrame.Minute)
            
            request = StockBarsRequest(
                symbol_or_symbols=[symbol],  # Use list format like working test
                timeframe=alpaca_timeframe,
                limit=limit,
                start=start_date,
                end=end_date,
                feed='iex'  # Explicitly specify IEX feed for extended hours data
            )
            
            # Use synchronous call in executor like the working test
            response = await run_blocking(self._client.get_stock_bars, request)
            
            # Fix: BarSet doesn't support 'in' operator, use direct access or response.data
            if response and symbol in response.data:
                bars = []
                extended_hours_bars = 0
                regular_hours_bars = 0
                
                for bar in response[symbol]:
                    bar_time_ny = bar.timestamp.astimezone(pytz.timezone('America/New_York'))
                    is_extended = self._is_extended_hours_time(bar_time_ny)
                    
                    if is_extended:
                        extended_hours_bars += 1
                    else:
                        regular_hours_bars += 1
                    
                    bars.append({
                        'timestamp': bar.timestamp,
                        'open': float(bar.open),
                        'high': float(bar.high),
                        'low': float(bar.low),
                        'close': float(bar.close),
                        'volume': int(bar.volume),
                        'extended_hours': is_extended  # Flag to identify extended hours bars
                    })
                
                # Log bar composition
                total_bars = len(bars)
                if total_bars > 0:
                    logger.info(f"📊 Historical bars for {symbol}: {total_bars} total, {regular_hours_bars} regular hours, {extended_hours_bars} extended hours")
                
                return bars
            
            return []
            
        except Exception as e:
            logger.error(f"Error fetching historical bars for {symbol}: {e}")
            raise MarketDataException(f"Failed to fetch historical bars for {symbol}: {e}")

    async def close(self):
        """Clean up resources."""
        self._price_cache.clear()
        logger.info("AlpacaMarketDataProvider closed")
