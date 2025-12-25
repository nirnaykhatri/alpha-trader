"""
Market Session Provider - Calendar-Aware Market Hours Detection.

Provides accurate market hours detection using the Alpaca Calendar API,
which includes holidays, early closes, and actual trading schedules.

Replaces hardcoded market hours logic with broker-backed calendar data.

Author: Trading Bot Team
Date: 2025
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import pytz

from src.core.logging_config import get_logger
from src.interfaces import IConfigurationManager
from src.utils import run_blocking

logger = get_logger(__name__)


class MarketStatus(Enum):
    """Market status enumeration."""
    OPEN = "open"
    PRE_MARKET = "pre_market"
    POST_MARKET = "post_market"
    CLOSED = "closed"
    EARLY_CLOSE = "early_close"
    HOLIDAY = "holiday"


@dataclass
class MarketSession:
    """Represents a market trading session."""
    date: date
    open_time: datetime
    close_time: datetime
    pre_market_start: datetime
    post_market_end: datetime
    is_early_close: bool = False
    session_open: Optional[datetime] = None  # For partial days
    session_close: Optional[datetime] = None  # For partial days


@dataclass
class MarketStatusInfo:
    """Current market status information."""
    status: MarketStatus
    is_regular_hours: bool
    is_pre_market: bool
    is_post_market: bool
    is_extended_hours: bool
    is_closed: bool
    is_weekend: bool
    is_holiday: bool
    current_time_ny: datetime
    next_open: Optional[datetime] = None
    next_close: Optional[datetime] = None
    session: Optional[MarketSession] = None


class MarketSessionProvider:
    """
    Provides accurate market hours detection using broker calendar data.
    
    Uses the Alpaca Calendar API to determine actual trading hours,
    including holidays, early closes, and special trading sessions.
    
    Falls back to hardcoded hours if API is unavailable.
    
    Example:
        ```python
        provider = MarketSessionProvider(config, trading_client)
        await provider.initialize()
        
        status = await provider.get_market_status()
        if status.is_regular_hours:
            # Execute trade
            pass
        elif status.is_holiday:
            logger.info(f"Market closed for holiday, opens {status.next_open}")
        ```
    """
    
    def __init__(
        self,
        config: IConfigurationManager,
        trading_client: Optional[Any] = None
    ):
        """
        Initialize the market session provider.
        
        Args:
            config: Configuration manager
            trading_client: Optional Alpaca trading client for calendar API
        """
        self._config = config
        self._trading_client = trading_client
        self._market_tz = pytz.timezone('America/New_York')
        
        # Calendar cache
        self._calendar_cache: Dict[str, MarketSession] = {}
        self._cache_expiry: Optional[datetime] = None
        self._cache_duration = timedelta(hours=12)  # Refresh twice daily
        
        # Holiday list (fallback if API unavailable)
        self._known_holidays_2025 = {
            date(2025, 1, 1),   # New Year's Day
            date(2025, 1, 20),  # MLK Day
            date(2025, 2, 17),  # Presidents Day
            date(2025, 4, 18),  # Good Friday
            date(2025, 5, 26),  # Memorial Day
            date(2025, 6, 19),  # Juneteenth
            date(2025, 7, 4),   # Independence Day
            date(2025, 9, 1),   # Labor Day
            date(2025, 11, 27), # Thanksgiving
            date(2025, 12, 25), # Christmas
        }
        
        # Early close dates (1 PM ET close)
        self._early_close_2025 = {
            date(2025, 7, 3),   # Day before Independence Day
            date(2025, 11, 28), # Day after Thanksgiving
            date(2025, 12, 24), # Christmas Eve
        }
        
        logger.info("MarketSessionProvider initialized")
    
    async def initialize(self) -> None:
        """Initialize the provider and load calendar data."""
        try:
            await self._refresh_calendar_cache()
            logger.info("Market calendar loaded successfully")
        except Exception as e:
            logger.warning(f"Failed to load market calendar, using fallback: {e}")
    
    async def get_market_status(self) -> MarketStatusInfo:
        """
        Get the current market status with full session information.
        
        Returns:
            MarketStatusInfo with detailed status and session data
        """
        now_ny = datetime.now(self._market_tz)
        today = now_ny.date()
        
        # Check cache freshness
        if self._cache_expiry and datetime.now() > self._cache_expiry:
            try:
                await self._refresh_calendar_cache()
            except Exception as e:
                logger.warning(f"Calendar refresh failed: {e}")
        
        # Get session for today
        session = await self._get_session(today)
        
        # Determine status
        return self._calculate_status(now_ny, session)
    
    async def get_market_status_dict(self) -> Dict[str, Any]:
        """
        Get market status as a dictionary (backward compatible).
        
        Returns:
            Dictionary with market status information
        """
        status = await self.get_market_status()
        return {
            'status': status.status.value.upper(),
            'is_regular_hours': status.is_regular_hours,
            'is_pre_market': status.is_pre_market,
            'is_post_market': status.is_post_market,
            'is_extended_hours': status.is_extended_hours,
            'is_closed': status.is_closed,
            'is_weekend': status.is_weekend,
            'is_holiday': status.is_holiday,
            'current_time_ny': status.current_time_ny,
            'next_open': status.next_open,
            'next_close': status.next_close,
        }
    
    async def is_market_open(self) -> bool:
        """Check if market is currently in regular trading hours."""
        status = await self.get_market_status()
        return status.is_regular_hours
    
    async def is_trading_allowed(self) -> bool:
        """Check if trading is allowed (regular or extended hours)."""
        status = await self.get_market_status()
        return status.is_regular_hours or status.is_extended_hours
    
    async def get_next_market_open(self) -> Optional[datetime]:
        """Get the next market open time."""
        status = await self.get_market_status()
        return status.next_open
    
    async def _refresh_calendar_cache(self) -> None:
        """Refresh the calendar cache from Alpaca API."""
        if not self._trading_client:
            logger.debug("No trading client, using fallback calendar")
            return
        
        try:
            # Get calendar for next 30 days
            start_date = date.today()
            end_date = start_date + timedelta(days=30)
            
            calendar_data = await run_blocking(
                self._trading_client.get_calendar,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d")
            )
            
            for day in calendar_data:
                day_date = day.date if hasattr(day, 'date') else date.fromisoformat(str(day.date))
                
                # Parse open/close times
                open_time = self._parse_time(day_date, day.open)
                close_time = self._parse_time(day_date, day.close)
                
                # Check for early close
                is_early = close_time.hour < 16
                
                session = MarketSession(
                    date=day_date,
                    open_time=open_time,
                    close_time=close_time,
                    pre_market_start=self._market_tz.localize(
                        datetime.combine(day_date, datetime.min.time().replace(hour=4))
                    ),
                    post_market_end=self._market_tz.localize(
                        datetime.combine(day_date, datetime.min.time().replace(hour=20))
                    ),
                    is_early_close=is_early
                )
                
                self._calendar_cache[day_date.isoformat()] = session
            
            self._cache_expiry = datetime.now() + self._cache_duration
            logger.debug(f"Calendar cache refreshed with {len(calendar_data)} days")
            
        except Exception as e:
            logger.error(f"Failed to fetch calendar from Alpaca: {e}")
            raise
    
    def _parse_time(self, day_date: date, time_str: str) -> datetime:
        """Parse a time string into a timezone-aware datetime."""
        hour, minute = map(int, str(time_str).split(":"))
        dt = datetime.combine(day_date, datetime.min.time().replace(hour=hour, minute=minute))
        return self._market_tz.localize(dt)
    
    async def _get_session(self, target_date: date) -> Optional[MarketSession]:
        """Get the market session for a specific date."""
        # Check cache first
        cache_key = target_date.isoformat()
        if cache_key in self._calendar_cache:
            return self._calendar_cache[cache_key]
        
        # Check if weekend
        if target_date.weekday() >= 5:
            return None
        
        # Check known holidays (fallback)
        if target_date in self._known_holidays_2025:
            return None
        
        # Build fallback session
        is_early = target_date in self._early_close_2025
        close_hour = 13 if is_early else 16
        
        return MarketSession(
            date=target_date,
            open_time=self._market_tz.localize(
                datetime.combine(target_date, datetime.min.time().replace(hour=9, minute=30))
            ),
            close_time=self._market_tz.localize(
                datetime.combine(target_date, datetime.min.time().replace(hour=close_hour))
            ),
            pre_market_start=self._market_tz.localize(
                datetime.combine(target_date, datetime.min.time().replace(hour=4))
            ),
            post_market_end=self._market_tz.localize(
                datetime.combine(target_date, datetime.min.time().replace(hour=20))
            ),
            is_early_close=is_early
        )
    
    def _calculate_status(
        self,
        now_ny: datetime,
        session: Optional[MarketSession]
    ) -> MarketStatusInfo:
        """Calculate detailed market status from session data."""
        is_weekend = now_ny.weekday() >= 5
        today = now_ny.date()
        is_holiday = today in self._known_holidays_2025 or session is None
        
        if is_weekend:
            return MarketStatusInfo(
                status=MarketStatus.CLOSED,
                is_regular_hours=False,
                is_pre_market=False,
                is_post_market=False,
                is_extended_hours=False,
                is_closed=True,
                is_weekend=True,
                is_holiday=False,
                current_time_ny=now_ny,
                next_open=self._find_next_open(today),
                session=session
            )
        
        if is_holiday:
            return MarketStatusInfo(
                status=MarketStatus.HOLIDAY,
                is_regular_hours=False,
                is_pre_market=False,
                is_post_market=False,
                is_extended_hours=False,
                is_closed=True,
                is_weekend=False,
                is_holiday=True,
                current_time_ny=now_ny,
                next_open=self._find_next_open(today),
                session=session
            )
        
        # Session exists - determine current status
        is_regular = session.open_time <= now_ny < session.close_time
        is_pre = session.pre_market_start <= now_ny < session.open_time
        is_post = session.close_time <= now_ny < session.post_market_end
        is_extended = is_pre or is_post
        is_closed = not (is_regular or is_extended)
        
        if is_regular:
            status = MarketStatus.EARLY_CLOSE if session.is_early_close else MarketStatus.OPEN
        elif is_pre:
            status = MarketStatus.PRE_MARKET
        elif is_post:
            status = MarketStatus.POST_MARKET
        else:
            status = MarketStatus.CLOSED
        
        return MarketStatusInfo(
            status=status,
            is_regular_hours=is_regular,
            is_pre_market=is_pre,
            is_post_market=is_post,
            is_extended_hours=is_extended,
            is_closed=is_closed,
            is_weekend=False,
            is_holiday=False,
            current_time_ny=now_ny,
            next_open=session.open_time if now_ny < session.open_time else self._find_next_open(today),
            next_close=session.close_time if is_regular else None,
            session=session
        )
    
    def _find_next_open(self, from_date: date) -> Optional[datetime]:
        """Find the next market open date/time."""
        for i in range(1, 8):  # Look ahead up to a week
            check_date = from_date + timedelta(days=i)
            
            # Skip weekends
            if check_date.weekday() >= 5:
                continue
            
            # Skip known holidays
            if check_date in self._known_holidays_2025:
                continue
            
            # Found a trading day
            cache_key = check_date.isoformat()
            if cache_key in self._calendar_cache:
                return self._calendar_cache[cache_key].open_time
            
            # Fallback to 9:30 AM
            return self._market_tz.localize(
                datetime.combine(check_date, datetime.min.time().replace(hour=9, minute=30))
            )
        
        return None
