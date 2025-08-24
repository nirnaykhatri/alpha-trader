"""
Alpaca Dynamic Market Status Provider
Implements dynamic market status using Alpaca's Clock and Calendar APIs.
"""

import asyncio
from datetime import datetime, timezone, time as dt_time
from typing import Set, Optional, Any, Dict
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import aiohttp
import pytz
import requests
from alpaca.trading.client import TradingClient
from alpaca.trading.models import Clock, Calendar
from alpaca.trading.requests import GetCalendarRequest
from alpaca.common.exceptions import APIError
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
        
        # Get API credentials for direct REST calls
        self._api_key = getattr(trading_client, '_api_key', None)
        self._api_secret = getattr(trading_client, '_secret_key', None)
        self._base_url = getattr(trading_client, '_base_url', 'https://paper-api.alpaca.markets')
        
        # Thread pool for blocking API calls
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="alpaca-api")
        
        # Cache for API responses
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes cache
        self._last_cache_time = None
        
        # Timezone setup
        self.eastern_tz = pytz.timezone('America/New_York')
        
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

    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid"""
        if not self._last_cache_time or not self._cache:
            return False
        
        cache_age = (datetime.now() - self._last_cache_time).total_seconds()
        return cache_age < self._cache_ttl

    async def _call_calendar_api_directly(self, start_date: str, end_date: str) -> Optional[list]:
        """Call Alpaca Calendar API directly via REST since SDK doesn't expose it."""
        try:
            # Get API credentials from config if not available from client
            if not self._api_key or not self._api_secret:
                # Try to get from config
                try:
                    broker_config = self.config.get_config("brokers.alpaca", {})
                    self._api_key = broker_config.get("api_key")
                    self._api_secret = broker_config.get("secret_key")
                    self._base_url = broker_config.get("base_url", "https://paper-api.alpaca.markets")
                    logger.debug(f"🔑 Got API credentials from config, base_url: {self._base_url}")
                except Exception as e:
                    logger.warning(f"⚠️ Could not get credentials from config: {e}")
            
            if not self._api_key or not self._api_secret:
                logger.warning("⚠️ API credentials not available for direct calendar call")
                logger.debug(f"API key present: {bool(self._api_key)}, Secret present: {bool(self._api_secret)}")
                return None
            
            # Check if using placeholder credentials
            if self._api_key == "REPLACE_WITH_YOUR_ACTUAL_API_KEY":
                logger.warning("⚠️ Using placeholder API credentials - calendar API will fail")
                return None
            
            # Prepare headers for Alpaca API
            headers = {
                "APCA-API-KEY-ID": self._api_key,
                "APCA-API-SECRET-KEY": self._api_secret,
                "Content-Type": "application/json"
            }
            
            # Make direct REST call to calendar endpoint
            url = f"{self._base_url}/v2/calendar"
            params = {
                "start": start_date,
                "end": end_date
            }
            
            logger.debug(f"📞 Making calendar API call to {url} with params {params}")
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                self._executor,
                lambda: requests.get(url, headers=headers, params=params, timeout=10)
            )
            
            logger.debug(f"📞 Calendar API response: status={response.status_code}")
            
            if response.status_code == 200:
                calendar_data = response.json()
                logger.info(f"✅ Got calendar data from direct REST call: {len(calendar_data)} entries")
                return calendar_data
            elif response.status_code == 403:
                logger.error("❌ Calendar API access forbidden - check API credentials")
                logger.debug(f"Response: {response.text}")
                return None
            else:
                logger.warning(f"⚠️ Calendar API returned status {response.status_code}: {response.text}")
                return None
                
        except Exception as e:
            logger.warning(f"⚠️ Direct calendar API call failed: {e}")
            import traceback
            logger.debug(f"Full traceback: {traceback.format_exc()}")
            return None
    
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
            default_set = self._get_default_symbol_set()
            # Ensure we never return None - this is critical for system stability
            return default_set if default_set is not None else set()
    
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
            # Try SDK methods first
            loop = asyncio.get_event_loop()
            assets = None
            
            # Try different method names for getting assets
            if hasattr(self.trading_client, 'get_all_assets'):
                try:
                    assets = await loop.run_in_executor(
                        self._executor,
                        lambda: self.trading_client.get_all_assets(status="active", asset_class="us_equity")
                    )
                except Exception as e:
                    logger.warning(f"⚠️ get_all_assets failed: {e}")
            elif hasattr(self.trading_client, 'get_assets'):
                try:
                    assets = await loop.run_in_executor(
                        self._executor,
                        lambda: self.trading_client.get_assets(status="active", asset_class="us_equity")
                    )
                except Exception as e:
                    logger.warning(f"⚠️ get_assets failed: {e}")
            
            # If SDK methods failed or don't exist, try direct REST API call
            if not assets:
                logger.info("📞 Trying direct REST API call for assets")
                assets = await self._call_assets_api_directly()
            
            # Extract symbols
            if assets:
                if isinstance(assets, list):
                    symbols = {asset.symbol for asset in assets if hasattr(asset, 'tradable') and asset.tradable and hasattr(asset, 'shortable') and asset.shortable}
                else:
                    # If it's a different format, try to handle it
                    symbols = set()
                
                if symbols:
                    logger.info(f"✅ Successfully fetched {len(symbols)} tradeable symbols")
                    return symbols
            
            # If everything failed, fall back to empty set (will use defaults)
            logger.warning("⚠️ No assets method available on trading client, using default symbols")
            return set()
            
        except Exception as e:
            logger.warning(f"⚠️ Failed to fetch Alpaca assets: {e}")
            return set()
    
    async def _call_assets_api_directly(self) -> Optional[list]:
        """Call Alpaca Assets API directly via REST."""
        try:
            # Get API credentials
            if not self._api_key or not self._api_secret:
                try:
                    broker_config = self.config.get_config("brokers.alpaca", {})
                    self._api_key = broker_config.get("api_key")
                    self._api_secret = broker_config.get("secret_key")
                    self._base_url = broker_config.get("base_url", "https://paper-api.alpaca.markets")
                except Exception as e:
                    logger.warning(f"⚠️ Could not get credentials for assets API: {e}")
                    return None
            
            if not self._api_key or not self._api_secret or self._api_key == "REPLACE_WITH_YOUR_ACTUAL_API_KEY":
                logger.debug("⚠️ API credentials not available for direct assets call")
                return None
            
            # Prepare headers for Alpaca API
            headers = {
                "APCA-API-KEY-ID": self._api_key,
                "APCA-API-SECRET-KEY": self._api_secret,
                "Content-Type": "application/json"
            }
            
            # Make direct REST call to assets endpoint
            url = f"{self._base_url}/v2/assets"
            params = {
                "status": "active",
                "asset_class": "us_equity"
            }
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                self._executor,
                lambda: requests.get(url, headers=headers, params=params, timeout=15)
            )
            
            if response.status_code == 200:
                assets_data = response.json()
                logger.debug(f"✅ Got {len(assets_data)} assets from direct REST call")
                
                # Convert to mock objects with necessary attributes
                mock_assets = []
                for asset_data in assets_data:
                    if asset_data.get('tradable') and asset_data.get('shortable'):
                        mock_asset = type('Asset', (), {
                            'symbol': asset_data.get('symbol'),
                            'tradable': asset_data.get('tradable', False),
                            'shortable': asset_data.get('shortable', False)
                        })()
                        mock_assets.append(mock_asset)
                
                return mock_assets
            else:
                logger.debug(f"⚠️ Assets API returned status {response.status_code}")
                return None
                
        except Exception as e:
            logger.debug(f"⚠️ Direct assets API call failed: {e}")
            return None
    
    async def get_market_status(self) -> BrokerMarketStatus:
        """Get current market status from Alpaca Calendar API."""
        try:
            # Get current market clock data from Alpaca
            clock_data = await self._get_alpaca_clock()
            
            if not clock_data:
                # If we can't get clock data, fall back to default closed state
                clock_data = self._get_fallback_clock()
            
            # Determine current session using improved logic
            current_session = self._determine_session_from_clock(clock_data)
            
            # Get next market open/close times
            next_open, next_close = await self._get_next_market_times(clock_data)
            
            # Ensure we have supported symbols
            supported_symbols = await self._load_supported_symbols()
            # Critical safety check - supported_symbols must never be None
            if supported_symbols is None:
                logger.error("❌ CRITICAL: supported_symbols was None, using empty set")
                supported_symbols = set()
            
            return BrokerMarketStatus(
                broker_type="alpaca",
                is_market_open=clock_data.get('is_open', False),
                current_session=current_session,
                is_trading_day=not clock_data.get('is_open', False) or current_session != TradingSession.CLOSED,
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
            # Return a safe fallback status instead of crashing the system
            return BrokerMarketStatus(
                broker_type="alpaca",
                is_market_open=False,  # Conservative assumption
                current_session=TradingSession.CLOSED,
                is_trading_day=False,
                supported_symbols=self._get_default_symbol_set(),  # Use default symbols
                next_market_open=None,
                next_market_close=None,
                extended_hours_available=False,
                weekend_trading_available=False,
                market_timezone="America/New_York",
                last_updated=datetime.now(timezone.utc)
            )
    
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

    def _get_fallback_clock(self) -> Dict[str, Any]:
        """Fallback method when API calls fail"""
        try:
            now = datetime.now(timezone.utc)
            eastern_now = now.astimezone(self.eastern_tz)
            
            # Simple market hours check (9:30 AM - 4:00 PM ET, Mon-Fri)
            is_weekday = eastern_now.weekday() < 5  # 0-4 are Mon-Fri
            is_market_hours = 9.5 <= eastern_now.hour + eastern_now.minute/60.0 <= 16.0
            is_open = is_weekday and is_market_hours
            
            clock_data = {
                'timestamp': now.isoformat(),
                'is_open': is_open,
                'next_open': None,
                'next_close': None,
                'timezone': 'America/New_York',
                'fallback': True
            }
            
            logger.warning("⚠️ Using fallback market status calculation")
            logger.info("💡 To use real-time market data, add valid Alpaca API credentials to config.yaml")
            return clock_data
            
        except Exception as e:
            logger.error(f"❌ Even fallback clock failed: {e}")
            # Ultimate fallback
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'is_open': False,
                'next_open': None,
                'next_close': None,
                'timezone': 'America/New_York',
                'fallback': True,
                'error': True
            }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, Exception))
    )
    async def _get_alpaca_clock(self) -> Optional[Dict[str, Any]]:
        """Get current market clock using Alpaca Calendar API since get_clock is not available."""
        try:
            # Check cache first
            if self._is_cache_valid():
                return self._cache.get('clock')
            
            # Try to get market calendar which includes current market status
            current_date = datetime.now(self.eastern_tz).date()
            date_str = current_date.strftime('%Y-%m-%d')
            
            # First try the SDK method if available
            calendar_data = None
            if hasattr(self.trading_client, 'get_calendar'):
                try:
                    calendar_request = GetCalendarRequest(
                        start=current_date,
                        end=current_date
                    )
                    
                    loop = asyncio.get_event_loop()
                    calendar_data = await loop.run_in_executor(
                        self._executor,
                        self.trading_client.get_calendar,
                        calendar_request
                    )
                except Exception as e:
                    logger.warning(f"⚠️ SDK calendar method failed: {e}")
                    calendar_data = None
            
            # If SDK method failed or doesn't exist, try direct REST API call
            if not calendar_data:
                logger.info("📞 Using direct REST API call to get calendar data")
                rest_calendar_data = await self._call_calendar_api_directly(date_str, date_str)
                
                if rest_calendar_data:
                    # Convert REST response to format similar to SDK
                    calendar_data = []
                    for day_data in rest_calendar_data:
                        # Parse the time strings from REST API response
                        open_time_str = day_data.get('open', '09:30')
                        close_time_str = day_data.get('close', '16:00')
                        
                        # Convert to time objects
                        from datetime import time as dt_time
                        open_parts = open_time_str.split(':')
                        close_parts = close_time_str.split(':')
                        
                        calendar_entry = type('CalendarEntry', (), {
                            'open': dt_time(int(open_parts[0]), int(open_parts[1])),
                            'close': dt_time(int(close_parts[0]), int(close_parts[1])),
                            'date': day_data.get('date')
                        })()
                        
                        calendar_data.append(calendar_entry)
                else:
                    logger.warning("⚠️ Both SDK and REST calendar methods failed, using fallback")
                    return self._get_fallback_clock()
            
            if calendar_data and len(calendar_data) > 0:
                today_calendar = calendar_data[0]
                
                # Create clock-like data structure
                now = datetime.now(timezone.utc)
                eastern_now = now.astimezone(self.eastern_tz)
                
                # Check if market is currently open
                market_open = today_calendar.open
                market_close = today_calendar.close
                
                # Convert to datetime objects if they're not already
                if hasattr(market_open, 'replace'):
                    market_open_dt = eastern_now.replace(
                        hour=market_open.hour,
                        minute=market_open.minute,
                        second=0,
                        microsecond=0
                    )
                else:
                    market_open_dt = market_open
                    
                if hasattr(market_close, 'replace'):
                    market_close_dt = eastern_now.replace(
                        hour=market_close.hour,
                        minute=market_close.minute,
                        second=0,
                        microsecond=0
                    )
                else:
                    market_close_dt = market_close
                
                is_open = market_open_dt <= eastern_now <= market_close_dt
                
                clock_data = {
                    'timestamp': now.isoformat(),
                    'is_open': is_open,
                    'next_open': market_open_dt.isoformat() if not is_open and eastern_now < market_open_dt else None,
                    'next_close': market_close_dt.isoformat() if is_open else None,
                    'timezone': 'America/New_York'
                }
                
                # Update cache
                self._cache['clock'] = clock_data
                self._last_cache_time = datetime.now()
                
                logger.debug(f"📅 Retrieved market status: open={is_open}")
                return clock_data
            
            else:
                # Fallback: assume market is closed if no calendar data
                now = datetime.now(timezone.utc)
                clock_data = {
                    'timestamp': now.isoformat(),
                    'is_open': False,
                    'next_open': None,
                    'next_close': None,
                    'timezone': 'America/New_York'
                }
                
                self._cache['clock'] = clock_data
                self._last_cache_time = datetime.now()
                
                logger.warning("⚠️ No calendar data available, assuming market closed")
                return clock_data
                
        except APIError as e:
            logger.error(f"❌ Alpaca API error getting market status: {e}")
            return self._get_fallback_clock()
        except Exception as e:
            logger.error(f"❌ Failed to get Alpaca market status: {e}")
            return self._get_fallback_clock()
    
    def _determine_session_from_clock(self, clock_data: Dict[str, Any]) -> TradingSession:
        """Determine current trading session from clock data using proper logic."""
        if not clock_data.get('is_open', False):
            return TradingSession.CLOSED
        
        # Market is open - determine if regular or extended hours
        # Convert current time to Eastern (where US markets operate)
        current_et = datetime.now(self.eastern_tz).time()
        
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
    
    async def _get_next_market_times(self, clock_data: Dict[str, Any]) -> tuple[Optional[datetime], Optional[datetime]]:
        """Get next market open and close times from clock data."""
        try:
            next_open_str = clock_data.get('next_open')
            next_close_str = clock_data.get('next_close')
            
            next_open = None
            next_close = None
            
            if next_open_str:
                try:
                    next_open = datetime.fromisoformat(next_open_str.replace('Z', '+00:00'))
                except Exception as e:
                    logger.warning(f"⚠️ Could not parse next_open time: {e}")
                    
            if next_close_str:
                try:
                    next_close = datetime.fromisoformat(next_close_str.replace('Z', '+00:00'))
                except Exception as e:
                    logger.warning(f"⚠️ Could not parse next_close time: {e}")
            
            return next_open, next_close
            
        except Exception as e:
            logger.error(f"❌ Error getting next market times: {e}")
            return None, None
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