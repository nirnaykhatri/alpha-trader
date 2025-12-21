"""
Martingale Strategy Configuration Validator and Safety Manager.

This module provides critical safety checks for martingale trading strategies
to prevent catastrophic account losses from exponential position sizing.

Architecture:
- MartingaleConfigValidator: Static validation of config at startup
- MartingaleSafetyPolicy: Immutable rules and thresholds from config
- MartingaleSafetyState: Mutable runtime tracking (losses, counters)
- MartingaleSafetyManager: Orchestrates policy + state for safety checks
"""

import sys
from typing import List, Dict, Optional, Tuple, Any
from collections import defaultdict
from datetime import datetime, timedelta, UTC
from dataclasses import dataclass, field
import structlog
from src.interfaces import IConfigurationManager
from src.exceptions import RiskLimitException

logger = structlog.get_logger(__name__)


class MartingaleConfigValidator:
    """
    Validates martingale configuration and warns about dangerous settings.
    
    Critical safety validator that analyzes martingale parameters and calculates
    maximum exposure risk before allowing the bot to start.
    """
    
    @staticmethod
    def validate_martingale_config(config: dict, strategy_name: str = "") -> Tuple[List[str], bool]:
        """
        Validate martingale configuration and return warnings.
        
        Args:
            config: Martingale configuration dictionary
            strategy_name: Name of strategy (e.g., "long_strategy", "short_strategy")
            
        Returns:
            Tuple of (list of warning messages, is_critical)
            is_critical=True means configuration is extremely dangerous
        """
        warnings = []
        is_critical = False
        
        if not config.get('enabled', False):
            return warnings, is_critical
        
        base_mult = config.get('base_multiplier', 1.0)
        max_mult = config.get('max_multiplier', 1.0)
        max_losses = config.get('max_consecutive_losses', 0)
        
        # Calculate maximum theoretical exposure
        # Sum of geometric series: 1 + r + r^2 + ... + r^n
        max_exposure = sum(min(base_mult ** i, max_mult) for i in range(max_losses + 1))
        
        prefix = f"[{strategy_name}] " if strategy_name else ""
        
        # Check 1: Base multiplier
        if base_mult >= 2.0:
            is_critical = True
            warnings.append(
                f"🚨 {prefix}CRITICAL: base_multiplier={base_mult} doubles or more than doubles position size. "
                f"Risk of account blowup is EXTREMELY HIGH!"
            )
        elif base_mult >= 1.5:
            warnings.append(
                f"⚠️  {prefix}WARNING: base_multiplier={base_mult} increases position by 50%+. "
                f"This is aggressive and risky."
            )
        
        # Check 2: Maximum multiplier
        if max_mult > 8.0:
            is_critical = True
            warnings.append(
                f"🚨 {prefix}CRITICAL: max_multiplier={max_mult} can lead to positions "
                f"{max_mult:.1f}x your initial size. This is EXTREMELY RISKY!"
            )
        elif max_mult > 4.0:
            warnings.append(
                f"⚠️  {prefix}WARNING: max_multiplier={max_mult} allows positions up to "
                f"{max_mult:.1f}x initial size."
            )
        
        # Check 3: Consecutive losses
        if max_losses > 3:
            is_critical = True
            warnings.append(
                f"🚨 {prefix}CRITICAL: max_consecutive_losses={max_losses} allows up to "
                f"{max_exposure:.1f}x total exposure. Account ruin is highly likely!"
            )
        elif max_losses > 2:
            warnings.append(
                f"⚠️  {prefix}WARNING: max_consecutive_losses={max_losses} allows up to "
                f"{max_exposure:.1f}x total exposure."
            )
        
        # Check 4: Combined risk
        if base_mult > 1.5 and max_losses > 2:
            is_critical = True
            warnings.append(
                f"🚨 {prefix}EXTREME RISK: Combination of base_multiplier={base_mult} and "
                f"max_consecutive_losses={max_losses} can wipe out account in a single losing streak! "
                f"Maximum exposure: {max_exposure:.1f}x initial position."
            )
        
        # Check 5: Calculate ruin probability
        # Assuming 50% win rate (optimistic for trading)
        ruin_probability = (0.5 ** max_losses) * 100
        if ruin_probability < 5:  # Less than 5% means it WILL happen
            is_critical = True
            warnings.append(
                f"🚨 {prefix}MATHEMATICAL CERTAINTY: {max_losses} consecutive losses has "
                f"{ruin_probability:.2f}% probability. This WILL occur approximately every "
                f"{int(1/ruin_probability * 100)} trading sequences!"
            )
        
        # Check 6: Missing safety parameters
        if 'max_account_risk_percent' not in config:
            warnings.append(
                f"⚠️  {prefix}MISSING SAFETY: No max_account_risk_percent configured. "
                f"Add this to cap total account exposure."
            )
        
        if 'daily_loss_limit_percent' not in config:
            warnings.append(
                f"⚠️  {prefix}MISSING SAFETY: No daily_loss_limit_percent configured. "
                f"Add circuit breaker to stop on daily losses."
            )
        
        return warnings, is_critical
    
    @staticmethod
    def validate_and_confirm(config_manager: IConfigurationManager) -> bool:
        """
        Validate martingale configuration and require user confirmation if risky.
        
        Args:
            config_manager: Configuration manager instance
            
        Returns:
            True if safe or user confirms, False if user rejects
            
        Raises:
            RiskLimitException: If configuration is critically dangerous and should not proceed
        """
        all_warnings = []
        has_critical = False
        
        # Check long strategy
        long_martingale = config_manager.get_config("strategies.long_strategy.martingale", {})
        if long_martingale:
            warnings, is_crit = MartingaleConfigValidator.validate_martingale_config(
                long_martingale, "LONG"
            )
            all_warnings.extend(warnings)
            has_critical = has_critical or is_crit
        
        # Check short strategy
        short_martingale = config_manager.get_config("strategies.short_strategy.martingale", {})
        if short_martingale:
            warnings, is_crit = MartingaleConfigValidator.validate_martingale_config(
                short_martingale, "SHORT"
            )
            all_warnings.extend(warnings)
            has_critical = has_critical or is_crit
        
        if not all_warnings:
            logger.info("✅ Martingale configuration validated - no risks detected")
            return True
        
        # Display warnings
        print("\n" + "=" * 80)
        print("⚠️  MARTINGALE STRATEGY RISK WARNINGS ⚠️")
        print("=" * 80)
        for warning in all_warnings:
            print(f"  {warning}")
        print("=" * 80)
        
        if has_critical:
            print("\n🚨 CRITICAL RISK DETECTED 🚨")
            print("The current martingale configuration poses EXTREME risk of total account loss.")
            print("\nRECOMMENDED ACTIONS:")
            print("  1. Set enabled: false to disable martingale")
            print("  2. Reduce base_multiplier to 1.5 or lower")
            print("  3. Reduce max_multiplier to 4.0 or lower")
            print("  4. Reduce max_consecutive_losses to 3 or lower")
            print("  5. Add max_account_risk_percent: 25.0")
            print("  6. Add daily_loss_limit_percent: 10.0")
            print("\nFor safer alternatives, use technical DCA (support_averaging) instead.")
            print("=" * 80)
            
            # Require explicit confirmation for critical risks
            response = input("\nDo you REALLY want to proceed with this configuration? (type 'YES I ACCEPT THE RISK'): ")
            if response != 'YES I ACCEPT THE RISK':
                logger.error("User rejected risky martingale configuration")
                raise RiskLimitException(
                    "Martingale configuration rejected due to critical risk. "
                    "Please adjust settings in config/settings.toml"
                )
            
            logger.warning("User accepted critical martingale risk - proceeding with extreme caution")
            return True
        else:
            # Non-critical warnings - simple confirmation
            response = input("\nDo you acknowledge these risks and want to continue? (yes/NO): ")
            if response.lower() != 'yes':
                logger.info("User rejected martingale configuration")
                print("\n✅ Exiting to allow configuration adjustments.")
                print("   Please review and update martingale settings in config/settings.toml")
                return False
            
            logger.info("User acknowledged martingale risks and confirmed")
            return True


