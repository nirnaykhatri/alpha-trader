"""
Exchange-Aware Market Hours Management
Provides exchange-specific market hours and trading session information.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, time, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
import pytz


class Exchange(Enum):
    """Supported exchanges."""
    NYSE = "NYSE"
    NASDAQ = "NASDAQ"
    LSE = "LSE"  # London Stock Exchange
    TSE = "TSE"  # Tokyo Stock Exchange
    CRYPTO = "CRYPTO"
    FOREX = "FOREX"
    

class TradingSession(Enum):
    """Trading session types."""
    PREMARKET = "premarket"
    REGULAR = "regular"
    POSTMARKET = "postmarket" 
    LUNCH_BREAK = "lunch_break"
    CLOSED = "closed"


@dataclass
class TradingHours:
    """Trading hours for a specific session."""
    start_time: time
    end_time: time
    enabled: bool = True
    timezone: str = "UTC"


@dataclass
class ExchangeSchedule:
    """Complete schedule for an exchange."""
    exchange: Exchange
    timezone: str
    regular_session: TradingHours
    premarket: Optional[TradingHours] = None
    postmarket: Optional[TradingHours] = None
    lunch_break: Optional[TradingHours] = None
    weekend_trading: bool = False
    holidays_closed: bool = True


@dataclass
class MarketStatus:
    """Current market status for a specific exchange."""
    exchange: Exchange
    current_session: TradingSession
    is_open: bool
    is_trading_day: bool
    next_session_start: Optional[datetime]
    next_session_type: Optional[TradingSession]
    timezone: str
    local_time: datetime
    bot_should_be_active: bool
    activation_reason: str


class IExchangeProvider(ABC):
    """Interface for exchange-specific data providers."""
    
    @abstractmethod
    async def get_market_status(self, exchange: Exchange) -> MarketStatus:
        """Get current market status for the exchange."""
        pass
    
    @abstractmethod
    async def is_market_open(self, exchange: Exchange) -> bool:
        """Check if market is currently open."""
        pass
    
    @abstractmethod
    async def get_next_market_open(self, exchange: Exchange) -> datetime:
        """Get the next market open time."""
        pass
    
    @abstractmethod
    async def is_trading_day(self, exchange: Exchange, date: datetime) -> bool:
        """Check if given date is a trading day."""
        pass


class IMultiExchangeMarketHoursManager(ABC):
    """Interface for managing market hours across multiple exchanges."""
    
    @abstractmethod
    async def get_exchange_for_symbol(self, symbol: str) -> Exchange:
        """Get the exchange for a symbol."""
        pass
    
    @abstractmethod
    async def get_market_status_for_symbol(self, symbol: str) -> MarketStatus:
        """Get market status for a symbol's exchange."""
        pass
    
    @abstractmethod
    async def get_market_status_for_exchange(self, exchange: Exchange) -> MarketStatus:
        """Get market status for a specific exchange."""
        pass
    
    @abstractmethod
    async def get_active_exchanges(self) -> List[Exchange]:
        """Get list of currently active (open) exchanges."""
        pass
    
    @abstractmethod
    async def should_bot_be_active(self) -> bool:
        """Determine if bot should be active based on any exchange being open."""
        pass
    
    @abstractmethod
    def get_supported_exchanges(self) -> List[Exchange]:
        """Get list of supported exchanges."""
        pass


