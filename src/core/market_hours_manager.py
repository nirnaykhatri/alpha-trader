"""
Alpaca Integrated Market Hours Manager - Comprehensive market hours management with Alpaca API integration.
Provides intelligent market status detection, session management, and bot lifecycle control.
"""

import asyncio
from typing import Dict, Any, Optional, Tuple, List, TYPE_CHECKING
from datetime import datetime, timezone, date, timedelta
from dataclasses import dataclass
from enum import Enum
import pytz

from ..interfaces import IConfigurationManager
from ..exceptions import MarketDataException, ConfigurationException
from ..core.logging_config import get_logger
from .market_status_provider import AlpacaMarketStatusProvider, MarketSession, MarketStatusResponse
from .calendar_provider import AlpacaCalendarProvider, TradingDay, SessionHours

if TYPE_CHECKING:
    from .extended_hours_manager import ExtendedHoursManager

logger = get_logger(__name__)


@dataclass
class MarketStatusInfo:
    """Complete market status information combining Clock and Calendar APIs."""
    is_open: bool
    current_session: MarketSession
    next_open: datetime
    next_close: datetime
    is_trading_day: bool
    session_hours: Optional[SessionHours]
    source: str  # "alpaca_api" or "fallback_config"
    extended_hours_enabled: bool
    bot_should_be_active: bool
    activation_reason: str
    
    # Additional metadata
    time_to_next_session_minutes: float
    is_weekend: bool
    is_holiday: bool
    market_timezone: str = "America/New_York"


