"""
Entry Signal Executor
Handles entry signal execution logic for long, short, and close signals.
Responsible for order placement, position creation, and initial setup.
"""

from typing import Optional
from datetime import datetime
from src.interfaces import IConfigurationManager, IOrderManager, IMarketDataProvider, IRiskManager
from src.core.logging_config import get_logger
from src import TradingSignal, Order, OrderType, OrderSide
from src.domain.position_lifecycle_service import PositionLifecycleService
from src.strategies.position_state import PositionState, PositionDirection, TradePhase
from src.utils.trading_utils import get_order_type

logger = get_logger(__name__)


class EntrySignalExecutor:
    """
    Executes entry signals for long/short positions.
    Follows Single Responsibility Principle - only handles signal entry logic.
    """
    
    def __init__(
        self,
        config: IConfigurationManager,
        order_manager: IOrderManager,
        market_data: IMarketDataProvider,
        risk_manager: IRiskManager,
        position_manager=None,
        dca_metadata_manager=None
    ):
        """Initialize the entry signal executor."""
        self.config = config
        self.order_manager = order_manager
        self.market_data = market_data
        self.risk_manager = risk_manager
        self.position_manager = position_manager
        self.dca_metadata_manager = dca_metadata_manager
        
        # Load strategy configurations
        self.long_config = config.get_config('strategies.long_strategy', {})
        self.short_config = config.get_config('strategies.short_strategy', {})
    
    async def handle_long_signal(
        self,
        signal: TradingSignal,
        existing_position: Optional[PositionState]
    ) -> Optional[PositionState]:
        """
        Handle a long (buy) signal.
        
        Args:
            signal: The trading signal to process
            existing_position: Existing position for this symbol (if any)
            
        Returns:
            PositionState if position created successfully, None otherwise
        """
        if not self.long_config.get('enabled', False):
            logger.info("Long strategy is disabled")
            return None
        
        symbol = signal.symbol
        
        # Fetch current market price
        try:
            current_price = await self.market_data.get_current_price(symbol)
            logger.info(f"Fetched current market price for {symbol}: ${current_price:.2f}")
            signal.price = current_price
        except Exception as e:
            logger.error(f"Failed to fetch current price for {symbol}: {e}")
            return None
        
        # Check for existing position conflicts
        if existing_position:
            if existing_position.direction == PositionDirection.LONG:
                logger.info(f"Already have long position in {symbol}, ignoring signal")
                return None
            else:
                # Handle opposing position
                ignore_opposing = self.config.get_config('trading.position_management.ignore_opposing_signals', True)
                if ignore_opposing:
                    logger.info(
                        f"Already have short position in {symbol}, ignoring opposing long signal. "
                        f"Wait for current position to be closed based on its own rules."
                    )
                    return None
        
        # Calculate position size
        quantity = await self.risk_manager.calculate_position_size(symbol, signal, averaging_attempt=0)
        
        if quantity <= 0:
            logger.warning(f"Insufficient funds to open long position in {symbol} at ${current_price:.2f}")
            return None
        
        # Determine order type and entry price
        order_type = get_order_type(self.config.get_config('trading.order_type', 'market'))
        
        if order_type == OrderType.LIMIT:
            entry_price = current_price * (1 - self.long_config.get('entry_limit_offset', 0.001))
        else:
            entry_price = current_price
        
        # Create and place entry order
        order = Order(
            order_id=None,
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            order_type=order_type,
            price=entry_price if order_type == OrderType.LIMIT else None
        )
        
        order_id = await self.order_manager.place_order(order)
        
        # Generate unique position lifecycle ID
        position_lifecycle_id = await PositionLifecycleService.generate(
            symbol=symbol,
            entry_time=datetime.utcnow(),
            strategy_id='long'
        )
        
        # Create position state
        position = PositionState(
            symbol=symbol,
            direction=PositionDirection.LONG,
            phase=TradePhase.ENTRY,
            quantity=quantity,
            average_price=entry_price,
            current_price=current_price,
            entry_time=datetime.utcnow(),
            active_orders=[order_id],
            position_lifecycle_id=position_lifecycle_id
        )
        
        # Initialize DCA metadata lifecycle
        if self.dca_metadata_manager:
            try:
                await self.dca_metadata_manager.create_position_lifecycle(
                    symbol=symbol,
                    direction='long',
                    entry_price=entry_price
                )
                logger.info(f"✅ DCA lifecycle created for {symbol} (ID: {position_lifecycle_id[:8]}...)")
            except Exception as e:
                logger.warning(f"⚠️ Failed to create DCA lifecycle for {symbol}: {e}")
        
        # Save position to database
        if self.position_manager:
            try:
                await self.position_manager.update_position(
                    symbol=symbol,
                    quantity=quantity,
                    price=entry_price
                )
                logger.info(f"✅ Position {symbol} saved to database")
            except Exception as e:
                logger.error(f"❌ Failed to save position to database: {e}")
        
        logger.info(f"🟢 LONG POSITION OPENED: {symbol} - {quantity} shares @ ${entry_price:.2f}")
        
        return position
    
    async def handle_short_signal(
        self,
        signal: TradingSignal,
        existing_position: Optional[PositionState]
    ) -> Optional[PositionState]:
        """
        Handle a short (sell) signal.
        
        Args:
            signal: The trading signal to process
            existing_position: Existing position for this symbol (if any)
            
        Returns:
            PositionState if position created successfully, None otherwise
        """
        if not self.short_config.get('enabled', False):
            logger.info("Short strategy is disabled")
            return None
        
        symbol = signal.symbol
        
        # Fetch current market price
        try:
            current_price = await self.market_data.get_current_price(symbol)
            logger.info(f"Fetched current market price for {symbol}: ${current_price:.2f}")
            signal.price = current_price
        except Exception as e:
            logger.error(f"Failed to fetch current price for {symbol}: {e}")
            return None
        
        # Check for existing position conflicts
        if existing_position:
            if existing_position.direction == PositionDirection.SHORT:
                logger.info(f"Already have short position in {symbol}, ignoring signal")
                return None
            else:
                # Handle opposing position
                ignore_opposing = self.config.get_config('trading.position_management.ignore_opposing_signals', True)
                if ignore_opposing:
                    logger.info(
                        f"Already have long position in {symbol}, ignoring opposing short signal. "
                        f"Wait for current position to be closed based on its own rules."
                    )
                    return None
        
        # Calculate position size
        quantity = await self.risk_manager.calculate_position_size(symbol, signal, averaging_attempt=0)
        
        if quantity <= 0:
            logger.warning(f"Insufficient funds to open short position in {symbol} at ${current_price:.2f}")
            return None
        
        # Determine order type and entry price
        order_type = get_order_type(self.config.get_config('trading.order_type', 'market'))
        
        if order_type == OrderType.LIMIT:
            entry_price = current_price * (1 + self.short_config.get('entry_limit_offset', 0.001))
        else:
            entry_price = current_price
        
        # Create and place entry order
        order = Order(
            order_id=None,
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            order_type=order_type,
            price=entry_price if order_type == OrderType.LIMIT else None
        )
        
        order_id = await self.order_manager.place_order(order)
        
        # Generate unique position lifecycle ID
        position_lifecycle_id = await PositionLifecycleService.generate(
            symbol=symbol,
            entry_time=datetime.utcnow(),
            strategy_id='short'
        )
        
        # Create position state
        position = PositionState(
            symbol=symbol,
            direction=PositionDirection.SHORT,
            phase=TradePhase.ENTRY,
            quantity=quantity,
            average_price=entry_price,
            current_price=current_price,
            entry_time=datetime.utcnow(),
            active_orders=[order_id],
            position_lifecycle_id=position_lifecycle_id
        )
        
        # Initialize DCA metadata lifecycle
        if self.dca_metadata_manager:
            try:
                await self.dca_metadata_manager.create_position_lifecycle(
                    symbol=symbol,
                    direction='short',
                    entry_price=entry_price
                )
                logger.info(f"✅ DCA lifecycle created for {symbol} (ID: {position_lifecycle_id[:8]}...)")
            except Exception as e:
                logger.warning(f"⚠️ Failed to create DCA lifecycle for {symbol}: {e}")
        
        # Save position to database
        if self.position_manager:
            try:
                await self.position_manager.update_position(
                    symbol=symbol,
                    quantity=-quantity,  # Negative for short
                    price=entry_price
                )
                logger.info(f"✅ Position {symbol} saved to database")
            except Exception as e:
                logger.error(f"❌ Failed to save position to database: {e}")
        
        logger.info(f"🔴 SHORT POSITION OPENED: {symbol} - {quantity} shares @ ${entry_price:.2f}")
        
        return position
    
    async def close_position(self, position: PositionState) -> bool:
        """
        Close a position completely.
        
        Args:
            position: The position to close
            
        Returns:
            True if position closed successfully, False otherwise
        """
        symbol = position.symbol
        
        # Cancel any active orders
        for order_id in position.active_orders:
            try:
                await self.order_manager.cancel_order(order_id)
            except Exception as e:
                logger.warning(f"Failed to cancel order {order_id}: {e}")
        
        # Create closing order
        if position.direction == PositionDirection.LONG:
            side = OrderSide.SELL
        else:
            side = OrderSide.BUY
        
        order_type = get_order_type(self.config.get_config('trading.order_type', 'market'))
        order = Order(
            order_id=None,
            symbol=symbol,
            side=side,
            quantity=position.quantity,
            order_type=order_type
        )
        
        try:
            order_id = await self.order_manager.place_order(order)
            logger.info(
                f"🔴 POSITION CLOSED: {symbol} {position.direction.value} "
                f"{position.quantity} @ {position.current_price:.2f}"
            )
            logger.info(
                f"   📊 Final P&L: {position.profit_percentage:.2%} | "
                f"Averaging attempts: {position.averaging_attempts}"
            )
            
            # Close position in database
            if self.position_manager:
                try:
                    await self.position_manager.update_position(
                        symbol=symbol,
                        quantity=-position.quantity,
                        price=position.current_price
                    )
                    logger.info(f"✅ Position {symbol} closed in database")
                except Exception as e:
                    logger.error(f"❌ Failed to close position {symbol} in database: {e}")
            
            # Close DCA metadata lifecycle
            if self.dca_metadata_manager and position.position_lifecycle_id:
                try:
                    await self.dca_metadata_manager.close_position_lifecycle(
                        position_lifecycle_id=position.position_lifecycle_id
                    )
                    logger.info(f"✅ DCA lifecycle closed for {symbol} (ID: {position.position_lifecycle_id[:8]}...)")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to close DCA lifecycle for {symbol}: {e}")
            
            logger.info(f"🧹 DCA METADATA CLEARED: {symbol} (position closed)")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to close position for {symbol}: {e}")
            return False
