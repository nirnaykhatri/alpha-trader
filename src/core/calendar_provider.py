"""
Alpaca Calendar Provider - Trading calendar and session information using Alpaca APIs.
Provides authoritative trading calendar data directly from the broker.
"""

import asyncio
import aiohttp
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone, date, timedelta
from dataclasses import dataclass
from enum import Enum

from ..interfaces import IConfigurationManager
from ..exceptions import MarketDataException
from ..core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class TradingDay:
    """Information about a specific trading day."""
    date: date
    open_time: datetime
    close_time: datetime
    is_trading_day: bool
    is_early_close: bool
    early_close_time: Optional[datetime] = None
    raw_data: Optional[Dict[str, Any]] = None


@dataclass
class SessionHours:
    """Trading session hours for a specific day."""
    regular_open: datetime
    regular_close: datetime
    premarket_open: Optional[datetime] = None
    postmarket_close: Optional[datetime] = None
    is_early_close: bool = False
    early_close_time: Optional[datetime] = None


class AlpacaCalendarProvider:
    """
    Provides official trading calendar data from Alpaca Calendar API.
    Handles holidays, early closes, and schedule changes.
    """
    
    def __init__(self, config: IConfigurationManager):
        """
        Initialize Alpaca calendar provider.
        
        Args:
            config: Configuration manager instance
        """
        self._config = config
        
        # Get Alpaca API credentials
        self._api_key = config.get_config("api.alpaca.api_key")
        self._secret_key = config.get_config("api.alpaca.secret_key")
        self._base_url = config.get_config("api.alpaca.base_url", "https://paper-api.alpaca.markets")
        
        if not self._api_key or not self._secret_key:
            raise MarketDataException("Alpaca API credentials required for calendar provider")
        
        # Configuration
        self._timeout = config.get_config("market_hours.alpaca_integration.timeout_seconds", 10)
        self._max_retries = config.get_config("market_hours.alpaca_integration.retry_attempts", 3)
        self._cache_duration_hours = config.get_config("market_hours.alpaca_integration.calendar_cache_hours", 24)
        
        # Cache management
        self._calendar_cache: Dict[str, List[TradingDay]] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        
        # Build API endpoint
        self._calendar_endpoint = f"{self._base_url.rstrip('/')}/v2/calendar"
        
        logger.info(f"AlpacaCalendarProvider initialized - endpoint: {self._calendar_endpoint}")
    
    async def get_trading_calendar(
        self,
        start_date: date,
        end_date: date,
        force_refresh: bool = False
    ) -> List[TradingDay]:
        """
        Fetch trading calendar for date range.
        
        Args:
            start_date: Start date for calendar data
            end_date: End date for calendar data
            force_refresh: Force refresh from API even if cached
            
        Returns:
            List of TradingDay objects
        """
        try:
            cache_key = f"{start_date}_{end_date}"
            
            # Check cache first
            if not force_refresh and self._is_calendar_cache_valid(cache_key):
                logger.debug(f"📋 Using cached calendar data for {cache_key}")
                return self._calendar_cache[cache_key]
            
            logger.debug(f"🔍 Fetching calendar data from Alpaca API: {start_date} to {end_date}")
            
            # Make API request with retries
            calendar_data = await self._fetch_calendar_data_with_retries(start_date, end_date)
            
            # Parse response
            trading_days = self._parse_calendar_response(calendar_data)
            
            # Update cache
            self._calendar_cache[cache_key] = trading_days
            self._cache_timestamps[cache_key] = datetime.now(timezone.utc)
            
            logger.info(f"📅 Retrieved {len(trading_days)} trading days from Alpaca calendar")
            
            return trading_days
            
        except Exception as e:
            logger.error(f"❌ Failed to get trading calendar: {e}")
            
            # Return cached data if available
            cache_key = f"{start_date}_{end_date}"
            if cache_key in self._calendar_cache:
                logger.warning("⚠️ Using stale cached calendar due to API failure")
                return self._calendar_cache[cache_key]
            
            raise MarketDataException(f"Unable to get trading calendar from Alpaca: {e}")
    
    async def is_trading_day(self, target_date: date) -> bool:
        """
        Check if specific date is a trading day.
        
        Args:
            target_date: Date to check
            
        Returns:
            True if it's a trading day, False otherwise
        """
        try:
            # Get calendar for the specific date (plus small buffer)
            calendar = await self.get_trading_calendar(
                start_date=target_date,
                end_date=target_date + timedelta(days=1)
            )
            
            # Check if target date is in the trading calendar
            for trading_day in calendar:
                if trading_day.date == target_date:
                    return trading_day.is_trading_day
            
            # Not found in calendar - assume non-trading day
            return False
            
        except Exception as e:
            logger.error(f"❌ Error checking if {target_date} is trading day: {e}")
            # Conservative default - check if it's a weekday
            return target_date.weekday() < 5
    
    async def get_next_trading_day(self, from_date: Optional[date] = None) -> date:
        """
        Get next official trading day considering holidays.
        
        Args:
            from_date: Starting date (defaults to today)
            
        Returns:
            Next trading day
        """
        try:
            if from_date is None:
                from_date = date.today()
            
            # Look ahead up to 30 days to find next trading day
            end_date = from_date + timedelta(days=30)
            calendar = await self.get_trading_calendar(from_date, end_date)
            
            for trading_day in calendar:
                if trading_day.date > from_date and trading_day.is_trading_day:
                    return trading_day.date
            
            # Fallback - find next weekday
            next_day = from_date + timedelta(days=1)
            while next_day.weekday() >= 5:  # Skip weekends
                next_day += timedelta(days=1)
            
            logger.warning(f"⚠️ No trading day found in calendar, using weekday fallback: {next_day}")
            return next_day
            
        except Exception as e:
            logger.error(f"❌ Error finding next trading day: {e}")
            # Simple fallback
            next_day = (from_date or date.today()) + timedelta(days=1)
            while next_day.weekday() >= 5:  # Skip weekends
                next_day += timedelta(days=1)
            return next_day
    
    async def get_session_hours(self, trading_date: date) -> SessionHours:
        """
        Get official open/close times for specific trading day.
        
        Args:
            trading_date: Date to get session hours for
            
        Returns:
            SessionHours with official times
        """
        try:
            calendar = await self.get_trading_calendar(
                start_date=trading_date,
                end_date=trading_date
            )
            
            for trading_day in calendar:
                if trading_day.date == trading_date:
                    # Build SessionHours from TradingDay data
                    session_hours = SessionHours(
                        regular_open=trading_day.open_time,
                        regular_close=trading_day.close_time,
                        is_early_close=trading_day.is_early_close,
                        early_close_time=trading_day.early_close_time
                    )
                    
                    # Add extended hours (standard times)
                    # Premarket: 4:00 AM ET
                    premarket_time = trading_day.open_time.replace(hour=4, minute=0, second=0)
                    session_hours.premarket_open = premarket_time
                    
                    # After-hours: 8:00 PM ET (or early close time + 4 hours)
                    if trading_day.is_early_close and trading_day.early_close_time:
                        afterhours_end = trading_day.early_close_time + timedelta(hours=4)
                    else:
                        afterhours_end = trading_day.close_time.replace(hour=20, minute=0, second=0)
                    session_hours.postmarket_close = afterhours_end
                    
                    return session_hours
            
            raise MarketDataException(f"No session hours found for {trading_date}")
            
        except Exception as e:
            logger.error(f"❌ Error getting session hours for {trading_date}: {e}")
            raise MarketDataException(f"Unable to get session hours: {e}")
    
    async def get_holidays_in_range(self, start_date: date, end_date: date) -> List[date]:
        """
        Get list of market holidays in date range.
        
        Args:
            start_date: Start date
            end_date: End date
            
        Returns:
            List of holiday dates
        """
        try:
            calendar = await self.get_trading_calendar(start_date, end_date)
            
            holidays = []
            current_date = start_date
            
            while current_date <= end_date:
                # Check if current date is a weekday but not in trading calendar
                if current_date.weekday() < 5:  # Weekday
                    is_trading_day = any(
                        td.date == current_date and td.is_trading_day 
                        for td in calendar
                    )
                    
                    if not is_trading_day:
                        holidays.append(current_date)
                
                current_date += timedelta(days=1)
            
            return holidays
            
        except Exception as e:
            logger.error(f"❌ Error getting holidays in range: {e}")
            return []  # Return empty list on error
    
    async def _fetch_calendar_data_with_retries(
        self, 
        start_date: date, 
        end_date: date
    ) -> List[Dict[str, Any]]:
        """
        Fetch calendar data from Alpaca API with retry logic.
        
        Args:
            start_date: Start date for calendar
            end_date: End date for calendar
            
        Returns:
            Raw calendar API response data
            
        Raises:
            MarketDataException: If all retries fail
        """
        last_error = None
        
        for attempt in range(self._max_retries):
            try:
                logger.debug(f"📡 Alpaca Calendar API request (attempt {attempt + 1}/{self._max_retries})")
                
                headers = {
                    'APCA-API-KEY-ID': self._api_key,
                    'APCA-API-SECRET-KEY': self._secret_key,
                    'Content-Type': 'application/json'
                }
                
                # Build query parameters
                params = {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        self._calendar_endpoint,
                        headers=headers,
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=self._timeout)
                    ) as response:
                        
                        if response.status == 200:
                            data = await response.json()
                            logger.debug(f"✅ Calendar API success: {len(data)} days returned")
                            return data
                        else:
                            error_text = await response.text()
                            raise MarketDataException(f"HTTP {response.status}: {error_text}")
                            
            except asyncio.TimeoutError as e:
                last_error = f"Timeout after {self._timeout}s"
                logger.warning(f"⏰ Calendar API timeout (attempt {attempt + 1})")
            except aiohttp.ClientError as e:
                last_error = f"Network error: {str(e)}"
                logger.warning(f"🌐 Calendar API network error (attempt {attempt + 1}): {e}")
            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                logger.warning(f"❌ Calendar API unexpected error (attempt {attempt + 1}): {e}")
            
            # Wait before retry (exponential backoff)
            if attempt < self._max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s...
                logger.debug(f"⏳ Waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)
        
        raise MarketDataException(f"All {self._max_retries} Calendar API attempts failed. Last error: {last_error}")
    
    def _parse_calendar_response(self, calendar_data: List[Dict[str, Any]]) -> List[TradingDay]:
        """
        Parse Alpaca Calendar API response into TradingDay objects.
        
        Args:
            calendar_data: Raw response from Alpaca Calendar API
            
        Returns:
            List of TradingDay objects
        """
        trading_days = []
        
        try:
            for day_data in calendar_data:
                # Extract fields
                date_str = day_data.get('date')
                open_str = day_data.get('open')
                close_str = day_data.get('close')
                
                if not all([date_str, open_str, close_str]):
                    logger.warning(f"⚠️ Incomplete calendar data: {day_data}")
                    continue
                
                # Parse date
                trading_date = datetime.fromisoformat(date_str).date()
                
                # Parse open/close times
                open_time = self._parse_time_with_date(open_str, trading_date)
                close_time = self._parse_time_with_date(close_str, trading_date)
                
                # Detect early close (close time before 4 PM ET)
                is_early_close = close_time.hour < 16
                early_close_time = close_time if is_early_close else None
                
                trading_day = TradingDay(
                    date=trading_date,
                    open_time=open_time,
                    close_time=close_time,
                    is_trading_day=True,  # If it's in the calendar, it's a trading day
                    is_early_close=is_early_close,
                    early_close_time=early_close_time,
                    raw_data=day_data
                )
                
                trading_days.append(trading_day)
                
                if is_early_close:
                    logger.info(f"📅 Early close detected: {trading_date} closes at {close_time.strftime('%I:%M %p')}")
            
            return trading_days
            
        except Exception as e:
            logger.error(f"❌ Error parsing calendar response: {e}")
            logger.error(f"Raw calendar data: {calendar_data}")
            raise MarketDataException(f"Failed to parse Alpaca calendar response: {e}")
    
    def _parse_time_with_date(self, time_str: str, trading_date: date) -> datetime:
        """
        Parse time string and combine with trading date.
        
        Args:
            time_str: Time string from API (e.g., "09:30")
            trading_date: Date to combine with time
            
        Returns:
            Complete datetime object in Eastern timezone
        """
        try:
            # Parse time (assume format like "09:30" or "09:30:00")
            if ':' in time_str:
                time_parts = time_str.split(':')
                hour = int(time_parts[0])
                minute = int(time_parts[1])
                second = int(time_parts[2]) if len(time_parts) > 2 else 0
            else:
                raise ValueError(f"Invalid time format: {time_str}")
            
            # Create datetime in Eastern timezone
            import pytz
            eastern = pytz.timezone('America/New_York')
            
            naive_datetime = datetime.combine(trading_date, datetime.min.time().replace(
                hour=hour, minute=minute, second=second
            ))
            
            # Localize to Eastern timezone, then convert to UTC
            eastern_datetime = eastern.localize(naive_datetime)
            utc_datetime = eastern_datetime.astimezone(timezone.utc)
            
            return utc_datetime
            
        except Exception as e:
            logger.error(f"❌ Error parsing time '{time_str}': {e}")
            raise ValueError(f"Invalid time format: {time_str}")
    
    def _is_calendar_cache_valid(self, cache_key: str) -> bool:
        """Check if cached calendar data is still valid."""
        if cache_key not in self._calendar_cache or cache_key not in self._cache_timestamps:
            return False
        
        age_hours = (datetime.now(timezone.utc) - self._cache_timestamps[cache_key]).total_seconds() / 3600
        return age_hours < self._cache_duration_hours
    
    def clear_cache(self) -> None:
        """Clear all cached calendar data."""
        self._calendar_cache.clear()
        self._cache_timestamps.clear()
        logger.info("🧹 Calendar cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring."""
        return {
            'cached_ranges': len(self._calendar_cache),
            'cache_keys': list(self._calendar_cache.keys()),
            'oldest_cache_age_hours': self._get_oldest_cache_age_hours()
        }
    
    def _get_oldest_cache_age_hours(self) -> float:
        """Get age of oldest cache entry in hours."""
        if not self._cache_timestamps:
            return 0.0
        
        oldest_timestamp = min(self._cache_timestamps.values())
        age_hours = (datetime.now(timezone.utc) - oldest_timestamp).total_seconds() / 3600
        return age_hours