"""
Advanced Trading Strategy Manager
Implements sophisticated long/short strategies with trailing stops, support/resistance averaging,
and configurable order types for different scenarios.
"""

import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
from ..interfaces import IConfigurationManager, IOrderManager, IMarketDataProvider, IRiskManager
from ..core.logging_config import get_logger
from .. import TradingSignal, SignalType, Order, OrderType, OrderSide, OrderStatus
from .support_calculator import TechnicalSupportCalculator


logger = get_logger(__name__)


class PositionDirection(Enum):
    """Position direction enumeration."""
    LONG = "long"
    SHORT = "short"


class TradePhase(Enum):
    """Trading phase enumeration."""
    ENTRY = "entry"
    PROFIT_TRAILING = "profit_trailing"
    SUPPORT_AVERAGING = "support_averaging"
    RESISTANCE_AVERAGING = "resistance_averaging"
    EXIT = "exit"


@dataclass
class PositionState:
    """Represents the current state of a position."""
    symbol: str
    direction: PositionDirection
    phase: TradePhase
    quantity: float
    average_price: float
    current_price: float
    entry_time: datetime
    
    # Trailing data
    peak_price: Optional[float] = None
    trail_price: Optional[float] = None
    profit_percentage: float = 0.0
    
    # Support/Resistance data
    support_level: Optional[float] = None
    resistance_level: Optional[float] = None
    averaging_attempts: int = 0
    
    # DCA Price Tracking for Progressive Enforcement
    last_dca_price: Optional[float] = None  # Price of last DCA order for progressive validation
    dca_order_prices: List[float] = None     # History of all DCA order prices
    position_lifecycle_id: Optional[str] = None  # Unique ID for this position lifecycle to prevent order history pollution
    
    # Orders
    active_orders: List[str] = None
    
    def __post_init__(self):
        if self.active_orders is None:
            self.active_orders = []
        if self.dca_order_prices is None:
            self.dca_order_prices = []


