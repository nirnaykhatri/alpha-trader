"""
Alpaca Dynamic Market Status Provider
Implements dynamic market status using Alpaca's Clock and Calendar APIs.
"""

import asyncio
from datetime import datetime, timezone, time as dt_time
from typing import Set, Optional, Any
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import aiohttp
from alpaca.trading.client import TradingClient
from alpaca.trading.models import Clock, Calendar
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..core.dynamic_market_hours import (
    IBrokerMarketStatusProvider, BrokerMarketStatus, TradingSession
)

logger = logging.getLogger(__name__)


class AlpacaDynamicMarketStatusProvider(IBrokerMarketStatusProvider):
    """
    Alpaca implementation of dynamic market status provider.
    Uses Alpaca's Clock API for real-time market status and Calendar API for trading days.
    """
    
    def __init__(self, trading_client: TradingClient, config: Any):
        self.trading_client = trading_client
        self.config = config
        
        # Thread pool for blocking API calls
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="alpaca-api")
        
        # Alpaca supports US stock markets with extended hours
        self._supported_symbols = None  # Will be loaded dynamically
        self._symbols_last_refresh = None
        self._symbols_refresh_interval = 3600  # 1 hour
        
        self._supports_extended_hours = True
        self._supports_weekend_trading = False  # Alpaca doesn't support crypto 24/7
        
        # Market hours configuration (Eastern Time)
        self._regular_open = dt_time(9, 30)  # 9:30 AM ET
        self._regular_close = dt_time(16, 0)  # 4:00 PM ET
        self._premarket_start = dt_time(4, 0)  # 4:00 AM ET
        self._postmarket_end = dt_time(20, 0)  # 8:00 PM ET
        
        logger.info("🕐 Alpaca Dynamic Market Status Provider initialized")
    
    async def _load_supported_symbols(self) -> Set[str]:
        """Load supported symbols from Alpaca Assets API or use default set."""
        try:
            # Check if we need to refresh symbols
            now = datetime.now(timezone.utc)
            if (self._symbols_last_refresh is None or 
                (now - self._symbols_last_refresh).total_seconds() > self._symbols_refresh_interval):
                
                # Try to fetch from Alpaca Assets API
                try:
                    symbols = await self._fetch_alpaca_assets()
                    if symbols:
                        self._supported_symbols = symbols
                        self._symbols_last_refresh = now
                        logger.info(f"✅ Loaded {len(symbols)} symbols from Alpaca Assets API")
                        return symbols
                except Exception as e:
                    logger.warning(f"⚠️ Failed to fetch assets from Alpaca API: {e}")
            
            # Return cached symbols if available
            if self._supported_symbols:
                return self._supported_symbols
                
            # Fall back to default symbol list
            default_symbols = self._get_default_symbol_set()
            self._supported_symbols = default_symbols
            logger.info(f"📋 Using default symbol set ({len(default_symbols)} symbols)")
            return default_symbols
            
        except Exception as e:
            logger.error(f"❌ Error loading supported symbols: {e}")
            return self._get_default_symbol_set()
    
    def _get_default_symbol_set(self) -> Set[str]:
        """Get default set of symbols for fallback."""
        default_symbols = {
            "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "BRK.B",
            "UNH", "JNJ", "V", "WMT", "JPM", "MA", "PG", "HD", "CVX", "ABBV",
            "BAC", "PFE", "KO", "AVGO", "PEP", "TMO", "COST", "DIS", "ABT",
            "MRK", "NFLX", "ACN", "LLY", "NKE", "TXN", "DHR", "NEE", "VZ",
            "CMCSA", "ADBE", "CRM", "INTC", "WFC", "AMD", "T", "BMY", "UPS",
            "QCOM", "LOW", "PM", "RTX", "HON", "SCHW", "SPGI", "CAT", "GS",
            "INTU", "IBM", "MDT", "CVS", "AXP", "GILD", "DE", "AMGN", "TJX",
            "BLK", "SYK", "BKNG", "AMT", "TMUS", "ADP", "MO", "ISRG", "MDLZ",
            "CI", "LRCX", "CB", "SO", "ZTS", "REGN", "PGR", "MMC", "DUK",
            "SLB", "CSX", "CME", "BSX", "EOG", "ITW", "USB", "PNC", "NSC",
            "SPY", "QQQ", "IWM", "VTI", "VOO", "VEA", "VWO", "IEFA", "IEMG",
            "GLD", "SLV", "TLT", "HYG", "LQD", "ARKK", "XLF", "XLK", "XLE"
        }
        
        # Allow configuration override
        config_symbols = self.config.get_config("symbols.default_symbols", [])
        if config_symbols:
            return set(config_symbols)
        
        return default_symbols
    
    async def _fetch_alpaca_assets(self) -> Set[str]:
        """Fetch tradeable assets from Alpaca API."""
        try:
            # Run blocking API call in thread pool
            loop = asyncio.get_event_loop()
            assets = await loop.run_in_executor(
                self._executor,
                lambda: self.trading_client.get_all_assets(status="active", asset_class="us_equity")
            )
            
            # Extract symbols
            symbols = {asset.symbol for asset in assets if asset.tradable and asset.shortable}
            return symbols
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to fetch Alpaca assets: {e}")
            return set()
    
    async def get_market_status(self) -> BrokerMarketStatus:
        """Get current market status from Alpaca Clock API."""
        try:
            # Get current market clock from Alpaca
            clock = await self._get_alpaca_clock()
            
            # Determine current session using improved logic
            current_session = self._determine_session_from_clock(clock)
            
            # Get next market open/close times
            next_open, next_close = await self._get_next_market_times(clock)
            
            # Ensure we have supported symbols
            supported_symbols = await self._load_supported_symbols()
            
            return BrokerMarketStatus(
                broker_type="alpaca",
                is_market_open=clock.is_open,
                current_session=current_session,
                is_trading_day=not clock.is_open or current_session != TradingSession.CLOSED,
                supported_symbols=supported_symbols,
                next_market_open=next_open,
                next_market_close=next_close,
                extended_hours_available=self._supports_extended_hours,
                weekend_trading_available=self._supports_weekend_trading,
                market_timezone="America/New_York",
                last_updated=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to get Alpaca market status: {e}")
            raise
    
    async def is_symbol_tradeable_now(self, symbol: str) -> bool:
        """Check if a specific symbol is tradeable right now via Alpaca."""
        try:
            # Ensure we have the latest symbols
            supported_symbols = await self._load_supported_symbols()
            if symbol not in supported_symbols:
                return False
            
            status = await self.get_market_status()
            
            # Symbol is tradeable if market is open or during extended hours
            if status.is_market_open:
                return True
            
            # Check extended hours
            if status.extended_hours_available and status.current_session in [
                TradingSession.PREMARKET, TradingSession.POSTMARKET
            ]:
                return True
            
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ Error checking {symbol} tradeability: {e}")
            return False
    
    def get_supported_symbols(self) -> Set[str]:
        """Get set of symbols this broker can trade."""
        # Return cached symbols if available, otherwise return default
        if self._supported_symbols:
            return self._supported_symbols.copy()
        return self._get_default_symbol_set()
    
    def supports_extended_hours(self) -> bool:
        """Check if broker supports extended hours trading."""
        return self._supports_extended_hours
    
    def supports_weekend_trading(self) -> bool:
        """Check if broker supports weekend trading (crypto)."""
        return self._supports_weekend_trading
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, Exception))
    )
    async def _get_alpaca_clock(self) -> Clock:
        """Get current market clock from Alpaca API with retry logic."""
        try:
            # Run blocking API call in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            clock = await loop.run_in_executor(
                self._executor,
                self.trading_client.get_clock
            )
            return clock
        except Exception as e:
            logger.error(f"❌ Failed to get Alpaca clock: {e}")
            raise
    
    def _determine_session_from_clock(self, clock: Clock) -> TradingSession:
        """Determine current trading session from Alpaca clock using proper logic."""
        if not clock.is_open:
            return TradingSession.CLOSED
        
        # Market is open - determine if regular or extended hours
        # Convert current time to Eastern (where US markets operate)
        from zoneinfo import ZoneInfo
        et_tz = ZoneInfo("America/New_York")
        current_et = datetime.now(et_tz).time()
        
        # Determine session based on Eastern Time
        if self._regular_open <= current_et <= self._regular_close:
            return TradingSession.REGULAR
        elif self._premarket_start <= current_et < self._regular_open:
            return TradingSession.PREMARKET
        elif self._regular_close < current_et <= self._postmarket_end:
            return TradingSession.POSTMARKET
        else:
            # This shouldn't happen if market is truly open, but fallback to closed
            logger.warning(f"⚠️ Market reported as open but time {current_et} doesn't match any session")
            return TradingSession.CLOSED
    
    async def _get_next_market_times(self, clock: Clock) -> tuple[Optional[datetime], Optional[datetime]]:
        """Get next market open and close times."""
        try:
            # Convert Alpaca times to UTC
            next_open = clock.next_open.replace(tzinfo=timezone.utc) if clock.next_open else None
            next_close = clock.next_close.replace(tzinfo=timezone.utc) if clock.next_close else None
            
            return next_open, next_close
            
        except Exception as e:
            logger.warning(f"⚠️ Error getting next market times: {e}")
            return None, None
    
    async def refresh_supported_symbols(self) -> None:
        """Refresh the list of supported symbols from Alpaca."""
        try:
            # Force refresh by clearing cache
            self._symbols_last_refresh = None
            self._supported_symbols = None
            
            # Reload symbols
            await self._load_supported_symbols()
            logger.info("✅ Successfully refreshed supported symbols from Alpaca API")
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to refresh supported symbols: {e}")
    
    def __del__(self):
        """Cleanup thread pool on destruction."""
        if hasattr(self, '_executor'):
            try:
                self._executor.shutdown(wait=False)
            except Exception:
                pass  # Ignore cleanup errors