class FallbackSchedule:
    """Static fallback schedule when Alpaca APIs are unavailable."""
    
    def __init__(self, config: IConfigurationManager):
        self._config = config
        self._eastern = pytz.timezone('America/New_York')
        
        # Load fallback schedule from config
        self.premarket_start = self._parse_time_config("market_hours.fallback_schedule.premarket.start_time", "04:00")
        self.premarket_end = self._parse_time_config("market_hours.fallback_schedule.premarket.end_time", "09:30")
        self.regular_start = self._parse_time_config("market_hours.fallback_schedule.regular_session.start_time", "09:30")
        self.regular_end = self._parse_time_config("market_hours.fallback_schedule.regular_session.end_time", "16:00")
        self.postmarket_start = self._parse_time_config("market_hours.fallback_schedule.postmarket.start_time", "16:00")
        self.postmarket_end = self._parse_time_config("market_hours.fallback_schedule.postmarket.end_time", "20:00")
    
    def _parse_time_config(self, config_key: str, default: str) -> tuple:
        """Parse time configuration into (hour, minute) tuple."""
        time_str = self._config.get_config(config_key, default)
        parts = time_str.split(":")
        return (int(parts[0]), int(parts[1]))
    
    def get_market_status(self, current_time: datetime) -> MarketStatusInfo:
        """Get market status using static fallback schedule."""
        eastern_time = current_time.astimezone(self._eastern)
        
        # Check if weekend
        is_weekend = eastern_time.weekday() >= 5
        if is_weekend:
            next_open = self._get_next_weekday_time(eastern_time, self.regular_start)
            next_close = self._get_next_weekday_time(eastern_time, self.regular_end)
            
            return MarketStatusInfo(
                is_open=False,
                current_session=MarketSession.WEEKEND,
                next_open=next_open,
                next_close=next_close,
                is_trading_day=False,
                session_hours=None,
                source="fallback_config",
                extended_hours_enabled=True,
                bot_should_be_active=False,
                activation_reason="weekend",
                time_to_next_session_minutes=(next_open - current_time).total_seconds() / 60,
                is_weekend=True,
                is_holiday=False
            )
        
        # Determine current session
        current_hour_minute = (eastern_time.hour, eastern_time.minute)
        
        if self._is_time_in_range(current_hour_minute, self.premarket_start, self.premarket_end):
            current_session = MarketSession.PREMARKET
            is_open = False  # Extended hours, not regular market
            next_session_time = self._get_today_time(eastern_time, self.regular_start)
        elif self._is_time_in_range(current_hour_minute, self.regular_start, self.regular_end):
            current_session = MarketSession.REGULAR
            is_open = True
            next_session_time = self._get_today_time(eastern_time, self.regular_end)
        elif self._is_time_in_range(current_hour_minute, self.postmarket_start, self.postmarket_end):
            current_session = MarketSession.POSTMARKET
            is_open = False  # Extended hours, not regular market
            next_session_time = self._get_next_weekday_time(eastern_time, self.regular_start)
        else:
            current_session = MarketSession.CLOSED
            is_open = False
            # Find next session
            if current_hour_minute < self.premarket_start:
                next_session_time = self._get_today_time(eastern_time, self.premarket_start)
            else:
                next_session_time = self._get_next_weekday_time(eastern_time, self.premarket_start)
        
        return MarketStatusInfo(
            is_open=is_open,
            current_session=current_session,
            next_open=next_session_time if not is_open else self._get_next_weekday_time(eastern_time, self.regular_start),
            next_close=next_session_time if is_open else self._get_today_time(eastern_time, self.regular_end),
            is_trading_day=True,
            session_hours=None,
            source="fallback_config",
            extended_hours_enabled=True,
            bot_should_be_active=True,  # Will be refined by manager
            activation_reason="fallback_schedule",
            time_to_next_session_minutes=(next_session_time - current_time).total_seconds() / 60,
            is_weekend=False,
            is_holiday=False
        )
    
    def _is_time_in_range(self, current: tuple, start: tuple, end: tuple) -> bool:
        """Check if current time is within range."""
        current_minutes = current[0] * 60 + current[1]
        start_minutes = start[0] * 60 + start[1]
        end_minutes = end[0] * 60 + end[1]
        
        return start_minutes <= current_minutes < end_minutes
    
    def _get_today_time(self, base_time: datetime, time_tuple: tuple) -> datetime:
        """Get datetime for today with specified time."""
        return base_time.replace(
            hour=time_tuple[0], minute=time_tuple[1], second=0, microsecond=0
        ).astimezone(timezone.utc)
    
    def _get_next_weekday_time(self, base_time: datetime, time_tuple: tuple) -> datetime:
        """Get datetime for next weekday with specified time."""
        next_day = base_time + timedelta(days=1)
        while next_day.weekday() >= 5:  # Skip weekends
            next_day += timedelta(days=1)
        
        return next_day.replace(
            hour=time_tuple[0], minute=time_tuple[1], second=0, microsecond=0
        ).astimezone(timezone.utc)


