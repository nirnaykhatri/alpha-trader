"""
DCA (Dollar Cost Average) Trading Strategy.

Implements the ITradingStrategy interface for DCA-based position management.
This is the primary strategy that processes TradingView webhooks and executes
trades using technical analysis-based DCA triggers.

Configuration is driven exclusively by bot's BotConfiguration from database.

Key Features:
- Technical analysis-based DCA triggers (NOT percentage-based)
- Progressive pricing validation (each DCA must improve average)
- Trailing take profit with configurable activation
- Martingale safety integration
- Position lifecycle management (entry, DCA, exit)

Author: Trading Bot Team
Version: 2.0.0 (Refactored from AdvancedTradingStrategy)
"""

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Optional, Any
from src.interfaces import (
    IOrderManager, IMarketDataProvider, IRiskManager, ITradingStrategy,
    TradingSignal, SignalType, Position, StrategyEvaluation
)
from src.core.logging_config import get_logger
from src.strategies.position_state import PositionState, PositionDirection, TradePhase
from src.strategies.entry_executor import EntrySignalExecutor
from src.strategies.dca_planner import DCAPlanner
from src.strategies.trailing_manager import TrailingManager
from src.strategies.phase_manager import PhaseManager
from src.strategies.position_bootstrapper import PositionBootstrapper
from src.risk.martingale_validator import MartingaleSafetyManager
from src.domain.bot_models import BotConfiguration, TakeProfitType, BotType


@dataclass
class DCAStrategyDependencies:
    """
    Container for optional DCAStrategy dependencies.
    
    Groups the 8 optional injected components into a single dataclass,
    reducing constructor complexity while maintaining flexibility.
    All fields default to None, allowing partial injection for testing.
    
    Example:
        # Full injection
        deps = DCAStrategyDependencies(
            martingale_safety=my_martingale,
            entry_executor=my_executor,
        )
        strategy = DCAStrategy(..., dependencies=deps)
        
        # Or individual fields via dataclass creation
        deps = DCAStrategyDependencies()
        deps.dca_planner = custom_planner
    
    Attributes:
        dca_metadata_manager: DCA metadata persistence manager.
        martingale_safety: Martingale safety validator.
        dca_pause_guard: DCA pause guard for resilience.
        position_bootstrapper: Position restoration from DB.
        entry_executor: Entry signal handler.
        dca_planner: DCA decision planner.
        trailing_manager: Trailing take profit manager.
        phase_manager: Position phase transitions manager.
    """
    dca_metadata_manager: Optional[Any] = None
    martingale_safety: Optional[MartingaleSafetyManager] = None
    dca_pause_guard: Optional[Any] = None
    position_bootstrapper: Optional[PositionBootstrapper] = None
    entry_executor: Optional[EntrySignalExecutor] = None
    dca_planner: Optional[DCAPlanner] = None
    trailing_manager: Optional[TrailingManager] = None
    phase_manager: Optional[PhaseManager] = None

logger = get_logger(__name__)


