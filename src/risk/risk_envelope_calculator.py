"""
Unified Risk Envelope Calculator

Consolidates multiple risk validators (Martingale, Kelly, Fibonacci)
into a single cohesive risk assessment system.
"""

import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from abc import ABC, abstractmethod

from src.domain import RiskDecision, RiskDecisionStatus, RiskEnvelope
from src.domain import DecisionContext

logger = logging.getLogger(__name__)


class IRiskValidator(ABC):
    """
    Abstract base class for risk validators.
    
    Each validator assesses one aspect of risk and returns a decision.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Validator name for logging."""
        pass
    
    @abstractmethod
    async def validate(
        self, 
        context: DecisionContext,
        proposed_size: float,
        account_balance: float
    ) -> RiskDecision:
        """
        Validate proposed position size against risk constraints.
        
        Args:
            context: Decision context
            proposed_size: Proposed position size (dollars)
            account_balance: Current account balance
            
        Returns:
            RiskDecision with safe/unsafe determination
        """
        pass


class ConsecutiveLossValidator(IRiskValidator):
    """Validates against consecutive loss limits."""
    
    def __init__(self, max_consecutive_losses: int = 5):
        self.max_consecutive_losses = max_consecutive_losses
    
    @property
    def name(self) -> str:
        return "ConsecutiveLossValidator"
    
    async def validate(
        self,
        context: DecisionContext,
        proposed_size: float,
        account_balance: float
    ) -> RiskDecision:
        """Check consecutive loss limit."""
        is_ok = context.dca_attempts < self.max_consecutive_losses
        reason = RiskEnvelopeCalculator.format_limit_state(
            current=context.dca_attempts,
            cap=self.max_consecutive_losses,
            label="Consecutive losses",
            is_ok=is_ok
        )
        
        if not is_ok:
            return RiskDecision.deny(
                status=RiskDecisionStatus.CONSECUTIVE_LOSS_LIMIT,
                reason=reason,
                details={
                    'dca_attempts': context.dca_attempts,
                    'max_allowed': self.max_consecutive_losses,
                    'symbol': context.symbol
                }
            )
        
        return RiskDecision.allow(
            reason=reason,
            details={'dca_attempts': context.dca_attempts}
        )


class SymbolLossLimitValidator(IRiskValidator):
    """Validates against per-symbol loss limits."""
    
    def __init__(self, max_symbol_loss_pct: float = 0.25):
        self.max_symbol_loss_pct = max_symbol_loss_pct
    
    @property
    def name(self) -> str:
        return "SymbolLossLimitValidator"
    
    async def validate(
        self,
        context: DecisionContext,
        proposed_size: float,
        account_balance: float
    ) -> RiskDecision:
        """Check per-symbol loss limit."""
        max_loss = account_balance * self.max_symbol_loss_pct
        current_loss = abs(context.unrealized_pnl)
        is_ok = current_loss < max_loss
        
        reason = "$" + RiskEnvelopeCalculator.format_limit_state(
            current=current_loss,
            cap=max_loss,
            label="Symbol loss",
            is_ok=is_ok
        )
        
        if not is_ok:
            return RiskDecision.deny(
                status=RiskDecisionStatus.SYMBOL_LOSS_LIMIT,
                reason=reason,
                details={
                    'unrealized_pnl': context.unrealized_pnl,
                    'max_loss': max_loss,
                    'symbol': context.symbol,
                    'account_balance': account_balance
                }
            )
        
        return RiskDecision.allow(
            reason=reason,
            details={'unrealized_pnl': context.unrealized_pnl, 'max_loss': max_loss}
        )


class IndividualLossLimitValidator(IRiskValidator):
    """Validates against individual trade loss limits."""
    
    def __init__(self, max_individual_loss_pct: float = 0.10):
        self.max_individual_loss_pct = max_individual_loss_pct
    
    @property
    def name(self) -> str:
        return "IndividualLossLimitValidator"
    
    async def validate(
        self,
        context: DecisionContext,
        proposed_size: float,
        account_balance: float
    ) -> RiskDecision:
        """Check individual trade loss limit."""
        max_loss = account_balance * self.max_individual_loss_pct
        is_ok = proposed_size <= max_loss
        
        reason = "$" + RiskEnvelopeCalculator.format_limit_state(
            current=proposed_size,
            cap=max_loss,
            label="Individual trade size",
            is_ok=is_ok
        )
        
        if not is_ok:
            return RiskDecision.deny(
                status=RiskDecisionStatus.INDIVIDUAL_LOSS_LIMIT,
                reason=reason,
                details={
                    'proposed_size': proposed_size,
                    'max_loss': max_loss,
                    'account_balance': account_balance
                }
            )
        
        return RiskDecision.allow(
            reason=reason,
            details={'proposed_size': proposed_size, 'max_loss': max_loss}
        )