class AlpacaIntegratedMarketHoursManager:
    """
    Market Hours Manager that uses Alpaca's Clock and Calendar APIs
    as the primary source of market status information.
    """
    
    def __init__(self, config: IConfigurationManager):
        """
        Initialize market hours manager with Alpaca API integration.
        
        Args:
            config: Configuration manager instance
        """
        self._config = config
        
        # Initialize API providers
        try:
            self._status_provider = AlpacaMarketStatusProvider(config)
            self._calendar_provider = AlpacaCalendarProvider(config)
            logger.info("✅ Alpaca API providers initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Alpaca providers: {e}")
            self._status_provider = None
            self._calendar_provider = None
        
        # Initialize fallback schedule
        self._fallback_schedule = FallbackSchedule(config)
        
        # Extended hours manager (initialized lazily)
        self._extended_hours_manager: Optional['ExtendedHoursManager'] = None
        
        # Configuration
        self._use_clock_api = config.get_config("market_hours.alpaca_integration.use_clock_api", True)
        self._use_calendar_api = config.get_config("market_hours.alpaca_integration.use_calendar_api", True)
        self._fallback_on_api_failure = config.get_config("market_hours.fallback_on_api_failure", True)
        self._max_consecutive_failures = config.get_config("market_hours.max_consecutive_api_failures", 3)
        self._auto_start_stop = config.get_config("market_hours.auto_start_stop", True)
        self._emergency_override = config.get_config("market_hours.emergency_override", False)
        
        # Buffer configuration
        self._start_buffer_minutes = config.get_config("market_hours.buffers.start_before_premarket_minutes", 15)
        self._stop_buffer_minutes = config.get_config("market_hours.buffers.stop_after_postmarket_minutes", 15)
        self._polling_interval = config.get_config("market_hours.buffers.api_polling_interval_seconds", 300)
        
        # Extended hours configuration
        self._premarket_enabled = config.get_config("market_hours.extended_hours.premarket_enabled", True)
        self._afterhours_enabled = config.get_config("market_hours.extended_hours.afterhours_enabled", True)
        self._data_streaming_enabled = config.get_config("market_hours.extended_hours.data_streaming_enabled", True)
        
        # State tracking
        self._consecutive_api_failures = 0
        self._using_fallback = False
        self._last_successful_api_call = None
        self._current_status: Optional[MarketStatusInfo] = None
        
        logger.info(f"AlpacaIntegratedMarketHoursManager initialized - API: {self._use_clock_api and self._status_provider is not None}, Fallback: {self._fallback_on_api_failure}")
    
    async def get_current_market_status(self, force_refresh: bool = False) -> MarketStatusInfo:
        """
        Get comprehensive market status using Alpaca APIs with intelligent caching.
        Falls back to static configuration if APIs are unavailable.
        
        Args:
            force_refresh: Force refresh from API even if cached
            
        Returns:
            Complete market status information
        """
        try:
            # Emergency override - always active
            if self._emergency_override:
                logger.warning("🚨 Emergency override active - bot will remain active regardless of market status")
                return self._create_override_status()
            
            # Try Alpaca APIs first
            if not self._using_fallback and self._status_provider and self._use_clock_api:
                try:
                    status_response = await self._status_provider.get_market_status()
                    
                    # Get additional calendar information if enabled
                    session_hours = None
                    is_trading_day = True
                    is_holiday = False
                    
                    if self._calendar_provider and self._use_calendar_api:
                        try:
                            today = datetime.now().date()
                            is_trading_day = await self._calendar_provider.is_trading_day(today)
                            if is_trading_day:
                                session_hours = await self._calendar_provider.get_session_hours(today)
                            else:
                                is_holiday = today.weekday() < 5  # Holiday if weekday but not trading day
                        except Exception as calendar_error:
                            logger.warning(f"⚠️ Calendar API failed, using clock data only: {calendar_error}")
                    
                    # Build comprehensive status
                    market_status = await self._build_comprehensive_status(
                        status_response, session_hours, is_trading_day, is_holiday
                    )
                    
                    # Reset failure tracking on success
                    self._consecutive_api_failures = 0
                    self._using_fallback = False
                    self._last_successful_api_call = datetime.now(timezone.utc)
                    self._current_status = market_status
                    
                    return market_status
                    
                except Exception as api_error:
                    logger.error(f"❌ Alpaca API failed: {api_error}")
                    return await self._handle_api_failure(api_error)
            
            # Use fallback schedule
            return await self._get_fallback_market_status()
            
        except Exception as e:
            logger.error(f"❌ Critical error in market status detection: {e}")
            return await self._get_emergency_fallback_status()
    
    async def should_bot_be_active(self) -> Tuple[bool, str]:
        """
        Determine if bot should be active based on Alpaca market status
        and configured buffer times.
        
        Returns:
            Tuple of (should_be_active, reason)
        """
        try:
            status = await self.get_current_market_status()
            
            # Emergency override
            if self._emergency_override:
                return True, "emergency_override"
            
            # Auto start/stop disabled - always active
            if not self._auto_start_stop:
                return True, "auto_start_stop_disabled"
            
            # Check if already determined by status
            return status.bot_should_be_active, status.activation_reason
            
        except Exception as e:
            logger.error(f"❌ Error determining bot activation: {e}")
            # Conservative default - activate if unsure
            return True, f"error_fallback_{str(e)[:30]}"
    
    async def get_next_activation_time(self) -> datetime:
        """
        Calculate when bot should next activate using Alpaca timing data.
        Accounts for weekends, holidays, and buffer times.
        
        Returns:
            Next activation time
        """
        try:
            status = await self.get_current_market_status()
            
            if status.bot_should_be_active:
                return datetime.now(timezone.utc)  # Already should be active
            
            # Calculate next activation considering buffers
            next_session_time = status.next_open
            
            # Apply start buffer
            next_activation = next_session_time - timedelta(minutes=self._start_buffer_minutes)
            
            # Ensure activation time is in the future
            now = datetime.now(timezone.utc)
            if next_activation <= now:
                next_activation = now + timedelta(minutes=1)
            
            return next_activation
            
        except Exception as e:
            logger.error(f"❌ Error calculating next activation time: {e}")
            # Fallback - activate in 1 hour
            return datetime.now(timezone.utc) + timedelta(hours=1)
    
    async def wait_for_next_market_session(self) -> None:
        """
        Intelligently wait until next trading session using Alpaca timing data.
        Includes periodic status checks and graceful interruption handling.
        """
        try:
            while True:
                should_be_active, reason = await self.should_bot_be_active()
                
                if should_be_active:
                    logger.info(f"🚀 Bot should be active: {reason}")
                    break
                
                next_activation = await self.get_next_activation_time()
                wait_minutes = (next_activation - datetime.now(timezone.utc)).total_seconds() / 60
                
                if wait_minutes <= 0:
                    logger.info("⏰ Activation time reached")
                    break
                
                logger.info(f"💤 Waiting {wait_minutes:.1f} minutes until next activation ({next_activation.strftime('%Y-%m-%d %H:%M:%S UTC')})")
                
                # Wait in intervals for responsive interruption
                wait_interval_minutes = min(wait_minutes, self._polling_interval / 60)
                await asyncio.sleep(wait_interval_minutes * 60)
                
        except asyncio.CancelledError:
            logger.info("⛔ Market session wait cancelled")
            raise
        except Exception as e:
            logger.error(f"❌ Error waiting for market session: {e}")
    
    async def _build_comprehensive_status(
        self,
        status_response: MarketStatusResponse,
        session_hours: Optional[SessionHours],
        is_trading_day: bool,
        is_holiday: bool
    ) -> MarketStatusInfo:
        """Build comprehensive market status from API responses."""
        
        # Determine if bot should be active
        bot_should_be_active, activation_reason = await self._determine_bot_activation(
            status_response, session_hours, is_trading_day
        )
        
        # Calculate time to next session
        now = datetime.now(timezone.utc)
        if status_response.is_open:
            time_to_next = (status_response.next_close - now).total_seconds() / 60
        else:
            time_to_next = (status_response.next_open - now).total_seconds() / 60
        
        return MarketStatusInfo(
            is_open=status_response.is_open,
            current_session=status_response.current_session,
            next_open=status_response.next_open,
            next_close=status_response.next_close,
            is_trading_day=is_trading_day,
            session_hours=session_hours,
            source="alpaca_api",
            extended_hours_enabled=self._premarket_enabled or self._afterhours_enabled,
            bot_should_be_active=bot_should_be_active,
            activation_reason=activation_reason,
            time_to_next_session_minutes=time_to_next,
            is_weekend=now.weekday() >= 5,
            is_holiday=is_holiday
        )
    
    async def _determine_bot_activation(
        self,
        status_response: MarketStatusResponse,
        session_hours: Optional[SessionHours],
        is_trading_day: bool
    ) -> Tuple[bool, str]:
        """Determine if bot should be active based on current status."""
        
        if not is_trading_day:
            return False, "not_trading_day"
        
        if status_response.is_open:
            return True, f"market_open_{status_response.current_session.value}"
        
        now = datetime.now(timezone.utc)
        
        # Check extended hours activation
        if status_response.current_session == MarketSession.PREMARKET and self._premarket_enabled:
            return True, "premarket_enabled"
        
        if status_response.current_session == MarketSession.POSTMARKET and self._afterhours_enabled:
            return True, "postmarket_enabled"
        
        # Check buffer periods
        time_to_open = (status_response.next_open - now).total_seconds() / 60
        if 0 < time_to_open <= self._start_buffer_minutes:
            return True, f"pre_open_buffer_{time_to_open:.1f}min"
        
        # Check if we're within stop buffer after close
        time_since_close = (now - status_response.next_close).total_seconds() / 60
        if 0 < time_since_close <= self._stop_buffer_minutes:
            return True, f"post_close_buffer_{time_since_close:.1f}min"
        
        return False, f"market_closed_{status_response.current_session.value}"
    
    async def _handle_api_failure(self, error: Exception) -> MarketStatusInfo:
        """Handle Alpaca API failures gracefully with fallback logic."""
        self._consecutive_api_failures += 1
        
        logger.error(f"❌ API failure #{self._consecutive_api_failures}: {error}")
        
        # Switch to fallback mode if too many failures
        if self._consecutive_api_failures >= self._max_consecutive_failures:
            if self._fallback_on_api_failure:
                logger.warning(f"⚠️ Switching to fallback mode after {self._consecutive_api_failures} failures")
                self._using_fallback = True
            else:
                logger.error("❌ API failures exceeded limit and fallback disabled")
                raise MarketDataException(f"Alpaca API unavailable after {self._consecutive_api_failures} attempts")
        
        # Try to return cached data or fallback
        if self._current_status:
            logger.warning("📋 Using cached market status due to API failure")
            return self._current_status
        
        return await self._get_fallback_market_status()
    
    async def _get_fallback_market_status(self) -> MarketStatusInfo:
        """Get market status using fallback static schedule."""
        logger.info("📋 Using fallback market status schedule")
        
        current_time = datetime.now(timezone.utc)
        fallback_status = self._fallback_schedule.get_market_status(current_time)
        
        # Refine bot activation based on manager configuration
        should_be_active, reason = self._refine_fallback_activation(fallback_status)
        fallback_status.bot_should_be_active = should_be_active
        fallback_status.activation_reason = reason
        
        return fallback_status
    
    def _refine_fallback_activation(self, fallback_status: MarketStatusInfo) -> Tuple[bool, str]:
        """Refine fallback activation decision based on manager config."""
        
        if not self._auto_start_stop:
            return True, "auto_start_stop_disabled_fallback"
        
        if fallback_status.is_weekend:
            return False, "weekend_fallback"
        
        if fallback_status.current_session == MarketSession.REGULAR:
            return True, "regular_hours_fallback"
        
        if fallback_status.current_session == MarketSession.PREMARKET and self._premarket_enabled:
            return True, "premarket_enabled_fallback"
        
        if fallback_status.current_session == MarketSession.POSTMARKET and self._afterhours_enabled:
            return True, "postmarket_enabled_fallback"
        
        # Check buffer periods for fallback
        now = datetime.now(timezone.utc)
        time_to_open = (fallback_status.next_open - now).total_seconds() / 60
        if 0 < time_to_open <= self._start_buffer_minutes:
            return True, f"pre_open_buffer_fallback_{time_to_open:.1f}min"
        
        return False, f"market_closed_fallback_{fallback_status.current_session.value}"
    
    async def _get_emergency_fallback_status(self) -> MarketStatusInfo:
        """Emergency fallback when all else fails."""
        logger.warning("🚨 Using emergency fallback market status")
        
        now = datetime.now(timezone.utc)
        
        return MarketStatusInfo(
            is_open=False,
            current_session=MarketSession.CLOSED,
            next_open=now + timedelta(hours=1),
            next_close=now + timedelta(hours=2),
            is_trading_day=True,
            session_hours=None,
            source="emergency_fallback",
            extended_hours_enabled=True,
            bot_should_be_active=True,  # Conservative - keep bot active
            activation_reason="emergency_fallback",
            time_to_next_session_minutes=60.0,
            is_weekend=now.weekday() >= 5,
            is_holiday=False
        )
    
    def _create_override_status(self) -> MarketStatusInfo:
        """Create status for emergency override mode."""
        now = datetime.now(timezone.utc)
        
        return MarketStatusInfo(
            is_open=True,  # Override - always "open"
            current_session=MarketSession.REGULAR,
            next_open=now,
            next_close=now + timedelta(hours=24),
            is_trading_day=True,
            session_hours=None,
            source="emergency_override",
            extended_hours_enabled=True,
            bot_should_be_active=True,
            activation_reason="emergency_override",
            time_to_next_session_minutes=0.0,
            is_weekend=False,
            is_holiday=False
        )
    
    # Public API methods for monitoring and control
    
    async def attempt_api_recovery(self) -> bool:
        """Attempt to restore Alpaca API connectivity."""
        if not self._using_fallback:
            return True  # Not in fallback mode
        
        try:
            logger.info("🔄 Attempting Alpaca API recovery...")
            
            if self._status_provider:
                await self._status_provider.get_market_status()
                logger.info("✅ Alpaca API recovery successful")
                self._using_fallback = False
                self._consecutive_api_failures = 0
                return True
                
        except Exception as e:
            logger.warning(f"❌ API recovery failed: {e}")
        
        return False
    
    def get_connection_status(self) -> Dict[str, Any]:
        """Get current connection status for monitoring."""
        return {
            'using_fallback': self._using_fallback,
            'consecutive_failures': self._consecutive_api_failures,
            'last_successful_api_call': self._last_successful_api_call.isoformat() if self._last_successful_api_call else None,
            'status_provider_available': self._status_provider is not None,
            'calendar_provider_available': self._calendar_provider is not None,
            'emergency_override': self._emergency_override,
            'auto_start_stop_enabled': self._auto_start_stop
        }
    
    def set_emergency_override(self, enabled: bool) -> None:
        """Enable/disable emergency override mode."""
        self._emergency_override = enabled
        logger.warning(f"🚨 Emergency override {'ENABLED' if enabled else 'DISABLED'}")
    
    async def force_refresh_status(self) -> MarketStatusInfo:
        """Force refresh market status from API."""
        return await self.get_current_market_status(force_refresh=True)
    
    def set_extended_hours_manager(self, extended_hours_manager: 'ExtendedHoursManager') -> None:
        """
        Set the extended hours manager for advanced trading session coordination.
        
        Args:
            extended_hours_manager: Extended hours manager instance
        """
        self._extended_hours_manager = extended_hours_manager
        logger.info("✅ Extended hours manager integrated with market hours manager")
    
    async def is_extended_hours_trading_enabled(self, symbol: str = None) -> bool:
        """
        Check if extended hours trading is currently enabled and allowed.
        
        Args:
            symbol: Optional symbol to check for extended hours eligibility
            
        Returns:
            True if extended hours trading is enabled and symbol is eligible
        """
        if not self._extended_hours_manager:
            return False
        
        try:
            if symbol:
                is_allowed, _ = await self._extended_hours_manager.is_extended_hours_trading_allowed(symbol)
                return is_allowed
            else:
                # General extended hours availability
                return await self._extended_hours_manager.is_extended_hours_available()
        except Exception as e:
            logger.error(f"❌ Error checking extended hours trading status: {e}")
            return False
    
    async def configure_order_for_current_session(self, order_request: Dict[str, Any], symbol: str) -> Dict[str, Any]:
        """
        Automatically configure order for the current trading session (regular or extended hours).
        
        Args:
            order_request: Original order request
            symbol: Trading symbol
            
        Returns:
            Order request optimized for current session
        """
        if not self._extended_hours_manager:
            logger.debug("📋 No extended hours manager - returning original order")
            return order_request
        
        try:
            return await self._extended_hours_manager.configure_extended_hours_order(order_request, symbol)
        except Exception as e:
            logger.error(f"❌ Error configuring order for current session: {e}")
            return order_request