class AdvancedTradingStrategy:
    """
    Advanced trading strategy with configurable order types, trailing stops,
    and support/resistance-based position averaging.
    """
    
    def __init__(self, config: IConfigurationManager, order_manager: IOrderManager, 
                 market_data: IMarketDataProvider, support_calculator: TechnicalSupportCalculator,
                 risk_manager: IRiskManager, position_manager=None):
        """Initialize the advanced trading strategy."""
        self.config = config
        self.order_manager = order_manager
        self.market_data = market_data
        self.support_calculator = support_calculator
        self.risk_manager = risk_manager
        self.position_manager = position_manager  # For database persistence
        
        # Active positions tracking
        self.positions: Dict[str, PositionState] = {}
        
        # Enhanced: Store original signal timeframes for each symbol
        self.position_timeframes: Dict[str, str] = {}
        
        # DCA metadata manager for proper persistence
        self.dca_metadata_manager = None
        if self.position_manager and hasattr(self.position_manager, 'database'):
            try:
                from ..database.dca_metadata_manager import DCAMetadataManager
                self.dca_metadata_manager = DCAMetadataManager(self.position_manager.database)
                logger.info("✅ DCA metadata manager initialized")
            except Exception as e:
                logger.warning(f"⚠️ Could not initialize DCA metadata manager: {e}")
        
        # Configuration cache
        self._load_config()
        
        logger.info("Advanced Trading Strategy initialized")
        
        # Load existing positions from database if available
        if self.position_manager:
            asyncio.create_task(self._load_positions_from_database())
    
    async def _load_positions_from_database(self):
        """Load existing positions from database on startup."""
        try:
            if not self.position_manager:
                return
            
            # Get all active positions from database
            positions = await self.position_manager.get_all_positions()
            
            for pos in positions:
                if pos.quantity != 0:  # Include both positive and negative positions
                    # Convert database position to PositionState
                    direction = PositionDirection.LONG if pos.quantity > 0 else PositionDirection.SHORT
                    
                    # ENHANCED: Load DCA metadata from database rather than order history
                    dca_history = await self._load_position_dca_metadata(pos.symbol, direction)
                    averaging_attempts = dca_history['attempts']
                    dca_order_prices = dca_history['prices']
                    last_dca_price = dca_history['last_price']
                    position_lifecycle_id = dca_history['lifecycle_id']  # Get lifecycle ID for position tracking
                    
                    logger.info(f"🔄 RESTORING POSITION: {pos.symbol}")
                    logger.info(f"   Direction: {direction.value}")
                    logger.info(f"   Quantity: {pos.quantity}")
                    logger.info(f"   Average Price: ${pos.avg_price:.2f}")
                    logger.info(f"   Lifecycle ID: {position_lifecycle_id[:8]}...")
                    logger.info(f"   Calculated DCA Attempts: {averaging_attempts}")
                    logger.info(f"   DCA Price History: {[f'${p:.2f}' for p in dca_order_prices]}")
                    logger.info(f"   Last DCA Price: ${last_dca_price:.2f}" if last_dca_price else "   Last DCA Price: None")
                    
                    position_state = PositionState(
                        symbol=pos.symbol,
                        direction=direction,
                        phase=TradePhase.ENTRY,  # Start in entry phase, will be updated by monitoring
                        quantity=abs(pos.quantity),  # Use absolute value
                        average_price=pos.avg_price,
                        current_price=pos.avg_price,  # Will be updated with real market price
                        entry_time=pos.entry_time or datetime.now(),
                        averaging_attempts=averaging_attempts,  # RESTORED FROM HISTORY
                        # ENHANCED: Restore DCA price tracking for progressive validation
                        last_dca_price=last_dca_price,
                        dca_order_prices=dca_order_prices.copy(),  # Copy list to avoid reference issues
                        position_lifecycle_id=position_lifecycle_id  # Restore lifecycle ID for DCA tracking
                    )
                    
                    self.positions[pos.symbol] = position_state
                    logger.info(f"✅ RESTORED POSITION: {pos.symbol} {direction.value} {pos.quantity} @ {pos.avg_price:.2f} (DCA attempts: {averaging_attempts})")
                    if last_dca_price:
                        logger.info(f"   🔄 Progressive DCA: Next must be {'below' if direction == PositionDirection.LONG else 'above'} ${last_dca_price:.2f}")
            
            if self.positions:
                logger.info(f"✅ Restored {len(self.positions)} positions from database")
                print(f"\n🔄 RESTORED {len(self.positions)} POSITIONS FROM DATABASE:")
                for symbol, pos in self.positions.items():
                    print(f"   {symbol}: {pos.direction.value} {pos.quantity} @ {pos.average_price:.2f} (DCA: {pos.averaging_attempts}/3)")
            else:
                logger.info("📝 No previous positions found in database")
                
        except Exception as e:
            logger.error(f"❌ Failed to load positions from database: {e}")
    
    async def _save_position_dca_metadata(self, symbol: str, attempts: int, prices: List[float], last_price: Optional[float]):
        """
        Save DCA metadata directly to the PositionState and database.
        This is the authoritative source for DCA tracking, avoiding order history pollution.
        """
        try:
            if symbol not in self.positions:
                logger.warning(f"⚠️ No position state found to save DCA metadata: {symbol}")
                return
            
            position = self.positions[symbol]
            
            # Update position state with DCA metadata
            position.averaging_attempts = attempts
            position.dca_order_prices = prices.copy()
            position.last_dca_price = last_price
            
            logger.info(f"💾 DCA METADATA UPDATED: {symbol}")
            logger.info(f"   Attempts: {attempts}")
            logger.info(f"   Prices: {[f'${p:.2f}' for p in prices]}")
            logger.info(f"   Last Price: ${last_price:.2f}" if last_price else "   Last Price: None")
            
            # Persist to database using DCA metadata manager
            if self.dca_metadata_manager and position.position_lifecycle_id:
                try:
                    await self.dca_metadata_manager.update_dca_metadata(
                        position_lifecycle_id=position.position_lifecycle_id,
                        dca_attempts=attempts,
                        dca_prices=prices,
                        last_dca_price=last_price
                    )
                    logger.info(f"✅ DCA metadata persisted to database for {symbol}")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to persist DCA metadata for {symbol}: {e}")
            
            # Also update position manager if available (legacy support)
            if self.position_manager:
                try:
                    await self.position_manager.update_position(
                        symbol=symbol,
                        quantity=position.quantity if position.direction == PositionDirection.LONG else -position.quantity,
                        price=position.current_price
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to update position manager for {symbol}: {e}")
                    
        except Exception as e:
            logger.error(f"❌ Failed to save DCA metadata for {symbol}: {e}")
            
        except Exception as e:
            logger.error(f"❌ Failed to save DCA metadata for {symbol}: {e}")

    async def _load_position_dca_metadata(self, symbol: str, direction: PositionDirection) -> dict:
        """
        Load DCA metadata from database using position lifecycle approach.
        This completely avoids order history pollution by using position-specific tracking.
        
        Returns dict with 'attempts', 'prices', 'last_price', and 'lifecycle_id' keys.
        """
        try:
            logger.info(f"🔍 LOADING DCA METADATA: {symbol} ({direction.value})")
            
            # Try to load from DCA metadata manager first
            if self.dca_metadata_manager:
                try:
                    metadata = await self.dca_metadata_manager.get_active_metadata(
                        symbol=symbol,
                        direction=direction.value.lower()
                    )
                    
                    if metadata:
                        logger.info(f"✅ LOADED DCA METADATA: {symbol}")
                        logger.info(f"   Lifecycle ID: {metadata['position_lifecycle_id'][:8]}...")
                        logger.info(f"   DCA Attempts: {metadata['dca_attempts']}")
                        logger.info(f"   DCA Prices: {[f'${p:.2f}' for p in metadata['dca_prices']]}")
                        logger.info(f"   Last DCA Price: ${metadata['last_dca_price']:.2f}" if metadata['last_dca_price'] else "None")
                        
                        return {
                            'attempts': metadata['dca_attempts'],
                            'prices': metadata['dca_prices'],
                            'last_price': metadata['last_dca_price'],
                            'lifecycle_id': metadata['position_lifecycle_id']
                        }
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load DCA metadata from database for {symbol}: {e}")
            
            # No existing metadata found - start fresh with new lifecycle ID
            import uuid
            new_lifecycle_id = str(uuid.uuid4())
            
            logger.info(f"📝 FRESH DCA TRACKING: {symbol} - starting new lifecycle")
            logger.info(f"   New Lifecycle ID: {new_lifecycle_id[:8]}...")
            
            return {
                'attempts': 0,
                'prices': [],
                'last_price': None,
                'lifecycle_id': new_lifecycle_id
            }
            
        except Exception as e:
            logger.warning(f"Could not load DCA metadata for {symbol}: {e}")
            import uuid
            fallback_lifecycle_id = str(uuid.uuid4())
            return {
                'attempts': 0,
                'prices': [],
                'last_price': None,
                'lifecycle_id': fallback_lifecycle_id
            }
    
    def _load_config(self):
        """Load configuration settings."""
        # Get global order type setting once
        global_order_type = self.config.get_config('trading.order_type', 'market')
        
        # Long strategy config (uses global order type)
        self.long_config = {
            'enabled': self.config.get_config('strategies.long_strategy.enabled', True),
            'entry_limit_offset': self.config.get_config('strategies.long_strategy.entry_limit_offset', 0.001),
            'profit_target': self.config.get_config('strategies.long_strategy.profit_target', 0.05),
            'trailing_enabled': self.config.get_config('strategies.long_strategy.trailing_profit.enabled', True),
            'trailing_percentage': self.config.get_config('strategies.long_strategy.trailing_profit.trailing_percentage', 0.015),
            'activation_threshold': self.config.get_config('strategies.long_strategy.trailing_profit.activation_threshold', 0.03),
            'min_profit_lock': self.config.get_config('strategies.long_strategy.trailing_profit.min_profit_lock', 0.01),
            'averaging_enabled': self.config.get_config('strategies.long_strategy.support_averaging.enabled', True),
            'max_averaging_attempts': self.config.get_config('strategies.long_strategy.support_averaging.max_attempts', 3),
            'position_multiplier': self.config.get_config('strategies.long_strategy.support_averaging.position_multiplier', 1.5),
            'averaging_loss_threshold': self.config.get_config('strategies.long_strategy.support_averaging.loss_threshold', 0.02),
            'support_trailing_enabled': self.config.get_config('strategies.long_strategy.support_averaging.support_trailing.enabled', True),
            'support_trailing_percentage': self.config.get_config('strategies.long_strategy.support_averaging.support_trailing.trailing_percentage', 0.01)
        }
        
        # Short strategy config (uses global order type)
        self.short_config = {
            'enabled': self.config.get_config('strategies.short_strategy.enabled', True),
            'entry_limit_offset': self.config.get_config('strategies.short_strategy.entry_limit_offset', 0.001),
            'profit_target': self.config.get_config('strategies.short_strategy.profit_target', 0.05),
            'trailing_enabled': self.config.get_config('strategies.short_strategy.trailing_profit.enabled', True),
            'trailing_percentage': self.config.get_config('strategies.short_strategy.trailing_profit.trailing_percentage', 0.015),
            'activation_threshold': self.config.get_config('strategies.short_strategy.trailing_profit.activation_threshold', 0.03),
            'min_profit_lock': self.config.get_config('strategies.short_strategy.trailing_profit.min_profit_lock', 0.01),
            'averaging_enabled': self.config.get_config('strategies.short_strategy.resistance_averaging.enabled', True),
            'max_averaging_attempts': self.config.get_config('strategies.short_strategy.resistance_averaging.max_attempts', 3),
            'position_multiplier': self.config.get_config('strategies.short_strategy.resistance_averaging.position_multiplier', 1.5),
            'averaging_loss_threshold': self.config.get_config('strategies.short_strategy.resistance_averaging.loss_threshold', 0.02),
            'resistance_trailing_enabled': self.config.get_config('strategies.short_strategy.resistance_averaging.resistance_trailing.enabled', True),
            'resistance_trailing_percentage': self.config.get_config('strategies.short_strategy.resistance_averaging.resistance_trailing.trailing_percentage', 0.01)
        }
        
        # General trading config - keeping for legacy compatibility only
        # Note: Position sizing now handled by RiskManager, not hardcoded quantity
        self.default_quantity = self.config.get_config('trading.position_sizing.default_quantity', 
                                                       self.config.get_config('trading.default_quantity', 100))
    
    async def process_signal(self, signal: TradingSignal) -> bool:
        """
        Process a trading signal and execute the appropriate strategy.
        ENHANCED: Store original signal timeframe for future DCA decisions.
        
        Args:
            signal: The trading signal to process
            
        Returns:
            True if signal was processed successfully
        """
        try:
            logger.info(f"Processing signal: {signal.symbol} {signal.signal_type.value} @ {signal.price}")
            
            # ENHANCED: Store original signal timeframe for DCA decisions
            timeframe = signal.metadata.get('timeframe', '15m')  # Default to 15m if not provided
            self.position_timeframes[signal.symbol] = timeframe
            logger.info(f"📊 TIMEFRAME STORED: {signal.symbol} -> {timeframe} (for future DCA analysis)")
            
            if signal.signal_type == SignalType.BUY:
                return await self._handle_long_signal(signal)
            elif signal.signal_type == SignalType.SELL:
                return await self._handle_short_signal(signal)
            elif signal.signal_type == SignalType.CLOSE:
                return await self._handle_close_signal(signal)
            else:
                logger.warning(f"Unknown signal type: {signal.signal_type}")
                return False
                
        except Exception as e:
            logger.error(f"Error processing signal: {str(e)}")
            return False
    

    
    async def _handle_long_signal(self, signal: TradingSignal) -> bool:
        """Handle a long (buy) signal."""
        if not self.long_config['enabled']:
            logger.info("Long strategy is disabled")
            return False
        
        symbol = signal.symbol
        
        # Fetch CURRENT market price (ignore signal price)
        try:
            current_price = await self.market_data.get_current_price(symbol)
            logger.info(f"Fetched current market price for {symbol}: ${current_price:.2f}")
            
            # Update signal with correct current price for position sizing
            signal.price = current_price
            
        except Exception as e:
            logger.error(f"Failed to fetch current price for {symbol}: {e}")
            return False
        
        # Check if we already have a position
        if symbol in self.positions:
            existing_position = self.positions[symbol]
            if existing_position.direction == PositionDirection.LONG:
                logger.info(f"Already have long position in {symbol}, ignoring signal")
                return False
            else:
                # Handle opposing position based on configuration
                ignore_opposing = self.config.get_config('trading.position_management.ignore_opposing_signals', True)
                if ignore_opposing:
                    # We have a short position, but we don't want to automatically close it
                    # Alpaca doesn't allow long and short positions on the same symbol simultaneously
                    # Instead of closing the short position, we ignore the long signal
                    logger.info(f"Already have short position in {symbol}, ignoring opposing long signal. "
                               f"Wait for current position to be closed based on its own rules (trailing/averaging) before opening new positions.")
                    return False
                else:
                    # Legacy behavior: Close existing short position first
                    logger.info(f"Closing existing short position in {symbol} to open new long position")
                    await self._close_position(symbol)
        
        # Calculate entry details using risk manager for initial position (averaging_attempt = 0)
        quantity = await self.risk_manager.calculate_position_size(symbol, signal, averaging_attempt=0)
        
        # Check if we have sufficient funds for the trade
        if quantity <= 0:
            logger.warning(f"Insufficient funds to open long position in {symbol} at ${current_price:.2f} - skipping trade")
            return False
        
        # Use global order type setting
        order_type = self._get_order_type(self.config.get_config('trading.order_type', 'market'))
        
        if order_type == OrderType.LIMIT:
            # For limit orders, buy slightly below current price
            entry_price = current_price * (1 - self.long_config['entry_limit_offset'])
        else:
            entry_price = current_price
        
        # Create and place entry order
        order = Order(
            order_id=None,  # Will be auto-generated
            symbol=symbol,
            side=OrderSide.BUY,
            quantity=quantity,
            order_type=order_type,
            price=entry_price if order_type == OrderType.LIMIT else None
        )
        
        order_id = await self.order_manager.place_order(order)
        
        # Generate unique position lifecycle ID for DCA tracking
        import uuid
        position_lifecycle_id = str(uuid.uuid4())
        
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
            position_lifecycle_id=position_lifecycle_id  # Unique ID for DCA tracking
        )
        
        self.positions[symbol] = position
        
        # Initialize DCA metadata for this position lifecycle
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
        
        # Save position to database for persistence
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
        
        return True
    
    async def _handle_short_signal(self, signal: TradingSignal) -> bool:
        """Handle a short (sell) signal."""
        if not self.short_config['enabled']:
            logger.info("Short strategy is disabled")
            return False
        
        symbol = signal.symbol
        
        # Fetch CURRENT market price (ignore signal price)
        try:
            current_price = await self.market_data.get_current_price(symbol)
            logger.info(f"Fetched current market price for {symbol}: ${current_price:.2f}")
            
            # Update signal with correct current price for position sizing
            signal.price = current_price
            
        except Exception as e:
            logger.error(f"Failed to fetch current price for {symbol}: {e}")
            return False
        
        # Check if we already have a position
        if symbol in self.positions:
            existing_position = self.positions[symbol]
            if existing_position.direction == PositionDirection.SHORT:
                logger.info(f"Already have short position in {symbol}, ignoring signal")
                return False
            else:
                # Handle opposing position based on configuration
                ignore_opposing = self.config.get_config('trading.position_management.ignore_opposing_signals', True)
                if ignore_opposing:
                    # We have a long position, but we don't want to automatically close it
                    # Alpaca doesn't allow long and short positions on the same symbol simultaneously
                    # Instead of closing the long position, we ignore the short signal
                    logger.info(f"Already have long position in {symbol}, ignoring opposing short signal. "
                               f"Wait for current position to be closed based on its own rules (trailing/averaging) before opening new positions.")
                    return False
                else:
                    # Legacy behavior: Close existing long position first
                    logger.info(f"Closing existing long position in {symbol} to open new short position")
                    await self._close_position(symbol)
        
        # Calculate entry details using risk manager for initial position (averaging_attempt = 0)
        quantity = await self.risk_manager.calculate_position_size(symbol, signal, averaging_attempt=0)
        
        # Check if we have sufficient funds for the trade
        if quantity <= 0:
            logger.warning(f"Insufficient funds to open short position in {symbol} at ${current_price:.2f} - skipping trade")
            return False
        
        # Use global order type setting
        order_type = self._get_order_type(self.config.get_config('trading.order_type', 'market'))
        
        if order_type == OrderType.LIMIT:
            # For limit orders, sell slightly above current price
            entry_price = current_price * (1 + self.short_config['entry_limit_offset'])
        else:
            entry_price = current_price
        
        # Create and place entry order
        order = Order(
            order_id=None,  # Will be auto-generated
            symbol=symbol,
            side=OrderSide.SELL,
            quantity=quantity,
            order_type=order_type,
            price=entry_price if order_type == OrderType.LIMIT else None
        )
        
        order_id = await self.order_manager.place_order(order)
        
        # Generate unique position lifecycle ID for DCA tracking
        import uuid
        position_lifecycle_id = str(uuid.uuid4())
        
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
            position_lifecycle_id=position_lifecycle_id  # Unique ID for DCA tracking
        )
        
        self.positions[symbol] = position
        
        # Initialize DCA metadata for this position lifecycle
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
        
        # Save position to database for persistence
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
        
        return True
    
    async def _handle_close_signal(self, signal: TradingSignal) -> bool:
        """Handle a close signal."""
        symbol = signal.symbol
        
        if symbol not in self.positions:
            logger.warning(f"No position found for {symbol} to close")
            return False
        
        return await self._close_position(symbol)
    
    async def _close_position(self, symbol: str) -> bool:
        """Close a position completely."""
        if symbol not in self.positions:
            return False
        
        position = self.positions[symbol]
        
        # Cancel any active orders
        for order_id in position.active_orders:
            try:
                await self.order_manager.cancel_order(order_id)
            except Exception as e:
                logger.warning(f"Failed to cancel order {order_id}: {e}")
        
        # Create closing order
        if position.direction == PositionDirection.LONG:
            side = OrderSide.SELL
            config = self.long_config
        else:
            side = OrderSide.BUY
            config = self.short_config
        
        # Use global order type for consistency
        order_type = self._get_order_type(self.config.get_config('trading.order_type', 'market'))
        order = Order(
            order_id=None,  # Will be auto-generated
            symbol=symbol,
            side=side,
            quantity=position.quantity,
            order_type=order_type
        )
        
        try:
            order_id = await self.order_manager.place_order(order)
            logger.info(f"🔴 POSITION CLOSED: {symbol} {position.direction.value} {position.quantity} @ {position.current_price:.2f}")
            logger.info(f"   📊 Final P&L: {position.profit_percentage:.2%} | Averaging attempts: {position.averaging_attempts}")
            
            # Remove position from database if position manager available
            if self.position_manager:
                try:
                    # Set quantity to 0 to indicate closed position
                    await self.position_manager.update_position(
                        symbol=symbol,
                        quantity=-position.quantity,  # Negative to close out
                        price=position.current_price
                    )
                    logger.info(f"✅ Position {symbol} closed in database")
                except Exception as e:
                    logger.error(f"❌ Failed to close position {symbol} in database: {e}")
            
            # Remove position from memory
            del self.positions[symbol]
            
            # ENHANCED: Close DCA metadata lifecycle to prevent pollution
            if self.dca_metadata_manager and position.position_lifecycle_id:
                try:
                    await self.dca_metadata_manager.close_position_lifecycle(
                        position_lifecycle_id=position.position_lifecycle_id
                    )
                    logger.info(f"✅ DCA lifecycle closed for {symbol} (ID: {position.position_lifecycle_id[:8]}...)")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to close DCA lifecycle for {symbol}: {e}")
            
            # Clear DCA metadata for closed position
            logger.info(f"🧹 DCA METADATA CLEARED: {symbol} (position closed)")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to close position for {symbol}: {e}")
            return False
    
    async def update_positions(self):
        """Update all positions with current market data and execute strategy logic."""
        for symbol in list(self.positions.keys()):
            await self._update_position(symbol)

    async def update_position_monitoring(self, symbol: str, current_price: float):
        """
        Enhanced position monitoring with PURE technical analysis DCA.
        NO loss thresholds - only support/resistance breaches trigger DCA.
        """
        try:
            # Get position from database if not in strategy tracker
            if symbol not in self.positions:
                db_position = await self.position_manager.get_position(symbol) if self.position_manager else None
                if db_position and db_position.quantity != 0:
                    # Create strategy position from database position
                    direction = PositionDirection.LONG if db_position.quantity > 0 else PositionDirection.SHORT
                    self.positions[symbol] = PositionState(
                        symbol=symbol,
                        direction=direction,
                        phase=TradePhase.ENTRY,
                        quantity=db_position.quantity,
                        average_price=db_position.avg_price,
                        current_price=current_price,
                        entry_time=datetime.utcnow()  # Use current time as fallback
                    )
                    logger.info(f"📊 Added existing position to strategy tracker: {symbol} {direction.value} {db_position.quantity} @ ${db_position.avg_price:.2f}")
                else:
                    return  # No position exists
            
            # Update current price
            position = self.positions[symbol]
            position.current_price = current_price
            
            # Calculate current profit/loss for logging
            if position.direction == PositionDirection.LONG:
                profit_pct = (current_price - position.average_price) / position.average_price
            else:
                profit_pct = (position.average_price - current_price) / position.average_price
            
            position.profit_percentage = profit_pct
            
            # Get configuration
            config = self.long_config if position.direction == PositionDirection.LONG else self.short_config
            max_attempts = config.get('max_averaging_attempts', 3)
            
            # Log position status for transparency
            logger.debug(f"📊 {symbol}: {profit_pct:.2%} profit, {position.averaging_attempts}/{max_attempts} DCA attempts")
            
            # ENHANCED: Pure technical analysis DCA (NO loss threshold)
            if (position.averaging_attempts < max_attempts and
                config.get('averaging_enabled', True)):
                
                # Get original signal timeframe for this position (defaulting to 15m for existing positions)
                timeframe = self._get_position_timeframe(symbol)
                
                logger.info(f"🔍 DCA CHECK: {symbol} - attempt {position.averaging_attempts}/{max_attempts}")
                logger.info(f"   Current: ${current_price:.2f}, Average: ${position.average_price:.2f}")
                logger.info(f"   P&L: {profit_pct:.2%}, Timeframe: {timeframe}")
                
                if position.direction == PositionDirection.LONG:
                    dca_decision = await self._check_support_breach_dca(position, timeframe)
                else:
                    dca_decision = await self._check_resistance_breach_dca(position, timeframe)
                
                logger.info(f"🎯 DCA DECISION: {symbol}")
                logger.info(f"   Should DCA: {dca_decision['should_dca']}")
                logger.info(f"   Reason: {dca_decision['reason']}")
                logger.info(f"   Message: {dca_decision['message']}")
                
                if dca_decision['should_dca']:
                    logger.info(f"🚀 EXECUTING DCA: {symbol}")
                    logger.info(f"   Level: ${dca_decision.get('level', 'N/A'):.2f}")
                    logger.info(f"   Timeframe: {timeframe}")
                    logger.info(f"   Attempt: {position.averaging_attempts + 1}/{max_attempts} (will increment on fill)")
                    
                    await self._execute_technical_dca(position, dca_decision)
                else:
                    # Enhanced debugging for why DCA was not triggered
                    logger.info(f"⏸️ DCA NOT TRIGGERED: {symbol}")
                    if 'level' in dca_decision:
                        logger.info(f"   Next level: ${dca_decision['level']:.2f}")
                    if 'distance_percent' in dca_decision:
                        logger.info(f"   Distance: {dca_decision['distance_percent']:.1f}%")
            else:
                # Log why DCA is not being checked
                if position.averaging_attempts >= max_attempts:
                    logger.info(f"🚫 DCA DISABLED: {symbol} - max attempts reached ({position.averaging_attempts}/{max_attempts})")
                elif not config.get('averaging_enabled', True):
                    logger.info(f"� DCA DISABLED: {symbol} - averaging disabled in config")
                else:
                    logger.debug(f"🔍 DCA conditions not met for {symbol}")
            
        except Exception as e:
            logger.error(f"Error updating position monitoring for {symbol}: {e}")

    def _get_position_timeframe(self, symbol: str) -> str:
        """
        Get the original signal timeframe for this position.
        Uses stored timeframe from when position was created.
        """
        # Use stored timeframe if available
        if symbol in self.position_timeframes:
            return self.position_timeframes[symbol]
        
        # For existing positions without stored timeframe, use configuration default
        default_timeframe = self.config.get_config('strategies.dca.default_timeframe', '15m')
        logger.debug(f"📊 Using default timeframe for {symbol}: {default_timeframe}")
        return default_timeframe

    def _is_progressive_dca_price(self, position: PositionState, proposed_price: float) -> dict:
        """
        Validate that the proposed DCA price is progressive (better than previous DCA).
        For LONG positions: each DCA must be BELOW the last DCA price (averaging down).
        For SHORT positions: each DCA must be ABOVE the last DCA price (averaging up).
        
        Returns:
            dict with keys: is_progressive, reason, message, last_price
        """
        symbol = position.symbol
        direction = position.direction
        
        # If no previous DCA orders, any price is acceptable
        if position.last_dca_price is None:
            logger.info(f"✅ PROGRESSIVE DCA: {symbol} - first DCA attempt, any price acceptable")
            return {
                'is_progressive': True,
                'reason': 'first_dca',
                'message': f'First DCA attempt for {symbol}',
                'last_price': None
            }
        
        last_dca_price = position.last_dca_price
        
        # Progressive validation based on position direction
        if direction == PositionDirection.LONG:
            # LONG position: new DCA price must be BELOW last DCA price (averaging down)
            is_progressive = proposed_price < last_dca_price
            required_direction = "below"
            improvement_pct = ((last_dca_price - proposed_price) / last_dca_price) * 100
        else:
            # SHORT position: new DCA price must be ABOVE last DCA price (averaging up)
            is_progressive = proposed_price > last_dca_price
            required_direction = "above"
            improvement_pct = ((proposed_price - last_dca_price) / last_dca_price) * 100
        
        if is_progressive:
            logger.info(f"✅ PROGRESSIVE DCA: {symbol}")
            logger.info(f"   Direction: {direction.value}")
            logger.info(f"   Last DCA: ${last_dca_price:.2f}")
            logger.info(f"   New DCA: ${proposed_price:.2f}")
            logger.info(f"   Improvement: {improvement_pct:.1f}% {required_direction} last DCA")
            
            return {
                'is_progressive': True,
                'reason': 'progressive_price',
                'message': f'Price ${proposed_price:.2f} is {improvement_pct:.1f}% {required_direction} last DCA ${last_dca_price:.2f}',
                'last_price': last_dca_price,
                'improvement_percent': improvement_pct
            }
        else:
            logger.warning(f"❌ NON-PROGRESSIVE DCA: {symbol}")
            logger.warning(f"   Direction: {direction.value}")
            logger.warning(f"   Last DCA: ${last_dca_price:.2f}")
            logger.warning(f"   Proposed: ${proposed_price:.2f}")
            logger.warning(f"   Required: Must be {required_direction} ${last_dca_price:.2f}")
            logger.warning(f"   Rejected: Prevents same-level or worse DCA entries")
            
            return {
                'is_progressive': False,
                'reason': 'non_progressive_price',
                'message': f'Price ${proposed_price:.2f} is not {required_direction} last DCA ${last_dca_price:.2f}',
                'last_price': last_dca_price,
                'required_direction': required_direction
            }

    async def _check_support_breach_dca(self, position: PositionState, timeframe: str) -> dict:
        """
        Check if price has breached support levels - PURE technical analysis DCA.
        NO loss threshold involved.
        """
        try:
            current_price = position.current_price
            symbol = position.symbol
            
            logger.debug(f"🔍 SUPPORT ANALYSIS: {symbol} @ ${current_price:.2f} using {timeframe}")
            
            # Calculate position-aware support levels for DCA averaging
            support_data = await self.support_calculator.calculate_support_levels_for_position(
                symbol, timeframe, position.average_price, "long"
            )
            
            if not support_data or not support_data.levels:
                logger.warning(f"⚠️ NO SUPPORT DATA: {symbol} ({timeframe}) - technical analysis unavailable")
                return {
                    'should_dca': False,
                    'reason': 'no_support_data',
                    'message': f'No support levels found for {timeframe} timeframe'
                }
            
            # Find the strongest support level below current price
            min_confidence = self.config.get_config('strategies.dca.min_support_confidence', 0.70)
            
            # Input validation for configuration
            if not isinstance(min_confidence, (int, float)) or min_confidence < 0 or min_confidence > 1:
                logger.warning(f"Invalid min_support_confidence: {min_confidence}, using default 0.70")
                min_confidence = 0.70
            
            # The support calculator already filtered for position-aware levels
            # Trust the position-aware filtering and only apply confidence filter
            valid_supports = [
                level for level in support_data.levels 
                if level.confidence >= min_confidence
            ]
            
            # Log detailed support analysis for debugging
            logger.info(f"🔍 SUPPORT ANALYSIS DETAIL: {symbol}")
            logger.info(f"   Current Price: ${current_price:.2f}")
            logger.info(f"   Position Average: ${position.average_price:.2f}")
            logger.info(f"   Timeframe: {timeframe}")
            logger.info(f"   Min Confidence: {min_confidence:.1%}")
            logger.info(f"   Raw Support Levels: {len(support_data.levels)}")
            
            for i, level in enumerate(support_data.levels[:5]):  # Show first 5 levels
                logger.info(f"     #{i+1}: ${level.price:.2f} (conf: {level.confidence:.1%})")
            
            logger.info(f"   Valid Support Levels: {len(valid_supports)}")
            for i, level in enumerate(valid_supports):
                logger.info(f"     Valid #{i+1}: ${level.price:.2f} (conf: {level.confidence:.1%})")
            
            if not valid_supports:
                # If no support found with position-aware filtering, this means either:
                # 1. No technical support levels exist in the data
                # 2. All support levels are above position average (which would be resistance)
                logger.info(f"📈 NO VALID SUPPORT: {symbol} - no position-appropriate support levels found")
                return {
                    'should_dca': False,
                    'reason': 'no_position_support',
                    'message': f'No support levels suitable for position averaging (below ${position.average_price:.2f})'
                }
            
            # Get the nearest strong support level
            nearest_support = max(valid_supports, key=lambda x: x.price)
            support_price = nearest_support.price
            support_confidence = nearest_support.confidence
            
            logger.info(f"🎯 NEAREST SUPPORT: {symbol}")
            logger.info(f"   Level: ${support_price:.2f} (confidence: {support_confidence:.1%})")
            
            # Check if we've breached support (with small buffer to ensure we're truly below)
            support_buffer = self.config.get_config('strategies.dca.support_buffer_percent', 0.005)  # 0.5% buffer
            support_trigger_price = support_price * (1 - support_buffer)
            
            logger.info(f"🔧 BREACH CALCULATION: {symbol}")
            logger.info(f"   Support Buffer: {support_buffer:.1%}")
            logger.info(f"   Trigger Price: ${support_trigger_price:.2f}")
            logger.info(f"   Price vs Trigger: ${current_price:.2f} {'<=' if current_price <= support_trigger_price else '>'} ${support_trigger_price:.2f}")
            
            if current_price <= support_trigger_price:
                logger.info(f"🎯 SUPPORT BREACH DETECTED: {symbol}")
                logger.info(f"   Current: ${current_price:.2f}")
                logger.info(f"   Support: ${support_price:.2f} (confidence: {support_confidence:.1%})")
                logger.info(f"   Trigger: ${support_trigger_price:.2f}")
                logger.info(f"   Timeframe: {timeframe}")
                
                return {
                    'should_dca': True,
                    'reason': 'support_breach',
                    'level': support_price,
                    'confidence': support_confidence,
                    'trigger_price': support_trigger_price,
                    'timeframe': timeframe,
                    'message': f'Price breached support at ${support_price:.2f}'
                }
            else:
                distance_pct = ((current_price - support_trigger_price) / current_price) * 100
                logger.info(f"🔍 WATCHING SUPPORT: {symbol} ${current_price:.2f} > ${support_trigger_price:.2f} ({distance_pct:.1f}% away)")
                return {
                    'should_dca': False,
                    'reason': 'watching_support',
                    'level': support_price,
                    'distance_percent': distance_pct,
                    'message': f'Monitoring support at ${support_price:.2f} ({distance_pct:.1f}% away)'
                }
                
        except Exception as e:
            logger.error(f"Error checking support breach DCA for {symbol}: {e}")
            return {
                'should_dca': False,
                'reason': 'error',
                'message': f'Error calculating support: {str(e)}'
            }

    async def _check_resistance_breach_dca(self, position: PositionState, timeframe: str) -> dict:
        """
        Check if price has breached resistance levels - for short positions.
        PURE technical analysis DCA, NO loss threshold involved.
        """
        try:
            current_price = position.current_price
            symbol = position.symbol
            
            logger.debug(f"🔍 RESISTANCE ANALYSIS: {symbol} @ ${current_price:.2f} using {timeframe}")
            
            # Calculate position-aware resistance levels for DCA averaging
            resistance_data = await self.support_calculator.calculate_resistance_levels_for_position(
                symbol=symbol, timeframe=timeframe, position_avg_price=position.average_price, position_type="short"
            )
            
            if not resistance_data or not resistance_data.levels:
                logger.warning(f"⚠️ NO RESISTANCE DATA: {symbol} ({timeframe}) - technical analysis unavailable")
                return {
                    'should_dca': False,
                    'reason': 'no_resistance_data',
                    'message': f'No resistance levels found for {timeframe} timeframe'
                }
            
            # Find the strongest resistance level above current price
            min_confidence = self.config.get_config('strategies.dca.min_resistance_confidence', 0.70)
            
            # Input validation for configuration
            if not isinstance(min_confidence, (int, float)) or min_confidence < 0 or min_confidence > 1:
                logger.warning(f"Invalid min_resistance_confidence: {min_confidence}, using default 0.70")
                min_confidence = 0.70
            
            # The resistance calculator already filtered for position-aware levels
            # Trust the position-aware filtering and only apply confidence filter
            valid_resistances = [
                level for level in resistance_data.levels 
                if level.confidence >= min_confidence
            ]
            
            # Log detailed resistance analysis for debugging
            self._log_resistance_analysis(symbol, current_price, min_confidence, valid_resistances)
            
            if not valid_resistances:
                # If no resistance found with position-aware filtering, this means either:
                # 1. No technical resistance levels exist in the data
                # 2. All resistance levels are below position average (which would be support)
                logger.debug(f"📉 NO VALID RESISTANCE: {symbol} - no position-appropriate resistance levels found")
                return {
                    'should_dca': False,
                    'reason': 'no_position_resistance',
                    'message': f'No resistance levels suitable for position averaging (above ${position.average_price:.2f})'
                }
            
            # Get the nearest strong resistance level
            nearest_resistance = min(valid_resistances, key=lambda x: x.price)
            resistance_price = nearest_resistance.price
            resistance_confidence = nearest_resistance.confidence
            
            # Check if we've breached resistance (with small buffer to ensure we're truly above)
            resistance_buffer = self.config.get_config('strategies.dca.resistance_buffer_percent', 0.005)  # 0.5% buffer
            resistance_trigger_price = resistance_price * (1 + resistance_buffer)
            
            if current_price >= resistance_trigger_price:
                logger.info(f"🎯 RESISTANCE BREACH DETECTED: {symbol}")
                logger.info(f"   Current: ${current_price:.2f}")
                logger.info(f"   Resistance: ${resistance_price:.2f} (confidence: {resistance_confidence:.1%})")
                logger.info(f"   Trigger: ${resistance_trigger_price:.2f}")
                logger.info(f"   Timeframe: {timeframe}")
                
                return {
                    'should_dca': True,
                    'reason': 'resistance_breach',
                    'level': resistance_price,
                    'confidence': resistance_confidence,
                    'trigger_price': resistance_trigger_price,
                    'timeframe': timeframe,
                    'message': f'Price breached resistance at ${resistance_price:.2f}'
                }
            else:
                distance_pct = ((resistance_trigger_price - current_price) / current_price) * 100
                logger.debug(f"🔍 WATCHING RESISTANCE: {symbol} ${current_price:.2f} < ${resistance_trigger_price:.2f} ({distance_pct:.1f}% away)")
                return {
                    'should_dca': False,
                    'reason': 'watching_resistance',
                    'next_resistance': resistance_price,
                    'distance_percent': distance_pct,
                    'message': f'Monitoring resistance at ${resistance_price:.2f} ({distance_pct:.1f}% away)'
                }
                
        except Exception as e:
            logger.error(f"Error checking resistance breach DCA for {symbol}: {e}")
            return {
                'should_dca': False,
                'reason': 'error',
                'message': f'Error calculating resistance: {str(e)}'
            }

    async def _execute_technical_dca(self, position: PositionState, dca_decision: dict):
        """
        Execute DCA order based on technical analysis decision with progressive price enforcement.
        This replaces the old loss-threshold based DCA.
        """
        try:
            # FIRST: Check for existing pending DCA orders to prevent multiple concurrent orders
            pending_orders = await self.order_manager.get_open_orders(symbol=position.symbol)
            
            # Check if any pending orders are DCA orders for this position
            pending_dca_orders = []
            for order in pending_orders:
                if self.order_manager.is_dca_order(order.order_id):
                    dca_info = self.order_manager.get_dca_order_info(order.order_id)
                    if dca_info and dca_info.get('position_lifecycle_id') == position.position_lifecycle_id:
                        pending_dca_orders.append(order)
            
            if pending_dca_orders:
                logger.warning(f"🚫 DCA ORDER BLOCKED: {position.symbol}")
                logger.warning(f"   Reason: {len(pending_dca_orders)} pending DCA order(s) already exist")
                for order in pending_dca_orders:
                    dca_info = self.order_manager.get_dca_order_info(order.order_id)
                    logger.warning(f"   Pending: {order.side.value} {order.quantity} @ ${order.price or 'MARKET'} (Level {dca_info.get('dca_level', '?')})")
                logger.warning(f"   Protection: Waiting for existing orders to fill before placing new DCA")
                return  # Exit without placing duplicate order
            
            # SECOND: Calculate progressive minimum price movement based on DCA attempts
            min_price_improvement = self._calculate_progressive_dca_threshold(position)
            
            if position.last_dca_price:
                current_price = position.current_price
                if position.direction == PositionDirection.LONG:
                    # For long positions, need price to drop by minimum threshold
                    required_price = position.last_dca_price * (1 - min_price_improvement)
                    if current_price >= required_price:
                        improvement_percent = ((position.last_dca_price - current_price) / position.last_dca_price) * 100
                        logger.warning(f"🚫 DCA ORDER BLOCKED: {position.symbol}")
                        logger.warning(f"   Reason: Insufficient price movement for DCA")
                        logger.warning(f"   Current: ${current_price:.2f}, Last DCA: ${position.last_dca_price:.2f}")
                        logger.warning(f"   Movement: {improvement_percent:.2f}%, Required: {min_price_improvement*100:.1f}%")
                        logger.warning(f"   DCA Level: {position.averaging_attempts + 1}, Progressive Threshold: {min_price_improvement*100:.1f}%")
                        logger.warning(f"   Protection: Preventing excessive DCA on minimal price changes")
                        return
                else:
                    # For short positions, need price to rise by minimum threshold
                    required_price = position.last_dca_price * (1 + min_price_improvement)
                    if current_price <= required_price:
                        improvement_percent = ((current_price - position.last_dca_price) / position.last_dca_price) * 100
                        logger.warning(f"🚫 DCA ORDER BLOCKED: {position.symbol}")
                        logger.warning(f"   Reason: Insufficient price movement for DCA")
                        logger.warning(f"   Current: ${current_price:.2f}, Last DCA: ${position.last_dca_price:.2f}")
                        logger.warning(f"   Movement: {improvement_percent:.2f}%, Required: {min_price_improvement*100:.1f}%")
                        logger.warning(f"   DCA Level: {position.averaging_attempts + 1}, Progressive Threshold: {min_price_improvement*100:.1f}%")
                        logger.warning(f"   Protection: Preventing excessive DCA on minimal price changes")
                        return
            
            logger.info(f"✅ DCA VALIDATION PASSED: {position.symbol}")
            logger.info(f"   No pending DCA orders found")
            if position.last_dca_price:
                improvement_percent = abs((position.current_price - position.last_dca_price) / position.last_dca_price) * 100
                logger.info(f"   Price movement: {improvement_percent:.2f}% (min required: {min_price_improvement*100:.1f}%)")
            
            config = self.long_config if position.direction == PositionDirection.LONG else self.short_config
            
            # Calculate new position size using configured multiplier
            current_position_value = abs(position.quantity * position.average_price)
            multiplier = config.get('position_multiplier', 1.5)
            
            # Calculate DCA quantity
            new_quantity = await self._calculate_averaging_position_size(
                position, 
                position.current_price, 
                position.direction == PositionDirection.LONG
            )
            
            # Use global order type setting
            order_type = self._get_order_type(self.config.get_config('trading.order_type', 'limit'))
            current_price = position.current_price
            
            # Calculate order price based on technical level
            if order_type == OrderType.LIMIT:
                technical_level = dca_decision['level']
                
                if position.direction == PositionDirection.LONG:
                    # CRITICAL FIX: DCA should be BELOW current price for averaging down
                    # Use the lower of: current price with buffer OR technical level with buffer
                    current_price_target = current_price * 0.998  # 0.2% below current price
                    technical_level_target = technical_level * 0.998  # 0.2% below support level
                    
                    # Choose the lower price to ensure true averaging down
                    order_price = min(current_price_target, technical_level_target)
                    order_side = OrderSide.BUY
                    
                    # Safety check: Never buy at or above current price for DCA
                    if order_price >= current_price:
                        logger.error(f"🚫 CRITICAL DCA SAFETY: {position.symbol} order price ${order_price:.2f} >= current ${current_price:.2f}")
                        logger.error(f"   This would defeat DCA averaging down purpose!")
                        logger.error(f"   Adjusting to safe price below current market")
                        order_price = current_price * 0.995  # 0.5% below current as safety fallback
                        
                else:
                    # For short positions: DCA should be ABOVE current price for averaging up
                    current_price_target = current_price * 1.002  # 0.2% above current price
                    technical_level_target = technical_level * 1.002  # 0.2% above resistance level
                    
                    # Choose the higher price to ensure true averaging up
                    order_price = max(current_price_target, technical_level_target)
                    order_side = OrderSide.SELL
                    
                    # Safety check: Never sell at or below current price for short DCA
                    if order_price <= current_price:
                        logger.error(f"🚫 CRITICAL DCA SAFETY: {position.symbol} order price ${order_price:.2f} <= current ${current_price:.2f}")
                        logger.error(f"   This would defeat DCA averaging up purpose!")
                        logger.error(f"   Adjusting to safe price above current market")
                        order_price = current_price * 1.005  # 0.5% above current as safety fallback
                    
                order_price = round(order_price, 2)
                
                # Log the corrected DCA pricing logic
                logger.info(f"💰 DCA PRICE CALCULATION: {position.symbol}")
                logger.info(f"   Direction: {position.direction.value}")
                logger.info(f"   Current Price: ${current_price:.2f}")
                logger.info(f"   Technical Level: ${technical_level:.2f}")
                logger.info(f"   Final Order Price: ${order_price:.2f}")
                if position.direction == PositionDirection.LONG:
                    price_vs_current = ((order_price - current_price) / current_price) * 100
                    price_vs_avg = ((order_price - position.average_price) / position.average_price) * 100
                    logger.info(f"   Price vs Current: {price_vs_current:.2f}% ({'ABOVE' if price_vs_current > 0 else 'BELOW'})")
                    logger.info(f"   Price vs Position Avg: {price_vs_avg:.2f}% ({'ABOVE' if price_vs_avg > 0 else 'BELOW'})")
                    if order_price < current_price and order_price < position.average_price:
                        logger.info(f"   ✅ SAFE DCA: Buying below both current price and position average")
                    else:
                        logger.warning(f"   ⚠️  DCA CONCERN: Review pricing logic")
            else:
                order_price = None
                order_side = OrderSide.BUY if position.direction == PositionDirection.LONG else OrderSide.SELL
            
            # CRITICAL: Validate progressive DCA pricing before placing order
            if order_price is not None:
                progressive_check = self._is_progressive_dca_price(position, order_price)
                
                if not progressive_check['is_progressive']:
                    logger.warning(f"🚫 DCA ORDER REJECTED: {position.symbol}")
                    logger.warning(f"   Reason: {progressive_check['reason']}")
                    logger.warning(f"   Message: {progressive_check['message']}")
                    logger.warning(f"   Technical Level: ${dca_decision['level']:.2f}")
                    logger.warning(f"   Proposed Price: ${order_price:.2f}")
                    logger.warning(f"   Last DCA Price: ${progressive_check['last_price']:.2f}")
                    logger.warning(f"   Required: Must be {progressive_check['required_direction']} last DCA")
                    logger.warning(f"   Protection: Preventing non-progressive martingale DCA")
                    return  # Exit without placing order
                
                logger.info(f"✅ PROGRESSIVE DCA VALIDATED: {position.symbol}")
                logger.info(f"   {progressive_check['message']}")
            
            # FINAL SAFETY CHECK: Validate DCA direction is correct
            if order_price is not None:
                if position.direction == PositionDirection.LONG:
                    if order_price >= current_price:
                        logger.error(f"🚨 FINAL SAFETY ABORT: {position.symbol}")
                        logger.error(f"   Long DCA order ${order_price:.2f} >= current price ${current_price:.2f}")
                        logger.error(f"   This violates DCA averaging down principle!")
                        logger.error(f"   ABORTING ORDER to protect portfolio")
                        return  # Exit without placing dangerous order
                    if order_price >= position.average_price:
                        logger.error(f"🚨 FINAL SAFETY ABORT: {position.symbol}")
                        logger.error(f"   Long DCA order ${order_price:.2f} >= position avg ${position.average_price:.2f}")
                        logger.error(f"   This would average UP instead of DOWN!")
                        logger.error(f"   ABORTING ORDER to protect portfolio")
                        return  # Exit without placing dangerous order
                else:  # SHORT position
                    if order_price <= current_price:
                        logger.error(f"🚨 FINAL SAFETY ABORT: {position.symbol}")
                        logger.error(f"   Short DCA order ${order_price:.2f} <= current price ${current_price:.2f}")
                        logger.error(f"   This violates DCA averaging up principle!")
                        logger.error(f"   ABORTING ORDER to protect portfolio")
                        return  # Exit without placing dangerous order
                        
                logger.info(f"✅ FINAL SAFETY CHECK PASSED: {position.symbol} DCA order is safe")
            
            # Create technical DCA order
            order = Order(
                order_id=None,
                symbol=position.symbol,
                side=order_side,
                quantity=new_quantity,
                order_type=order_type,
                price=order_price
            )
            
            order_id = await self.order_manager.place_order(order)
            
            # Track active order (DCA attempt counter will increment on fill, not placement)
            position.active_orders.append(order_id)
            
            # Track DCA order price for progressive validation
            if order_price is not None:
                position.last_dca_price = order_price
                position.dca_order_prices.append(order_price)
                logger.info(f"📊 DCA PRICE TRACKING: {position.symbol}")
                logger.info(f"   Order Price: ${order_price:.2f}")
                logger.info(f"   DCA History: {[f'${p:.2f}' for p in position.dca_order_prices]}")
                
                # CRITICAL: Save DCA metadata to prevent order history pollution
                await self._save_position_dca_metadata(
                    symbol=position.symbol,
                    attempts=position.averaging_attempts,
                    prices=position.dca_order_prices,
                    last_price=position.last_dca_price
                )
            
            # Update phase based on DCA reason
            if dca_decision['reason'] == 'support_breach':
                position.phase = TradePhase.SUPPORT_AVERAGING
                position.support_level = dca_decision['level']
            elif dca_decision['reason'] == 'resistance_breach':
                position.phase = TradePhase.RESISTANCE_AVERAGING
                position.resistance_level = dca_decision['level']
            
            logger.info(f"💰 TECHNICAL DCA ORDER PLACED: {position.symbol}")
            logger.info(f"   Type: {dca_decision['reason']}")
            logger.info(f"   Level: ${dca_decision['level']:.2f} (confidence: {dca_decision['confidence']:.1%})")
            logger.info(f"   Order: {order_side.value} {new_quantity} @ {order_price or 'MARKET'}")
            logger.info(f"   Timeframe: {dca_decision['timeframe']}")
            logger.info(f"   Attempt: {position.averaging_attempts}/{config.get('max_averaging_attempts', 3)}")
            logger.info(f"   Order ID: {order_id}")
            
        except Exception as e:
            logger.error(f"Error executing technical DCA for {position.symbol}: {e}")

    async def _execute_immediate_dca(self, position: PositionState):
        """Execute immediate DCA when support/resistance levels are not available."""
        try:
            config = self.long_config if position.direction == PositionDirection.LONG else self.short_config
            
            # Calculate new position size using martingale multiplier
            current_position_value = abs(position.quantity * position.average_price)
            multiplier = config.get('position_multiplier', 2.0)
            new_quantity = await self._calculate_averaging_position_size(position, position.current_price, 
                                                                        position.direction == PositionDirection.LONG)
            
            # Use global order type setting
            order_type = self._get_order_type(self.config.get_config('trading.order_type', 'limit'))
            current_price = position.current_price
            
            # Calculate order price
            if order_type == OrderType.LIMIT:
                limit_offset = self.config.get_config('trading.limit_order_offset', 0.001)
                if position.direction == PositionDirection.LONG:
                    # Buy slightly below current price
                    order_price = current_price * (1 - limit_offset)
                    order_side = OrderSide.BUY
                else:
                    # Sell slightly above current price  
                    order_price = current_price * (1 + limit_offset)
                    order_side = OrderSide.SELL
                order_price = round(order_price, 2)
            else:
                order_price = None
                order_side = OrderSide.BUY if position.direction == PositionDirection.LONG else OrderSide.SELL
            
            # Create DCA order
            order = Order(
                order_id=None,
                symbol=position.symbol,
                side=order_side,
                quantity=new_quantity,
                order_type=order_type,
                price=order_price
            )
            
            order_id = await self.order_manager.place_order(order)
            
            # Track active order (DCA attempt counter will increment on fill, not placement)
            position.active_orders.append(order_id)
            
            logger.info(f"💰 DCA ORDER PLACED: {position.symbol} {order_side.value} {new_quantity} @ {order_price or 'MARKET'}")
            logger.info(f"   Attempt: {position.averaging_attempts + 1}/{config.get('max_averaging_attempts', 3)} (will increment on fill)")
            logger.info(f"   Order ID: {order_id}")
            
            # Update average price calculation (will be updated when order fills)
            # For now, just log the expected new average
            if order_price:
                total_cost = (position.quantity * position.average_price) + (new_quantity * order_price)
                total_quantity = position.quantity + (new_quantity if position.direction == PositionDirection.LONG else -new_quantity)
                if total_quantity != 0:
                    expected_avg = total_cost / abs(total_quantity)
                    logger.info(f"   Expected new average: ${expected_avg:.2f}")
            
        except Exception as e:
            logger.error(f"Error executing immediate DCA for {position.symbol}: {e}")
    
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
            if position.average_price > 0:  # Prevent division by zero
                if position.direction == PositionDirection.LONG:
                    position.profit_percentage = (current_price - position.average_price) / position.average_price
                else:
                    position.profit_percentage = (position.average_price - current_price) / position.average_price
            else:
                position.profit_percentage = 0.0
            
            # Update position based on current phase and direction
            if position.direction == PositionDirection.LONG:
                await self._update_long_position(position)
            else:
                await self._update_short_position(position)
                
        except Exception as e:
            logger.error(f"Error updating position for {symbol}: {e}")
    
    async def _update_long_position(self, position: PositionState):
        """Update logic for long positions."""
        config = self.long_config
        
        if position.phase == TradePhase.ENTRY:
            # Check if we should start profit trailing
            if position.profit_percentage >= config['activation_threshold']:
                position.phase = TradePhase.PROFIT_TRAILING
                position.peak_price = position.current_price
                position.trail_price = position.current_price * (1 - config['trailing_percentage'])
                logger.info(f"🎯 TRAILING STARTED: {position.symbol} LONG @ {position.current_price:.2f}")
                logger.info(f"   📊 Profit: {position.profit_percentage:.2%} | Threshold: {config['activation_threshold']:.2%}")
                logger.info(f"   🛡️ Trail distance: {config['trailing_percentage']:.2%} | Initial trail: {position.trail_price:.2f}")
            
            # Check if we should start support averaging (price moving against us)
            elif position.profit_percentage <= -config['averaging_loss_threshold'] and config['averaging_enabled']:
                logger.info(f"📉 LOSS DETECTED: {position.symbol} {position.profit_percentage:.2%} ≤ -{config['averaging_loss_threshold']:.2%}")
                await self._check_support_averaging(position)
        
        elif position.phase == TradePhase.PROFIT_TRAILING:
            await self._update_profit_trailing_long(position)
        
        elif position.phase == TradePhase.SUPPORT_AVERAGING:
            await self._update_support_averaging(position)
    
    async def _update_short_position(self, position: PositionState):
        """Update logic for short positions."""
        config = self.short_config
        
        if position.phase == TradePhase.ENTRY:
            # Check if we should start profit trailing
            if position.profit_percentage >= config['activation_threshold']:
                position.phase = TradePhase.PROFIT_TRAILING
                position.peak_price = position.current_price  # Lowest price for shorts
                position.trail_price = position.current_price * (1 + config['trailing_percentage'])
                logger.info(f"🎯 TRAILING STARTED: {position.symbol} SHORT @ {position.current_price:.2f}")
                logger.info(f"   📊 Profit: {position.profit_percentage:.2%} | Threshold: {config['activation_threshold']:.2%}")
                logger.info(f"   🛡️ Trail distance: {config['trailing_percentage']:.2%} | Initial trail: {position.trail_price:.2f}")
            
            # Check if we should start resistance averaging (price moving against us)
            elif position.profit_percentage <= -config['averaging_loss_threshold'] and config['averaging_enabled']:
                logger.info(f"📈 LOSS DETECTED: {position.symbol} {position.profit_percentage:.2%} ≤ -{config['averaging_loss_threshold']:.2%}")
                await self._check_resistance_averaging(position)
        
        elif position.phase == TradePhase.PROFIT_TRAILING:
            await self._update_profit_trailing_short(position)
        
        elif position.phase == TradePhase.RESISTANCE_AVERAGING:
            await self._update_resistance_averaging(position)
    
    async def _update_profit_trailing_long(self, position: PositionState):
        """Update profit trailing for long positions."""
        config = self.long_config
        current_price = position.current_price
        
        # Update peak price if we have a new high
        if current_price > position.peak_price:
            old_peak = position.peak_price
            position.peak_price = current_price
            position.trail_price = current_price * (1 - config['trailing_percentage'])
            logger.info(f"🏔️ NEW PEAK: {position.symbol} {old_peak:.2f} → {current_price:.2f} | Trail: {position.trail_price:.2f}")
        
        # Check if trailing stop is hit
        if current_price <= position.trail_price:
            logger.info(f"🛑 TRAILING STOP HIT: {position.symbol} {current_price:.2f} ≤ {position.trail_price:.2f}")
            logger.info(f"   📊 Final profit from peak: {((position.trail_price / position.peak_price) - 1):.2%}")
            await self._close_position(position.symbol)
    
    async def _update_profit_trailing_short(self, position: PositionState):
        """Update profit trailing for short positions."""
        config = self.short_config
        current_price = position.current_price
        
        # Update peak price if we have a new low
        if current_price < position.peak_price:
            old_peak = position.peak_price
            position.peak_price = current_price
            position.trail_price = current_price * (1 + config['trailing_percentage'])
            logger.info(f"🏔️ NEW PEAK: {position.symbol} {old_peak:.2f} → {current_price:.2f} | Trail: {position.trail_price:.2f}")
        
        # Check if trailing stop is hit
        if current_price >= position.trail_price:
            logger.info(f"🛑 TRAILING STOP HIT: {position.symbol} {current_price:.2f} ≥ {position.trail_price:.2f}")
            logger.info(f"   📊 Final profit from peak: {((position.peak_price / position.trail_price) - 1):.2%}")
            await self._close_position(position.symbol)
    
    async def _check_support_averaging(self, position: PositionState):
        """Check if we should start support-based averaging down."""
        config = self.long_config
        
        if position.averaging_attempts >= config['max_averaging_attempts']:
            logger.info(f"🚫 MAX AVERAGING REACHED: {position.symbol} ({position.averaging_attempts}/{config['max_averaging_attempts']})")
            return
        
        # Get position-aware support levels for averaging down
        try:
            support_data = await self.support_calculator.calculate_support_levels_for_position(
                symbol=position.symbol, 
                timeframe="15m",
                position_avg_price=position.average_price,
                position_type="long"
            )
            
            if not support_data or not support_data.levels:
                logger.warning(f"⚠️ NO SUPPORT DATA: {position.symbol} - cannot set support averaging target")
                return
            
            # Find the nearest support level below current price
            current_price = position.current_price
            support_level = None
            
            # Log all available support levels for debugging
            logger.debug(f"📊 SUPPORT AVERAGING ANALYSIS for {position.symbol}:")
            logger.debug(f"   Current Price: ${current_price:.2f}")
            valid_supports = [level for level in support_data.levels if level.price < current_price]
            if valid_supports:
                for level in sorted(valid_supports, key=lambda x: x.price, reverse=True):
                    distance = ((current_price - level.price) / level.price) * 100
                    logger.debug(f"     ${level.price:.2f} ({level.method}, {level.confidence:.2f}, {distance:.1f}% below)")
            
            for level in support_data.levels:
                if level.price < current_price:
                    if support_level is None or level.price > support_level:
                        support_level = level.price
            
            if support_level:
                position.support_level = support_level
                position.phase = TradePhase.SUPPORT_AVERAGING
                distance = ((current_price - support_level) / support_level) * 100
                logger.info(f"🎯 SUPPORT TARGET SET: {position.symbol} @ ${support_level:.2f} ({distance:.1f}% below current)")
            else:
                logger.warning(f"⚠️ NO VALID SUPPORT: {position.symbol} - no support levels below ${current_price:.2f}")
            
        except Exception as e:
            logger.error(f"Error calculating support for {position.symbol}: {e}")
    
    async def _check_resistance_averaging(self, position: PositionState):
        """Check if we should start resistance-based averaging up."""
        config = self.short_config
        
        if position.averaging_attempts >= config['max_averaging_attempts']:
            logger.info(f"Max averaging attempts reached for {position.symbol}")
            return
        
        # Get position-aware resistance levels for averaging up
        try:
            resistance_data = await self.support_calculator.calculate_resistance_levels_for_position(
                symbol=position.symbol, 
                timeframe="15m",
                position_avg_price=position.average_price,
                position_type="short"
            )
            
            if not resistance_data or not resistance_data.levels:
                logger.warning(f"⚠️ NO RESISTANCE DATA: {position.symbol} - cannot set resistance averaging target")
                return
            
            # Find the nearest resistance level above current price
            current_price = position.current_price
            resistance_level = None
            
            # Log all available resistance levels for debugging
            logger.debug(f"📊 RESISTANCE AVERAGING ANALYSIS for {position.symbol}:")
            logger.debug(f"   Current Price: ${current_price:.2f}")
            valid_resistances = [level for level in resistance_data.levels if level.price > current_price]
            if valid_resistances:
                for level in sorted(valid_resistances, key=lambda x: x.price):
                    distance = ((level.price - current_price) / current_price) * 100
                    logger.debug(f"     ${level.price:.2f} ({level.method}, {level.confidence:.2f}, {distance:.1f}% above)")
            
            for level in resistance_data.levels:
                if level.price > current_price:
                    if resistance_level is None or level.price < resistance_level:
                        resistance_level = level.price
            
            if resistance_level:
                position.resistance_level = resistance_level
                position.phase = TradePhase.RESISTANCE_AVERAGING
                distance = ((resistance_level - current_price) / current_price) * 100
                logger.info(f"🎯 RESISTANCE TARGET SET: {position.symbol} @ ${resistance_level:.2f} ({distance:.1f}% above current)")
            else:
                logger.warning(f"⚠️ NO VALID RESISTANCE: {position.symbol} - no resistance levels above ${current_price:.2f}")
            
        except Exception as e:
            logger.error(f"Error calculating resistance for {position.symbol}: {e}")
    
    async def _update_support_averaging(self, position: PositionState):
        """Update support averaging logic."""
        config = self.long_config
        
        if not position.support_level:
            return
        
        current_price = position.current_price
        
        # If price reaches support level, start trailing down
        if current_price <= position.support_level * 1.005:  # Within 0.5% of support
            if not position.trail_price:
                # Start trailing down from support level
                position.trail_price = current_price * (1 - config['support_trailing_percentage'])
                logger.info(f"Started support trailing for {position.symbol} at {current_price}")
            else:
                # Update trailing price if price goes lower
                new_trail = current_price * (1 - config['support_trailing_percentage'])
                if new_trail < position.trail_price:
                    position.trail_price = new_trail
        
        # Check if trailing stop is breached (time to average down)
        if position.trail_price and current_price > position.trail_price:
            await self._execute_averaging_down(position)
    
    async def _update_resistance_averaging(self, position: PositionState):
        """Update resistance averaging logic."""
        config = self.short_config
        
        if not position.resistance_level:
            return
        
        current_price = position.current_price
        
        # If price reaches resistance level, start trailing up
        if current_price >= position.resistance_level * 0.995:  # Within 0.5% of resistance
            if not position.trail_price:
                # Start trailing up from resistance level
                position.trail_price = current_price * (1 + config['resistance_trailing_percentage'])
                logger.info(f"Started resistance trailing for {position.symbol} at {current_price}")
            else:
                # Update trailing price if price goes higher
                new_trail = current_price * (1 + config['resistance_trailing_percentage'])
                if new_trail > position.trail_price:
                    position.trail_price = new_trail
        
        # Check if trailing stop is breached (time to average up)
        if position.trail_price and current_price < position.trail_price:
            await self._execute_averaging_up(position)
    
    async def _execute_averaging_down(self, position: PositionState):
        """Execute averaging down order for long positions."""
        config = self.long_config
        
        # Calculate new position size using averaging sizing method
        new_quantity = await self._calculate_averaging_position_size(position, position.current_price, True)
        # Use global order type setting for averaging
        order_type = self._get_order_type(self.config.get_config('trading.order_type', 'market'))
        current_price = position.current_price
        
        if order_type == OrderType.LIMIT:
            # Place limit order slightly below current price
            entry_price = current_price * (1 - config['entry_limit_offset'])
        else:
            entry_price = current_price
        
        # Create averaging order
        order = Order(
            order_id=None,  # Will be auto-generated
            symbol=position.symbol,
            side=OrderSide.BUY,
            quantity=new_quantity,
            order_type=order_type,
            price=entry_price if order_type == OrderType.LIMIT else None
        )
        
        try:
            order_id = await self.order_manager.place_order(order)
            
            # Update position
            total_quantity = position.quantity + new_quantity
            total_cost = (position.quantity * position.average_price) + (new_quantity * entry_price)
            if total_quantity > 0:
                position.average_price = total_cost / total_quantity
            else:
                logger.error(f"Invalid total_quantity calculation for {position.symbol}")
                return
            position.quantity = total_quantity
            position.averaging_attempts += 1
            position.active_orders.append(order_id)
            
            # Reset trailing and go back to entry phase
            position.trail_price = None
            position.phase = TradePhase.ENTRY
            
            logger.info(f"📈 AVERAGING DOWN: {position.symbol} +{new_quantity} @ {entry_price:.2f}")
            logger.info(f"   💰 New average price: {position.average_price:.2f} | Total quantity: {position.quantity}")
            logger.info(f"   🔄 Attempt {position.averaging_attempts}/{config['max_averaging_attempts']}")
            
            # Persist updated position to database
            if self.position_manager:
                try:
                    await self.position_manager.update_position(
                        symbol=position.symbol,
                        quantity=new_quantity,  # Just the new quantity added
                        price=entry_price
                    )
                    logger.info(f"✅ Averaged position {position.symbol} saved to database")
                except Exception as e:
                    logger.error(f"❌ Failed to save averaged position {position.symbol}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to execute averaging down for {position.symbol}: {e}")
    
    async def _execute_averaging_up(self, position: PositionState):
        """Execute averaging up order for short positions."""
        config = self.short_config
        
        # Calculate new position size using averaging sizing method
        new_quantity = await self._calculate_averaging_position_size(position, position.current_price, False)
        order_type = self._get_order_type(self.config.get_config('trading.order_type', 'market'))
        current_price = position.current_price
        
        if order_type == OrderType.LIMIT:
            # Place limit order slightly above current price
            entry_price = current_price * (1 + config['entry_limit_offset'])
        else:
            entry_price = current_price
        
        # Create averaging order
        order = Order(
            order_id=None,  # Will be auto-generated
            symbol=position.symbol,
            side=OrderSide.SELL,
            quantity=new_quantity,
            order_type=order_type,
            price=entry_price if order_type == OrderType.LIMIT else None
        )
        
        try:
            order_id = await self.order_manager.place_order(order)
            
            # Update position
            total_quantity = position.quantity + new_quantity
            total_cost = (position.quantity * position.average_price) + (new_quantity * entry_price)
            if total_quantity > 0:
                position.average_price = total_cost / total_quantity
            else:
                logger.error(f"Invalid total_quantity calculation for {position.symbol}")
                return
            position.quantity = total_quantity
            position.averaging_attempts += 1
            position.active_orders.append(order_id)
            
            # Reset trailing and go back to entry phase
            position.trail_price = None
            position.phase = TradePhase.ENTRY
            
            logger.info(f"📉 AVERAGING UP: {position.symbol} +{new_quantity} @ {entry_price:.2f}")
            logger.info(f"   💰 New average price: {position.average_price:.2f} | Total quantity: {position.quantity}")
            logger.info(f"   🔄 Attempt {position.averaging_attempts}/{config['max_averaging_attempts']}")
            
            # Persist updated position to database
            if self.position_manager:
                try:
                    await self.position_manager.update_position(
                        symbol=position.symbol,
                        quantity=-new_quantity,  # Negative for short addition
                        price=entry_price
                    )
                    logger.info(f"✅ Averaged position {position.symbol} saved to database")
                except Exception as e:
                    logger.error(f"❌ Failed to save averaged position {position.symbol}: {e}")
            
        except Exception as e:
            logger.error(f"Failed to execute averaging up for {position.symbol}: {e}")
    
    async def _calculate_averaging_position_size(self, position: PositionState, 
                                               current_price: float, is_long: bool) -> float:
        """Calculate position size for averaging down/up using risk manager's martingale logic."""
        try:
            # Create a temporary signal for position sizing calculation
            from .. import TradingSignal, SignalType
            
            signal_type = SignalType.BUY if is_long else SignalType.SELL
            temp_signal = TradingSignal(
                signal_id=f"avg-{position.symbol}-{datetime.utcnow().timestamp()}",
                symbol=position.symbol,
                signal_type=signal_type,
                price=current_price,
                timestamp=datetime.utcnow()
            )
            
            # Use risk manager with proper averaging attempt for martingale sizing
            # This will apply the martingale multiplier (1%, 2%, 4%, etc.)
            quantity = await self.risk_manager.calculate_position_size(
                symbol=position.symbol,
                signal=temp_signal,
                averaging_attempt=position.averaging_attempts + 1  # Next attempt number
            )
            
            logger.info(f"Martingale position sizing for {position.symbol} "
                       f"(attempt #{position.averaging_attempts + 1}): {quantity} shares")
            
            return quantity
                
        except Exception as e:
            logger.error(f"Error calculating averaging position size: {e}")
            # Fallback to current position size
            return position.quantity
    
    def _calculate_progressive_dca_threshold(self, position: PositionState) -> float:
        """
        Calculate progressive minimum price improvement for DCA orders.
        
        Uses a logarithmic scale that increases with each DCA attempt:
        - DCA 1: 1.5% minimum improvement
        - DCA 2: 2.5% minimum improvement  
        - DCA 3: 4.0% minimum improvement
        - DCA 4+: 6.0% minimum improvement
        
        This ensures meaningful price movements and protects against order spam
        while still respecting technical support/resistance levels.
        
        Args:
            position: Current position state
            
        Returns:
            Minimum price improvement as decimal (e.g., 0.025 for 2.5%)
        """
        try:
            # Get base configuration
            base_threshold = self.config.get_config('strategies.dca.base_threshold_percent', 1.5) / 100.0
            multiplier = self.config.get_config('strategies.dca.progressive_multiplier', 1.8)
            max_threshold = self.config.get_config('strategies.dca.max_threshold_percent', 6.0) / 100.0
            
            # Calculate progressive threshold using logarithmic scaling
            # Formula: base_threshold * (multiplier ^ attempts)
            dca_attempt = position.averaging_attempts + 1  # Next attempt number
            progressive_threshold = base_threshold * (multiplier ** (dca_attempt - 1))
            
            # Cap at maximum threshold
            progressive_threshold = min(progressive_threshold, max_threshold)
            
            logger.debug(f"📊 PROGRESSIVE DCA THRESHOLD: {position.symbol}")
            logger.debug(f"   DCA Attempt: #{dca_attempt}")
            logger.debug(f"   Base Threshold: {base_threshold*100:.1f}%")
            logger.debug(f"   Progressive Multiplier: {multiplier}x")
            logger.debug(f"   Calculated Threshold: {progressive_threshold*100:.1f}%")
            logger.debug(f"   Max Threshold Cap: {max_threshold*100:.1f}%")
            
            return progressive_threshold
            
        except Exception as e:
            logger.error(f"Error calculating progressive DCA threshold: {e}")
            # Fallback to 2% threshold
            return 0.02
    
    def _get_order_type(self, order_type_str: str) -> OrderType:
        """Convert string order type to OrderType enum."""
        order_type_map = {
            'market': OrderType.MARKET,
            'limit': OrderType.LIMIT,
            'stop': OrderType.STOP,
            'stop_limit': OrderType.STOP_LIMIT
        }
        
        return order_type_map.get(order_type_str.lower(), OrderType.LIMIT)
    
    def get_position_summary(self) -> Dict[str, Dict]:
        """Get summary of all active positions with detailed trailing and averaging info."""
        summary = {}
        
        for symbol, position in self.positions.items():
            # Calculate profit/loss in dollars
            profit_loss_dollars = position.profit_percentage * position.average_price * position.quantity
            
            # Determine trailing status
            trailing_status = "inactive"
            if position.phase == TradePhase.PROFIT_TRAILING:
                trailing_status = "profit_trailing"
            elif position.phase == TradePhase.SUPPORT_AVERAGING and position.trail_price:
                trailing_status = "support_trailing"
            elif position.phase == TradePhase.RESISTANCE_AVERAGING and position.trail_price:
                trailing_status = "resistance_trailing"
            
            summary[symbol] = {
                'direction': position.direction.value,
                'phase': position.phase.value,
                'quantity': position.quantity,
                'average_price': position.average_price,
                'current_price': position.current_price,
                'profit_percentage': round(position.profit_percentage * 100, 2),  # Convert to percentage
                'profit_loss_dollars': round(profit_loss_dollars, 2),
                'averaging_attempts': position.averaging_attempts,
                'active_orders': len(position.active_orders),
                'entry_time': position.entry_time.isoformat(),
                
                # Trailing information
                'trailing_status': trailing_status,
                'peak_price': position.peak_price,
                'trail_price': position.trail_price,
                
                # Support/Resistance information
                'support_level': position.support_level,
                'resistance_level': position.resistance_level,
                
                # Trading thresholds (from config)
                'profit_target_pct': self.long_config['activation_threshold'] * 100 if position.direction == PositionDirection.LONG else self.short_config['activation_threshold'] * 100,
                'averaging_threshold_pct': self.long_config['averaging_loss_threshold'] * 100 if position.direction == PositionDirection.LONG else self.short_config['averaging_loss_threshold'] * 100
            }
        
        return summary

    def _log_support_analysis(self, symbol: str, current_price: float, 
                             min_confidence: float, valid_supports: List) -> None:
        """
        Centralized method for logging support analysis details.
        
        Args:
            symbol: Stock symbol
            current_price: Current market price 
            min_confidence: Minimum confidence threshold
            valid_supports: List of valid support levels
        """
        try:
            logger.debug(f"📊 SUPPORT ANALYSIS RESULT for {symbol}:")
            logger.debug(f"   Current Price: ${current_price:.2f}")
            logger.debug(f"   Min Confidence Required: {min_confidence:.0%}")
            logger.debug(f"   Valid Supports Found: {len(valid_supports)}")
            
            if valid_supports:
                for level in sorted(valid_supports, key=lambda x: x.price, reverse=True):
                    try:
                        distance = ((current_price - level.price) / level.price) * 100
                        logger.debug(f"     ${level.price:.2f} ({level.method}, {level.confidence:.2f}, {distance:.1f}% below)")
                    except (AttributeError, ZeroDivisionError) as e:
                        logger.warning(f"Error calculating distance for support level: {e}")
                        logger.debug(f"     ${level.price:.2f} ({getattr(level, 'method', 'unknown')}, {getattr(level, 'confidence', 0):.2f})")
        except Exception as e:
            logger.warning(f"Error logging support analysis for {symbol}: {e}")

    def _log_resistance_analysis(self, symbol: str, current_price: float,
                                min_confidence: float, valid_resistances: List) -> None:
        """
        Centralized method for logging resistance analysis details.
        
        Args:
            symbol: Stock symbol
            current_price: Current market price
            min_confidence: Minimum confidence threshold  
            valid_resistances: List of valid resistance levels
        """
        try:
            logger.debug(f"📊 RESISTANCE ANALYSIS RESULT for {symbol}:")
            logger.debug(f"   Current Price: ${current_price:.2f}")
            logger.debug(f"   Min Confidence Required: {min_confidence:.0%}")
            logger.debug(f"   Valid Resistances Found: {len(valid_resistances)}")
            
            if valid_resistances:
                for level in sorted(valid_resistances, key=lambda x: x.price):
                    try:
                        distance = ((level.price - current_price) / current_price) * 100
                        logger.debug(f"     ${level.price:.2f} ({level.method}, {level.confidence:.2f}, {distance:.1f}% above)")
                    except (AttributeError, ZeroDivisionError) as e:
                        logger.warning(f"Error calculating distance for resistance level: {e}")
                        logger.debug(f"     ${level.price:.2f} ({getattr(level, 'method', 'unknown')}, {getattr(level, 'confidence', 0):.2f})")
        except Exception as e:
            logger.warning(f"Error logging resistance analysis for {symbol}: {e}")