class DCAStrategy(ITradingStrategy):
    """
    DCA (Dollar Cost Average) trading strategy implementing ITradingStrategy interface.
    
    Delegates to focused components following Single Responsibility Principle:
    - EntrySignalExecutor: Handles position entries
    - DCAPlanner: Manages DCA (safety order) decisions
    - TrailingManager: Handles trailing take profit
    - PhaseManager: Manages position phase transitions
    - MartingaleSafetyManager: Validates martingale safety limits
    
    Configuration is driven exclusively by bot's BotConfiguration from database.
    
    This strategy can be swapped with other ITradingStrategy implementations
    (e.g., GridStrategy, LoopStrategy) without modifying the BotRunner.
    
    Example:
        strategy = DCAStrategy(order_manager, market_data, risk_manager, bot_config)
        await strategy.initialize()
        
        # Process signals
        evaluation = await strategy.evaluate_entry(signal)
        if evaluation.should_act:
            await strategy.process_signal(signal)
    """
    
    # Strategy identification
    STRATEGY_NAME = "dca_strategy"
    BOT_TYPE = BotType.DCA
    
    def __init__(
        self,
        order_manager: IOrderManager,
        market_data: IMarketDataProvider,
        risk_manager: IRiskManager,
        bot_config: BotConfiguration,
        position_manager=None,
        resilience_tracker=None,
        # Grouped optional dependencies (preferred approach)
        dependencies: Optional[DCAStrategyDependencies] = None,
    ):
        """
        Initialize the DCA trading strategy with dependency injection.
        
        All components can be injected via the dependencies dataclass for cleaner DI.
        If not provided, default implementations are created for backward compatibility.
        
        Args:
            order_manager: Order execution manager
            market_data: Market data provider
            risk_manager: Risk management service
            bot_config: Bot's configuration from database (REQUIRED)
            position_manager: Position tracking manager (optional)
            resilience_tracker: Resilience tracking service (optional)
            dependencies: Grouped optional dependencies container. Contains:
                - dca_metadata_manager: DCA metadata persistence
                - martingale_safety: Martingale safety validator
                - dca_pause_guard: DCA pause guard for resilience
                - position_bootstrapper: Position restoration from DB
                - entry_executor: Entry signal handler
                - dca_planner: DCA decision planner
                - trailing_manager: Trailing take profit manager
                - phase_manager: Position phase transitions
            
        Raises:
            ValueError: If bot_config is None
            
        Example:
            # Simple usage (creates defaults)
            strategy = DCAStrategy(order_mgr, market_data, risk_mgr, bot_config)
            
            # With custom dependencies
            deps = DCAStrategyDependencies(
                martingale_safety=custom_martingale,
                entry_executor=custom_executor,
            )
            strategy = DCAStrategy(order_mgr, market_data, risk_mgr, bot_config, dependencies=deps)
        """
        # Initialize dependencies container (empty if not provided)
        deps = dependencies or DCAStrategyDependencies()
        
        if bot_config is None:
            raise ValueError("bot_config is required - configuration must come from database")
        
        self.order_manager = order_manager
        self.market_data = market_data
        self.risk_manager = risk_manager
        self.position_manager = position_manager
        self._bot_config = bot_config
        
        # Strategy state tracking
        self._is_active = False
        self._is_initialized = False
        
        # Active positions tracking
        self.positions: Dict[str, PositionState] = {}
        self.position_timeframes: Dict[str, str] = {}
        
        # Use injected DCA metadata manager (Cosmos-based) or None
        # Note: DCA metadata is now stored in Cosmos DB via BotOrder/BotHistory
        if deps.dca_metadata_manager is not None:
            self.dca_metadata_manager = deps.dca_metadata_manager
            logger.info("✅ DCA metadata manager injected")
        else:
            # DCA metadata is tracked via Cosmos DB bot orders/history
            self.dca_metadata_manager = None
            logger.debug("DCA metadata manager not injected - using Cosmos DB for order tracking")
        
        # Use injected martingale safety manager or create default
        if deps.martingale_safety is not None:
            self.martingale_safety = deps.martingale_safety
            logger.info("✅ Martingale safety manager injected")
        else:
            self.martingale_safety = MartingaleSafetyManager(bot_config.dca_config)
            logger.info("✅ Martingale safety manager created (default)")
        
        # Use injected DCA pause guard or create default
        if deps.dca_pause_guard is not None:
            self.dca_pause_guard = deps.dca_pause_guard
            logger.info("✅ DCA pause guard injected")
        elif resilience_tracker:
            try:
                from src.resilience.dca_pause_guard import DcaPauseGuard
                self.dca_pause_guard = DcaPauseGuard(resilience_tracker)
                logger.info("✅ DCA pause guard created (default)")
            except Exception as e:
                logger.warning(f"⚠️ Could not create DCA pause guard: {e}")
                self.dca_pause_guard = None
        else:
            self.dca_pause_guard = None
        
        # Use injected position bootstrapper or create default
        if deps.position_bootstrapper is not None:
            self.position_bootstrapper = deps.position_bootstrapper
            logger.info("✅ Position bootstrapper injected")
        else:
            self.position_bootstrapper = PositionBootstrapper(
                self.position_manager,
                self.dca_metadata_manager
            )
            logger.info("✅ Position bootstrapper created (default)")
        
        # Use injected entry executor or create default
        if deps.entry_executor is not None:
            self.entry_executor = deps.entry_executor
            logger.info("✅ Entry executor injected")
        else:
            self.entry_executor = EntrySignalExecutor(
                order_manager=order_manager,
                market_data=market_data,
                risk_manager=risk_manager,
                bot_config=bot_config,
                position_manager=position_manager,
                dca_metadata_manager=self.dca_metadata_manager
            )
            logger.info("✅ Entry executor created (default)")
        
        # Use injected DCA planner or create default
        if deps.dca_planner is not None:
            self.dca_planner = deps.dca_planner
            logger.info("✅ DCA planner injected")
        else:
            self.dca_planner = DCAPlanner(
                order_manager=order_manager,
                martingale_safety=self.martingale_safety,
                bot_dca_config=bot_config.dca_config,
                dca_metadata_manager=self.dca_metadata_manager
            )
            logger.info("✅ DCA planner created (default)")
        
        # Use injected trailing manager or create default
        if deps.trailing_manager is not None:
            self.trailing_manager = deps.trailing_manager
            logger.info("✅ Trailing manager injected")
        else:
            self.trailing_manager = TrailingManager(bot_config=bot_config)
            logger.info("✅ Trailing manager created (default)")
        
        # Use injected phase manager or create default
        if deps.phase_manager is not None:
            self.phase_manager = deps.phase_manager
            logger.info("✅ Phase manager injected")
        else:
            self.phase_manager = PhaseManager(bot_config=bot_config)
            logger.info("✅ Phase manager created (default)")
        
        logger.info("✅ DCA Trading Strategy initialized")
        logger.info("⚠️  Call await strategy.initialize() to load positions from database")
    
    def set_bot_config(self, bot_config: BotConfiguration) -> None:
        """
        Update the bot's configuration at runtime.
        
        This allows dynamic configuration updates when a bot's settings
        are modified in the database.
        
        Args:
            bot_config: New bot configuration from the database
            
        Raises:
            ValueError: If bot_config is None
        """
        if bot_config is None:
            raise ValueError("bot_config cannot be None - database configuration required")
        self._bot_config = bot_config
        self.dca_planner.set_bot_config(bot_config.dca_config)
        self.entry_executor.set_bot_config(bot_config)
        logger.info(f"✅ Bot configuration updated")
    
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
        
        # Update profit percentage (ensure float for calculations)
        avg_price = float(position.average_price) if position.average_price else 0
        curr_price = float(current_price) if current_price else 0
        if avg_price > 0:
            if position.direction == PositionDirection.LONG:
                position.profit_percentage = (curr_price - avg_price) / avg_price
            else:
                position.profit_percentage = (avg_price - curr_price) / avg_price
        
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
            
            # Calculate current profit percentage (ensure float for calculations)
            avg_price = float(position.average_price) if position.average_price else 0
            curr_price = float(current_price) if current_price else 0
            if avg_price > 0:
                if position.direction == PositionDirection.LONG:
                    position.profit_percentage = (curr_price - avg_price) / avg_price
                else:
                    position.profit_percentage = (avg_price - curr_price) / avg_price
            
            # Delegate to unified position update handler
            await self._update_position_by_direction(position)
            
        except Exception as e:
            logger.error(f"❌ Error updating position for {symbol}: {e}")
    
    async def _update_position_by_direction(self, position: PositionState) -> None:
        """
        Unified position update handler for both LONG and SHORT positions.
        
        Delegates to appropriate trailing and DCA managers based on position direction.
        Eliminates duplicate code between _update_long_position and _update_short_position.
        
        Args:
            position: Current position state to update
        """
        is_long = position.direction == PositionDirection.LONG
        
        # Get profit threshold from database config
        profit_threshold = self._get_profit_threshold()
        
        # Check if trailing take profit is enabled
        is_trailing_tp_enabled = self._is_trailing_take_profit_enabled()
        
        # Check if should start profit trailing (only if trailing TP type is enabled)
        if is_trailing_tp_enabled and position.profit_percentage >= profit_threshold:
            if position.phase != TradePhase.PROFIT_TRAILING:
                self.trailing_manager.initialize_trailing(position)
        
        # Phase-specific logic
        if position.phase == TradePhase.PROFIT_TRAILING:
            # Select trailing update method based on direction
            trailing_method = (
                self.trailing_manager.update_long_trailing if is_long
                else self.trailing_manager.update_short_trailing
            )
            await trailing_method(
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
                            "component": "DCAStrategy",
                            "symbol": position.symbol,
                            "reason": pause_decision.reason
                        }
                    )
                    return  # Skip DCA execution
            
            # Check for martingale DCA opportunity (loss-based trigger)
            timeframe = self._get_position_timeframe(position.symbol)
            
            # Select DCA check method based on direction
            dca_check_method = (
                self.dca_planner.check_martingale_dca_long if is_long
                else self.dca_planner.check_martingale_dca_short
            )
            dca_decision = await dca_check_method(position, timeframe)
            
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
    
    def _get_profit_threshold(self) -> float:
        """
        Get profit threshold from database configuration.
        
        Returns:
            Profit threshold as a decimal (e.g., 0.01 for 1%)
            
        Raises:
            ValueError: If take_profit configuration is missing
        """
        if (self._bot_config.dca_config and 
            self._bot_config.dca_config.take_profit):
            # Convert percentage to decimal (ensure float for mixed-type calculations)
            return float(self._bot_config.dca_config.take_profit.price_change_percent) / 100.0
        raise ValueError("take_profit.price_change_percent configuration is required in database")
    
    def _is_trailing_take_profit_enabled(self) -> bool:
        """
        Check if trailing take profit mode is enabled.
        
        Returns:
            True if take_profit.type is TRAILING, False otherwise (defaults to regular TP)
        """
        if (self._bot_config.dca_config and 
            self._bot_config.dca_config.take_profit):
            return self._bot_config.dca_config.take_profit.type == TakeProfitType.TRAILING
        return False  # Default to regular take profit (no trailing)
    
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
    
    # =========================================================================
    # ITradingStrategy Interface Implementation
    # =========================================================================
    
    async def initialize(self) -> None:
        """
        Initialize the strategy and load existing positions from database.
        
        Called once before the strategy starts processing signals.
        Loads historical positions and DCA metadata for continuity.
        """
        if self._is_initialized:
            logger.warning("Strategy already initialized, skipping re-initialization")
            return
        
        logger.info(f"🚀 Initializing {self.name} strategy...")
        
        try:
            # Load existing positions from database
            await self._load_positions_from_database()
            
            self._is_initialized = True
            self._is_active = True
            
            logger.info(f"✅ {self.name} strategy initialized successfully")
            logger.info(f"   Loaded {len(self.positions)} active positions")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize strategy: {e}")
            raise
    
    async def close(self) -> None:
        """
        Close the strategy and release resources.
        
        Called when the strategy is being shut down.
        Saves any pending state and cleans up resources.
        """
        logger.info(f"🛑 Closing {self.name} strategy...")
        
        self._is_active = False
        
        # Log final state
        logger.info(f"   Final state: {len(self.positions)} active positions")
        for symbol, position in self.positions.items():
            logger.info(f"   - {symbol}: {position.quantity} @ ${position.average_price:.2f}")
        
        # Clear position tracking (positions remain in database)
        self.positions.clear()
        self.position_timeframes.clear()
        
        self._is_initialized = False
        logger.info(f"✅ {self.name} strategy closed")
    
    async def evaluate_entry(
        self,
        signal: TradingSignal,
        position: Optional[Position] = None,
        market_context: Optional[Dict[str, Any]] = None
    ) -> StrategyEvaluation:
        """
        Evaluate whether to enter a new position or add to existing.
        
        Args:
            signal: The incoming trading signal
            position: Existing position if any (for DCA evaluation)
            market_context: Additional market data (support levels, volatility, etc.)
            
        Returns:
            StrategyEvaluation with entry decision and recommended size
        """
        symbol = signal.symbol
        existing_position = self.positions.get(symbol)
        
        # Check if we already have a position
        if existing_position:
            # Evaluate for potential DCA instead of new entry
            return await self.evaluate_dca(
                position=existing_position,
                current_price=signal.price,
                market_context=market_context
            )
        
        # New position evaluation
        try:
            # Validate signal with risk manager
            is_valid = await self.risk_manager.validate_order(None)  # Basic validation
            
            if not is_valid:
                return StrategyEvaluation(
                    should_act=False,
                    action_type="skip",
                    reason="Risk validation failed",
                    confidence=0.0
                )
            
            # Calculate recommended position size
            recommended_size = await self.risk_manager.calculate_position_size(
                symbol, signal
            )
            
            return StrategyEvaluation(
                should_act=True,
                action_type="entry",
                reason=f"New {signal.signal_type.value} signal at ${signal.price:.2f}",
                confidence=0.8,  # Base confidence for signal-based entries
                recommended_size=recommended_size,
                metadata={
                    'signal_type': signal.signal_type.value,
                    'timeframe': signal.metadata.get('timeframe', '15m') if signal.metadata else '15m'
                }
            )
            
        except Exception as e:
            logger.error(f"Error evaluating entry for {symbol}: {e}")
            return StrategyEvaluation(
                should_act=False,
                action_type="skip",
                reason=f"Evaluation error: {str(e)}",
                confidence=0.0
            )
    
    async def evaluate_exit(
        self,
        position: Position,
        current_price: float,
        market_context: Optional[Dict[str, Any]] = None
    ) -> StrategyEvaluation:
        """
        Evaluate whether to exit an existing position.
        
        Args:
            position: The current position to evaluate
            current_price: Current market price
            market_context: Additional market data (resistance levels, etc.)
            
        Returns:
            StrategyEvaluation with exit decision and size (partial/full)
        """
        symbol = position.symbol
        strategy_position = self.positions.get(symbol)
        
        if not strategy_position:
            return StrategyEvaluation(
                should_act=False,
                action_type="skip",
                reason="Position not tracked by strategy",
                confidence=0.0
            )
        
        # Calculate profit percentage
        if strategy_position.direction == PositionDirection.LONG:
            profit_pct = (current_price - strategy_position.average_price) / strategy_position.average_price
        else:
            profit_pct = (strategy_position.average_price - current_price) / strategy_position.average_price
        
        # Check if trailing stop should trigger
        profit_threshold = self._get_profit_threshold()
        
        if strategy_position.phase == TradePhase.PROFIT_TRAILING:
            # Check trailing stop condition
            if strategy_position.direction == PositionDirection.LONG:
                should_exit = current_price <= strategy_position.trail_price
            else:
                should_exit = current_price >= strategy_position.trail_price
            
            if should_exit:
                return StrategyEvaluation(
                    should_act=True,
                    action_type="exit",
                    reason=f"Trailing stop triggered at ${current_price:.2f}",
                    confidence=1.0,
                    recommended_size=abs(strategy_position.quantity),
                    metadata={
                        'exit_type': 'trailing_stop',
                        'profit_percent': profit_pct * 100,
                        'trail_price': strategy_position.trail_price,
                        'peak_price': strategy_position.peak_price
                    }
                )
        
        # Check profit target
        if profit_pct >= profit_threshold:
            return StrategyEvaluation(
                should_act=True,
                action_type="exit",
                reason=f"Profit target reached: {profit_pct*100:.2f}%",
                confidence=0.9,
                recommended_size=abs(strategy_position.quantity),
                metadata={
                    'exit_type': 'profit_target',
                    'profit_percent': profit_pct * 100
                }
            )
        
        return StrategyEvaluation(
            should_act=False,
            action_type="hold",
            reason=f"Profit {profit_pct*100:.2f}% below threshold {profit_threshold*100:.2f}%",
            confidence=0.5,
            metadata={'current_profit_percent': profit_pct * 100}
        )
    
    async def evaluate_dca(
        self,
        position: Position,
        current_price: float,
        market_context: Optional[Dict[str, Any]] = None
    ) -> StrategyEvaluation:
        """
        Evaluate whether to execute a DCA (Dollar Cost Average) order.
        
        Uses martingale-based loss thresholds for DCA decisions.
        Each DCA must improve the position's average price (progressive pricing).
        
        Args:
            position: The current position to average into
            current_price: Current market price
            market_context: Additional market data (support levels, volume, etc.)
            
        Returns:
            StrategyEvaluation with DCA decision and recommended size
        """
        symbol = position.symbol if isinstance(position, Position) else position.symbol
        strategy_position = self.positions.get(symbol)
        
        if not strategy_position:
            return StrategyEvaluation(
                should_act=False,
                action_type="skip",
                reason="Position not tracked by strategy",
                confidence=0.0
            )
        
        # Update current price
        strategy_position.current_price = current_price
        
        # Check DCA pause guard
        if self.dca_pause_guard:
            pause_decision = await self.dca_pause_guard.evaluate()
            if not pause_decision.allow_dca:
                return StrategyEvaluation(
                    should_act=False,
                    action_type="skip",
                    reason=f"DCA paused: {pause_decision.reason}",
                    confidence=0.0
                )
        
        # Delegate to DCA planner
        timeframe = self._get_position_timeframe(symbol)
        
        if strategy_position.direction == PositionDirection.LONG:
            dca_decision = await self.dca_planner.check_martingale_dca_long(
                strategy_position, timeframe
            )
        else:
            dca_decision = await self.dca_planner.check_martingale_dca_short(
                strategy_position, timeframe
            )
        
        if dca_decision['should_dca']:
            # Calculate DCA quantity
            is_long = strategy_position.direction == PositionDirection.LONG
            recommended_size = await self._calculate_averaging_position_size(
                strategy_position, current_price, is_long
            )
            
            return StrategyEvaluation(
                should_act=True,
                action_type="dca",
                reason=dca_decision.get('message', 'DCA threshold reached'),
                confidence=dca_decision.get('confidence', 0.8),
                recommended_size=recommended_size,
                metadata={
                    'dca_level': strategy_position.averaging_attempts + 1,
                    'trigger_price': dca_decision.get('trigger_price', current_price),
                    'last_dca_price': strategy_position.last_dca_price
                }
            )
        
        return StrategyEvaluation(
            should_act=False,
            action_type="hold",
            reason=dca_decision.get('message', 'DCA threshold not reached'),
            confidence=0.0,
            metadata={
                'distance_percent': dca_decision.get('distance_percent', 0),
                'current_loss_percent': strategy_position.profit_percentage * -100 if strategy_position.profit_percentage < 0 else 0
            }
        )
    
    async def execute_tick(
        self,
        current_price: float,
        market_context: Optional[Dict[str, Any]] = None
    ) -> Optional[StrategyEvaluation]:
        """
        Execute one tick of the DCA strategy's main loop.
        
        For DCA strategy, this monitors existing positions for:
        - Take profit conditions (regular or trailing)
        - DCA (safety order) conditions
        
        Args:
            current_price: Current market price
            market_context: Additional market data
            
        Returns:
            StrategyEvaluation if action needed, None otherwise
        """
        if not self._is_active:
            return None
        
        # Process all tracked positions
        for symbol, position in list(self.positions.items()):
            try:
                # Update position with current price
                await self.update_position_monitoring(symbol, current_price)
                
                # Check for exit conditions
                exit_eval = await self.evaluate_exit(position, current_price, market_context)
                if exit_eval.should_act:
                    return exit_eval
                
                # Check for DCA conditions (handled in update_position_monitoring)
                
            except Exception as e:
                logger.error(f"Error in tick for {symbol}: {e}")
        
        return None
    
    async def handle_signal(
        self,
        signal: Dict[str, Any]
    ) -> Optional[StrategyEvaluation]:
        """
        Handle an incoming trading signal.
        
        Converts raw signal dict to TradingSignal and evaluates entry.
        
        Args:
            signal: Signal data with action, symbol, price, etc.
            
        Returns:
            StrategyEvaluation if action should be taken
        """
        try:
            action = signal.get("action", "").lower()
            symbol = signal.get("symbol", "")
            price = float(signal.get("price", 0))
            
            # Convert to TradingSignal
            signal_type_map = {
                "buy": SignalType.BUY,
                "sell": SignalType.SELL,
                "close": SignalType.CLOSE
            }
            
            signal_type = signal_type_map.get(action)
            if not signal_type:
                logger.warning(f"Unknown signal action: {action}")
                return None
            
            trading_signal = TradingSignal(
                symbol=symbol,
                signal_type=signal_type,
                price=price,
                timestamp=None,
                metadata=signal.get("metadata", {})
            )
            
            # Handle close signals directly
            if signal_type == SignalType.CLOSE:
                if symbol in self.positions:
                    return StrategyEvaluation(
                        should_act=True,
                        action_type="close",
                        reason="Close signal received",
                        confidence=1.0,
                        recommended_size=abs(self.positions[symbol].quantity)
                    )
                return None
            
            # Evaluate entry for buy/sell
            return await self.evaluate_entry(trading_signal)
            
        except Exception as e:
            logger.error(f"Error handling signal: {e}")
            return None
    
    def get_state(self) -> Dict[str, Any]:
        """
        Get the current state of the strategy.
        
        Returns:
            Dictionary containing strategy state for monitoring/debugging.
        """
        return {
            'name': self.name,
            'bot_type': self.bot_type.value,
            'is_active': self.is_active,
            'is_initialized': self._is_initialized,
            'active_positions_count': len(self.positions),
            'positions': self.get_position_summary(),
            'pending_signals': {},  # Could track pending signals if needed
            'performance': {
                'total_positions_managed': len(self.positions),
                'positions_in_profit': sum(
                    1 for p in self.positions.values() 
                    if p.profit_percentage > 0
                ),
                'positions_in_loss': sum(
                    1 for p in self.positions.values() 
                    if p.profit_percentage < 0
                ),
                'positions_trailing': sum(
                    1 for p in self.positions.values() 
                    if p.phase == TradePhase.PROFIT_TRAILING
                )
            }
        }
    
    @property
    def name(self) -> str:
        """Get the strategy name for identification."""
        return self.STRATEGY_NAME
    
    @property
    def is_active(self) -> bool:
        """Check if the strategy is currently active and processing signals."""
        return self._is_active
    
    @property
    def bot_type(self) -> BotType:
        """Get the bot type this strategy implements."""
        return self.BOT_TYPE
