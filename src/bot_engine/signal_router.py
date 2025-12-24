"""
Signal Router - Webhook Signal Routing to Specific Bots.

The SignalRouter efficiently routes incoming trading signals from webhooks
to the appropriate bot instances based on symbol, strategy, and other
matching criteria.

Key Features:
- Symbol-based signal routing
- Multi-criteria bot matching
- Callback-based signal delivery
- Subscription management for dynamic bot registration

Signal Flow:
    Webhook → API → SignalRouter → [Bot1, Bot2, ...] → Strategy Execution

Author: Trading Bot Team
Version: 1.0.0
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set
import uuid

from src.core.logging_config import get_logger
from src.bot_engine.interfaces import ISignalRouter, SignalSubscription
from src.bot_engine.exceptions import SignalRoutingError

logger = get_logger(__name__)


@dataclass
class SignalFilter:
    """
    Filter criteria for signal routing.
    
    Defines what signals a bot is interested in receiving.
    """
    
    symbols: Set[str]
    signal_types: Optional[Set[str]] = None  # buy, sell, close, etc.
    exchanges: Optional[Set[str]] = None
    strategies: Optional[Set[str]] = None
    custom_filters: Optional[Dict[str, Any]] = None


@dataclass
class BotSignalSubscription:
    """
    Represents a bot's signal subscription.
    
    Contains the bot ID, filter criteria, and callback for delivery.
    """
    
    bot_id: str
    filter: SignalFilter
    callback: Callable[[Dict[str, Any]], None]
    created_at: datetime = field(default_factory=datetime.utcnow)
    signals_received: int = 0
    last_signal_at: Optional[datetime] = None


class SignalRouter(ISignalRouter):
    """
    Routes webhook signals to appropriate bot instances.
    
    The SignalRouter maintains a registry of bot subscriptions and
    efficiently routes incoming signals to all matching bots. This
    enables multiple bots to receive the same signal without the
    webhook needing to know about individual bots.
    
    Routing Strategy:
    1. Signal arrives via webhook
    2. Router extracts symbol/type from signal
    3. Router finds all bots subscribed to that symbol
    4. Signal is delivered to each matching bot's callback
    
    Thread Safety:
    - All operations are async and run in single event loop
    - Subscription modifications are atomic within coroutines
    
    Usage:
        router = SignalRouter()
        await router.start()
        
        router.register_bot("bot_123", {"BTCUSD"}, bot_callback)
        
        # When webhook arrives:
        await router.route_signal({"action": "buy", "symbol": "BTCUSD"})
        
        await router.stop()
    """
    
    def __init__(self):
        """Initialize the signal router."""
        # Bot subscriptions: bot_id -> BotSignalSubscription
        self._subscriptions: Dict[str, BotSignalSubscription] = {}
        
        # Quick lookup indexes
        self._symbol_index: Dict[str, Set[str]] = {}  # symbol -> set of bot_ids
        self._type_index: Dict[str, Set[str]] = {}    # signal_type -> set of bot_ids
        
        # Statistics
        self._signals_routed = 0
        self._signals_delivered = 0
        self._routing_errors = 0
        
        # Engine state
        self._is_running = False
        
        logger.info("SignalRouter initialized")
    
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def is_running(self) -> bool:
        """Check if the router is running."""
        return self._is_running
    
    @property
    def subscription_count(self) -> int:
        """Get the number of active subscriptions."""
        return len(self._subscriptions)
    
    @property
    def unique_symbols(self) -> int:
        """Get the number of unique symbols being watched."""
        return len(self._symbol_index)
    
    # =========================================================================
    # Lifecycle
    # =========================================================================
    
    async def start(self) -> None:
        """Start the signal router."""
        if self._is_running:
            logger.warning("SignalRouter is already running")
            return
        
        logger.info("Starting SignalRouter...")
        self._is_running = True
        logger.info("SignalRouter started successfully")
    
    async def stop(self) -> None:
        """Stop the signal router."""
        if not self._is_running:
            logger.warning("SignalRouter is not running")
            return
        
        logger.info("Stopping SignalRouter...")
        
        # Clear all subscriptions
        self._subscriptions.clear()
        self._symbol_index.clear()
        self._type_index.clear()
        
        self._is_running = False
        logger.info("SignalRouter stopped")
    
    # =========================================================================
    # Bot Registration
    # =========================================================================
    
    def register_bot(
        self,
        bot_id: str,
        symbols: Set[str],
        callback: Callable[[Dict[str, Any]], None],
        signal_types: Optional[Set[str]] = None,
        exchanges: Optional[Set[str]] = None,
        strategies: Optional[Set[str]] = None,
    ) -> None:
        """
        Register a bot to receive signals.
        
        Args:
            bot_id: Unique bot identifier
            symbols: Set of symbols to subscribe to
            callback: Async or sync callback for signal delivery
            signal_types: Optional filter for specific signal types
            exchanges: Optional filter for specific exchanges
            strategies: Optional filter for specific strategies
        """
        if not self._is_running:
            raise SignalRoutingError("SignalRouter is not running")
        
        # Create filter
        signal_filter = SignalFilter(
            symbols=symbols,
            signal_types=signal_types,
            exchanges=exchanges,
            strategies=strategies,
        )
        
        # Create subscription
        subscription = BotSignalSubscription(
            bot_id=bot_id,
            filter=signal_filter,
            callback=callback,
        )
        
        # Store subscription
        self._subscriptions[bot_id] = subscription
        
        # Update indexes
        for symbol in symbols:
            if symbol not in self._symbol_index:
                self._symbol_index[symbol] = set()
            self._symbol_index[symbol].add(bot_id)
        
        if signal_types:
            for sig_type in signal_types:
                if sig_type not in self._type_index:
                    self._type_index[sig_type] = set()
                self._type_index[sig_type].add(bot_id)
        
        logger.debug(
            f"Registered bot {bot_id} for symbols {symbols} "
            f"(total subscriptions: {len(self._subscriptions)})"
        )
    
    def unregister_bot(self, bot_id: str) -> None:
        """
        Unregister a bot from receiving signals.
        
        Args:
            bot_id: Bot identifier to unregister
        """
        subscription = self._subscriptions.pop(bot_id, None)
        if not subscription:
            logger.warning(f"Bot {bot_id} was not registered")
            return
        
        # Remove from symbol index
        for symbol in subscription.filter.symbols:
            if symbol in self._symbol_index:
                self._symbol_index[symbol].discard(bot_id)
                if not self._symbol_index[symbol]:
                    del self._symbol_index[symbol]
        
        # Remove from type index
        if subscription.filter.signal_types:
            for sig_type in subscription.filter.signal_types:
                if sig_type in self._type_index:
                    self._type_index[sig_type].discard(bot_id)
                    if not self._type_index[sig_type]:
                        del self._type_index[sig_type]
        
        logger.debug(
            f"Unregistered bot {bot_id} "
            f"(remaining subscriptions: {len(self._subscriptions)})"
        )
    
    def update_subscription(
        self,
        bot_id: str,
        symbols: Optional[Set[str]] = None,
        signal_types: Optional[Set[str]] = None,
    ) -> None:
        """
        Update a bot's subscription.
        
        Args:
            bot_id: Bot identifier
            symbols: New set of symbols (if provided)
            signal_types: New set of signal types (if provided)
        """
        if bot_id not in self._subscriptions:
            raise SignalRoutingError(f"Bot {bot_id} is not registered")
        
        subscription = self._subscriptions[bot_id]
        
        # Update symbols if provided
        if symbols is not None:
            # Remove from old symbol indexes
            for symbol in subscription.filter.symbols:
                if symbol in self._symbol_index:
                    self._symbol_index[symbol].discard(bot_id)
                    if not self._symbol_index[symbol]:
                        del self._symbol_index[symbol]
            
            # Update filter
            subscription.filter.symbols = symbols
            
            # Add to new symbol indexes
            for symbol in symbols:
                if symbol not in self._symbol_index:
                    self._symbol_index[symbol] = set()
                self._symbol_index[symbol].add(bot_id)
        
        # Update signal types if provided
        if signal_types is not None:
            # Remove from old type indexes
            if subscription.filter.signal_types:
                for sig_type in subscription.filter.signal_types:
                    if sig_type in self._type_index:
                        self._type_index[sig_type].discard(bot_id)
                        if not self._type_index[sig_type]:
                            del self._type_index[sig_type]
            
            # Update filter
            subscription.filter.signal_types = signal_types
            
            # Add to new type indexes
            for sig_type in signal_types:
                if sig_type not in self._type_index:
                    self._type_index[sig_type] = set()
                self._type_index[sig_type].add(bot_id)
        
        logger.debug(f"Updated subscription for bot {bot_id}")
    
    # =========================================================================
    # Signal Routing
    # =========================================================================
    
    async def route_signal(self, signal: Dict[str, Any]) -> List[str]:
        """
        Route a signal to all matching bots.
        
        Args:
            signal: Signal data containing at minimum:
                - symbol: Trading symbol
                - action: Signal type (buy, sell, close, etc.)
                
        Returns:
            List of bot IDs that received the signal
        """
        if not self._is_running:
            raise SignalRoutingError("SignalRouter is not running")
        
        self._signals_routed += 1
        
        # Extract routing keys
        symbol = signal.get("symbol", "").upper()
        action = signal.get("action", "").lower()
        exchange = signal.get("exchange", "")
        strategy = signal.get("strategy", "")
        
        logger.debug(f"Routing signal: {action} for {symbol}")
        
        if not symbol:
            logger.warning("Signal missing symbol, cannot route")
            return []
        
        # Find matching bots
        matching_bots = self._find_matching_bots(signal)
        
        if not matching_bots:
            logger.debug(f"No bots subscribed to {symbol}/{action}")
            return []
        
        # Deliver signal to matching bots
        delivered_to = []
        
        for bot_id in matching_bots:
            subscription = self._subscriptions.get(bot_id)
            if not subscription:
                continue
            
            try:
                # Update statistics
                subscription.signals_received += 1
                subscription.last_signal_at = datetime.utcnow()
                
                # Deliver via callback
                if asyncio.iscoroutinefunction(subscription.callback):
                    await subscription.callback(signal)
                else:
                    subscription.callback(signal)
                
                delivered_to.append(bot_id)
                self._signals_delivered += 1
                
            except Exception as e:
                logger.error(f"Error delivering signal to bot {bot_id}: {e}")
                self._routing_errors += 1
        
        logger.debug(
            f"Signal routed to {len(delivered_to)} bots: {delivered_to}"
        )
        
        return delivered_to
    
    def _find_matching_bots(self, signal: Dict[str, Any]) -> Set[str]:
        """
        Find all bots that match the signal criteria.
        
        Args:
            signal: Signal data
            
        Returns:
            Set of matching bot IDs
        """
        symbol = signal.get("symbol", "").upper()
        action = signal.get("action", "").lower()
        exchange = signal.get("exchange", "")
        strategy = signal.get("strategy", "")
        
        # Start with symbol index (most selective)
        candidates = self._symbol_index.get(symbol, set()).copy()
        
        if not candidates:
            # Check for wildcard subscriptions (empty symbol set = all symbols)
            candidates = {
                bot_id for bot_id, sub in self._subscriptions.items()
                if not sub.filter.symbols
            }
        
        # Filter by signal type if specified
        if action:
            type_matches = self._type_index.get(action, set())
            # Bots with no type filter match all types
            no_type_filter = {
                bot_id for bot_id in candidates
                if not self._subscriptions[bot_id].filter.signal_types
            }
            candidates = (candidates & type_matches) | no_type_filter
        
        # Apply additional filters
        final_matches = set()
        for bot_id in candidates:
            subscription = self._subscriptions.get(bot_id)
            if not subscription:
                continue
            
            # Check exchange filter
            if subscription.filter.exchanges and exchange:
                if exchange not in subscription.filter.exchanges:
                    continue
            
            # Check strategy filter
            if subscription.filter.strategies and strategy:
                if strategy not in subscription.filter.strategies:
                    continue
            
            # Check custom filters
            if subscription.filter.custom_filters:
                if not self._matches_custom_filters(
                    signal, subscription.filter.custom_filters
                ):
                    continue
            
            final_matches.add(bot_id)
        
        return final_matches
    
    def _matches_custom_filters(
        self, 
        signal: Dict[str, Any], 
        filters: Dict[str, Any]
    ) -> bool:
        """
        Check if signal matches custom filter criteria.
        
        Args:
            signal: Signal data
            filters: Custom filter dictionary
            
        Returns:
            True if signal matches all filters
        """
        for key, expected in filters.items():
            actual = signal.get(key)
            if actual != expected:
                return False
        return True
    
    # =========================================================================
    # Query Methods
    # =========================================================================
    
    def get_subscription(self, bot_id: str) -> Optional[SignalSubscription]:
        """
        Get subscription info for a bot.
        
        Args:
            bot_id: Bot identifier
            
        Returns:
            SignalSubscription or None if not found
        """
        sub = self._subscriptions.get(bot_id)
        if not sub:
            return None
        
        return SignalSubscription(
            bot_id=sub.bot_id,
            symbols=sub.filter.symbols,
            signal_types=sub.filter.signal_types,
            created_at=sub.created_at,
            signals_received=sub.signals_received,
            last_signal_at=sub.last_signal_at,
        )
    
    def get_all_subscriptions(self) -> List[SignalSubscription]:
        """
        Get all active subscriptions.
        
        Returns:
            List of SignalSubscription
        """
        return [
            self.get_subscription(bot_id)
            for bot_id in self._subscriptions.keys()
        ]
    
    def get_bots_for_symbol(self, symbol: str) -> Set[str]:
        """
        Get all bots subscribed to a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Set of bot IDs
        """
        return self._symbol_index.get(symbol, set()).copy()
    
    def get_symbols_for_bot(self, bot_id: str) -> Set[str]:
        """
        Get all symbols a bot is subscribed to.
        
        Args:
            bot_id: Bot identifier
            
        Returns:
            Set of symbols
        """
        sub = self._subscriptions.get(bot_id)
        if sub:
            return sub.filter.symbols.copy()
        return set()
    
    # =========================================================================
    # Statistics
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get router statistics.
        
        Returns:
            Dictionary with router statistics
        """
        return {
            "is_running": self._is_running,
            "total_subscriptions": len(self._subscriptions),
            "unique_symbols": len(self._symbol_index),
            "unique_signal_types": len(self._type_index),
            "signals_routed": self._signals_routed,
            "signals_delivered": self._signals_delivered,
            "routing_errors": self._routing_errors,
            "delivery_success_rate": (
                self._signals_delivered / self._signals_routed * 100
                if self._signals_routed > 0 else 100.0
            ),
            "symbol_index": {
                symbol: len(bots) 
                for symbol, bots in self._symbol_index.items()
            },
        }
    
    def reset_stats(self) -> None:
        """Reset routing statistics."""
        self._signals_routed = 0
        self._signals_delivered = 0
        self._routing_errors = 0
        
        for sub in self._subscriptions.values():
            sub.signals_received = 0
            sub.last_signal_at = None