class ExchangeAwareMarketHoursManager(IMultiExchangeMarketHoursManager):
    """
    Exchange-aware market hours manager that supports multiple exchanges
    and determines market hours based on symbol-to-exchange mappings.
    """
    
    def __init__(self, config: Any, broker_manager: Optional[Any] = None):
        self.config = config
        self.broker_manager = broker_manager
        
        # Load exchange configurations
        self.exchange_schedules = self._load_exchange_schedules()
        self.symbol_exchange_map = self._load_symbol_exchange_mappings()
        self.broker_exchange_map = self._load_broker_exchange_mappings()
        
        # Initialize exchange providers
        self.exchange_providers: Dict[Exchange, IExchangeProvider] = {}
        self._initialize_exchange_providers()
    
    def _load_exchange_schedules(self) -> Dict[Exchange, ExchangeSchedule]:
        """Load exchange schedules from configuration."""
        schedules = {}
        
        exchange_configs = self.config.get_config("market_hours.exchanges", {})
        
        for exchange_name, config in exchange_configs.items():
            try:
                exchange = Exchange(exchange_name)
                
                # Parse regular session
                regular_config = config.get("regular_session", {})
                regular_hours = TradingHours(
                    start_time=self._parse_time(regular_config.get("start_time", "09:30")),
                    end_time=self._parse_time(regular_config.get("end_time", "16:00")),
                    timezone=config.get("timezone", "UTC")
                )
                
                # Parse extended hours
                extended_config = config.get("extended_hours", {})
                premarket = None
                postmarket = None
                
                if extended_config.get("premarket", {}).get("enabled", False):
                    premarket_config = extended_config["premarket"]
                    premarket = TradingHours(
                        start_time=self._parse_time(premarket_config.get("start_time", "04:00")),
                        end_time=self._parse_time(premarket_config.get("end_time", "09:30")),
                        timezone=config.get("timezone", "UTC")
                    )
                
                if extended_config.get("postmarket", {}).get("enabled", False):
                    postmarket_config = extended_config["postmarket"]
                    postmarket = TradingHours(
                        start_time=self._parse_time(postmarket_config.get("start_time", "16:00")),
                        end_time=self._parse_time(postmarket_config.get("end_time", "20:00")),
                        timezone=config.get("timezone", "UTC")
                    )
                
                # Parse lunch break (for exchanges like TSE)
                lunch_break = None
                if "lunch_break" in config:
                    lunch_config = config["lunch_break"]
                    lunch_break = TradingHours(
                        start_time=self._parse_time(lunch_config.get("start_time", "11:30")),
                        end_time=self._parse_time(lunch_config.get("end_time", "12:30")),
                        timezone=config.get("timezone", "UTC")
                    )
                
                schedule = ExchangeSchedule(
                    exchange=exchange,
                    timezone=config.get("timezone", "UTC"),
                    regular_session=regular_hours,
                    premarket=premarket,
                    postmarket=postmarket,
                    lunch_break=lunch_break,
                    weekend_trading=config.get("weekend_trading", False),
                    holidays_closed=config.get("holidays_closed", True)
                )
                
                schedules[exchange] = schedule
                
            except (ValueError, KeyError) as e:
                print(f"Warning: Invalid exchange configuration for {exchange_name}: {e}")
                continue
        
        return schedules
    
    def _load_symbol_exchange_mappings(self) -> Dict[str, Exchange]:
        """Load symbol-to-exchange mappings from configuration."""
        mappings = {}
        
        symbol_exchanges = self.config.get_config("market_hours.symbol_exchanges", {})
        
        for symbol, exchange_name in symbol_exchanges.items():
            try:
                exchange = Exchange(exchange_name)
                mappings[symbol] = exchange
            except ValueError:
                print(f"Warning: Unknown exchange '{exchange_name}' for symbol {symbol}")
                continue
        
        return mappings
    
    def _load_broker_exchange_mappings(self) -> Dict[str, Dict[str, Any]]:
        """Load broker-to-exchange mappings from configuration."""
        return self.config.get_config("market_hours.broker_exchanges", {})
    
    def _initialize_exchange_providers(self):
        """Initialize exchange-specific data providers."""
        # For now, use a default provider for all exchanges
        # In the future, specific providers can be added per exchange
        for exchange in self.exchange_schedules.keys():
            self.exchange_providers[exchange] = DefaultExchangeProvider(
                exchange, self.exchange_schedules[exchange], self.config
            )
    
    def _parse_time(self, time_str: str) -> time:
        """Parse time string to time object."""
        try:
            hour, minute = time_str.split(":")
            return time(int(hour), int(minute))
        except (ValueError, AttributeError):
            return time(9, 30)  # Default fallback
    
    async def get_exchange_for_symbol(self, symbol: str) -> Exchange:
        """Get the exchange for a symbol."""
        # Check explicit symbol mappings first
        if symbol in self.symbol_exchange_map:
            return self.symbol_exchange_map[symbol]
        
        # Check if we can determine from broker (if broker manager available)
        if self.broker_manager:
            try:
                broker_type = await self.broker_manager._router.get_broker_for_symbol(symbol)
                broker_config = self.broker_exchange_map.get(broker_type.value, {})
                default_exchange = broker_config.get("default_exchange", "NYSE")
                return Exchange(default_exchange)
            except Exception:
                pass
        
        # Fallback to default exchange
        default_exchange_name = self.config.get_config("market_hours.default_exchange", "NYSE")
        return Exchange(default_exchange_name)
    
    async def get_market_status_for_symbol(self, symbol: str) -> MarketStatus:
        """Get market status for a symbol's exchange."""
        exchange = await self.get_exchange_for_symbol(symbol)
        return await self.get_market_status_for_exchange(exchange)
    
    async def get_market_status_for_exchange(self, exchange: Exchange) -> MarketStatus:
        """Get market status for a specific exchange."""
        if exchange not in self.exchange_providers:
            # Fallback to NYSE if exchange not supported
            exchange = Exchange.NYSE
            if exchange not in self.exchange_providers:
                raise ValueError(f"No provider available for exchange {exchange}")
        
        provider = self.exchange_providers[exchange]
        return await provider.get_market_status(exchange)
    
    async def get_active_exchanges(self) -> List[Exchange]:
        """Get list of currently active (open) exchanges."""
        active_exchanges = []
        
        for exchange in self.exchange_schedules.keys():
            try:
                status = await self.get_market_status_for_exchange(exchange)
                if status.is_open:
                    active_exchanges.append(exchange)
            except Exception:
                continue
        
        return active_exchanges
    
    async def should_bot_be_active(self) -> bool:
        """Determine if bot should be active based on any exchange being open."""
        # Check if any exchange is currently open
        active_exchanges = await self.get_active_exchanges()
        
        if active_exchanges:
            return True
        
        # Check if we're within buffer time of any exchange opening
        buffers = self.config.get_config("market_hours.buffers", {})
        start_buffer_minutes = buffers.get("start_before_session_minutes", 15)
        
        for exchange in self.exchange_schedules.keys():
            try:
                provider = self.exchange_providers[exchange]
                next_open = await provider.get_next_market_open(exchange)
                
                # If next open is within buffer time, bot should be active
                now = datetime.now(timezone.utc)
                time_to_open = (next_open - now).total_seconds() / 60
                
                if 0 <= time_to_open <= start_buffer_minutes:
                    return True
                    
            except Exception:
                continue
        
        return False
    
    def get_supported_exchanges(self) -> List[Exchange]:
        """Get list of supported exchanges."""
        return list(self.exchange_schedules.keys())


