"""
Alpaca Market Status Provider - Real-time market status using Alpaca APIs.
Provides authoritative market status information directly from the broker.
"""

import asyncio
import aiohttp
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum

from ..interfaces import IConfigurationManager
from ..exceptions import MarketDataException
from ..core.logging_config import get_logger

logger = get_logger(__name__)


class MarketSession(Enum):
    """Market session types."""
    CLOSED = "closed"
    PREMARKET = "premarket"
    REGULAR = "regular"
    POSTMARKET = "postmarket"
    HOLIDAY = "holiday"
    WEEKEND = "weekend"


@dataclass
class MarketStatusResponse:
    """Complete market status information from Alpaca Clock API."""
    is_open: bool
    current_session: MarketSession
    next_open: datetime
    next_close: datetime
    timestamp: datetime
    raw_response: Dict[str, Any]
    source: str = "alpaca_clock_api"


class AlpacaMarketStatusProvider:
    """
    Provides real-time market status using Alpaca's Clock API.
    Primary source of truth for market open/closed status.
    """
    
    def __init__(self, config: IConfigurationManager):
        """
        Initialize Alpaca market status provider.
        
        Args:
            config: Configuration manager instance
        """
        self._config = config
        
        # Get Alpaca API credentials using consolidated method
        credentials = config.get_broker_credentials("alpaca")
        self._api_key = credentials["api_key"]
        self._secret_key = credentials["secret_key"]
        self._base_url = credentials.get("base_url", "https://paper-api.alpaca.markets")
        
        if not self._api_key or not self._secret_key:
            raise MarketDataException("Alpaca API credentials required for market status provider")
        
        # Configuration
        self._timeout = config.get_config("market_hours.alpaca_integration.timeout_seconds", 10)
        self._max_retries = config.get_config("market_hours.alpaca_integration.retry_attempts", 3)
        self._cache_duration_minutes = config.get_config("market_hours.alpaca_integration.cache_duration_minutes", 5)
        
        # Cache management
        self._status_cache: Optional[MarketStatusResponse] = None
        self._last_api_call: Optional[datetime] = None
        self._api_failure_count = 0
        
        # Build API endpoint
        self._clock_endpoint = f"{self._base_url.rstrip('/')}/v2/clock"
        
        logger.info(f"AlpacaMarketStatusProvider initialized - endpoint: {self._clock_endpoint}")
    
    async def get_market_status(self) -> MarketStatusResponse:
        """
        Get current market status from Alpaca Clock API with intelligent caching.
        
        Returns:
            MarketStatusResponse with complete market status information
            
        Raises:
            MarketDataException: If API call fails after retries
        """
        try:
            # Check cache first
            if self._is_cache_valid():
                logger.debug("📋 Using cached market status")
                return self._status_cache
            
            logger.debug("🔍 Fetching market status from Alpaca Clock API...")
            
            # Make API request with retries
            clock_data = await self._fetch_clock_data_with_retries()
            
            # Parse response
            status_response = self._parse_clock_response(clock_data)
            
            # Update cache
            self._status_cache = status_response
            self._last_api_call = datetime.now(timezone.utc)
            self._api_failure_count = 0
            
            logger.info(f"🕐 MARKET STATUS: {status_response.current_session.value.upper()} "
                       f"(is_open: {status_response.is_open})")
            
            return status_response
            
        except Exception as e:
            self._api_failure_count += 1
            logger.error(f"❌ Failed to get market status (attempt {self._api_failure_count}): {e}")
            
            # Return cached data if available
            if self._status_cache:
                logger.warning("⚠️ Using stale cached market status due to API failure")
                return self._status_cache
            
            raise MarketDataException(f"Unable to get market status from Alpaca: {e}")
    
    async def is_market_currently_open(self) -> bool:
        """
        Direct boolean check if market is open right now.
        
        Returns:
            True if market is currently open, False otherwise
        """
        try:
            status = await self.get_market_status()
            return status.is_open
        except Exception as e:
            logger.error(f"❌ Error checking if market is open: {e}")
            return False  # Conservative default
    
    async def should_activate_bot(self, buffer_minutes: int = 15) -> Tuple[bool, str]:
        """
        Check if bot should be active considering buffer time.
        
        Args:
            buffer_minutes: Buffer time before market open and after market close
            
        Returns:
            Tuple of (should_be_active, reason)
        """
        try:
            status = await self.get_market_status()
            now = datetime.now(timezone.utc)
            
            # Always active if market is open
            if status.is_open:
                return True, f"market_open_{status.current_session.value}"
            
            # Check buffer time before market open
            time_to_open = (status.next_open - now).total_seconds() / 60
            if 0 < time_to_open <= buffer_minutes:
                return True, f"pre_market_buffer_{time_to_open:.1f}min"
            
            # Check buffer time after market close
            time_since_close = (now - status.next_close).total_seconds() / 60
            if 0 < time_since_close <= buffer_minutes:
                return True, f"post_market_buffer_{time_since_close:.1f}min"
            
            # Market is closed and outside buffer times
            return False, f"market_closed_{status.current_session.value}"
            
        except Exception as e:
            logger.error(f"❌ Error determining bot activation status: {e}")
            # Conservative default - activate if unsure
            return True, f"error_fallback_{str(e)[:50]}"
    
    async def get_time_to_next_session(self) -> float:
        """
        Calculate minutes until next market session change.
        
        Returns:
            Minutes until next market open or close
        """
        try:
            status = await self.get_market_status()
            now = datetime.now(timezone.utc)
            
            if status.is_open:
                # Market is open - return time to close
                return (status.next_close - now).total_seconds() / 60
            else:
                # Market is closed - return time to open
                return (status.next_open - now).total_seconds() / 60
                
        except Exception as e:
            logger.error(f"❌ Error calculating time to next session: {e}")
            return 60.0  # Default to 60 minutes
    
    async def _fetch_clock_data_with_retries(self) -> Dict[str, Any]:
        """
        Fetch clock data from Alpaca API with retry logic.
        
        Returns:
            Raw clock API response data
            
        Raises:
            MarketDataException: If all retries fail
        """
        last_error = None
        
        for attempt in range(self._max_retries):
            try:
                logger.debug(f"📡 Alpaca Clock API request (attempt {attempt + 1}/{self._max_retries})")
                
                headers = {
                    'APCA-API-KEY-ID': self._api_key,
                    'APCA-API-SECRET-KEY': self._secret_key,
                    'Content-Type': 'application/json'
                }
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        self._clock_endpoint,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=self._timeout)
                    ) as response:
                        
                        if response.status == 200:
                            data = await response.json()
                            logger.debug(f"✅ Clock API success: {data}")
                            return data
                        else:
                            error_text = await response.text()
                            raise MarketDataException(f"HTTP {response.status}: {error_text}")
                            
            except asyncio.TimeoutError as e:
                last_error = f"Timeout after {self._timeout}s"
                logger.warning(f"⏰ Clock API timeout (attempt {attempt + 1})")
            except aiohttp.ClientError as e:
                last_error = f"Network error: {str(e)}"
                logger.warning(f"🌐 Clock API network error (attempt {attempt + 1}): {e}")
            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                logger.warning(f"❌ Clock API unexpected error (attempt {attempt + 1}): {e}")
            
            # Wait before retry (exponential backoff)
            if attempt < self._max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s...
                logger.debug(f"⏳ Waiting {wait_time}s before retry...")
                await asyncio.sleep(wait_time)
        
        raise MarketDataException(f"All {self._max_retries} Clock API attempts failed. Last error: {last_error}")
    
    def _parse_clock_response(self, clock_data: Dict[str, Any]) -> MarketStatusResponse:
        """
        Parse Alpaca Clock API response into MarketStatusResponse.
        
        Args:
            clock_data: Raw response from Alpaca Clock API
            
        Returns:
            Parsed MarketStatusResponse
        """
        try:
            # Extract fields from response
            is_open = clock_data.get('is_open', False)
            timestamp_str = clock_data.get('timestamp')
            next_open_str = clock_data.get('next_open')
            next_close_str = clock_data.get('next_close')
            
            # Parse timestamps
            timestamp = self._parse_timestamp(timestamp_str)
            next_open = self._parse_timestamp(next_open_str)
            next_close = self._parse_timestamp(next_close_str)
            
            # Determine current session
            current_session = self._determine_current_session(is_open, timestamp, next_open, next_close)
            
            return MarketStatusResponse(
                is_open=is_open,
                current_session=current_session,
                next_open=next_open,
                next_close=next_close,
                timestamp=timestamp,
                raw_response=clock_data,
                source="alpaca_clock_api"
            )
            
        except Exception as e:
            logger.error(f"❌ Error parsing clock response: {e}")
            logger.error(f"Raw clock data: {clock_data}")
            raise MarketDataException(f"Failed to parse Alpaca clock response: {e}")
    
    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse timestamp string to datetime object."""
        if not timestamp_str:
            raise ValueError("Timestamp string is empty")
        
        # Handle various timestamp formats
        try:
            # Try ISO format with timezone
            if timestamp_str.endswith('Z'):
                return datetime.fromisoformat(timestamp_str[:-1]).replace(tzinfo=timezone.utc)
            elif '+' in timestamp_str or timestamp_str.endswith(('T00:00')):
                return datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                # Assume UTC if no timezone
                return datetime.fromisoformat(timestamp_str).replace(tzinfo=timezone.utc)
        except Exception as e:
            logger.error(f"❌ Error parsing timestamp '{timestamp_str}': {e}")
            raise ValueError(f"Invalid timestamp format: {timestamp_str}")
    
    def _determine_current_session(
        self,
        is_open: bool,
        timestamp: datetime,
        next_open: datetime,
        next_close: datetime
    ) -> MarketSession:
        """
        Determine current market session based on Alpaca data.
        
        Args:
            is_open: Whether market is currently open
            timestamp: Current server timestamp
            next_open: Next market open time
            next_close: Next market close time
            
        Returns:
            Current market session
        """
        try:
            # Check for weekend
            if timestamp.weekday() >= 5:  # Saturday = 5, Sunday = 6
                return MarketSession.WEEKEND
            
            if is_open:
                # Market is open - determine if regular or extended hours
                # This requires additional logic or configuration to distinguish
                # For now, assume regular hours when is_open=True
                return MarketSession.REGULAR
            else:
                # Market is closed - determine if premarket, postmarket, or closed
                now = timestamp
                
                # Estimate based on time to next open/close
                time_to_open = (next_open - now).total_seconds()
                time_to_close = (next_close - now).total_seconds()
                
                # If next_close is sooner than next_open, we're likely in premarket
                if time_to_close < time_to_open:
                    return MarketSession.PREMARKET
                
                # Check if we're in typical after-hours window (rough estimation)
                hour_of_day = now.hour
                if 16 <= hour_of_day <= 20:  # 4 PM - 8 PM UTC approximation
                    return MarketSession.POSTMARKET
                elif 4 <= hour_of_day <= 9:   # 4 AM - 9:30 AM UTC approximation
                    return MarketSession.PREMARKET
                else:
                    return MarketSession.CLOSED
                    
        except Exception as e:
            logger.warning(f"⚠️ Error determining market session: {e}")
            return MarketSession.CLOSED  # Conservative default
    
    def _is_cache_valid(self) -> bool:
        """Check if cached market status is still valid."""
        if not self._status_cache or not self._last_api_call:
            return False
        
        age_minutes = (datetime.now(timezone.utc) - self._last_api_call).total_seconds() / 60
        return age_minutes < self._cache_duration_minutes
    
    def get_api_failure_count(self) -> int:
        """Get current API failure count for monitoring."""
        return self._api_failure_count
    
    def reset_failure_count(self) -> None:
        """Reset API failure count (useful after successful recovery)."""
        self._api_failure_count = 0
        logger.info("✅ Market status API failure count reset")