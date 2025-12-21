"""
Unified Position Sizing Service

Centralizes all position sizing logic to eliminate duplication between
DCA and initial entry paths. Single source of truth for size calculation.
"""

import logging
from dataclasses import dataclass
from typing import Optional, List
from src.domain import DecisionContext
from src.domain.errors import DomainError, ErrorCode
from src.risk.risk_envelope_calculator import RiskEnvelopeCalculator
from src.risk.portfolio_exposure_validator import PortfolioExposureValidator
from src.strategies.config_accessor import StrategyConfigAccessor
from src.interfaces import IConfigurationManager

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SizingResult:
    """
    Result of position sizing calculation.
    
    Provides transparency into sizing decisions with original request,
    effective approved size, and detailed reasoning.
    """
    requested: float
    effective: float
    capped: bool
    approved: bool
    reasons: List[str]
    risk_details: dict
    
    @property
    def cap_percentage(self) -> float:
        """Calculate percentage of request that was capped."""
        if self.requested > 0:
            return ((self.requested - self.effective) / self.requested) * 100.0
        return 0.0


class SizingService:
    """
    Unified position sizing service.
    
    Centralizes all sizing logic through risk envelope evaluation,
    providing consistent sizing across entry and DCA operations.
    
    Example:
        service = SizingService(config, risk_calculator)
        
        result = await service.compute(
            context=decision_context,
            proposed_size=5000.0,
            account_balance=50000.0
        )
        
        if result.approved:
            execute_order(size=result.effective)
        else:
            logger.warning(f"Sizing rejected: {result.reasons}")
    """
    
    def __init__(
        self,
        config: IConfigurationManager,
        risk_calculator: RiskEnvelopeCalculator,
        portfolio_exposure_validator: Optional[PortfolioExposureValidator] = None
    ):
        """
        Initialize sizing service.
        
        Args:
            config: Configuration manager
            risk_calculator: Risk envelope calculator
            portfolio_exposure_validator: Optional portfolio exposure validator for scaling
        """
        self.config = config
        self.config_accessor = StrategyConfigAccessor(config)
        self.risk_calculator = risk_calculator
        self.portfolio_exposure_validator = portfolio_exposure_validator
        logger.info(
            f"SizingService initialized "
            f"(portfolio_scaling_enabled={portfolio_exposure_validator is not None})"
        )
    
    async def compute(
        self,
        context: DecisionContext,
        proposed_size: float,
        account_balance: float,
        is_dca: bool = False
    ) -> SizingResult:
        """
        Compute effective position size with risk validation.
        
        Args:
            context: Decision context with position/market state
            proposed_size: Proposed position size (dollars)
            account_balance: Current account balance
            is_dca: Whether this is a DCA order (affects multipliers)
            
        Returns:
            SizingResult with approved size and reasoning
        """
        try:
            logger.info(
                f"Computing size: symbol={context.symbol}, "
                f"proposed=${proposed_size:.2f}, balance=${account_balance:.2f}, "
                f"is_dca={is_dca}"
            )
            
            # Validate proposed size
            if proposed_size <= 0:
                return SizingResult(
                    requested=proposed_size,
                    effective=0.0,
                    capped=False,
                    approved=False,
                    reasons=["Invalid proposed size: must be > 0"],
                    risk_details={'proposed_size': proposed_size}
                )
            
            # Apply DCA multiplier if applicable
            if is_dca:
                # Infer direction from context
                direction = 'long' if context.position_direction == 'LONG' else 'short'
                dca_multiplier = self.config_accessor.get_dca_multiplier(direction)
                adjusted_size = proposed_size * dca_multiplier
                
                logger.info(
                    f"DCA multiplier applied: {proposed_size:.2f} × {dca_multiplier} = {adjusted_size:.2f}"
                )
            else:
                adjusted_size = proposed_size
            
            # Evaluate through risk envelope
            envelope = await self.risk_calculator.calculate(
                context=context,
                proposed_size=adjusted_size,
                account_balance=account_balance
            )
            
            # Apply portfolio exposure scaling if validator is available
            portfolio_scaling_factor = 1.0
            portfolio_scaling_reasons = []
            
            if self.portfolio_exposure_validator:
                try:
                    # Get current positions from context (if available)
                    current_positions = getattr(context, 'current_positions', {})
                    
                    exposure_result = await self.portfolio_exposure_validator.validate_new_position(
                        symbol=context.symbol,
                        position_value=envelope.effective_limit,
                        current_positions=current_positions,
                        account_value=account_balance
                    )
                    
                    if not exposure_result.approved:
                        # Portfolio exposure denied
                        return SizingResult(
                            requested=proposed_size,
                            effective=0.0,
                            capped=False,
                            approved=False,
                            reasons=exposure_result.reasons,
                            risk_details={
                                'envelope_safe': envelope.safe,
                                'portfolio_scaling_factor': 0.0,
                                'portfolio_denied': True
                            }
                        )
                    
                    portfolio_scaling_factor = exposure_result.scaling_factor
                    portfolio_scaling_reasons = exposure_result.reasons
                    
                    if portfolio_scaling_factor < 1.0:
                        logger.info(
                            f"📊 Portfolio scaling applied: {portfolio_scaling_factor:.2%}",
                            extra={
                                "component": "SizingService",
                                "symbol": context.symbol,
                                "scaling_factor": portfolio_scaling_factor,
                                "reasons": portfolio_scaling_reasons
                            }
                        )
                    
                except Exception as e:
                    logger.error(
                        f"Portfolio exposure validation failed: {e}",
                        exc_info=True
                    )
                    # Continue without portfolio scaling on error
            
            # Apply portfolio scaling to effective limit
            final_effective_size = envelope.effective_limit * portfolio_scaling_factor
            
            # Determine approval
            approved = envelope.safe and final_effective_size > 0
            capped = final_effective_size < adjusted_size
            
            reasons = []
            
            if not envelope.safe:
                reasons.append(f"Risk check failed: {envelope.primary_constraint.value}")
                for code in envelope.reason_codes:
                    if code != envelope.primary_constraint:
                        reasons.append(f"  - {code.value}")
            
            if portfolio_scaling_factor < 1.0:
                # Add portfolio scaling reasons
                reasons.extend(portfolio_scaling_reasons)
            
            if capped:
                cap_pct = ((adjusted_size - final_effective_size) / adjusted_size) * 100
                reasons.append(
                    f"Size capped: ${adjusted_size:.2f} → ${final_effective_size:.2f} "
                    f"({cap_pct:.1f}% reduction)"
                )
            
            if approved and not reasons:
                reasons.append("All risk checks passed")
            
            result = SizingResult(
                requested=proposed_size,
                effective=final_effective_size,
                capped=capped,
                approved=approved,
                reasons=reasons,
                risk_details={
                    'envelope_safe': envelope.safe,
                    'primary_constraint': envelope.primary_constraint.value,
                    'max_position_size': envelope.max_position_size,
                    'dynamic_ceiling': envelope.dynamic_ceiling,
                    'dca_multiplier': dca_multiplier if is_dca else 1.0,
                    'portfolio_scaling_factor': portfolio_scaling_factor
                }
            )
            
            logger.info(
                f"Sizing result: approved={approved}, "
                f"effective=${result.effective:.2f}, "
                f"capped={capped}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error computing size for {context.symbol}: {e}", exc_info=True)
            
            raise DomainError(
                code=ErrorCode.VALIDATION_FAILED,
                detail=f"Position sizing failed: {str(e)}",
                context={
                    'symbol': context.symbol,
                    'proposed_size': proposed_size,
                    'is_dca': is_dca
                },
                cause=e
            )
    
    async def compute_initial_entry(
        self,
        context: DecisionContext,
        account_balance: float
    ) -> SizingResult:
        """
        Compute size for initial position entry.
        
        Uses default position sizing from configuration.
        
        Args:
            context: Decision context
            account_balance: Current account balance
            
        Returns:
            SizingResult for initial entry
        """
        default_size = self.config.get(
            'strategies.position_sizing.default_size', 1000.0
        )
        
        return await self.compute(
            context=context,
            proposed_size=default_size,
            account_balance=account_balance,
            is_dca=False
        )
    
    async def compute_dca_size(
        self,
        context: DecisionContext,
        base_size: float,
        account_balance: float
    ) -> SizingResult:
        """
        Compute size for DCA order.
        
        Applies DCA multiplier and progressive sizing logic.
        
        Args:
            context: Decision context
            base_size: Base position size to multiply
            account_balance: Current account balance
            
        Returns:
            SizingResult for DCA order
        """
        return await self.compute(
            context=context,
            proposed_size=base_size,
            account_balance=account_balance,
            is_dca=True
        )