class VolatilityValidator(IRiskValidator):
    """Validates against volatility thresholds."""
    
    def __init__(self, max_volatility: float = 0.05):
        self.max_volatility = max_volatility
    
    @property
    def name(self) -> str:
        return "VolatilityValidator"
    
    async def validate(
        self,
        context: DecisionContext,
        proposed_size: float,
        account_balance: float
    ) -> RiskDecision:
        """Check volatility threshold."""
        if context.volatility > self.max_volatility:
            return RiskDecision.deny(
                status=RiskDecisionStatus.VOLATILITY_TOO_HIGH,
                reason=f"Volatility too high: {context.volatility:.2%} > {self.max_volatility:.2%}",
                details={
                    'volatility': context.volatility,
                    'max_volatility': self.max_volatility,
                    'symbol': context.symbol
                }
            )
        
        return RiskDecision.allow(
            reason=f"Volatility acceptable: {context.volatility:.2%}",
            details={'volatility': context.volatility}
        )


class KellyCriterionSizer(IRiskValidator):
    """
    Kelly Criterion position sizing.
    
    Calculates optimal position size based on win probability and payoff ratio.
    """
    
    def __init__(self, safety_factor: float = 0.25):
        """
        Initialize Kelly sizer.
        
        Args:
            safety_factor: Fraction of Kelly to use (0.25 = quarter Kelly)
        """
        self.safety_factor = safety_factor
    
    @property
    def name(self) -> str:
        return "KellyCriterionSizer"
    
    def calculate_kelly_fraction(
        self,
        win_probability: float,
        win_loss_ratio: float
    ) -> float:
        """
        Calculate Kelly fraction.
        
        Formula: f* = (p * b - q) / b
        where:
          p = win probability
          q = loss probability (1 - p)
          b = win/loss ratio
        """
        if win_probability <= 0 or win_probability >= 1:
            return 0.0
        
        q = 1 - win_probability
        kelly = (win_probability * win_loss_ratio - q) / win_loss_ratio
        
        return max(0.0, kelly)
    
    async def validate(
        self,
        context: DecisionContext,
        proposed_size: float,
        account_balance: float
    ) -> RiskDecision:
        """
        Calculate Kelly-optimal position size.
        
        Returns recommended size rather than deny/allow.
        """
        # Estimate win probability based on confidence (if available)
        # Default to conservative 50%
        win_probability = 0.50
        win_loss_ratio = 1.5  # Default 1.5:1 reward/risk
        
        kelly_fraction = self.calculate_kelly_fraction(win_probability, win_loss_ratio)
        safe_fraction = kelly_fraction * self.safety_factor
        
        recommended_size = account_balance * safe_fraction
        
        if proposed_size > recommended_size * 1.5:
            # Proposed size significantly exceeds Kelly recommendation
            return RiskDecision(
                status=RiskDecisionStatus.POSITION_SIZE_LIMIT,
                safe=False,
                reason=f"Proposed size ${proposed_size:.2f} exceeds Kelly recommendation ${recommended_size:.2f}",
                details={
                    'kelly_fraction': kelly_fraction,
                    'safe_fraction': safe_fraction,
                    'recommended_size': recommended_size,
                    'proposed_size': proposed_size
                },
                recommended_size=recommended_size
            )
        
        return RiskDecision(
            status=RiskDecisionStatus.SAFE,
            safe=True,
            reason=f"Position size within Kelly bounds",
            details={
                'kelly_fraction': kelly_fraction,
                'recommended_size': recommended_size,
                'proposed_size': proposed_size
            },
            recommended_size=recommended_size
        )


