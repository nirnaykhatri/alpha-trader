"""
DCA (Dollar-Cost Averaging) Planner
Handles martingale-based DCA planning and execution with progressive validation.
Uses unrealized loss percentage as DCA trigger (NO technical analysis).

Configuration is driven by bot's DCAConfig from database, NOT from config files.
"""

from typing import Dict, Optional, Any, Callable
from decimal import Decimal
from src.interfaces import IOrderManager, IDCAPlanner, PositionStateType
from src.core.logging_config import get_logger
from src import Order, OrderType, OrderSide
from src.strategies.position_state import PositionState, PositionDirection, TradePhase
from src.risk.martingale_validator import MartingaleSafetyManager
from src.utils.trading_utils import get_order_type
from src.constants import TradingConstants
from src.domain.bot_models import DCAConfig, AveragingOrdersConfig

logger = get_logger(__name__)


class DCAPlanner(IDCAPlanner):
    """
    Plans and executes DCA orders based on martingale loss thresholds.
    Follows Single Responsibility Principle - only handles DCA logic.
    
    Implements IDCAPlanner interface for polymorphic DCA strategy execution.
    Configuration is driven exclusively by bot's DCAConfig from database.
    No config file fallback - bot configuration must be provided.
    """
    
    def __init__(
        self,
        order_manager: IOrderManager,
        martingale_safety: MartingaleSafetyManager,
        bot_dca_config: DCAConfig,
        dca_metadata_manager=None
    ):
        """
        Initialize the DCA planner.
        
        Args:
            order_manager: Order execution manager
            martingale_safety: Safety validator for martingale limits
            bot_dca_config: Bot's DCA configuration from database (REQUIRED)
            dca_metadata_manager: Optional metadata persistence
            
        Raises:
            ValueError: If bot_dca_config is None
        """
        if bot_dca_config is None:
            raise ValueError("bot_dca_config is required - DCA configuration must come from database")
        
        self.order_manager = order_manager
        self.martingale_safety = martingale_safety
        self.dca_metadata_manager = dca_metadata_manager
        
        # Bot-specific DCA config from database (REQUIRED - no file fallback)
        self._bot_dca_config = bot_dca_config
    
    def set_bot_config(self, dca_config: DCAConfig) -> None:
        """
        Update the bot's DCA configuration at runtime.
        
        Args:
            dca_config: Bot's DCA configuration from database
            
        Raises:
            ValueError: If dca_config is None
        """
        if dca_config is None:
            raise ValueError("dca_config cannot be None - database configuration required")
        self._bot_dca_config = dca_config
        logger.info(f"✅ DCAPlanner updated with bot-specific DCA config")
        if dca_config.averaging_orders:
            logger.info(f"   - Orders count: {dca_config.averaging_orders.orders_count}")
            logger.info(f"   - Step percent: {dca_config.averaging_orders.step_percent}%")
            logger.info(f"   - Step multiplier: {dca_config.averaging_orders.step_multiplier}x")
    
    def _get_dca_thresholds(self) -> tuple[float, float, float]:
        """
        Get DCA threshold configuration.
        
        Returns:
            Tuple of (base_threshold_percent, progressive_multiplier, max_threshold_percent)
            
        Priority:
            1. Bot's DCAConfig.averaging_orders (from database)
            2. Global config file (legacy fallback)
        """
        # Priority 1: Use bot-specific config from database
        if self._bot_dca_config and self._bot_dca_config.averaging_orders:
            avg_config = self._bot_dca_config.averaging_orders
            base_threshold = float(avg_config.step_percent)
            
            # Use step_multiplier if enabled, otherwise no progression (1.0)
            if avg_config.step_multiplier_enabled:
                progressive_multiplier = float(avg_config.step_multiplier)
            else:
                progressive_multiplier = 1.0
            
            # Max threshold is capped at 6x base threshold or 15% max
            max_threshold = min(base_threshold * 6, 15.0)
            
            logger.debug(f"📊 Using bot database config for DCA thresholds:")
            logger.debug(f"   Base: {base_threshold}%, Multiplier: {progressive_multiplier}x, Max: {max_threshold}%")
            
            return base_threshold, progressive_multiplier, max_threshold
        
        # No fallback - configuration must come from database
        raise ValueError("Bot DCA config with averaging_orders is required - no config file fallback")
    
    def _get_order_type(self) -> OrderType:
        """
        Get order type for DCA orders from bot database config.
        
        Returns:
            OrderType from bot config
            
        Raises:
            ValueError: If bot config is missing start_settings
        """
        if self._bot_dca_config and self._bot_dca_config.start_settings:
            order_type_str = self._bot_dca_config.start_settings.base_order_type.value
            return get_order_type(order_type_str)
        
        raise ValueError("Bot DCA config with start_settings is required for order type")
    
    def _get_max_averaging_attempts(self) -> int:
        """
        Get maximum DCA attempts allowed from bot database config.
        
        Returns:
            Max DCA attempts from bot config
            
        Raises:
            ValueError: If bot config is missing averaging_orders
        """
        if self._bot_dca_config and self._bot_dca_config.averaging_orders:
            return self._bot_dca_config.averaging_orders.orders_count
        
        raise ValueError("Bot DCA config with averaging_orders is required for max attempts")
    
    def _check_martingale_dca(
        self, 
        position: PositionState, 
        is_long: bool
    ) -> dict:
        """
        Shared martingale DCA trigger logic for both LONG and SHORT positions.
        Uses unrealized loss percentage as trigger (NO technical analysis).
        
        Progressive DCA thresholds:
        - DCA 1: 1.5% loss from average price
        - DCA 2: 2.7% loss (1.5% * 1.8)
        - DCA 3: 4.9% loss (2.7% * 1.8)
        - Max: 6.0% loss threshold cap
        
        Args:
            position: Current position state
            is_long: True for LONG positions, False for SHORT
            
        Returns:
            dict with keys: should_dca, reason, level, confidence, message
        """
        try:
            current_price = position.current_price
            symbol = position.symbol
            average_price = position.average_price
            direction_str = "LONG" if is_long else "SHORT"
            
            # Calculate unrealized loss percentage
            # For LONG: loss when price drops (current < average)
            # For SHORT: loss when price rises (current > average)
            if is_long:
                unrealized_pnl_percent = ((current_price - average_price) / average_price) * 100
            else:
                unrealized_pnl_percent = ((average_price - current_price) / average_price) * 100
            
            loss_percent = abs(unrealized_pnl_percent) if unrealized_pnl_percent < 0 else 0
            
            logger.info(f"🔍 MARTINGALE DCA CHECK: {symbol}")
            logger.info(f"   Direction: {direction_str}")
            logger.info(f"   Current Price: ${current_price:.2f}")
            logger.info(f"   Position Average: ${average_price:.2f}")
            logger.info(f"   Unrealized P&L: {unrealized_pnl_percent:.2f}%")
            logger.info(f"   Loss Amount: {loss_percent:.2f}%")
            logger.info(f"   DCA Attempts: {position.averaging_attempts}")
            
            # Calculate progressive DCA threshold based on attempts
            # Uses bot config from database (preferred) or global config (fallback)
            base_threshold, progressive_multiplier, max_threshold = self._get_dca_thresholds()
            
            current_threshold = base_threshold
            for _ in range(position.averaging_attempts):
                current_threshold *= progressive_multiplier
                current_threshold = min(current_threshold, max_threshold)
            
            logger.info(f"   Progressive Threshold: {current_threshold:.2f}%")
            logger.info(f"   (base={base_threshold}%, multiplier={progressive_multiplier})")
            
            # Check if unrealized loss exceeds threshold
            if loss_percent >= current_threshold:
                logger.info(f"✅ MARTINGALE TRIGGER: {symbol}")
                logger.info(f"   Loss {loss_percent:.2f}% >= Threshold {current_threshold:.2f}%")
                logger.info(f"   🎯 DCA RECOMMENDED (loss-based trigger)")
                
                return {
                    'should_dca': True,
                    'reason': 'loss_threshold_exceeded',
                    'level': current_price,
                    'confidence': 1.0,  # No TA uncertainty
                    'trigger_price': current_price,
                    'timeframe': 'N/A',  # No TA timeframe
                    'message': f'Loss {loss_percent:.2f}% exceeds threshold {current_threshold:.2f}%'
                }
            
            logger.info(f"⏳ NO MARTINGALE TRIGGER: {symbol}")
            logger.info(f"   Loss {loss_percent:.2f}% < Threshold {current_threshold:.2f}%")
            logger.info(f"   Waiting for loss to reach threshold...")
            
            return {
                'should_dca': False,
                'reason': 'loss_below_threshold',
                'level': current_price,
                'distance_percent': current_threshold - loss_percent,
                'message': f'Loss {loss_percent:.2f}% below threshold {current_threshold:.2f}%'
            }
                
        except Exception as e:
            logger.error(f"Error checking martingale DCA for {position.symbol}: {e}")
            return {
                'should_dca': False,
                'reason': 'error',
                'message': f'Error calculating DCA: {str(e)}'
            }
    
    def is_progressive_dca_price(self, position: PositionState, proposed_price: float) -> dict:
        """
        Validate that the proposed DCA price is progressive (better than previous DCA).
        For LONG positions: each DCA must be BELOW the last DCA price (averaging down).
        For SHORT positions: each DCA must be ABOVE the last DCA price (averaging up).
        
        Args:
            position: Current position state
            proposed_price: Proposed DCA order price
            
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
    
    async def check_martingale_dca_long(self, position: PositionState, timeframe: str) -> dict:
        """
        MARTINGALE-ONLY DCA TRIGGER for LONG positions.
        Uses unrealized loss percentage as trigger (NO technical analysis).
        
        Args:
            position: Current position state
            timeframe: Ignored (kept for compatibility)
            
        Returns:
            dict with keys: should_dca, reason, level, confidence, message
        """
        return self._check_martingale_dca(position, is_long=True)
    
    async def check_martingale_dca_short(self, position: PositionState, timeframe: str) -> dict:
        """
        MARTINGALE-ONLY DCA TRIGGER for SHORT positions.
        Uses unrealized loss percentage as trigger (NO technical analysis).
        
        Args:
            position: Current position state
            timeframe: Ignored (kept for compatibility)
            
        Returns:
            dict with keys: should_dca, reason, level, confidence, message
        """
        return self._check_martingale_dca(position, is_long=False)
    
    async def _check_pending_dca_orders(self, position: PositionState) -> bool:
        """
        Check for existing pending DCA orders to prevent multiple concurrent orders.
        
        Args:
            position: Current position state
            
        Returns:
            True if no pending DCA orders exist, False otherwise
        """
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
            return False
        
        return True
    
    def _check_progressive_price_movement(self, position: PositionState) -> bool:
        """
        Validate that price has moved enough from last DCA to justify new DCA.
        
        Args:
            position: Current position state
            
        Returns:
            True if price movement is sufficient, False otherwise
        """
        if not position.last_dca_price:
            return True
        
        min_price_improvement = self._calculate_progressive_dca_threshold(position)
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
                return False
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
                return False
        
        return True
    
    def _calculate_dca_order_price(
        self,
        position: PositionState,
        dca_decision: dict
    ) -> tuple[Optional[float], OrderSide]:
        """
        Calculate the DCA order price and side based on position direction and technical level.
        
        Args:
            position: Current position state
            dca_decision: DCA decision dict with 'level' key
            
        Returns:
            Tuple of (order_price, order_side). order_price is None for market orders.
        """
        order_type = self._get_order_type()
        current_price = position.current_price
        
        if order_type != OrderType.LIMIT:
            order_side = OrderSide.BUY if position.direction == PositionDirection.LONG else OrderSide.SELL
            return None, order_side
        
        technical_level = dca_decision['level']
        
        if position.direction == PositionDirection.LONG:
            # CRITICAL FIX: DCA should be BELOW current price for averaging down
            current_price_target = current_price * TradingConstants.DCA_PRICE_OFFSET_NORMAL  # 0.2% below current price
            technical_level_target = technical_level * TradingConstants.DCA_PRICE_OFFSET_NORMAL  # 0.2% below support level
            
            # Choose the lower price to ensure true averaging down
            order_price = min(current_price_target, technical_level_target)
            order_side = OrderSide.BUY
            
            # Safety check: Never buy at or above current price for DCA
            if order_price >= current_price:
                logger.error(f"🚫 CRITICAL DCA SAFETY: {position.symbol} order price ${order_price:.2f} >= current ${current_price:.2f}")
                logger.error(f"   This would defeat DCA averaging down purpose!")
                logger.error(f"   Adjusting to safe price below current market")
                order_price = current_price * TradingConstants.DCA_PRICE_OFFSET_SAFETY  # 0.5% below current as safety fallback
        else:
            # For short positions: DCA should be ABOVE current price for averaging up
            current_price_target = current_price * TradingConstants.DCA_PRICE_OFFSET_SHORT_NORMAL  # 0.2% above current price
            technical_level_target = technical_level * TradingConstants.DCA_PRICE_OFFSET_SHORT_NORMAL  # 0.2% above resistance level
            
            # Choose the higher price to ensure true averaging up
            order_price = max(current_price_target, technical_level_target)
            order_side = OrderSide.SELL
            
            # Safety check: Never sell at or below current price for short DCA
            if order_price <= current_price:
                logger.error(f"🚫 CRITICAL DCA SAFETY: {position.symbol} order price ${order_price:.2f} <= current ${current_price:.2f}")
                logger.error(f"   This would defeat DCA averaging up purpose!")
                logger.error(f"   Adjusting to safe price above current market")
                order_price = current_price * TradingConstants.DCA_PRICE_OFFSET_SHORT_SAFETY  # 0.5% above current as safety fallback
        
        order_price = round(order_price, 2)
        
        # Log the DCA pricing logic
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
        
        return order_price, order_side
    
    def _validate_dca_price_safety(
        self,
        position: PositionState,
        order_price: Optional[float],
        dca_decision: dict
    ) -> bool:
        """
        Validate progressive DCA pricing and final safety checks.
        
        Args:
            position: Current position state
            order_price: Proposed order price (None for market orders)
            dca_decision: DCA decision dict with 'level' key
            
        Returns:
            True if price is safe to use, False otherwise
        """
        if order_price is None:
            return True
        
        current_price = position.current_price
        
        # Validate progressive DCA pricing
        progressive_check = self.is_progressive_dca_price(position, order_price)
        
        if not progressive_check['is_progressive']:
            logger.warning(f"🚫 DCA ORDER REJECTED: {position.symbol}")
            logger.warning(f"   Reason: {progressive_check['reason']}")
            logger.warning(f"   Message: {progressive_check['message']}")
            logger.warning(f"   Technical Level: ${dca_decision['level']:.2f}")
            logger.warning(f"   Proposed Price: ${order_price:.2f}")
            logger.warning(f"   Last DCA Price: ${progressive_check['last_price']:.2f}")
            logger.warning(f"   Required: Must be {progressive_check['required_direction']} last DCA")
            logger.warning(f"   Protection: Preventing non-progressive martingale DCA")
            return False
        
        logger.info(f"✅ PROGRESSIVE DCA VALIDATED: {position.symbol}")
        logger.info(f"   {progressive_check['message']}")
        
        # FINAL SAFETY CHECK: Validate DCA direction is correct
        if position.direction == PositionDirection.LONG:
            if order_price >= current_price:
                logger.error(f"🚨 FINAL SAFETY ABORT: {position.symbol}")
                logger.error(f"   Long DCA order ${order_price:.2f} >= current price ${current_price:.2f}")
                logger.error(f"   This violates DCA averaging down principle!")
                logger.error(f"   ABORTING ORDER to protect portfolio")
                return False
            if order_price >= position.average_price:
                logger.error(f"🚨 FINAL SAFETY ABORT: {position.symbol}")
                logger.error(f"   Long DCA order ${order_price:.2f} >= position avg ${position.average_price:.2f}")
                logger.error(f"   This would average UP instead of DOWN!")
                logger.error(f"   ABORTING ORDER to protect portfolio")
                return False
        else:  # SHORT position
            if order_price <= current_price:
                logger.error(f"🚨 FINAL SAFETY ABORT: {position.symbol}")
                logger.error(f"   Short DCA order ${order_price:.2f} <= current price ${current_price:.2f}")
                logger.error(f"   This violates DCA averaging up principle!")
                logger.error(f"   ABORTING ORDER to protect portfolio")
                return False
        
        logger.info(f"✅ FINAL SAFETY CHECK PASSED: {position.symbol} DCA order is safe")
        return True
    
    async def _run_martingale_safety_check(
        self,
        position: PositionState,
        new_quantity: float
    ) -> bool:
        """
        Run martingale safety validation against risk limits.
        
        Args:
            position: Current position state
            new_quantity: Proposed new quantity to add
            
        Returns:
            True if safe to proceed, False otherwise
        """
        current_price = position.current_price
        potential_loss = abs(
            position.quantity * position.average_price - 
            (position.quantity + new_quantity) * current_price
        )
        
        safety_check = await self.martingale_safety.check_safety(
            symbol=position.symbol,
            loss_amount=potential_loss,
            consecutive_losses=position.averaging_attempts
        )
        
        if not safety_check['safe']:
            logger.critical(f"🛑 MARTINGALE SAFETY TRIGGERED: {position.symbol}")
            logger.critical(f"   Reason: {safety_check['reason']}")
            logger.critical(f"   Details: {safety_check['details']}")
            logger.critical(f"   DCA ORDER REJECTED to protect account")
            logger.critical(f"   Current Loss: ${potential_loss:.2f}")
            logger.critical(f"   Consecutive DCA Attempts: {position.averaging_attempts}")
            logger.critical(f"   Protection: Martingale limits enforced")
            return False
        
        logger.info(f"✅ MARTINGALE SAFETY CHECK PASSED: {position.symbol}")
        logger.info(f"   Safety details: {safety_check['details']}")
        return True
    
    async def _place_dca_order_and_track(
        self,
        position: PositionState,
        dca_decision: dict,
        order_price: Optional[float],
        order_side: OrderSide,
        new_quantity: float
    ) -> bool:
        """
        Place the DCA order and update tracking state.
        
        Args:
            position: Current position state
            dca_decision: DCA decision dict with 'level', 'reason', 'confidence', 'timeframe'
            order_price: Order price (None for market orders)
            order_side: Order side (BUY or SELL)
            new_quantity: Quantity to order
            
        Returns:
            True if order placed successfully, False otherwise
        """
        config = self.long_config if position.direction == PositionDirection.LONG else self.short_config
        order_type = self._get_order_type()
        max_attempts = self._get_max_averaging_attempts()
        
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
        
        # Track active order
        position.active_orders.append(order_id)
        
        # Track DCA order price for progressive validation
        if order_price is not None:
            position.last_dca_price = order_price
            position.dca_order_prices.append(order_price)
            logger.info(f"📊 DCA PRICE TRACKING: {position.symbol}")
            logger.info(f"   Order Price: ${order_price:.2f}")
            logger.info(f"   DCA History: {[f'${p:.2f}' for p in position.dca_order_prices]}")
            
            # Save DCA metadata to prevent order history pollution
            if self.dca_metadata_manager:
                try:
                    await self.dca_metadata_manager.save_metadata(
                        symbol=position.symbol,
                        attempts=position.averaging_attempts,
                        prices=position.dca_order_prices,
                        last_price=position.last_dca_price
                    )
                except Exception as e:
                    logger.warning(f"Failed to save DCA metadata: {e}")
        
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
        
        return True
    
    async def execute_technical_dca(
        self,
        position: PositionState,
        dca_decision: dict,
        calculate_position_size_callback
    ) -> bool:
        """
        Execute DCA order based on technical analysis decision with progressive price enforcement.
        
        Orchestrates the DCA execution workflow:
        1. Check for pending DCA orders
        2. Validate progressive price movement
        3. Calculate DCA quantity and order price
        4. Validate price safety
        5. Run martingale safety checks
        6. Place order and update tracking
        
        Args:
            position: Current position state
            dca_decision: DCA decision dict from check_support/resistance_breach_dca
            calculate_position_size_callback: Callback function to calculate new position size
            
        Returns:
            True if DCA order placed successfully, False otherwise
        """
        try:
            # Step 1: Check for existing pending DCA orders
            if not await self._check_pending_dca_orders(position):
                return False
            
            # Step 2: Validate progressive price movement from last DCA
            if not self._check_progressive_price_movement(position):
                return False
            
            # Log validation passed
            min_price_improvement = self._calculate_progressive_dca_threshold(position)
            logger.info(f"✅ DCA VALIDATION PASSED: {position.symbol}")
            logger.info(f"   No pending DCA orders found")
            if position.last_dca_price:
                improvement_percent = abs((position.current_price - position.last_dca_price) / position.last_dca_price) * 100
                logger.info(f"   Price movement: {improvement_percent:.2f}% (min required: {min_price_improvement*100:.1f}%)")
            
            # Step 3: Calculate DCA quantity and order price
            new_quantity = await calculate_position_size_callback(
                position, 
                position.current_price, 
                position.direction == PositionDirection.LONG
            )
            order_price, order_side = self._calculate_dca_order_price(position, dca_decision)
            
            # Step 4: Validate price safety (progressive and final safety checks)
            if not self._validate_dca_price_safety(position, order_price, dca_decision):
                return False
            
            # Step 5: Run martingale safety checks
            if not await self._run_martingale_safety_check(position, new_quantity):
                return False
            
            # Step 6: Place order and update tracking
            return await self._place_dca_order_and_track(
                position, dca_decision, order_price, order_side, new_quantity
            )
            
        except Exception as e:
            logger.error(f"Error executing technical DCA for {position.symbol}: {e}")
            return False
    
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
            # Get DCA thresholds from bot-specific config (database) or global config file
            base_threshold, multiplier, max_threshold = self._get_dca_thresholds()
            
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

    # =========================================================================
    # IDCAPlanner Interface Implementation
    # =========================================================================
    
    async def check_dca_opportunity(
        self,
        position: PositionStateType,
        current_price: float,
        timeframe: str = "15m"
    ) -> Dict[str, Any]:
        """
        Check if DCA should be executed for the given position.
        
        Implements IDCAPlanner.check_dca_opportunity by delegating to
        the internal martingale DCA check logic.
        
        Args:
            position: Current position state
            current_price: Current market price
            timeframe: Signal timeframe for context
            
        Returns:
            Dictionary with keys: should_dca, reason, level, confidence, message
        """
        # Update position's current price for accuracy
        position.current_price = current_price
        
        # Determine position direction and delegate to martingale check
        is_long = position.direction == PositionDirection.LONG
        return self._check_martingale_dca(position, is_long)
    
    def is_progressive_price(
        self,
        position: PositionStateType,
        proposed_price: float
    ) -> Dict[str, Any]:
        """
        Validate that the proposed DCA price improves the average.
        
        Implements IDCAPlanner.is_progressive_price by delegating to
        the internal progressive price validation.
        
        For LONG: new price must be BELOW last DCA (averaging down)
        For SHORT: new price must be ABOVE last DCA (averaging up)
        
        Args:
            position: Current position state
            proposed_price: Proposed DCA order price
            
        Returns:
            Dictionary with keys: is_progressive, reason, message, last_price
        """
        return self.is_progressive_dca_price(position, proposed_price)
    
    async def execute_dca(
        self,
        position: PositionStateType,
        dca_decision: Dict[str, Any],
        calculate_size_callback: Callable
    ) -> bool:
        """
        Execute a DCA order based on the decision.
        
        Implements IDCAPlanner.execute_dca by delegating to
        the internal technical DCA execution logic.
        
        Args:
            position: Current position state
            dca_decision: DCA decision from check_dca_opportunity
            calculate_size_callback: Callback to calculate position size
            
        Returns:
            True if DCA order was placed successfully
        """
        return await self.execute_technical_dca(
            position, 
            dca_decision, 
            calculate_size_callback
        )