@dataclass
class MartingaleSafetyPolicy:
    """
    Immutable policy configuration for martingale safety limits.
    
    Contains all thresholds and rules loaded from configuration.
    This class is immutable after initialization and thread-safe.
    
    Attributes:
        max_account_risk: Maximum account risk as decimal (e.g., 0.25 for 25%)
        daily_loss_limit: Daily loss limit as decimal (e.g., 0.10 for 10%)
        weekly_loss_limit: Weekly loss limit as decimal (e.g., 0.20 for 20%)
        max_single_loss: Maximum single loss as decimal (default 0.10 for 10%)
        default_max_consecutive_losses: Default max consecutive losses if not specified
        default_account_value: Default account value if not provided at runtime
    """
    max_account_risk: float = 0.25
    daily_loss_limit: float = 0.10
    weekly_loss_limit: float = 0.20
    max_single_loss: float = 0.10
    default_max_consecutive_losses: int = 3
    default_account_value: float = 100000.0
    
    @classmethod
    def from_config(cls, config_manager: IConfigurationManager) -> 'MartingaleSafetyPolicy':
        """
        Create a policy from configuration manager.
        
        Args:
            config_manager: Configuration manager instance
            
        Returns:
            MartingaleSafetyPolicy: Immutable policy object
        """
        return cls(
            max_account_risk=config_manager.get_config(
                "strategies.long_strategy.martingale.max_account_risk_percent", 25.0
            ) / 100.0,
            daily_loss_limit=config_manager.get_config(
                "strategies.long_strategy.martingale.daily_loss_limit_percent", 10.0
            ) / 100.0,
            weekly_loss_limit=config_manager.get_config(
                "strategies.long_strategy.martingale.weekly_loss_limit_percent", 20.0
            ) / 100.0,
            max_single_loss=config_manager.get_config(
                "strategies.long_strategy.martingale.max_single_loss_percent", 10.0
            ) / 100.0,
            default_max_consecutive_losses=config_manager.get_config(
                "strategies.long_strategy.martingale.max_consecutive_losses", 3
            ),
            default_account_value=config_manager.get_config(
                "trading.account_value", 100000.0
            )
        )
    
    def check_consecutive_losses(self, current: int, max_allowed: int) -> Tuple[bool, Optional[str]]:
        """Check if consecutive losses exceed limit."""
        if current > max_allowed:
            return False, f"Exceeded max consecutive losses ({max_allowed})"
        return True, None
    
    def check_symbol_loss(self, symbol_loss: float, account_value: float) -> Tuple[bool, Optional[str]]:
        """Check if symbol loss exceeds account risk limit."""
        pct = symbol_loss / account_value
        if pct >= self.max_account_risk:
            return False, f"Symbol losses ({pct*100:.1f}%) exceed account risk limit ({self.max_account_risk*100:.1f}%)"
        return True, None
    
    def check_single_loss(self, loss_amount: float, account_value: float) -> Tuple[bool, Optional[str]]:
        """Check if single loss exceeds limit."""
        pct = loss_amount / account_value
        if pct >= self.max_single_loss:
            return False, f"Single loss ({pct*100:.1f}%) exceeds {self.max_single_loss*100:.1f}% of account"
        return True, None
    
    def check_daily_loss(self, daily_loss: float, account_value: float) -> Tuple[bool, Optional[str]]:
        """Check if daily loss exceeds limit."""
        pct = daily_loss / account_value
        if pct >= self.daily_loss_limit:
            return False, f"Daily loss ({pct*100:.1f}%) exceeds limit ({self.daily_loss_limit*100:.1f}%)"
        return True, None
    
    def check_weekly_loss(self, weekly_loss: float, account_value: float) -> Tuple[bool, Optional[str]]:
        """Check if weekly loss exceeds limit."""
        pct = weekly_loss / account_value
        if pct >= self.weekly_loss_limit:
            return False, f"Weekly loss ({pct*100:.1f}%) exceeds limit ({self.weekly_loss_limit*100:.1f}%)"
        return True, None


