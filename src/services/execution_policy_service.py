"""
Execution Policy Service

Encapsulates policy decisions for trade execution, including:
- Profit-taking execution policy
- Aggressive order management policy
- Order timeout and price adjustment rules

Extracted from TradingBotOrchestrator to follow Single Responsibility Principle.
The orchestrator should focus on lifecycle + wiring, not policy decisions.

SOLID Compliance:
- SRP: Single responsibility for execution policy decisions
- OCP: Extensible for new execution policies via strategy pattern
- LSP: N/A (no inheritance hierarchy)
- ISP: Focused interface for execution policy only
- DIP: Depends on abstractions (interfaces) not concretions

Thread Safety: Async-safe (stateless policy methods)

Author: Trading Bot Team
Version: 1.1.0 - Uses canonical interfaces from src.interfaces and src.broker.interfaces
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any, Protocol, Callable, Awaitable

from src import Order, OrderType, OrderSide, Position
from src.interfaces import (
    IConfigurationManager, 
    IOrderManager, 
    IPositionManager,
    IMarketDataProvider,
    ITrailingManager,
)
from src.broker.interfaces import IBrokerAccountProvider
from src.trading.exit_planner import ExitPlanner

logger = logging.getLogger(__name__)


# ============================================================================
# Data Classes for Policy Results
# ============================================================================

@dataclass(frozen=True)
class ProfitTakingDecision:
    """
    Result of profit-taking policy evaluation.
    
    Attributes:
        should_execute: Whether to proceed with profit-taking
        action_type: Type of action ("profit_taking" or "stop_loss")
        exit_quantity: Quantity to exit
        reason: Human-readable reason for decision
        skip_reason: If should_execute is False, why we're skipping
    """
    should_execute: bool
    action_type: str
    exit_quantity: float
    reason: str
    skip_reason: Optional[str] = None


@dataclass(frozen=True)
class OrderAdjustmentDecision:
    """
    Result of aggressive order adjustment policy evaluation.
    
    Attributes:
        should_adjust: Whether to adjust the order
        reason: Reason for adjustment decision
        new_price: Suggested new price (if should_adjust is True)
    """
    should_adjust: bool
    reason: str
    new_price: Optional[float] = None


# ============================================================================
# Execution Policy Service
# ============================================================================

class ExecutionPolicyService:
    """
    Service for making execution policy decisions.
    
    This service encapsulates the "what to do" decisions:
    - Should we execute profit-taking?
    - Should we adjust an unfilled order?
    - What quantity should we trade?
    
    The actual execution is delegated back to the orchestrator/order manager.
    This separation allows policy logic to be tested independently.
    
    Usage:
        policy_service = ExecutionPolicyService(
            config=config,
            exit_planner=exit_planner
        )
        
        # Evaluate profit-taking
        decision = await policy_service.evaluate_profit_taking(
            position=position,
            current_price=100.0,
            broker_position_qty=100.0,
            open_orders=open_orders
        )
        
        if decision.should_execute:
            # Proceed with execution
            pass
    """
    
    def __init__(
        self,
        config: IConfigurationManager,
        exit_planner: ExitPlanner,
    ):
        """
        Initialize ExecutionPolicyService.
        
        Args:
            config: Configuration provider for policy thresholds
            exit_planner: Exit order planning service
        """
        self._config = config
        self._exit_planner = exit_planner
        logger.debug("ExecutionPolicyService initialized")
    
    # ========================================================================
    # Profit-Taking Policy
    # ========================================================================
    
    async def evaluate_profit_taking(
        self,
        position: Position,
        current_price: float,
        broker_position_qty: Optional[float],
        open_orders: List[Order],
    ) -> ProfitTakingDecision:
        """
        Evaluate whether to execute profit-taking for a position.
        
        This method encapsulates all the policy decisions for profit-taking:
        1. Position verification with broker
        2. Direction validation
        3. Available quantity calculation
        4. Final safety checks
        
        Args:
            position: Database position to evaluate
            current_price: Current market price
            broker_position_qty: Actual position from broker (None if unavailable)
            open_orders: List of open orders for pending quantity calculation
            
        Returns:
            ProfitTakingDecision with policy outcome
        """
        # Step 1: Verify broker position is available
        if broker_position_qty is None:
            return ProfitTakingDecision(
                should_execute=False,
                action_type="",
                exit_quantity=0.0,
                reason="",
                skip_reason="Could not verify actual position with broker"
            )
        
        # Step 2: Handle externally closed position
        if broker_position_qty == 0:
            return ProfitTakingDecision(
                should_execute=False,
                action_type="external_close",
                exit_quantity=0.0,
                reason="Position closed externally",
                skip_reason="Position already closed at broker (needs reconciliation)"
            )
        
        # Step 3: Validate position direction matches
        direction_valid, direction_error = self._validate_position_direction(
            position, broker_position_qty
        )
        if not direction_valid:
            return ProfitTakingDecision(
                should_execute=False,
                action_type="",
                exit_quantity=0.0,
                reason="",
                skip_reason=direction_error
            )
        
        # Step 4: Calculate pending quantity from open orders
        pending_qty = self._calculate_pending_quantity(position, open_orders)
        
        # Step 5: Validate exit quantity
        available_qty, is_valid = self._exit_planner.validate_exit_quantity(
            requested_qty=abs(position.quantity),
            position_qty=position.quantity,
            pending_qty=pending_qty
        )
        
        if not is_valid or available_qty <= 0:
            return ProfitTakingDecision(
                should_execute=False,
                action_type="",
                exit_quantity=0.0,
                reason="",
                skip_reason="No available quantity - pending orders cover position"
            )
        
        # Step 6: Final safety check - don't exit more than broker has
        max_available = abs(broker_position_qty)
        if available_qty > max_available:
            logger.warning(
                f"Quantity adjustment: Reducing from {available_qty} to {max_available}"
            )
            available_qty = max_available
        
        if available_qty <= 0:
            return ProfitTakingDecision(
                should_execute=False,
                action_type="",
                exit_quantity=0.0,
                reason="",
                skip_reason="No quantity to close after adjustment"
            )
        
        # Step 7: Determine action type (profit vs stop-loss)
        action_type = self._determine_action_type(position, current_price)
        
        return ProfitTakingDecision(
            should_execute=True,
            action_type=action_type,
            exit_quantity=available_qty,
            reason=f"{action_type.replace('_', ' ').title()} triggered"
        )
    
    def _validate_position_direction(
        self, 
        position: Position, 
        broker_position_qty: float
    ) -> tuple[bool, Optional[str]]:
        """
        Validate that database and broker position directions match.
        
        Args:
            position: Database position
            broker_position_qty: Actual position from broker
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        db_sign = 1 if position.quantity > 0 else -1
        broker_sign = 1 if broker_position_qty > 0 else -1
        
        if db_sign != broker_sign:
            db_direction = "LONG" if position.quantity > 0 else "SHORT"
            broker_direction = "LONG" if broker_position_qty > 0 else "SHORT"
            error = (
                f"Position direction mismatch for {position.symbol}: "
                f"Database={db_direction} ({position.quantity}), "
                f"Broker={broker_direction} ({broker_position_qty}). "
                f"Manual intervention required."
            )
            return False, error
        
        return True, None
    
    def _calculate_pending_quantity(
        self, 
        position: Position, 
        open_orders: List[Order]
    ) -> float:
        """
        Calculate pending quantity for a position from open orders.
        
        Args:
            position: Position to check
            open_orders: List of open orders
            
        Returns:
            Pending quantity in the exit direction
        """
        pending_sell_qty = 0.0
        pending_buy_qty = 0.0
        
        for order in open_orders:
            if order.symbol == position.symbol:
                if order.side == OrderSide.SELL:
                    pending_sell_qty += order.quantity
                elif order.side == OrderSide.BUY:
                    pending_buy_qty += order.quantity
        
        # Return pending quantity in the exit direction
        if position.quantity > 0:  # Long position exits via sell
            return pending_sell_qty
        else:  # Short position exits via buy
            return pending_buy_qty
    
    def _determine_action_type(self, position: Position, current_price: float) -> str:
        """
        Determine if this is profit-taking or stop-loss.
        
        Args:
            position: Position being closed
            current_price: Current market price
            
        Returns:
            "profit_taking" or "stop_loss"
        """
        if position.quantity > 0:  # Long position
            profit_pct = (current_price - position.avg_price) / position.avg_price * 100
        else:  # Short position
            profit_pct = (position.avg_price - current_price) / position.avg_price * 100
        
        return "profit_taking" if profit_pct >= 0 else "stop_loss"
    
    # ========================================================================
    # Aggressive Order Management Policy
    # ========================================================================
    
    def evaluate_order_adjustment(
        self,
        order: Order,
        current_price: float,
        order_age_minutes: Optional[float],
    ) -> OrderAdjustmentDecision:
        """
        Evaluate whether to aggressively adjust an unfilled order.
        
        Policy rules:
        1. Skip market orders (should fill immediately)
        2. Skip very new orders (< 2 minutes)
        3. Adjust if order exceeds timeout threshold
        4. Adjust if price gap is significant (> 1%)
        
        Args:
            order: The unfilled order to evaluate
            current_price: Current market price
            order_age_minutes: Order age in minutes (None if unknown)
            
        Returns:
            OrderAdjustmentDecision with policy outcome
        """
        # Skip market orders
        if order.order_type != OrderType.LIMIT:
            return OrderAdjustmentDecision(
                should_adjust=False,
                reason="Market orders should fill immediately"
            )
        
        # Skip very new orders (give them a chance)
        if order_age_minutes is None or order_age_minutes < 2:
            return OrderAdjustmentDecision(
                should_adjust=False,
                reason="Order too new (< 2 minutes)"
            )
        
        # Get policy thresholds from config
        aggressive_timeout = self._config.get_config(
            "trading.aggressive_order_timeout_minutes", 5
        )
        max_adjustment_pct = self._config.get_config(
            "trading.max_price_adjustment_percent", 0.3
        )
        
        # Calculate price gap
        price_diff = abs(order.price - current_price)
        price_diff_pct = (price_diff / current_price) * 100
        
        # Decision logic
        should_adjust = False
        reason = ""
        
        if order_age_minutes >= aggressive_timeout:
            should_adjust = True
            reason = f"Order timeout ({order_age_minutes:.1f} min >= {aggressive_timeout} min)"
        elif price_diff_pct > 1.0:
            should_adjust = True
            reason = f"Price gap too large ({price_diff_pct:.1f}% > 1.0%)"
        
        if should_adjust:
            # Calculate new price
            new_price = self._calculate_adjusted_price(
                order, current_price, max_adjustment_pct
            )
            return OrderAdjustmentDecision(
                should_adjust=True,
                reason=reason,
                new_price=new_price
            )
        
        return OrderAdjustmentDecision(
            should_adjust=False,
            reason="Order within normal parameters"
        )
    
    def _calculate_adjusted_price(
        self,
        order: Order,
        current_price: float,
        max_adjustment_pct: float
    ) -> float:
        """
        Calculate adjusted price toward market.
        
        Args:
            order: Order to adjust
            current_price: Current market price
            max_adjustment_pct: Maximum adjustment percentage
            
        Returns:
            Adjusted price
        """
        # Move order price toward market price
        price_diff = current_price - order.price
        max_adjustment = order.price * (max_adjustment_pct / 100)
        
        if abs(price_diff) <= max_adjustment:
            # Price is within max adjustment, use market price
            return current_price
        else:
            # Adjust by max amount toward market
            if price_diff > 0:
                return order.price + max_adjustment
            else:
                return order.price - max_adjustment
    
    # ========================================================================
    # Order Monitoring Interval Policy
    # ========================================================================
    
    def get_order_monitoring_interval(self) -> float:
        """
        Get the configured order monitoring interval.
        
        Returns:
            Interval in seconds
        """
        return self._config.get_config("monitoring.order_monitoring_interval", 5)
    
    def get_position_monitoring_interval(self) -> float:
        """
        Get the configured position monitoring interval.
        
        Returns:
            Interval in seconds
        """
        return self._config.get_config("monitoring.position_monitoring_interval", 30)


# ============================================================================
# Factory Function
# ============================================================================

def create_execution_policy_service(
    config: IConfigurationManager,
    exit_planner: ExitPlanner,
) -> ExecutionPolicyService:
    """
    Factory function to create ExecutionPolicyService.
    
    Args:
        config: Configuration provider
        exit_planner: Exit planning service
        
    Returns:
        Configured ExecutionPolicyService instance
    """
    return ExecutionPolicyService(
        config=config,
        exit_planner=exit_planner,
    )
