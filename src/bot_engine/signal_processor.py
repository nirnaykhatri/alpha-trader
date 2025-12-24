"""
Signal Processor - Handles trading signal dispatch and processing.

Extracted from TradingBotOrchestrator to follow Single Responsibility Principle.
This class is responsible for processing incoming trading signals and routing
them to appropriate handlers.

Author: Trading Bot Team
Version: 1.0.0
"""

from typing import Dict, Optional, TYPE_CHECKING

from src.core.logging_config import get_logger
from src import TradingSignal, Order, OrderType, OrderSide, SignalType

if TYPE_CHECKING:
    from src.risk import RiskManager
    from src.position import PositionManager
    from src.trading import OrderManager, ExitPlanner
    from src.strategies import DCAStrategy


logger = get_logger(__name__)


class SignalProcessor:
    """
    Processes incoming trading signals and routes to handlers.
    
    Responsibilities:
    - Validating signals against risk constraints
    - Routing signals to appropriate handlers (buy/sell/close)
    - Managing processed signal history
    - Coordinating with DCA strategy for position management
    
    This class implements the Command pattern, where each signal
    type is handled by a specific method.
    
    Usage:
        processor = SignalProcessor(
            risk_manager=risk,
            position_manager=positions,
            order_manager=orders,
            exit_planner=planner,
            dca_strategy=strategy
        )
        await processor.process_signal(signal)
    """
    
    def __init__(
        self,
        risk_manager: "RiskManager",
        position_manager: "PositionManager",
        order_manager: "OrderManager",
        exit_planner: "ExitPlanner",
        dca_strategy: Optional["DCAStrategy"] = None
    ):
        """
        Initialize signal processor with required dependencies.
        
        Args:
            risk_manager: Risk validation service
            position_manager: Position tracking service
            order_manager: Order execution service
            exit_planner: Exit order planning service
            dca_strategy: Optional DCA strategy for advanced signal handling
        """
        self._risk_manager = risk_manager
        self._position_manager = position_manager
        self._order_manager = order_manager
        self._exit_planner = exit_planner
        self._dca_strategy = dca_strategy
        
        # Track processed signals
        self._processed_signals: Dict[str, TradingSignal] = {}
        
        logger.debug("SignalProcessor initialized")
    
    @property
    def processed_signals(self) -> Dict[str, TradingSignal]:
        """Get dictionary of processed signals."""
        return self._processed_signals.copy()
    
    @property
    def processed_signal_count(self) -> int:
        """Get count of processed signals."""
        return len(self._processed_signals)
    
    def set_dca_strategy(self, strategy: "DCAStrategy") -> None:
        """Set or update the DCA strategy."""
        self._dca_strategy = strategy
        logger.debug("DCA strategy updated in SignalProcessor")
    
    async def process_signal(self, signal: TradingSignal) -> bool:
        """
        Process an incoming trading signal.
        
        Validates the signal against risk constraints and routes
        to the appropriate handler based on signal type.
        
        Args:
            signal: The trading signal to process
            
        Returns:
            True if signal was processed successfully, False otherwise
        """
        try:
            logger.info(
                f"Processing signal: {signal.symbol} {signal.signal_type.value} "
                f"@ {signal.price}"
            )
            
            # Store signal for tracking
            self._processed_signals[signal.signal_id] = signal
            
            # Risk validation
            if not await self._risk_manager.validate_signal(signal):
                logger.warning(f"Signal rejected by risk manager: {signal.signal_id}")
                return False
            
            # Route to appropriate handler
            if self._dca_strategy:
                # Use DCA strategy for advanced handling
                await self._dca_strategy.process_signal(signal)
            else:
                # Fallback to basic signal handling
                await self._handle_signal_basic(signal)
            
            logger.info(f"Signal processed successfully: {signal.signal_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error processing signal {signal.signal_id}: {str(e)}")
            return False
    
    async def _handle_signal_basic(self, signal: TradingSignal) -> None:
        """
        Basic signal handling when DCA strategy is not available.
        
        Routes signals to specific handlers based on signal type.
        """
        if signal.signal_type == SignalType.BUY:
            await self._handle_buy_signal(signal)
        elif signal.signal_type == SignalType.SELL:
            await self._handle_sell_signal(signal)
        elif signal.signal_type == SignalType.CLOSE:
            await self._handle_close_signal(signal)
        else:
            logger.warning(f"Unknown signal type: {signal.signal_type}")
    
    async def _handle_buy_signal(self, signal: TradingSignal) -> None:
        """
        Handle buy signals.
        
        Note: DCA is handled by DCAStrategy when available.
        """
        try:
            symbol = signal.symbol
            
            # Check if we already have a position
            existing_position = await self._position_manager.get_position(symbol)
            
            if existing_position and existing_position.quantity > 0:
                # Position exists - DCA should be handled by strategy
                logger.info(
                    f"Position exists for {symbol} - DCA handled by DCAStrategy"
                )
                return
            
            # Calculate position size
            position_size = await self._risk_manager.calculate_position_size(
                symbol, signal
            )
            
            # Create buy order
            order = Order(
                order_id=None,
                symbol=symbol,
                quantity=position_size,
                order_type=OrderType.MARKET if signal.price == 0 else OrderType.LIMIT,
                side=OrderSide.BUY,
                price=signal.price if signal.price > 0 else None
            )
            
            # Place order
            order_id = await self._order_manager.place_order(order)
            logger.info(f"Buy order placed: {order_id}")
            
        except Exception as e:
            logger.error(f"Error handling buy signal: {str(e)}")
    
    async def _handle_sell_signal(self, signal: TradingSignal) -> None:
        """Handle sell signals."""
        try:
            symbol = signal.symbol
            
            # Check if we have a position to sell
            position = await self._position_manager.get_position(symbol)
            
            if not position or position.quantity <= 0:
                logger.warning(f"No position to sell for {symbol}")
                return
            
            # Calculate quantity to sell
            sell_quantity = signal.quantity or position.quantity
            
            # Create sell order
            order = Order(
                order_id=None,
                symbol=symbol,
                quantity=sell_quantity,
                order_type=OrderType.MARKET if signal.price == 0 else OrderType.LIMIT,
                side=OrderSide.SELL,
                price=signal.price if signal.price > 0 else None
            )
            
            # Place order
            order_id = await self._order_manager.place_order(order)
            logger.info(f"Sell order placed: {order_id}")
            
        except Exception as e:
            logger.error(f"Error handling sell signal: {str(e)}")
    
    async def _handle_close_signal(self, signal: TradingSignal) -> None:
        """Handle close signals - close all positions for the symbol."""
        try:
            symbol = signal.symbol
            position = await self._position_manager.get_position(symbol)
            
            if not position:
                logger.warning(f"No position to close for {symbol}")
                return
            
            # Use ExitPlanner to build exit order
            exit_plan = await self._exit_planner.plan_exit(
                position,
                reason="signal_close"
            )
            
            # Submit the exit order
            order = exit_plan.to_order()
            order_id = await self._order_manager.place_order(order)
            logger.info(f"Close order placed: {order_id}")
            
        except Exception as e:
            logger.error(f"Error handling close signal: {str(e)}")
    
    def clear_processed_signals(self) -> None:
        """Clear the processed signals history."""
        self._processed_signals.clear()
        logger.debug("Processed signals history cleared")
    
    def get_signal(self, signal_id: str) -> Optional[TradingSignal]:
        """Get a processed signal by ID."""
        return self._processed_signals.get(signal_id)
