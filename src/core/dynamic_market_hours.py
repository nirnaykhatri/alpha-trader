"""
Dynamic Broker-Based Market Hours Management
Uses broker APIs to determine market status instead of hardcoded exchange schedules.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Set
import asyncio
import logging

logger = logging.getLogger(__name__)


class TradingSession(Enum):
    """Trading session types as reported by brokers."""
    PREMARKET = "premarket"
    REGULAR = "regular"
    POSTMARKET = "postmarket"
    CLOSED = "closed"
    UNKNOWN = "unknown"


@dataclass
class BrokerMarketStatus:
    """Market status as reported by a specific broker."""
    broker_type: str
    is_market_open: bool
    current_session: TradingSession
    is_trading_day: bool
    supported_symbols: Set[str]  # Symbols this broker can trade
    next_market_open: Optional[datetime] = None
    next_market_close: Optional[datetime] = None
    extended_hours_available: bool = False
    weekend_trading_available: bool = False  # For crypto brokers
    market_timezone: Optional[str] = None
    last_updated: Optional[datetime] = None


@dataclass
class AggregatedMarketStatus:
    """Aggregated market status across all brokers."""
    should_bot_be_active: bool
    active_brokers: List[str]
    available_sessions: Dict[str, TradingSession]  # broker -> current session
    total_tradeable_symbols: Set[str]
    has_24_7_markets: bool  # True if any broker supports 24/7 trading
    next_market_activity: Optional[datetime] = None
    reason: str = ""


class IBrokerMarketStatusProvider(ABC):
    """Interface for brokers to provide their market status."""
    
    @abstractmethod
    async def get_market_status(self) -> BrokerMarketStatus:
        """Get current market status from this broker."""
        pass
    
    @abstractmethod
    async def is_symbol_tradeable_now(self, symbol: str) -> bool:
        """Check if a specific symbol is tradeable right now via this broker."""
        pass
    
    @abstractmethod
    def get_supported_symbols(self) -> Set[str]:
        """Get set of symbols this broker can trade."""
        pass
    
    @abstractmethod
    def supports_extended_hours(self) -> bool:
        """Check if broker supports extended hours trading."""
        pass
    
    @abstractmethod
    def supports_weekend_trading(self) -> bool:
        """Check if broker supports weekend trading (crypto)."""
        pass


class IDynamicMarketHoursManager(ABC):
    """Interface for dynamic market hours management using broker APIs."""
    
    @abstractmethod
    async def should_bot_be_active(self) -> bool:
        """Determine if bot should be active based on any broker's market status."""
        pass
    
    @abstractmethod
    async def get_aggregated_market_status(self) -> AggregatedMarketStatus:
        """Get aggregated market status across all brokers."""
        pass
    
    @abstractmethod
    async def is_symbol_tradeable(self, symbol: str) -> bool:
        """Check if a symbol is tradeable via any available broker."""
        pass
    
    @abstractmethod
    async def get_best_broker_for_symbol(self, symbol: str) -> Optional[str]:
        """Get the best broker for trading a symbol based on current market status."""
        pass
    
    @abstractmethod
    def register_broker(self, broker_type: str, status_provider: IBrokerMarketStatusProvider) -> None:
        """Register a broker's market status provider."""
        pass


