"""
Position Adjustment Planner

Handles DCA execution planning, order size calculation, 
Martingale safety checks, and Kelly criterion sizing.
"""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from src.strategies.config_accessor import StrategyConfigAccessor
from src.interfaces import IConfigurationManager, IRiskManager
from src.risk.martingale_validator import MartingaleSafetyManager

logger = logging.getLogger(__name__)


@dataclass
class AdjustmentPlan:
    """Plan for position adjustment (DCA)."""
    approved: bool
    reason: str
    order_size: Optional[float] = None
    entry_price: Optional[float] = None
    safety_details: Optional[Dict[str, Any]] = None
    risk_details: Optional[Dict[str, Any]] = None


class PositionAdjustmentPlanner:
    """
    Plans position size adjustments (DCA orders).
    
    Integrates risk management, Martingale safety, and Kelly sizing
    to determine safe DCA order parameters.
    """
    
    def __init__(
        self,
        config: IConfigurationManager,
        risk_manager: IRiskManager,
        martingale_safety: MartingaleSafetyManager
    ):
        """
        Initialize position adjustment planner.
        
        Args:
            config: Configuration manager
            risk_manager: Risk manager interface
            martingale_safety: Martingale safety validator
        """
        self.config = config
        self.config_accessor = StrategyConfigAccessor(config)
        self.risk_manager = risk_manager
        self.martingale_safety = martingale_safety
        logger.info("PositionAdjustmentPlanner initialized")
    
    async def plan_dca_order(
        self,
        symbol: str,
        current_price: float,
        position_average: float,
        position_quantity: float,
        averaging_attempts: int,
        direction: str,
        signal=None
    ) -> AdjustmentPlan:
        """
        Plan a DCA order with safety checks.
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            position_average: Current position average price
            position_quantity: Current position size
            averaging_attempts: Number of previous DCA attempts
            direction: Position direction ('long' or 'short')
            signal: Optional trading signal for risk calculation
            
        Returns:
            AdjustmentPlan with order parameters or rejection
        """
        try:
            # Check max attempts
            max_attempts = self.config_accessor.get_max_dca_attempts(direction)
            
            if averaging_attempts >= max_attempts:
                return AdjustmentPlan(
                    approved=False,
                    reason='max_attempts_reached',
                    safety_details={
                        'attempts': averaging_attempts,
                        'max_attempts': max_attempts
                    }
                )
            
            # Calculate potential loss for Martingale check
            unrealized_pnl = self._calculate_unrealized_pnl(
                position_average, current_price, position_quantity, direction
            )
            
            # Martingale safety check
            safety_check = await self.martingale_safety.check_safety(
                symbol=symbol,
                loss_amount=abs(unrealized_pnl),
                consecutive_losses=averaging_attempts
            )
            
            if not safety_check['safe']:
                logger.critical(
                    f"🛑 MARTINGALE SAFETY: {symbol} - {safety_check['reason']}"
                )
                return AdjustmentPlan(
                    approved=False,
                    reason='martingale_safety_block',
                    safety_details=safety_check
                )
            
            # Calculate DCA order size
            order_size = await self.risk_manager.calculate_position_size(
                symbol=symbol,
                signal=signal,
                averaging_attempt=averaging_attempts + 1
            )
            
            if order_size <= 0:
                return AdjustmentPlan(
                    approved=False,
                    reason='insufficient_funds',
                    risk_details={'calculated_size': order_size}
                )
            
            logger.info(
                f"✅ DCA PLAN APPROVED: {symbol} - {order_size} shares @ ${current_price:.2f}"
            )
            
            return AdjustmentPlan(
                approved=True,
                reason='safety_checks_passed',
                order_size=order_size,
                entry_price=current_price,
                safety_details=safety_check,
                risk_details={'order_size': order_size}
            )
            
        except Exception as e:
            logger.error(f"Error planning DCA order for {symbol}: {e}")
            return AdjustmentPlan(
                approved=False,
                reason='planning_error',
                risk_details={'error': str(e)}
            )
    
    def _calculate_unrealized_pnl(
        self,
        average_price: float,
        current_price: float,
        quantity: float,
        direction: str
    ) -> float:
        """
        Calculate unrealized P&L.
        
        Args:
            average_price: Position average price
            current_price: Current market price
            quantity: Position size
            direction: Position direction
            
        Returns:
            Unrealized P&L (negative if losing)
        """
        if direction.lower() == 'long':
            return (current_price - average_price) * quantity
        else:
            return (average_price - current_price) * quantity
