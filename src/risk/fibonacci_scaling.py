"""
Fibonacci-Based Gradual Scaling Strategy.

An alternative to geometric martingale that uses the Fibonacci sequence for position sizing.
This provides more natural, less aggressive scaling compared to exponential growth.

Fibonacci sequence: 1, 1, 2, 3, 5, 8, 13, 21...
Each term is the sum of the two preceding ones.

Example with 1% initial position:
- Position 0 (initial): 1.0% × Fib(1) = 1.0%
- Position 1 (DCA 1):   1.0% × Fib(2) = 1.0%
- Position 2 (DCA 2):   1.0% × Fib(3) = 2.0%
- Position 3 (DCA 3):   1.0% × Fib(4) = 3.0%
- Position 4 (DCA 4):   1.0% × Fib(5) = 5.0%
Total exposure: 12.0% vs 31.0% with 2x martingale
"""

from typing import List, Dict, Tuple
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)


class FibonacciSequence:
    """
    Fibonacci sequence generator with caching for performance.
    """
    
    def __init__(self, max_terms: int = 20):
        """
        Initialize Fibonacci sequence generator.
        
        Args:
            max_terms: Maximum number of terms to pre-calculate
        """
        self._cache: List[int] = [1, 1]  # F(0)=1, F(1)=1
        self._generate_sequence(max_terms)
        logger.debug(f"Fibonacci sequence initialized with {len(self._cache)} terms")
    
    def _generate_sequence(self, n: int):
        """Generate Fibonacci sequence up to n terms."""
        while len(self._cache) < n:
            self._cache.append(self._cache[-1] + self._cache[-2])
    
    def get_term(self, n: int) -> int:
        """
        Get nth term of Fibonacci sequence.
        
        Args:
            n: Index (0-based)
            
        Returns:
            nth Fibonacci number
        """
        if n < 0:
            raise ValueError("Fibonacci index must be non-negative")
        
        # Extend sequence if needed
        if n >= len(self._cache):
            self._generate_sequence(n + 1)
        
        return self._cache[n]
    
    def get_sequence(self, n: int) -> List[int]:
        """
        Get first n terms of Fibonacci sequence.
        
        Args:
            n: Number of terms
            
        Returns:
            List of first n Fibonacci numbers
        """
        if n >= len(self._cache):
            self._generate_sequence(n + 1)
        
        return self._cache[:n]


@dataclass
class FibonacciScalingConfig:
    """Configuration for Fibonacci-based position scaling."""
    initial_position_pct: float  # Base position size as % of account (e.g., 0.01 = 1%)
    max_attempts: int  # Maximum number of scaling attempts
    max_single_position_pct: float = 0.10  # Maximum size for any single position (10% default)
    total_exposure_limit_pct: float = 0.25  # Maximum total exposure across all positions (25% default)