class MockDynamicMarketStatusProvider(IBrokerMarketStatusProvider):
    """
    Mock implementation for testing and crypto/forex simulation.
    Supports 24/7 trading for testing purposes.
    """
    
    def __init__(self, broker_type: str = "mock", supports_24_7: bool = False):
        self.broker_type = broker_type
        self._supports_24_7 = supports_24_7
        
        # Mock supports a wide range of symbols including crypto
        self._supported_symbols = {
            "AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "AMD", "SPY", "QQQ",
            "BTCUSD", "ETHUSD", "LTCUSD", "ADAUSD", "DOGEUSD",
            "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"
        }
        
        logger.info(f"🧪 Mock Dynamic Market Status Provider initialized ({broker_type}, 24/7={supports_24_7})")
    
    async def get_market_status(self) -> BrokerMarketStatus:
        """Get mock market status."""
        now = datetime.now(timezone.utc)
        
        if self._supports_24_7:
            # 24/7 market (crypto)
            return BrokerMarketStatus(
                broker_type=self.broker_type,
                is_market_open=True,
                current_session=TradingSession.REGULAR,
                is_trading_day=True,
                supported_symbols=self._supported_symbols,
                next_market_open=None,  # Always open
                next_market_close=None,  # Never closes
                extended_hours_available=False,  # N/A for 24/7
                weekend_trading_available=True,
                market_timezone="UTC",
                last_updated=now
            )
        else:
            # Traditional market simulation
            current_hour = now.hour
            is_weekend = now.weekday() >= 5
            
            # Simple market hours simulation (US market)
            if is_weekend:
                is_open = False
                session = TradingSession.CLOSED
            elif 4 <= current_hour < 9:  # 4-9 AM UTC (premarket in EST)
                is_open = True
                session = TradingSession.PREMARKET
            elif 9 <= current_hour < 16:  # 9-4 PM UTC (regular in EST)
                is_open = True
                session = TradingSession.REGULAR
            elif 16 <= current_hour < 20:  # 4-8 PM UTC (postmarket in EST)
                is_open = True
                session = TradingSession.POSTMARKET
            else:
                is_open = False
                session = TradingSession.CLOSED
            
            return BrokerMarketStatus(
                broker_type=self.broker_type,
                is_market_open=is_open,
                current_session=session,
                is_trading_day=not is_weekend,
                supported_symbols=self._supported_symbols,
                next_market_open=None,  # Simplified
                next_market_close=None,  # Simplified
                extended_hours_available=True,
                weekend_trading_available=False,
                market_timezone="America/New_York",
                last_updated=now
            )
    
    async def is_symbol_tradeable_now(self, symbol: str) -> bool:
        """Check if symbol is tradeable in mock broker."""
        if symbol not in self._supported_symbols:
            return False
        
        status = await self.get_market_status()
        return status.is_market_open
    
    def get_supported_symbols(self) -> Set[str]:
        """Get supported symbols."""
        return self._supported_symbols.copy()
    
    def supports_extended_hours(self) -> bool:
        """Mock supports extended hours."""
        return not self._supports_24_7  # 24/7 markets don't have "extended" hours
    
    def supports_weekend_trading(self) -> bool:
        """Mock supports weekend trading if 24/7."""
        return self._supports_24_7