class DynamicMarketHoursManager(IDynamicMarketHoursManager):
    """
    Dynamic market hours manager that uses broker APIs to determine market status.
    No hardcoded exchange schedules - everything comes from broker APIs.
    """
    
    def __init__(self, config: Any):
        self.config = config
        self._broker_providers: Dict[str, IBrokerMarketStatusProvider] = {}
        self._last_status_cache: Dict[str, BrokerMarketStatus] = {}
        self._cache_duration_seconds = 60  # Cache broker status for 1 minute
        
        # Configuration
        self._polling_interval = config.get_config("market_hours.polling_interval_seconds", 60)
        self._enable_caching = config.get_config("market_hours.enable_caching", True)
        
        logger.info("🕐 Dynamic Market Hours Manager initialized")
    
    def register_broker(self, broker_type: str, status_provider: IBrokerMarketStatusProvider) -> None:
        """Register a broker's market status provider."""
        self._broker_providers[broker_type] = status_provider
        logger.info(f"📈 Registered market status provider for {broker_type}")
    
    async def should_bot_be_active(self) -> bool:
        """
        Determine if bot should be active based on any broker's market status.
        Bot is active if ANY broker has tradeable markets.
        """
        try:
            aggregated_status = await self.get_aggregated_market_status()
            return aggregated_status.should_bot_be_active
        except Exception as e:
            logger.error(f"❌ Error checking if bot should be active: {e}")
            # Fail-safe: assume bot should be active if we can't determine status
            return True
    
    async def get_aggregated_market_status(self) -> AggregatedMarketStatus:
        """Get aggregated market status across all brokers."""
        active_brokers = []
        available_sessions = {}
        all_tradeable_symbols = set()
        has_24_7_markets = False
        next_activities = []
        
        # Query all registered brokers
        for broker_type, provider in self._broker_providers.items():
            try:
                status = await self._get_cached_broker_status(broker_type, provider)
                
                # Check if this broker has active markets
                if status.is_market_open or status.weekend_trading_available:
                    active_brokers.append(broker_type)
                
                # Track current session
                available_sessions[broker_type] = status.current_session
                
                # Aggregate tradeable symbols
                all_tradeable_symbols.update(status.supported_symbols)
                
                # Check for 24/7 markets
                if status.weekend_trading_available:
                    has_24_7_markets = True
                
                # Track next market activities
                if status.next_market_open:
                    next_activities.append(status.next_market_open)
                    
            except Exception as e:
                logger.warning(f"⚠️ Failed to get status from {broker_type}: {e}")
                # Don't let one broker failure stop the entire system
                continue
        
        # Determine overall bot activation
        should_be_active = len(active_brokers) > 0 or has_24_7_markets
        
        # Find next market activity
        next_market_activity = min(next_activities) if next_activities else None
        
        # Generate reason
        if should_be_active:
            if has_24_7_markets:
                reason = f"24/7 markets available via {active_brokers}"
            else:
                reason = f"Active markets via brokers: {active_brokers}"
        else:
            reason = "No active markets across any broker"
            if next_market_activity:
                time_to_next = (next_market_activity - datetime.now(timezone.utc)).total_seconds() / 60
                reason += f", next opens in {time_to_next:.0f}min"
        
        return AggregatedMarketStatus(
            should_bot_be_active=should_be_active,
            active_brokers=active_brokers,
            available_sessions=available_sessions,
            total_tradeable_symbols=all_tradeable_symbols,
            has_24_7_markets=has_24_7_markets,
            next_market_activity=next_market_activity,
            reason=reason
        )
    
    async def is_symbol_tradeable(self, symbol: str) -> bool:
        """Check if a symbol is tradeable via any available broker."""
        for broker_type, provider in self._broker_providers.items():
            try:
                if await provider.is_symbol_tradeable_now(symbol):
                    return True
            except Exception as e:
                logger.warning(f"⚠️ Error checking {symbol} tradeability on {broker_type}: {e}")
                continue
        
        return False
    
    async def get_best_broker_for_symbol(self, symbol: str) -> Optional[str]:
        """Get the best broker for trading a symbol based on current market status."""
        available_brokers = []
        
        for broker_type, provider in self._broker_providers.items():
            try:
                if await provider.is_symbol_tradeable_now(symbol):
                    available_brokers.append(broker_type)
            except Exception as e:
                logger.warning(f"⚠️ Error checking {symbol} on {broker_type}: {e}")
                continue
        
        if not available_brokers:
            return None
        
        # Simple strategy: return first available broker
        # Could be enhanced with priority, health scoring, etc.
        return available_brokers[0]
    
    async def _get_cached_broker_status(self, broker_type: str, provider: IBrokerMarketStatusProvider) -> BrokerMarketStatus:
        """Get broker status with caching."""
        now = datetime.now(timezone.utc)
        
        # Check if we have a recent cached status
        if self._enable_caching and broker_type in self._last_status_cache:
            cached_status = self._last_status_cache[broker_type]
            if cached_status.last_updated:
                cache_age = (now - cached_status.last_updated).total_seconds()
                if cache_age < self._cache_duration_seconds:
                    return cached_status
        
        # Fetch fresh status from broker
        try:
            status = await provider.get_market_status()
            status.last_updated = now
            
            # Cache the result
            if self._enable_caching:
                self._last_status_cache[broker_type] = status
            
            return status
            
        except Exception as e:
            logger.error(f"❌ Failed to get market status from {broker_type}: {e}")
            
            # Return cached status if available, even if stale
            if broker_type in self._last_status_cache:
                logger.warning(f"⚠️ Using stale cached status for {broker_type}")
                return self._last_status_cache[broker_type]
            
            # Last resort: return a "unknown" status
            return BrokerMarketStatus(
                broker_type=broker_type,
                is_market_open=False,
                current_session=TradingSession.UNKNOWN,
                is_trading_day=True,  # Assume it's a trading day
                supported_symbols=set(),
                last_updated=now
            )
    
    def get_registered_brokers(self) -> List[str]:
        """Get list of registered broker types."""
        return list(self._broker_providers.keys())
    
    async def refresh_all_broker_status(self) -> None:
        """Force refresh of all broker statuses (clears cache)."""
        self._last_status_cache.clear()
        logger.info("🔄 Cleared broker status cache, will fetch fresh data")
    
    async def get_broker_status(self, broker_type: str) -> Optional[BrokerMarketStatus]:
        """Get status for a specific broker."""
        if broker_type not in self._broker_providers:
            return None
        
        provider = self._broker_providers[broker_type]
        return await self._get_cached_broker_status(broker_type, provider)