class GradualScalingStrategy:
    """
    Fibonacci-based gradual position scaling strategy.
    
    Provides a mathematically elegant alternative to geometric martingale:
    - Natural growth pattern (less aggressive than exponential)
    - Self-limiting (Fibonacci grows slower than geometric)
    - Better risk-adjusted returns in many scenarios
    - More predictable exposure accumulation
    """
    
    def __init__(self):
        """Initialize gradual scaling strategy."""
        self.fibonacci = FibonacciSequence(max_terms=20)
        logger.info("GradualScalingStrategy initialized with Fibonacci scaling")
    
    def calculate_position_size(self, config: FibonacciScalingConfig, 
                               attempt: int,
                               account_value: float) -> Tuple[float, Dict]:
        """
        Calculate position size for given attempt using Fibonacci scaling.
        
        Args:
            config: Fibonacci scaling configuration
            attempt: Position attempt number (0 = initial, 1+ = DCA)
            account_value: Total account value
            
        Returns:
            Tuple of (position_value, details_dict)
        """
        if attempt < 0:
            logger.error(f"Invalid attempt number: {attempt}")
            return 0.0, {"error": "Invalid attempt number"}
        
        if attempt > config.max_attempts:
            logger.warning(f"Attempt {attempt} exceeds max_attempts {config.max_attempts}")
            return 0.0, {"error": "Max attempts exceeded"}
        
        # Get Fibonacci multiplier for this attempt
        fib_multiplier = self.fibonacci.get_term(attempt)
        
        # Calculate position size
        position_pct = config.initial_position_pct * fib_multiplier
        
        # Apply single position limit
        if position_pct > config.max_single_position_pct:
            logger.warning(f"🛡️ Position size {position_pct*100:.2f}% capped at "
                         f"{config.max_single_position_pct*100:.1f}%")
            position_pct = config.max_single_position_pct
        
        position_value = account_value * position_pct
        
        # Calculate details
        details = {
            "attempt": attempt,
            "fibonacci_term": fib_multiplier,
            "position_pct": f"{position_pct*100:.2f}%",
            "position_value": f"${position_value:,.2f}",
            "account_value": f"${account_value:,.2f}"
        }
        
        logger.info(f"📊 Fibonacci Scaling: Attempt #{attempt}, Fib({attempt})={fib_multiplier}, "
                   f"Size={position_pct*100:.2f}% (${position_value:,.2f})")
        
        return position_value, details
    
    def calculate_total_exposure(self, config: FibonacciScalingConfig) -> Dict:
        """
        Calculate total exposure at each attempt level.
        
        Args:
            config: Fibonacci scaling configuration
            
        Returns:
            Dictionary with exposure details at each level
        """
        exposure_data = {
            "positions": [],
            "cumulative_exposure": [],
            "individual_sizes": []
        }
        
        total_exposure = 0.0
        
        for attempt in range(config.max_attempts + 1):
            fib_mult = self.fibonacci.get_term(attempt)
            position_pct = min(
                config.initial_position_pct * fib_mult,
                config.max_single_position_pct
            )
            total_exposure += position_pct
            
            exposure_data["positions"].append(attempt)
            exposure_data["cumulative_exposure"].append(total_exposure)
            exposure_data["individual_sizes"].append(position_pct)
        
        # Check if total exposure exceeds limit
        if total_exposure > config.total_exposure_limit_pct:
            logger.warning(f"⚠️  Total exposure {total_exposure*100:.1f}% exceeds limit "
                         f"{config.total_exposure_limit_pct*100:.1f}%")
        
        return {
            "total_exposure_pct": total_exposure * 100,
            "max_attempts": config.max_attempts,
            "positions": exposure_data,
            "exceeds_limit": total_exposure > config.total_exposure_limit_pct
        }
    
    def compare_with_martingale(self, 
                               initial_pct: float,
                               max_attempts: int,
                               martingale_multiplier: float = 2.0) -> Dict:
        """
        Compare Fibonacci scaling with geometric martingale.
        
        Args:
            initial_pct: Initial position percentage
            max_attempts: Number of scaling attempts
            martingale_multiplier: Geometric multiplier for comparison
            
        Returns:
            Comparison dictionary with both strategies
        """
        # Fibonacci scaling
        fib_config = FibonacciScalingConfig(
            initial_position_pct=initial_pct,
            max_attempts=max_attempts
        )
        fib_exposure = self.calculate_total_exposure(fib_config)
        
        # Martingale (geometric) scaling
        martingale_exposure = sum(
            initial_pct * (martingale_multiplier ** i)
            for i in range(max_attempts + 1)
        )
        
        comparison = {
            "fibonacci": {
                "total_exposure_pct": fib_exposure["total_exposure_pct"],
                "sequence": self.fibonacci.get_sequence(max_attempts + 1)
            },
            "martingale": {
                "total_exposure_pct": martingale_exposure * 100,
                "sequence": [martingale_multiplier ** i for i in range(max_attempts + 1)]
            },
            "difference_pct": fib_exposure["total_exposure_pct"] - (martingale_exposure * 100),
            "safer_strategy": "Fibonacci" if fib_exposure["total_exposure_pct"] < martingale_exposure * 100 else "Martingale"
        }
        
        # Log comparison
        logger.info("="*80)
        logger.info("📊 FIBONACCI vs MARTINGALE COMPARISON")
        logger.info("="*80)
        logger.info(f"Configuration: {initial_pct*100:.2f}% initial, {max_attempts} attempts")
        logger.info("")
        logger.info("Fibonacci Sequence:")
        for i, fib in enumerate(comparison["fibonacci"]["sequence"]):
            size_pct = initial_pct * fib * 100
            logger.info(f"  Position {i}: {fib:>2} × {initial_pct*100:.2f}% = {size_pct:>5.2f}%")
        logger.info(f"  Total Fibonacci Exposure: {comparison['fibonacci']['total_exposure_pct']:.2f}%")
        logger.info("")
        logger.info(f"Martingale Sequence ({martingale_multiplier}x):")
        for i, mult in enumerate(comparison["martingale"]["sequence"]):
            size_pct = initial_pct * mult * 100
            logger.info(f"  Position {i}: {mult:>5.1f} × {initial_pct*100:.2f}% = {size_pct:>6.2f}%")
        logger.info(f"  Total Martingale Exposure: {comparison['martingale']['total_exposure_pct']:.2f}%")
        logger.info("")
        logger.info(f"Difference: {comparison['difference_pct']:+.2f}% "
                   f"({comparison['safer_strategy']} is safer)")
        logger.info("="*80)
        
        return comparison
    
    def generate_scaling_schedule(self, config: FibonacciScalingConfig,
                                 account_value: float,
                                 price_levels: List[float]) -> Dict:
        """
        Generate a complete scaling schedule with price levels.
        
        Args:
            config: Fibonacci scaling configuration
            account_value: Account value for sizing
            price_levels: List of price levels for each attempt
            
        Returns:
            Complete scaling schedule with all details
        """
        if len(price_levels) != config.max_attempts + 1:
            logger.error(f"Price levels ({len(price_levels)}) must match attempts ({config.max_attempts + 1})")
            return {}
        
        schedule = {
            "total_positions": config.max_attempts + 1,
            "positions": []
        }
        
        total_cost = 0.0
        total_shares = 0.0
        
        for attempt, price in enumerate(price_levels):
            position_value, details = self.calculate_position_size(config, attempt, account_value)
            shares = position_value / price if price > 0 else 0
            cost = shares * price
            
            total_shares += shares
            total_cost += cost
            
            avg_price = total_cost / total_shares if total_shares > 0 else 0
            
            schedule["positions"].append({
                "attempt": attempt,
                "price": f"${price:.2f}",
                "shares": int(shares),
                "cost": f"${cost:,.2f}",
                "fibonacci_term": self.fibonacci.get_term(attempt),
                "total_shares": int(total_shares),
                "average_price": f"${avg_price:.2f}",
                "total_invested": f"${total_cost:,.2f}",
                "account_pct": f"{(cost/account_value)*100:.2f}%"
            })
        
        schedule["summary"] = {
            "total_shares": int(total_shares),
            "average_price": f"${total_cost/total_shares:.2f}" if total_shares > 0 else "$0.00",
            "total_invested": f"${total_cost:,.2f}",
            "account_exposure_pct": f"{(total_cost/account_value)*100:.2f}%"
        }
        
        return schedule
    
    def recommend_fibonacci_config(self, 
                                  account_value: float,
                                  risk_tolerance: str = "moderate") -> FibonacciScalingConfig:
        """
        Recommend Fibonacci scaling configuration based on risk tolerance.
        
        Args:
            account_value: Account value for reference
            risk_tolerance: "conservative", "moderate", or "aggressive"
            
        Returns:
            Recommended FibonacciScalingConfig
        """
        configs = {
            "conservative": FibonacciScalingConfig(
                initial_position_pct=0.005,  # 0.5%
                max_attempts=3,
                max_single_position_pct=0.05,  # 5%
                total_exposure_limit_pct=0.15  # 15%
            ),
            "moderate": FibonacciScalingConfig(
                initial_position_pct=0.01,  # 1%
                max_attempts=4,
                max_single_position_pct=0.08,  # 8%
                total_exposure_limit_pct=0.25  # 25%
            ),
            "aggressive": FibonacciScalingConfig(
                initial_position_pct=0.02,  # 2%
                max_attempts=5,
                max_single_position_pct=0.10,  # 10%
                total_exposure_limit_pct=0.40  # 40%
            )
        }
        
        config = configs.get(risk_tolerance.lower(), configs["moderate"])
        
        logger.info(f"📋 Recommended Fibonacci Config ({risk_tolerance}):")
        logger.info(f"   Initial Position: {config.initial_position_pct*100:.2f}%")
        logger.info(f"   Max Attempts: {config.max_attempts}")
        logger.info(f"   Max Single Position: {config.max_single_position_pct*100:.1f}%")
        logger.info(f"   Total Exposure Limit: {config.total_exposure_limit_pct*100:.1f}%")
        
        # Show total exposure
        exposure = self.calculate_total_exposure(config)
        logger.info(f"   Calculated Total Exposure: {exposure['total_exposure_pct']:.2f}%")
        
        return config
