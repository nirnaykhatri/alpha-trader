"""
Advanced Trading Strategy Orchestrator (Refactored)
Thin orchestrator that delegates to focused strategy components.
Maintains backward compatibility while following SOLID principles.
"""

import asyncio
from typing import Dict, Optional
from src.interfaces import IConfigurationManager, IOrderManager, IMarketDataProvider, IRiskManager
from src.core.logging_config import get_logger
from src import TradingSignal, SignalType
from src.strategies.position_state import PositionState, PositionDirection, TradePhase
from src.strategies.entry_executor import EntrySignalExecutor
from src.strategies.dca_planner import DCAPlanner
from src.strategies.trailing_manager import TrailingManager
from src.strategies.phase_manager import PhaseManager
from src.strategies.position_bootstrapper import PositionBootstrapper
from src.risk.martingale_validator import MartingaleSafetyManager

logger = get_logger(__name__)


class AdvancedTradingStrategy:
    """
    Advanced trading strategy orchestrator.
    Delegates to focused components following Single Responsibility Principle.
    """
    
    def __init__(
        self,
        config: IConfigurationManager,
        order_manager: IOrderManager,
        market_data: IMarketDataProvider,
        risk_manager: IRiskManager,
        position_manager=None,
        resilience_tracker=None
    ):
        """Initialize the advanced trading strategy orchestrator."""
        self.config = config
        self.order_manager = order_manager
        self.market_data = market_data
        self.risk_manager = risk_manager
        self.position_manager = position_manager
        
        # Active positions tracking
        self.positions: Dict[str, PositionState] = {}
        self.position_timeframes: Dict[str, str] = {}
        
        # Initialize DCA metadata manager
        self.dca_metadata_manager = None
        if self.position_manager and hasattr(self.position_manager, 'database'):
            try:
                from ..database.dca_metadata_manager import DCAMetadataManager
                self.dca_metadata_manager = DCAMetadataManager(self.position_manager.database)
                logger.info("✅ DCA metadata manager initialized")
            except Exception as e:
                logger.warning(f"⚠️ Could not initialize DCA metadata manager: {e}")
        
        # Initialize martingale safety manager
        self.martingale_safety = MartingaleSafetyManager(config)
        
        # Initialize DCA pause guard
        self.dca_pause_guard = None
        if resilience_tracker:
            try:
                from src.resilience.dca_pause_guard import DcaPauseGuard
                self.dca_pause_guard = DcaPauseGuard(resilience_tracker)
                logger.info("✅ DCA pause guard initialized")
            except Exception as e:
                logger.warning(f"⚠️ Could not initialize DCA pause guard: {e}")
        
        # Initialize position bootstrapper
        self.position_bootstrapper = PositionBootstrapper(
            self.position_manager,
            self.dca_metadata_manager
        )
        
        # Initialize strategy components (Dependency Injection)
        self.entry_executor = EntrySignalExecutor(
            config=config,
            order_manager=order_manager,
            market_data=market_data,
            risk_manager=risk_manager,
            position_manager=position_manager,
            dca_metadata_manager=self.dca_metadata_manager
        )
        
        self.dca_planner = DCAPlanner(
            config=config,
            order_manager=order_manager,
            martingale_safety=self.martingale_safety,
            dca_metadata_manager=self.dca_metadata_manager
        )
        
        self.trailing_manager = TrailingManager(config=config)
        
        self.phase_manager = PhaseManager(
            config=config
        )
        
        # Configuration cache
        self.long_config = config.get_config('strategies.long_strategy', {})
        self.short_config = config.get_config('strategies.short_strategy', {})
        
        logger.info("✅ Advanced Trading Strategy Orchestrator initialized")
        logger.info("⚠️  Call await strategy.initialize() to load positions from database")
    
    async def _load_positions_from_database(self):
        """Load existing positions from database on startup using bootstrapper."""
        try:
            self.positions = await self.position_bootstrapper.restore_positions()
        except Exception as e:
            logger.error(f"❌ Failed to load positions from database: {e}")
    
    async def process_signal(self, signal: TradingSignal) -> bool:
        """
        Process a trading signal and execute the appropriate strategy.
        
        Args:
            signal: The trading signal to process
            
        Returns:
            True if signal was processed successfully
        """
        try:
            logger.info(f"📨 Processing signal: {signal.symbol} {signal.signal_type.value} @ ${signal.price:.2f}")
            
            # Store original signal timeframe for future DCA decisions
            timeframe = signal.metadata.get('timeframe', '15m')
            self.position_timeframes[signal.symbol] = timeframe
            logger.info(f"📊 TIMEFRAME STORED: {signal.symbol} -> {timeframe}")
            
            # Delegate to appropriate handler
            if signal.signal_type == SignalType.BUY:
                return await self._handle_long_signal(signal)
            elif signal.signal_type == SignalType.SELL:
                return await self._handle_short_signal(signal)
            elif signal.signal_type == SignalType.CLOSE:
                return await self._handle_close_signal(signal)
            else:
                logger.warning(f"⚠️ Unknown signal type: {signal.signal_type}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error processing signal: {str(e)}")
            return False
    
    async def _handle_long_signal(self, signal: TradingSignal) -> bool:
        """Handle long signal by delegating to entry executor."""
        existing_position = self.positions.get(signal.symbol)
        
        # Delegate to entry executor
        position = await self.entry_executor.handle_long_signal(signal, existing_position)
        
        if position:
            self.positions[signal.symbol] = position
            return True
        
        return False
    
    async def _handle_short_signal(self, signal: TradingSignal) -> bool:
        """Handle short signal by delegating to entry executor."""
        existing_position = self.positions.get(signal.symbol)
        
        # Delegate to entry executor
        position = await self.entry_executor.handle_short_signal(signal, existing_position)
        
        if position:
            self.positions[signal.symbol] = position
            return True
        
        return False
    
    async def _handle_close_signal(self, signal: TradingSignal) -> bool:
        """Handle close signal by delegating to entry executor."""
        symbol = signal.symbol
        
        if symbol not in self.positions:
            logger.warning(f"⚠️ No position found for {symbol} to close")
            return False
        
        position = self.positions[symbol]
        success = await self.entry_executor.close_position(position)
        
        if success:
            del self.positions[symbol]
            if symbol in self.position_timeframes:
                del self.position_timeframes[symbol]
        
        return success
    
    async def update_positions(self):
        """Update all positions with current market data and execute strategy logic."""
        for symbol in list(self.positions.keys()):
            await self._update_position(symbol)
    
    async def update_position_monitoring(self, symbol: str, current_price: float):
        """
        Enhanced position monitoring with technical analysis DCA.
        Entry point for position updates with current price.
        """
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        position.current_price = current_price
        
        # Update profit percentage
        if position.average_price > 0:
            if position.direction == PositionDirection.LONG:
                position.profit_percentage = (current_price - position.average_price) / position.average_price
            else:
                position.profit_percentage = (position.average_price - current_price) / position.average_price
        
        # Delegate to phase-specific update logic
        await self._update_position(symbol)
    
    async def _update_position(self, symbol: str):
        """Update a single position with current market data."""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        
        try:
            # Get current market price
            current_price = await self.market_data.get_current_price(symbol)
            position.current_price = current_price
            
            # Calculate current profit percentage
            if position.average_price > 0:
                if position.direction == PositionDirection.LONG:
                    position.profit_percentage = (current_price - position.average_price) / position.average_price
                else:
                    position.profit_percentage = (position.average_price - current_price) / position.average_price
            
            # Delegate to direction-specific update
            if position.direction == PositionDirection.LONG:
                await self._update_long_position(position)
            else:
                await self._update_short_position(position)
            
        except Exception as e:
            logger.error(f"❌ Error updating position for {symbol}: {e}")
    
    async def _update_long_position(self, position: PositionState):
        """Update long position - delegates to appropriate component based on phase."""
        config = self.long_config
        
        # Check if should start profit trailing
        if position.profit_percentage >= config.get('profit_threshold', 0.01):
            if position.phase != TradePhase.PROFIT_TRAILING:
                self.trailing_manager.initialize_trailing(position)
        
        # Phase-specific logic
        if position.phase == TradePhase.PROFIT_TRAILING:
            await self.trailing_manager.update_long_trailing(
                position,
                close_position_callback=self._close_position_by_symbol
            )
        
        elif position.phase == TradePhase.ENTRY:
            # Check for DCA pause due to resilience state
            if self.dca_pause_guard:
                pause_decision = await self.dca_pause_guard.evaluate()
                if not pause_decision.allow_dca:
                    logger.warning(
                        f"🛑 DCA paused for {position.symbol}: {pause_decision.reason}",
                        extra={
                            "component": "AdvancedTradingStrategy",
                            "symbol": position.symbol,
                            "reason": pause_decision.reason
                        }
                    )
                    return  # Skip DCA execution
            
            # Check for martingale DCA opportunity (loss-based trigger)
            timeframe = self._get_position_timeframe(position.symbol)
            dca_decision = await self.dca_planner.check_martingale_dca_long(position, timeframe)
            
            if dca_decision['should_dca']:
                await self.dca_planner.execute_technical_dca(
                    position,
                    dca_decision,
                    calculate_position_size_callback=self._calculate_averaging_position_size
                )
                # Note: Phase transitions now handled automatically by DCA logic (martingale-only mode)
    
    async def _update_short_position(self, position: PositionState):
        """Update short position - delegates to appropriate component based on phase."""
        config = self.short_config
        
        # Check if should start profit trailing
        if position.profit_percentage >= config.get('profit_threshold', 0.01):
            if position.phase != TradePhase.PROFIT_TRAILING:
                self.trailing_manager.initialize_trailing(position)
        
        # Phase-specific logic
        if position.phase == TradePhase.PROFIT_TRAILING:
            await self.trailing_manager.update_short_trailing(
                position,
                close_position_callback=self._close_position_by_symbol
            )
        
        elif position.phase == TradePhase.ENTRY:
            # Check for DCA pause due to resilience state
            if self.dca_pause_guard:
                pause_decision = await self.dca_pause_guard.evaluate()
                if not pause_decision.allow_dca:
                    logger.warning(
                        f"🛑 DCA paused for {position.symbol}: {pause_decision.reason}",
                        extra={
                            "component": "AdvancedTradingStrategy",
                            "symbol": position.symbol,
                            "reason": pause_decision.reason
                        }
                    )
                    return  # Skip DCA execution
            
            # Check for martingale DCA opportunity (loss-based trigger)
            timeframe = self._get_position_timeframe(position.symbol)
            dca_decision = await self.dca_planner.check_martingale_dca_short(position, timeframe)
            
            if dca_decision['should_dca']:
                await self.dca_planner.execute_technical_dca(
                    position,
                    dca_decision,
                    calculate_position_size_callback=self._calculate_averaging_position_size
                )
                # Note: Phase transitions now handled automatically by DCA logic (martingale-only mode)
    
    async def _close_position_by_symbol(self, symbol: str):
        """Helper to close position by symbol (used by callbacks)."""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        success = await self.entry_executor.close_position(position)
        
        if success:
            del self.positions[symbol]
            if symbol in self.position_timeframes:
                del self.position_timeframes[symbol]
    
    def _get_position_timeframe(self, symbol: str) -> str:
        """Get the original signal timeframe for a position."""
        return self.position_timeframes.get(symbol, '15m')
    
    async def _calculate_averaging_position_size(
        self,
        position: PositionState,
        current_price: float,
        is_long: bool
    ) -> float:
        """
        Calculate position size for averaging orders.
        Delegates to risk manager with DCA context.
        """
        config = self.long_config if is_long else self.short_config
        
        # Create a signal-like object for risk manager
        from src import TradingSignal, SignalType
        signal = TradingSignal(
            symbol=position.symbol,
            signal_type=SignalType.BUY if is_long else SignalType.SELL,
            price=current_price,
            timestamp=None,
            metadata={'timeframe': self._get_position_timeframe(position.symbol)}
        )
        
        # Calculate position size with DCA context
        quantity = await self.risk_manager.calculate_position_size(
            position.symbol,
            signal,
            averaging_attempt=position.averaging_attempts + 1
        )
        
        return quantity
    
    def get_position_summary(self) -> Dict[str, Dict]:
        """Get summary of all active positions with detailed info."""
        summary = {}
        
        for symbol, position in self.positions.items():
            summary[symbol] = {
                'symbol': symbol,
                'direction': position.direction.value,
                'phase': position.phase.value,
                'phase_description': self.phase_manager.get_current_phase_description(position),
                'quantity': position.quantity,
                'average_price': position.average_price,
                'current_price': position.current_price,
                'profit_percentage': position.profit_percentage,
                'profit_amount': position.quantity * (position.current_price - position.average_price) if position.direction == PositionDirection.LONG else position.quantity * (position.average_price - position.current_price),
                'entry_time': position.entry_time.isoformat() if position.entry_time else None,
                'peak_price': position.peak_price,
                'trail_price': position.trail_price,
                'support_level': position.support_level,
                'resistance_level': position.resistance_level,
                'averaging_attempts': position.averaging_attempts,
                'dca_order_prices': position.dca_order_prices,
                'last_dca_price': position.last_dca_price,
                'active_orders': position.active_orders,
                'timeframe': self._get_position_timeframe(symbol)
            }
        
        return summary
