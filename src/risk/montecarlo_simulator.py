"""
Monte Carlo Risk Simulator for Martingale Strategies.

Simulates thousands of trading scenarios to calculate risk metrics including:
- Probability of account ruin
- Maximum drawdown
- Expected return
- Confidence intervals for outcomes
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class MartingaleConfig:
    """Configuration for martingale simulation."""
    initial_position_pct: float  # Initial position as % of account (e.g., 0.01 = 1%)
    multiplier: float  # Position size multiplier (e.g., 1.5 or 2.0)
    max_multiplier: float  # Maximum multiplier cap (e.g., 4.0)
    max_attempts: int  # Maximum consecutive DCA attempts
    win_probability: float  # Probability of winning trade (0.0 to 1.0)
    avg_win_pct: float  # Average win as % of position (e.g., 0.03 = 3%)
    avg_loss_pct: float  # Average loss as % of position (e.g., 0.02 = 2%)


@dataclass
class SimulationResults:
    """Results from Monte Carlo simulation."""
    ruin_probability: float  # Probability of losing 90%+ of account
    max_drawdown: float  # Maximum drawdown observed (as %)
    avg_drawdown: float  # Average maximum drawdown (as %)
    expected_return: float  # Expected account value after simulation (as %)
    median_return: float  # Median account value (as %)
    percentile_5: float  # 5th percentile outcome (worst 5%)
    percentile_95: float  # 95th percentile outcome (best 5%)
    consecutive_loss_probabilities: Dict[int, float]  # P(N consecutive losses)
    final_balances: np.ndarray  # All final account balances from simulations


class MartingaleRiskSimulator:
    """
    Monte Carlo simulator for martingale trading strategies.
    
    Runs thousands of simulated trading sequences to estimate the probability
    distribution of outcomes, including catastrophic loss scenarios.
    """
    
    def __init__(self, iterations: int = 10000, starting_balance: float = 100000):
        """
        Initialize Monte Carlo simulator.
        
        Args:
            iterations: Number of Monte Carlo iterations (default 10,000)
            starting_balance: Starting account balance for simulations
        """
        self.iterations = iterations
        self.starting_balance = starting_balance
        logger.info(f"MartingaleRiskSimulator initialized: {iterations:,} iterations, ${starting_balance:,.2f} starting balance")
    
    def simulate_martingale_risk(self, config: MartingaleConfig, 
                                trades_per_simulation: int = 100) -> SimulationResults:
        """
        Run Monte Carlo simulation of martingale strategy.
        
        Args:
            config: Martingale configuration parameters
            trades_per_simulation: Number of trades to simulate per run
            
        Returns:
            SimulationResults with comprehensive risk metrics
        """
        logger.info(f"🎲 Running Monte Carlo simulation: {self.iterations:,} iterations × {trades_per_simulation} trades")
        logger.info(f"   Config: {config.initial_position_pct*100:.2f}% initial, "
                   f"{config.multiplier}x multiplier (max {config.max_multiplier}x), "
                   f"{config.max_attempts} max attempts, {config.win_probability*100:.1f}% win rate")
        
        final_balances = []
        max_drawdowns = []
        ruin_count = 0
        consecutive_losses = {i: 0 for i in range(config.max_attempts + 2)}  # Track up to max+1
        
        for iteration in range(self.iterations):
            balance = self.starting_balance
            peak_balance = balance
            max_drawdown = 0.0
            current_losing_streak = 0
            
            for trade_num in range(trades_per_simulation):
                # Determine if trade wins or loses
                is_win = np.random.random() < config.win_probability
                
                # Calculate position size with martingale
                attempt_multiplier = min(
                    config.multiplier ** current_losing_streak,
                    config.max_multiplier
                )
                position_pct = config.initial_position_pct * attempt_multiplier
                position_size = balance * position_pct
                
                # Ensure we can afford the position
                if position_size > balance * 0.95:  # Can't use more than 95% of balance
                    position_size = balance * 0.95
                
                # Calculate profit/loss
                if is_win:
                    profit = position_size * config.avg_win_pct
                    balance += profit
                    current_losing_streak = 0  # Reset on win
                else:
                    loss = position_size * config.avg_loss_pct
                    balance -= loss
                    current_losing_streak += 1
                    
                    # Track consecutive losses
                    if current_losing_streak <= config.max_attempts + 1:
                        consecutive_losses[current_losing_streak] += 1
                
                # Update peak and drawdown
                if balance > peak_balance:
                    peak_balance = balance
                
                current_drawdown = (peak_balance - balance) / peak_balance if peak_balance > 0 else 0
                max_drawdown = max(max_drawdown, current_drawdown)
                
                # Check for ruin (90% loss)
                if balance < self.starting_balance * 0.10:
                    ruin_count += 1
                    break  # Account blown up, end this simulation
                
                # Reset losing streak if it exceeds max attempts
                if current_losing_streak > config.max_attempts:
                    current_losing_streak = 0
            
            final_balances.append(balance)
            max_drawdowns.append(max_drawdown)
        
        # Convert to numpy array for analysis
        final_balances = np.array(final_balances)
        max_drawdowns = np.array(max_drawdowns)
        
        # Calculate results
        ruin_probability = ruin_count / self.iterations
        expected_return = (np.mean(final_balances) / self.starting_balance - 1) * 100
        median_return = (np.median(final_balances) / self.starting_balance - 1) * 100
        avg_drawdown = np.mean(max_drawdowns) * 100
        max_drawdown_observed = np.max(max_drawdowns) * 100
        
        # Calculate percentiles
        percentile_5 = (np.percentile(final_balances, 5) / self.starting_balance - 1) * 100
        percentile_95 = (np.percentile(final_balances, 95) / self.starting_balance - 1) * 100
        
        # Calculate consecutive loss probabilities
        total_losses = sum(consecutive_losses.values())
        consecutive_loss_probs = {
            k: (v / total_losses * 100) if total_losses > 0 else 0.0
            for k, v in consecutive_losses.items()
        }
        
        results = SimulationResults(
            ruin_probability=ruin_probability,
            max_drawdown=max_drawdown_observed,
            avg_drawdown=avg_drawdown,
            expected_return=expected_return,
            median_return=median_return,
            percentile_5=percentile_5,
            percentile_95=percentile_95,
            consecutive_loss_probabilities=consecutive_loss_probs,
            final_balances=final_balances
        )
        
        # Log comprehensive results
        self._log_results(results, config)
        
        return results
    
    def _log_results(self, results: SimulationResults, config: MartingaleConfig):
        """Log comprehensive simulation results."""
        logger.info("=" * 80)
        logger.info("📊 MONTE CARLO SIMULATION RESULTS")
        logger.info("=" * 80)
        
        # Risk metrics
        logger.info(f"🎲 Risk Metrics:")
        logger.info(f"   Ruin Probability (90%+ loss): {results.ruin_probability*100:.2f}%")
        logger.info(f"   Maximum Drawdown Observed: {results.max_drawdown:.1f}%")
        logger.info(f"   Average Maximum Drawdown: {results.avg_drawdown:.1f}%")
        
        # Return metrics
        logger.info(f"💰 Return Metrics:")
        logger.info(f"   Expected Return: {results.expected_return:+.1f}%")
        logger.info(f"   Median Return: {results.median_return:+.1f}%")
        logger.info(f"   5th Percentile (worst 5%): {results.percentile_5:+.1f}%")
        logger.info(f"   95th Percentile (best 5%): {results.percentile_95:+.1f}%")
        
        # Consecutive loss probabilities
        logger.info(f"📉 Consecutive Loss Analysis:")
        for losses, prob in sorted(results.consecutive_loss_probabilities.items()):
            if losses > 0 and prob > 0.01:  # Only show probabilities > 0.01%
                frequency = 1 / (prob / 100) if prob > 0 else float('inf')
                logger.info(f"   {losses} consecutive losses: {prob:.2f}% "
                          f"(happens ~1 in {frequency:.0f} times)")
        
        # Risk warnings
        if results.ruin_probability > 0.01:  # > 1% ruin probability
            logger.warning(f"🚨 HIGH RUIN RISK: {results.ruin_probability*100:.2f}% chance of account blowup detected!")
            logger.warning(f"   This strategy WILL ruin your account approximately 1 in {int(1/results.ruin_probability)} times")
        
        if results.max_drawdown > 50:
            logger.warning(f"⚠️  EXTREME DRAWDOWN: Maximum drawdown of {results.max_drawdown:.1f}% observed in simulations")
        
        if results.expected_return < 0:
            logger.error(f"❌ NEGATIVE EXPECTED VALUE: This strategy loses money on average ({results.expected_return:.1f}%)")
        
        logger.info("=" * 80)
    
    def calculate_theoretical_ruin(self, config: MartingaleConfig) -> float:
        """
        Calculate theoretical probability of N consecutive losses (simplified).
        
        Args:
            config: Martingale configuration
            
        Returns:
            Probability of experiencing max_attempts consecutive losses
        """
        # P(N consecutive losses) = (1 - win_rate) ^ N
        prob_ruin = (1 - config.win_probability) ** (config.max_attempts + 1)
        
        logger.info(f"📐 Theoretical Analysis:")
        logger.info(f"   Win rate: {config.win_probability*100:.1f}%")
        logger.info(f"   P({config.max_attempts + 1} consecutive losses) = {prob_ruin*100:.4f}%")
        logger.info(f"   Expected frequency: 1 in {int(1/prob_ruin):,} trading sequences")
        
        return prob_ruin
    
    def compare_configurations(self, configs: List[Tuple[str, MartingaleConfig]], 
                              trades_per_simulation: int = 100) -> Dict[str, SimulationResults]:
        """
        Compare multiple martingale configurations side-by-side.
        
        Args:
            configs: List of (name, config) tuples to compare
            trades_per_simulation: Number of trades per simulation
            
        Returns:
            Dictionary mapping configuration names to their results
        """
        logger.info(f"🔬 Comparing {len(configs)} martingale configurations...")
        
        results_dict = {}
        for name, config in configs:
            logger.info(f"\n{'='*80}")
            logger.info(f"Simulating: {name}")
            logger.info(f"{'='*80}")
            results = self.simulate_martingale_risk(config, trades_per_simulation)
            results_dict[name] = results
        
        # Print comparison table
        logger.info("\n" + "="*80)
        logger.info("📊 CONFIGURATION COMPARISON")
        logger.info("="*80)
        logger.info(f"{'Configuration':<30} {'Ruin %':<12} {'Avg DD %':<12} {'Exp Return %':<15}")
        logger.info("-"*80)
        
        for name, results in results_dict.items():
            logger.info(
                f"{name:<30} "
                f"{results.ruin_probability*100:>10.2f}% "
                f"{results.avg_drawdown:>10.1f}% "
                f"{results.expected_return:>13.1f}%"
            )
        
        logger.info("="*80)
        
        return results_dict
    
    def generate_risk_report(self, config: MartingaleConfig, 
                           trades_per_simulation: int = 100) -> str:
        """
        Generate a comprehensive risk report for a martingale configuration.
        
        Args:
            config: Martingale configuration to analyze
            trades_per_simulation: Number of trades per simulation
            
        Returns:
            Formatted risk report as string
        """
        results = self.simulate_martingale_risk(config, trades_per_simulation)
        theoretical_ruin = self.calculate_theoretical_ruin(config)
        
        report = []
        report.append("="*80)
        report.append("MARTINGALE STRATEGY RISK REPORT")
        report.append("="*80)
        report.append("")
        report.append("CONFIGURATION:")
        report.append(f"  Initial Position: {config.initial_position_pct*100:.2f}% of account")
        report.append(f"  Multiplier: {config.multiplier}x (capped at {config.max_multiplier}x)")
        report.append(f"  Max Attempts: {config.max_attempts}")
        report.append(f"  Win Rate: {config.win_probability*100:.1f}%")
        report.append(f"  Avg Win: {config.avg_win_pct*100:.1f}% | Avg Loss: {config.avg_loss_pct*100:.1f}%")
        report.append("")
        report.append("SIMULATION RESULTS:")
        report.append(f"  Iterations: {self.iterations:,}")
        report.append(f"  Trades per Simulation: {trades_per_simulation}")
        report.append("")
        report.append("RISK METRICS:")
        report.append(f"  Ruin Probability: {results.ruin_probability*100:.2f}%")
        report.append(f"  Theoretical Ruin Prob: {theoretical_ruin*100:.4f}%")
        report.append(f"  Maximum Drawdown: {results.max_drawdown:.1f}%")
        report.append(f"  Average Drawdown: {results.avg_drawdown:.1f}%")
        report.append("")
        report.append("RETURN METRICS:")
        report.append(f"  Expected Return: {results.expected_return:+.1f}%")
        report.append(f"  Median Return: {results.median_return:+.1f}%")
        report.append(f"  5th Percentile: {results.percentile_5:+.1f}% (worst 5% of cases)")
        report.append(f"  95th Percentile: {results.percentile_95:+.1f}% (best 5% of cases)")
        report.append("")
        
        # Risk warnings
        if results.ruin_probability > 0.05:
            report.append("🚨 CRITICAL RISK WARNING:")
            report.append(f"   This configuration has a {results.ruin_probability*100:.1f}% chance of account ruin!")
            report.append(f"   You will blow up your account approximately 1 in {int(1/results.ruin_probability)} times.")
            report.append("")
        elif results.ruin_probability > 0.01:
            report.append("⚠️  HIGH RISK WARNING:")
            report.append(f"   Ruin probability of {results.ruin_probability*100:.2f}% is concerning.")
            report.append("")
        
        report.append("="*80)
        
        return "\n".join(report)