@dataclass
class MartingaleSafetyState:
    """
    Mutable runtime state for martingale safety tracking.
    
    Tracks losses, counters, and emergency stop flags at runtime.
    This class is mutable and should be used by a single MartingaleSafetyManager.
    
    Attributes:
        consecutive_losses: Per-symbol consecutive loss count
        total_martingale_loss: Per-symbol total loss amount
        daily_loss: Current day's total loss
        weekly_loss: Current week's total loss
        emergency_stop: Whether emergency stop is activated
        last_daily_reset: Timestamp of last daily reset
        last_weekly_reset: Timestamp of last weekly reset
    """
    consecutive_losses: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    total_martingale_loss: Dict[str, float] = field(default_factory=lambda: defaultdict(float))
    daily_loss: float = 0.0
    weekly_loss: float = 0.0
    emergency_stop: bool = False
    last_daily_reset: datetime = field(default_factory=lambda: datetime.now(UTC))
    last_weekly_reset: datetime = field(default_factory=lambda: datetime.now(UTC))
    
    def record_loss(self, symbol: str, loss_amount: float, consecutive_count: int):
        """
        Record a loss for tracking.
        
        Args:
            symbol: Trading symbol
            loss_amount: Amount of the loss
            consecutive_count: Current consecutive loss count
        """
        self.consecutive_losses[symbol] = consecutive_count + 1
        self.total_martingale_loss[symbol] += loss_amount
        self.daily_loss += loss_amount
        self.weekly_loss += loss_amount
    
    def maybe_reset_daily(self) -> bool:
        """
        Reset daily counter if 24 hours have passed.
        
        Returns:
            bool: True if reset occurred
        """
        now = datetime.now(UTC)
        SECONDS_IN_DAY = 24 * 60 * 60  # 86400 seconds
        if (now - self.last_daily_reset).total_seconds() > SECONDS_IN_DAY:
            logger.info(f"Resetting daily loss tracker. Previous daily loss: ${self.daily_loss:.2f}")
            self.daily_loss = 0.0
            self.last_daily_reset = now
            return True
        return False
    
    def maybe_reset_weekly(self) -> bool:
        """
        Reset weekly counter if 7 days have passed.
        
        Returns:
            bool: True if reset occurred
        """
        now = datetime.now(UTC)
        SECONDS_IN_WEEK = 7 * 24 * 60 * 60  # 604800 seconds
        if (now - self.last_weekly_reset).total_seconds() > SECONDS_IN_WEEK:
            logger.info(f"Resetting weekly loss tracker. Previous weekly loss: ${self.weekly_loss:.2f}")
            self.weekly_loss = 0.0
            self.last_weekly_reset = now
            return True
        return False
    
    def reset_symbol(self, symbol: str):
        """
        Reset tracking for a symbol after profitable trade.
        
        Args:
            symbol: Symbol to reset
        """
        if symbol in self.consecutive_losses:
            logger.info(
                f"Resetting martingale tracking for {symbol} after profit",
                previous_losses=self.consecutive_losses[symbol],
                total_loss=self.total_martingale_loss[symbol]
            )
            self.consecutive_losses[symbol] = 0
            self.total_martingale_loss[symbol] = 0.0
    
    def activate_emergency_stop(self):
        """Activate emergency stop flag."""
        self.emergency_stop = True
        logger.critical("🚨 EMERGENCY STOP ACTIVATED - All martingale trading halted")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current state status."""
        return {
            "emergency_stop": self.emergency_stop,
            "daily_loss": self.daily_loss,
            "weekly_loss": self.weekly_loss,
            "symbols_tracked": len(self.consecutive_losses),
            "max_consecutive_losses": max(self.consecutive_losses.values()) if self.consecutive_losses else 0
        }


class MartingaleSafetyManager:
    """
    Emergency circuit breaker for martingale strategies.
    
    Orchestrates MartingaleSafetyPolicy (rules) and MartingaleSafetyState (tracking)
    to provide real-time safety checks and prevent catastrophic losses.
    
    Architecture:
        - Policy: Immutable rules/thresholds from config
        - State: Mutable runtime tracking (losses, counters)
        - Manager: Orchestrates checks using both
    """
    
    def __init__(self, config_manager: IConfigurationManager):
        """
        Initialize safety manager with policy and state.
        
        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        self.policy = MartingaleSafetyPolicy.from_config(config_manager)
        self.state = MartingaleSafetyState()
        
        logger.info(
            "MartingaleSafetyManager initialized",
            max_account_risk_pct=self.policy.max_account_risk * 100,
            daily_limit_pct=self.policy.daily_loss_limit * 100,
            weekly_limit_pct=self.policy.weekly_loss_limit * 100
        )
    
    async def check_safety(
        self, 
        symbol: str, 
        loss_amount: float, 
        consecutive_losses: int = 0,
        account_value: Optional[float] = None,
        max_consecutive_losses: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Check if martingale is safe to continue.
        
        Uses policy rules to evaluate current state and determine if
        trading should continue or be halted.
        
        Args:
            symbol: Trading symbol
            loss_amount: Amount lost on current position
            consecutive_losses: Current consecutive loss count for this position
            account_value: Total account portfolio value (uses default if not provided)
            max_consecutive_losses: Maximum allowed consecutive losses (uses config if not provided)
            
        Returns:
            Dict with keys:
                - 'safe': bool - True if safe to continue
                - 'reason': Optional[str] - Reason if not safe
                - 'details': Dict - Additional safety check details
        """
        # Use policy defaults if not provided
        if account_value is None:
            account_value = self.policy.default_account_value
        if max_consecutive_losses is None:
            max_consecutive_losses = self.policy.default_max_consecutive_losses
        
        # Update state tracking
        self.state.record_loss(symbol, loss_amount, consecutive_losses)
        
        # Reset counters if needed
        self.state.maybe_reset_daily()
        self.state.maybe_reset_weekly()
        
        # Build details dict for transparency
        details = {
            'consecutive_losses': self.state.consecutive_losses[symbol],
            'max_consecutive_losses': max_consecutive_losses,
            'total_symbol_loss': self.state.total_martingale_loss[symbol],
            'daily_loss': self.state.daily_loss,
            'weekly_loss': self.state.weekly_loss,
            'account_value': account_value
        }
        
        # Run policy checks in order of severity
        
        # Check 1: Emergency stop flag
        if self.state.emergency_stop:
            return {'safe': False, 'reason': "Emergency stop activated", 'details': details}
        
        # Check 2: Consecutive loss limit
        safe, reason = self.policy.check_consecutive_losses(
            self.state.consecutive_losses[symbol], max_consecutive_losses
        )
        if not safe:
            return {'safe': False, 'reason': reason, 'details': details}
        
        # Check 3: Total symbol loss vs account
        safe, reason = self.policy.check_symbol_loss(
            self.state.total_martingale_loss[symbol], account_value
        )
        if not safe:
            return {'safe': False, 'reason': reason, 'details': details}
        
        # Check 4: Individual loss size
        safe, reason = self.policy.check_single_loss(loss_amount, account_value)
        if not safe:
            return {'safe': False, 'reason': reason, 'details': details}
        
        # Check 5: Daily loss limit
        safe, reason = self.policy.check_daily_loss(self.state.daily_loss, account_value)
        if not safe:
            self.state.activate_emergency_stop()
            return {'safe': False, 'reason': reason, 'details': details}
        
        # Check 6: Weekly loss limit
        safe, reason = self.policy.check_weekly_loss(self.state.weekly_loss, account_value)
        if not safe:
            self.state.activate_emergency_stop()
            return {'safe': False, 'reason': reason, 'details': details}
        
        # All checks passed
        symbol_loss_pct = self.state.total_martingale_loss[symbol] / account_value
        daily_loss_pct = self.state.daily_loss / account_value
        
        logger.debug(
            f"Martingale safety checks passed for {symbol}",
            consecutive_losses=self.state.consecutive_losses[symbol],
            symbol_loss_pct=f"{symbol_loss_pct*100:.2f}%",
            daily_loss_pct=f"{daily_loss_pct*100:.2f}%"
        )
        
        return {'safe': True, 'reason': None, 'details': details}
    
    def reset_symbol(self, symbol: str):
        """
        Reset tracking for a symbol after profitable trade.
        
        Delegates to state for actual reset.
        
        Args:
            symbol: Symbol to reset
        """
        self.state.reset_symbol(symbol)
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current safety manager status.
        
        Returns combined policy and state information.
        """
        state_status = self.state.get_status()
        return {
            **state_status,
            "policy": {
                "max_account_risk_pct": self.policy.max_account_risk * 100,
                "daily_loss_limit_pct": self.policy.daily_loss_limit * 100,
                "weekly_loss_limit_pct": self.policy.weekly_loss_limit * 100,
                "max_single_loss_pct": self.policy.max_single_loss * 100
            }
        }
