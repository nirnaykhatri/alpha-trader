"""
DCA Signal Router.

Routes trading signals to appropriate handlers for DCA strategy.
Extracted from DCAStrategy to follow Single Responsibility Principle.

Author: Trading Bot Team
Version: 1.0.0
"""

from typing import Dict, Optional, Any
from src.interfaces import TradingSignal, SignalType, StrategyEvaluation
from src.core.logging_config import get_logger
from src.strategies.position_state import PositionState
from src.strategies.entry_executor import EntrySignalExecutor

logger = get_logger(__name__)


class DCASignalRouter:
    """
    Routes trading signals to appropriate handlers.
    
    Handles:
    - Signal type dispatching (BUY, SELL, CLOSE)
    - Signal validation before routing
    - Timeframe preservation for DCA decisions
    
    This class is responsible only for routing - actual execution
    is delegated to EntrySignalExecutor.
    
    Example:
        router = DCASignalRouter(entry_executor)
        
        # Route a signal
        position = await router.route_signal(
            signal,
            positions,
            position_timeframes
        )
    """
    
    def __init__(
        self,
        entry_executor: EntrySignalExecutor,
    ):
        """
        Initialize the signal router.
        
        Args:
            entry_executor: Entry signal executor for position operations
        """
        self.entry_executor = entry_executor
    
    async def route_signal(
        self,
        signal: TradingSignal,
        positions: Dict[str, PositionState],
        position_timeframes: Dict[str, str],
    ) -> Optional[PositionState]:
        """
        Route a trading signal to the appropriate handler.
        
        Args:
            signal: The trading signal to route
            positions: Current active positions (mutable - will be updated)
            position_timeframes: Timeframe tracking (mutable - will be updated)
            
        Returns:
            Updated PositionState if signal was handled, None otherwise
        """
        logger.info(
            f"📨 Routing signal: {signal.symbol} {signal.signal_type.value} "
            f"@ ${signal.price:.2f}"
        )
        
        # Store original signal timeframe
        timeframe = signal.metadata.get('timeframe', '15m') if signal.metadata else '15m'
        position_timeframes[signal.symbol] = timeframe
        logger.info(f"📊 TIMEFRAME STORED: {signal.symbol} -> {timeframe}")
        
        # Route to appropriate handler
        if signal.signal_type == SignalType.BUY:
            return await self._handle_long_signal(signal, positions)
        elif signal.signal_type == SignalType.SELL:
            return await self._handle_short_signal(signal, positions)
        elif signal.signal_type == SignalType.CLOSE:
            return await self._handle_close_signal(signal, positions, position_timeframes)
        else:
            logger.warning(f"⚠️ Unknown signal type: {signal.signal_type}")
            return None
    
    async def _handle_long_signal(
        self,
        signal: TradingSignal,
        positions: Dict[str, PositionState],
    ) -> Optional[PositionState]:
        """Handle long signal by delegating to entry executor."""
        existing_position = positions.get(signal.symbol)
        
        position = await self.entry_executor.handle_long_signal(
            signal, existing_position
        )
        
        if position:
            positions[signal.symbol] = position
            return position
        
        return None
    
    async def _handle_short_signal(
        self,
        signal: TradingSignal,
        positions: Dict[str, PositionState],
    ) -> Optional[PositionState]:
        """Handle short signal by delegating to entry executor."""
        existing_position = positions.get(signal.symbol)
        
        position = await self.entry_executor.handle_short_signal(
            signal, existing_position
        )
        
        if position:
            positions[signal.symbol] = position
            return position
        
        return None
    
    async def _handle_close_signal(
        self,
        signal: TradingSignal,
        positions: Dict[str, PositionState],
        position_timeframes: Dict[str, str],
    ) -> Optional[PositionState]:
        """Handle close signal by delegating to entry executor."""
        symbol = signal.symbol
        
        if symbol not in positions:
            logger.warning(f"⚠️ No position found for {symbol} to close")
            return None
        
        position = positions[symbol]
        success = await self.entry_executor.close_position(position)
        
        if success:
            # Clean up position tracking
            del positions[symbol]
            if symbol in position_timeframes:
                del position_timeframes[symbol]
            logger.info(f"✅ Position closed and cleaned up for {symbol}")
        
        return None
    
    def convert_raw_signal(
        self,
        signal_dict: Dict[str, Any]
    ) -> Optional[TradingSignal]:
        """
        Convert raw signal dictionary to TradingSignal object.
        
        Args:
            signal_dict: Raw signal data with action, symbol, price, etc.
            
        Returns:
            TradingSignal object or None if invalid
        """
        try:
            action = signal_dict.get("action", "").lower()
            symbol = signal_dict.get("symbol", "")
            price = float(signal_dict.get("price", 0))
            
            if not symbol or not action:
                logger.warning(f"Invalid signal: missing symbol or action")
                return None
            
            signal_type_map = {
                "buy": SignalType.BUY,
                "sell": SignalType.SELL,
                "close": SignalType.CLOSE
            }
            
            signal_type = signal_type_map.get(action)
            if not signal_type:
                logger.warning(f"Unknown signal action: {action}")
                return None
            
            return TradingSignal(
                symbol=symbol,
                signal_type=signal_type,
                price=price,
                timestamp=None,
                metadata=signal_dict.get("metadata", {})
            )
            
        except Exception as e:
            logger.error(f"Error converting signal: {e}")
            return None
    
    async def handle_raw_signal(
        self,
        signal_dict: Dict[str, Any],
        positions: Dict[str, PositionState],
    ) -> Optional[StrategyEvaluation]:
        """
        Handle a raw signal dictionary and return evaluation.
        
        This is a convenience method that combines conversion and basic
        evaluation for signals that need immediate response.
        
        Args:
            signal_dict: Raw signal data
            positions: Current active positions
            
        Returns:
            StrategyEvaluation for the signal
        """
        trading_signal = self.convert_raw_signal(signal_dict)
        if not trading_signal:
            return None
        
        symbol = trading_signal.symbol
        
        # Handle close signals directly
        if trading_signal.signal_type == SignalType.CLOSE:
            if symbol in positions:
                return StrategyEvaluation(
                    should_act=True,
                    action_type="close",
                    reason="Close signal received",
                    confidence=1.0,
                    recommended_size=abs(positions[symbol].quantity)
                )
            return None
        
        # For buy/sell, return basic evaluation
        return StrategyEvaluation(
            should_act=True,
            action_type="entry",
            reason=f"{trading_signal.signal_type.value} signal for {symbol}",
            confidence=0.8,
            metadata={'signal': trading_signal}
        )
