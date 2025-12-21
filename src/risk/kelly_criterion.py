"""
Kelly Criterion Calculator for Scientific Position Sizing.

The Kelly Criterion is a formula used to determine the optimal size of a series of bets
to maximize the logarithm of wealth. In trading, it helps determine the optimal position
size based on win rate and risk/reward ratio.

Formula: f* = (p × b - q) / b
Where:
  f* = optimal fraction of capital to wager
  p = probability of winning
  b = net odds received (profit/loss ratio)
  q = probability of losing (1 - p)
"""

from typing import Dict, Optional, Tuple
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class KellyParameters:
    """Parameters for Kelly Criterion calculation."""
    win_probability: float  # Probability of trade being profitable (0.0 to 1.0)
    profit_loss_ratio: float  # Average profit / average loss (e.g., 2.0 = profit is 2x loss)
    fractional_kelly: float = 0.25  # Use fractional Kelly to reduce volatility (0.25 = quarter Kelly)
    max_position_size: float = 0.02  # Maximum position size cap (2% of account)
    min_position_size: float = 0.001  # Minimum position size (0.1% of account)


class KellyCriterionCalculator:
    """
    Calculate optimal position sizes using the Kelly Criterion.
    
    The Kelly Criterion provides a mathematically optimal position size, but
    full Kelly can be aggressive. We use fractional Kelly (typically 25% or 50%)
    to reduce volatility while still achieving good growth.
    """
    
    def __init__(self):
        """Initialize Kelly Criterion calculator."""
        self._historical_trades: list = []  # Track trades for dynamic parameter estimation
        logger.info("KellyCriterionCalculator initialized")
    
    def calculate_optimal_size(self, params: KellyParameters, 
                              account_value: float) -> Tuple[float, Dict]:
        """
        Calculate optimal position size using Kelly Criterion.
        
        Args:
            params: Kelly parameters (win probability, profit/loss ratio, etc.)
            account_value: Total account value
            
        Returns:
            Tuple of (position_value, details_dict)
            position_value: Dollar amount to risk on position
            details_dict: Calculation details for logging
        """
        try:
            # Validate inputs
            if not 0 <= params.win_probability <= 1:
                logger.error(f"Invalid win probability: {params.win_probability}. Must be 0-1.")
                return 0.0, {"error": "Invalid win probability"}
            
            if params.profit_loss_ratio <= 0:
                logger.error(f"Invalid profit/loss ratio: {params.profit_loss_ratio}. Must be > 0.")
                return 0.0, {"error": "Invalid profit/loss ratio"}
            
            # Calculate full Kelly percentage
            # f* = (p × b - q) / b
            p = params.win_probability
            b = params.profit_loss_ratio
            q = 1 - p
            
            full_kelly = (p * b - q) / b
            
            # Apply fractional Kelly to reduce risk
            fractional_kelly = full_kelly * params.fractional_kelly
            
            # Cap at maximum and floor at minimum
            optimal_pct = max(
                params.min_position_size,
                min(fractional_kelly, params.max_position_size)
            )
            
            # Convert to dollar amount
            position_value = account_value * optimal_pct
            
            # Calculate details for logging
            details = {
                "win_probability": f"{p*100:.1f}%",
                "profit_loss_ratio": f"{b:.2f}",
                "full_kelly_pct": f"{full_kelly*100:.2f}%",
                "fractional_kelly_pct": f"{fractional_kelly*100:.2f}%",
                "optimal_pct": f"{optimal_pct*100:.2f}%",
                "position_value": f"${position_value:,.2f}",
                "account_value": f"${account_value:,.2f}",
                "capped": fractional_kelly > params.max_position_size or fractional_kelly < params.min_position_size
            }
            
            # Log warnings for edge cases
            if full_kelly <= 0:
                logger.warning(f"⚠️ KELLY WARNING: Full Kelly is {full_kelly*100:.2f}% (negative or zero). "
                             f"This suggests negative expected value - DO NOT TRADE!")
                details["warning"] = "Negative expected value detected"
                return 0.0, details
            
            if full_kelly > 0.5:
                logger.warning(f"⚠️ KELLY WARNING: Full Kelly is {full_kelly*100:.2f}% (very high). "
                             f"Fractional Kelly strongly recommended to avoid excessive risk.")
                details["warning"] = "Very high Kelly percentage detected"
            
            logger.info(
                f"📊 Kelly Criterion: {optimal_pct*100:.2f}% of account (${position_value:,.2f})",
                **details
            )
            
            return position_value, details
            
        except Exception as e:
            logger.error(f"Error calculating Kelly position size: {e}")
            return 0.0, {"error": str(e)}
    
    def estimate_parameters_from_history(self, trades: Optional[list] = None) -> KellyParameters:
        """
        Estimate Kelly parameters from historical trade results.
        
        Args:
            trades: List of trade results (dicts with 'profit' and 'is_win' keys)
                   If None, uses internal trade history
            
        Returns:
            KellyParameters estimated from historical performance
        """
        trade_list = trades if trades is not None else self._historical_trades
        
        if not trade_list:
            # Default conservative parameters when no history
            logger.warning("No trade history available. Using conservative default Kelly parameters.")
            return KellyParameters(
                win_probability=0.50,  # Assume 50% win rate
                profit_loss_ratio=1.5,  # Assume 1.5:1 reward/risk
                fractional_kelly=0.25,  # Quarter Kelly (conservative)
                max_position_size=0.02  # 2% max
            )
        
        # Calculate win rate
        wins = sum(1 for t in trade_list if t.get('is_win', False))
        win_rate = wins / len(trade_list)
        
        # Calculate average profit and loss
        profits = [t['profit'] for t in trade_list if t.get('is_win', False) and 'profit' in t]
        losses = [abs(t['profit']) for t in trade_list if not t.get('is_win', True) and 'profit' in t]
        
        avg_profit = sum(profits) / len(profits) if profits else 100
        avg_loss = sum(losses) / len(losses) if losses else 100
        profit_loss_ratio = avg_profit / avg_loss if avg_loss > 0 else 1.5
        
        logger.info(
            f"📈 Estimated Kelly parameters from {len(trade_list)} trades: "
            f"Win rate={win_rate*100:.1f}%, P/L ratio={profit_loss_ratio:.2f}"
        )
        
        return KellyParameters(
            win_probability=win_rate,
            profit_loss_ratio=profit_loss_ratio,
            fractional_kelly=0.25,  # Conservative fractional Kelly
            max_position_size=0.02
        )
    
    def add_trade_result(self, profit: float, is_win: bool):
        """
        Add a trade result to historical tracking for parameter estimation.
        
        Args:
            profit: Profit/loss amount (positive for profit, negative for loss)
            is_win: Whether the trade was profitable
        """
        self._historical_trades.append({
            'profit': profit,
            'is_win': is_win
        })
        
        # Keep only last 100 trades for parameter estimation
        if len(self._historical_trades) > 100:
            self._historical_trades = self._historical_trades[-100:]
        
        logger.debug(f"Added trade result: {'WIN' if is_win else 'LOSS'} ${profit:,.2f} "
                    f"(history size: {len(self._historical_trades)})")
    
    def calculate_optimal_kelly_for_strategy(self, 
                                            win_rate: float, 
                                            avg_win: float, 
                                            avg_loss: float,
                                            account_value: float,
                                            fractional: float = 0.25) -> Tuple[float, Dict]:
        """
        Convenience method to calculate Kelly size with direct win/loss parameters.
        
        Args:
            win_rate: Historical win rate (0.0 to 1.0)
            avg_win: Average winning trade profit (dollars)
            avg_loss: Average losing trade loss (dollars, as positive number)
            account_value: Total account value
            fractional: Fractional Kelly to use (default 0.25 = quarter Kelly)
            
        Returns:
            Tuple of (position_value, details_dict)
        """
        # Calculate profit/loss ratio
        if avg_loss <= 0:
            logger.error("Average loss must be positive")
            return 0.0, {"error": "Invalid average loss"}
        
        profit_loss_ratio = avg_win / avg_loss
        
        # Create Kelly parameters
        params = KellyParameters(
            win_probability=win_rate,
            profit_loss_ratio=profit_loss_ratio,
            fractional_kelly=fractional,
            max_position_size=0.02,  # 2% max
            min_position_size=0.001  # 0.1% min
        )
        
        return self.calculate_optimal_size(params, account_value)
    
    def compare_with_fixed_sizing(self, kelly_size: float, 
                                 fixed_size: float, 
                                 account_value: float) -> Dict:
        """
        Compare Kelly sizing with fixed percentage sizing.
        
        Args:
            kelly_size: Dollar amount from Kelly calculation
            fixed_size: Dollar amount from fixed percentage method
            account_value: Total account value
            
        Returns:
            Comparison dictionary with metrics
        """
        kelly_pct = (kelly_size / account_value) * 100
        fixed_pct = (fixed_size / account_value) * 100
        difference_pct = ((kelly_size - fixed_size) / fixed_size) * 100 if fixed_size > 0 else 0
        
        comparison = {
            "kelly_size": f"${kelly_size:,.2f}",
            "kelly_pct": f"{kelly_pct:.2f}%",
            "fixed_size": f"${fixed_size:,.2f}",
            "fixed_pct": f"{fixed_pct:.2f}%",
            "difference": f"{difference_pct:+.1f}%",
            "recommendation": "Kelly" if kelly_size > fixed_size else "Fixed"
        }
        
        logger.info("Kelly vs Fixed Sizing Comparison:", **comparison)
        
        return comparison