class DefaultExchangeProvider(IExchangeProvider):
    """Default exchange provider using configuration and system time."""
    
    def __init__(self, exchange: Exchange, schedule: ExchangeSchedule, config: Any):
        self.exchange = exchange
        self.schedule = schedule
        self.config = config
    
    async def get_market_status(self, exchange: Exchange) -> MarketStatus:
        """Get current market status for the exchange."""
        # Get current time in exchange timezone
        tz = pytz.timezone(self.schedule.timezone)
        now = datetime.now(tz)
        
        # Determine current session
        current_session = self._determine_current_session(now.time())
        
        # Check if market is open
        is_open = self._is_market_open(now, current_session)
        
        # Check if it's a trading day
        is_trading_day = await self.is_trading_day(exchange, now)
        
        # Get next session information
        next_session_start, next_session_type = self._get_next_session(now)
        
        return MarketStatus(
            exchange=exchange,
            current_session=current_session,
            is_open=is_open and is_trading_day,
            is_trading_day=is_trading_day,
            next_session_start=next_session_start,
            next_session_type=next_session_type,
            timezone=self.schedule.timezone,
            local_time=now,
            bot_should_be_active=is_open and is_trading_day,
            activation_reason=f"Market {current_session.value} session active" if is_open else "Market closed"
        )
    
    def _determine_current_session(self, current_time: time) -> TradingSession:
        """Determine which session we're currently in."""
        # Check lunch break first (for exchanges like TSE)
        if self.schedule.lunch_break:
            if self.schedule.lunch_break.start_time <= current_time <= self.schedule.lunch_break.end_time:
                return TradingSession.LUNCH_BREAK
        
        # Check premarket
        if self.schedule.premarket:
            if self.schedule.premarket.start_time <= current_time < self.schedule.premarket.end_time:
                return TradingSession.PREMARKET
        
        # Check regular session
        if self.schedule.regular_session.start_time <= current_time < self.schedule.regular_session.end_time:
            # Skip if we're in lunch break
            if self.schedule.lunch_break:
                if self.schedule.lunch_break.start_time <= current_time <= self.schedule.lunch_break.end_time:
                    return TradingSession.LUNCH_BREAK
            return TradingSession.REGULAR
        
        # Check postmarket
        if self.schedule.postmarket:
            if self.schedule.postmarket.start_time <= current_time < self.schedule.postmarket.end_time:
                return TradingSession.POSTMARKET
        
        return TradingSession.CLOSED
    
    def _is_market_open(self, now: datetime, current_session: TradingSession) -> bool:
        """Check if market is currently open."""
        if current_session == TradingSession.CLOSED:
            return False
        
        if current_session == TradingSession.LUNCH_BREAK:
            return False
        
        # For 24/7 markets (crypto)
        if self.exchange in [Exchange.CRYPTO]:
            return True
        
        # For forex (24/5)
        if self.exchange == Exchange.FOREX:
            weekday = now.weekday()
            if weekday == 6:  # Sunday
                return now.time() >= time(21, 0)  # Opens Sunday 21:00 UTC
            elif weekday == 5:  # Friday
                return now.time() < time(21, 0)   # Closes Friday 21:00 UTC
            else:
                return True  # Open Monday-Thursday
        
        # Weekend check for traditional markets
        if not self.schedule.weekend_trading and now.weekday() >= 5:  # Saturday or Sunday
            return False
        
        return True
    
    def _get_next_session(self, now: datetime) -> tuple[Optional[datetime], Optional[TradingSession]]:
        """Get next session start time and type."""
        # Simplified implementation - returns next regular session start
        # In practice, this would calculate the actual next session based on current state
        
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        
        if self.schedule.premarket:
            next_start = tomorrow.replace(
                hour=self.schedule.premarket.start_time.hour,
                minute=self.schedule.premarket.start_time.minute
            )
            return next_start, TradingSession.PREMARKET
        else:
            next_start = tomorrow.replace(
                hour=self.schedule.regular_session.start_time.hour,
                minute=self.schedule.regular_session.start_time.minute
            )
            return next_start, TradingSession.REGULAR
    
    async def is_market_open(self, exchange: Exchange) -> bool:
        """Check if market is currently open."""
        status = await self.get_market_status(exchange)
        return status.is_open
    
    async def get_next_market_open(self, exchange: Exchange) -> datetime:
        """Get the next market open time."""
        status = await self.get_market_status(exchange)
        return status.next_session_start or datetime.now(timezone.utc)
    
    async def is_trading_day(self, exchange: Exchange, date: datetime) -> bool:
        """Check if given date is a trading day."""
        # Weekend check
        if not self.schedule.weekend_trading and date.weekday() >= 5:
            return False
        
        # Holiday check would go here (simplified for now)
        # In practice, this would check against a holiday calendar
        
        return True