class RiskEnvelopeCalculator:
    """
    Unified risk assessment system.
    
    Consolidates multiple validators into a single comprehensive risk envelope.
    
    Example:
        calculator = RiskEnvelopeCalculator()
        envelope = await calculator.calculate(
            context=decision_context,
            proposed_size=5000.0,
            account_balance=50000.0
        )
        
        if envelope.safe:
            # Execute with effective_limit
            execute_order(size=envelope.effective_limit)
    """
    
    @staticmethod
    def format_limit_state(current: float, cap: float, label: str, is_ok: bool = None) -> str:
        """
        Format limit state messages consistently.
        
        This utility method provides standardized formatting for all
        risk validator limit messages, ensuring consistent output.
        
        Args:
            current: Current value
            cap: Maximum allowed value
            label: Descriptive label for the limit
            is_ok: Optional explicit OK/exceeded flag (auto-determined if None)
            
        Returns:
            Formatted limit state string
            
        Example:
            >>> RiskEnvelopeCalculator.format_limit_state(3, 5, "DCA attempts")
            "DCA attempts OK: 3.00/5.00"
            >>> RiskEnvelopeCalculator.format_limit_state(6, 5, "DCA attempts")
            "DCA attempts exceeded: 6.00 >= 5.00"
        """
        if is_ok is None:
            is_ok = current < cap
        
        if is_ok:
            return f"{label} OK: {current:.2f}/{cap:.2f}"
        else:
            return f"{label} exceeded: {current:.2f} >= {cap:.2f}"
    
    def __init__(
        self,
        validators: Optional[List[IRiskValidator]] = None,
        enable_kelly_sizing: bool = True
    ):
        """
        Initialize risk envelope calculator.
        
        Args:
            validators: List of risk validators (defaults to standard set)
            enable_kelly_sizing: Use Kelly Criterion for position sizing
        """
        if validators is None:
            validators = [
                ConsecutiveLossValidator(max_consecutive_losses=5),
                SymbolLossLimitValidator(max_symbol_loss_pct=0.25),
                IndividualLossLimitValidator(max_individual_loss_pct=0.10),
                VolatilityValidator(max_volatility=0.05)
            ]
            
            if enable_kelly_sizing:
                validators.append(KellyCriterionSizer(safety_factor=0.25))
        
        self.validators = validators
        
        logger.info(
            f"RiskEnvelopeCalculator initialized with {len(validators)} validators: "
            f"{[v.name for v in validators]}"
        )
    
    async def calculate(
        self,
        context: DecisionContext,
        proposed_size: float,
        account_balance: float
    ) -> RiskEnvelope:
        """
        Calculate comprehensive risk envelope.
        
        Args:
            context: Decision context
            proposed_size: Proposed position size (dollars)
            account_balance: Current account balance
            
        Returns:
            RiskEnvelope with composite assessment
        """
        decisions: List[RiskDecision] = []
        reason_codes: List[RiskDecisionStatus] = []
        details: Dict[str, Any] = {
            'proposed_size': proposed_size,
            'account_balance': account_balance,
            'symbol': context.symbol,
            'validator_results': {}
        }
        
        # Run all validators
        for validator in self.validators:
            try:
                decision = await validator.validate(context, proposed_size, account_balance)
                decisions.append(decision)
                reason_codes.append(decision.status)
                
                details['validator_results'][validator.name] = decision.to_dict()
                
                logger.debug(
                    f"Validator {validator.name}: {decision.status.value} - {decision.reason}"
                )
                
            except Exception as e:
                logger.error(
                    f"Validator {validator.name} failed: {e}",
                    exc_info=True
                )
                # Continue with other validators
        
        # Determine overall safety
        all_safe = all(d.safe for d in decisions)
        
        # Find most restrictive constraint
        if not all_safe:
            primary_constraint = next(
                (d.status for d in decisions if not d.safe),
                RiskDecisionStatus.SAFE
            )
        else:
            primary_constraint = RiskDecisionStatus.SAFE
        
        # Calculate effective limits
        max_position_size = proposed_size
        
        # Get Kelly recommendation if available
        kelly_recommendations = [
            d.recommended_size for d in decisions 
            if d.recommended_size is not None
        ]
        
        if kelly_recommendations:
            dynamic_ceiling = min(kelly_recommendations)
        else:
            dynamic_ceiling = proposed_size
        
        envelope = RiskEnvelope(
            max_position_size=max_position_size,
            dynamic_ceiling=dynamic_ceiling,
            reason_codes=tuple(reason_codes),
            safe=all_safe,
            primary_constraint=primary_constraint,
            details=details
        )
        
        logger.info(
            f"Risk envelope calculated: safe={all_safe}, "
            f"effective_limit=${envelope.effective_limit:.2f}, "
            f"primary_constraint={primary_constraint.value}"
        )
        
        return envelope
    
    def add_validator(self, validator: IRiskValidator) -> None:
        """Add a custom validator to the calculator."""
        self.validators.append(validator)
        logger.info(f"Added validator: {validator.name}")
    
    def remove_validator(self, validator_name: str) -> bool:
        """Remove a validator by name."""
        initial_count = len(self.validators)
        self.validators = [v for v in self.validators if v.name != validator_name]
        
        if len(self.validators) < initial_count:
            logger.info(f"Removed validator: {validator_name}")
            return True
        
        return False
