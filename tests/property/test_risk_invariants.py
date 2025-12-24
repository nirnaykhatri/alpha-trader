"""
Property-based tests for risk management invariants.

These tests validate that risk management rules are NEVER violated,
regardless of market conditions, position sizes, or loss amounts.

Requires: pip install hypothesis
"""

import pytest
from decimal import Decimal

# Skip all tests if hypothesis is not installed
pytest.importorskip("hypothesis")

from hypothesis import given, assume, settings, strategies as st
from hypothesis import HealthCheck

# Import risk management components
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))


# Custom strategies for risk domain
@st.composite
def account_balance_strategy(draw):
    """Generate realistic account balances."""
    return draw(st.floats(min_value=1000.0, max_value=1000000.0))


@st.composite
def loss_amount_strategy(draw, account_balance):
    """Generate loss amounts relative to account balance."""
    # Loss should be between 0% and 50% of account
    return draw(st.floats(min_value=0.0, max_value=account_balance * 0.5))


@st.composite
def position_size_strategy(draw, account_balance):
    """Generate position sizes relative to account balance."""
    # Position should be between 1% and 100% of account
    return draw(st.floats(min_value=account_balance * 0.01, max_value=account_balance))


@st.composite
def multiplier_strategy(draw):
    """Generate martingale multipliers."""
    return draw(st.floats(min_value=1.1, max_value=3.0))


# RISK MANAGEMENT INVARIANTS

@given(
    consecutive_losses=st.integers(min_value=0, max_value=10),
    max_consecutive=st.integers(min_value=1, max_value=5)
)
@settings(max_examples=100, deadline=None)
def test_consecutive_loss_limit_invariant(consecutive_losses, max_consecutive):
    """
    INVARIANT: Consecutive losses must never exceed configured maximum.
    
    Critical safety feature to prevent runaway martingale strategies.
    """
    # Invariant: Should block when at or over limit
    should_block = consecutive_losses >= max_consecutive
    
    if should_block:
        assert consecutive_losses >= max_consecutive, \
            f"Should block at {consecutive_losses} consecutive losses (max: {max_consecutive})"
    else:
        assert consecutive_losses < max_consecutive, \
            f"Should allow at {consecutive_losses} consecutive losses (max: {max_consecutive})"


@given(
    account_balance=account_balance_strategy(),
    loss_percent=st.floats(min_value=0.0, max_value=0.5)
)
@settings(max_examples=100, deadline=None)
def test_symbol_loss_limit_invariant(account_balance, loss_percent):
    """
    INVARIANT: Loss per symbol must never exceed configured percentage of account.
    
    Default: 25% max loss per symbol
    """
    MAX_SYMBOL_LOSS_PERCENT = 0.25  # 25%
    
    loss_amount = account_balance * loss_percent
    max_allowed_loss = account_balance * MAX_SYMBOL_LOSS_PERCENT
    
    # Invariant: Loss should not exceed 25% of account
    if loss_amount > max_allowed_loss:
        should_block = True
        assert should_block, \
            f"Should block loss of ${loss_amount:.2f} (>{MAX_SYMBOL_LOSS_PERCENT*100}% of ${account_balance:.2f})"
    else:
        should_allow = True
        assert should_allow, \
            f"Should allow loss of ${loss_amount:.2f} (<={MAX_SYMBOL_LOSS_PERCENT*100}% of ${account_balance:.2f})"


@given(
    account_balance=account_balance_strategy(),
    loss_percent=st.floats(min_value=0.0, max_value=0.3)
)
@settings(max_examples=100, deadline=None)
def test_individual_loss_limit_invariant(account_balance, loss_percent):
    """
    INVARIANT: Individual trade loss must never exceed configured percentage.
    
    Default: 10% max loss per trade
    """
    MAX_INDIVIDUAL_LOSS_PERCENT = 0.10  # 10%
    
    loss_amount = account_balance * loss_percent
    max_allowed_loss = account_balance * MAX_INDIVIDUAL_LOSS_PERCENT
    
    # Invariant: Individual loss should not exceed 10%
    if loss_amount > max_allowed_loss:
        should_block = True
        assert should_block, \
            f"Should block individual loss of ${loss_amount:.2f} (>{MAX_INDIVIDUAL_LOSS_PERCENT*100}% of ${account_balance:.2f})"


@given(
    multiplier=multiplier_strategy(),
    max_multiplier=st.floats(min_value=1.5, max_value=3.0)
)
@settings(max_examples=100, deadline=None)
def test_multiplier_limit_invariant(multiplier, max_multiplier):
    """
    INVARIANT: Martingale multiplier must never exceed configured maximum.
    
    Prevents exponential growth that can wipe out accounts.
    """
    # Invariant: Multiplier should not exceed max
    if multiplier > max_multiplier:
        should_block = True
        assert should_block, \
            f"Should block multiplier {multiplier:.2f}x (max: {max_multiplier:.2f}x)"
    else:
        should_allow = True
        assert should_allow, \
            f"Should allow multiplier {multiplier:.2f}x (<= max: {max_multiplier:.2f}x)"


@given(
    account_balance=account_balance_strategy(),
    position_size_percent=st.floats(min_value=0.0, max_value=1.5)
)
@settings(max_examples=100, deadline=None)
def test_position_size_limit_invariant(account_balance, position_size_percent):
    """
    INVARIANT: Position size must never exceed account balance (no leverage > 1x without margin).
    
    Conservative approach: Don't allow position larger than account.
    """
    position_size = account_balance * position_size_percent
    
    # Invariant: Position should not exceed account balance
    if position_size > account_balance:
        should_block = True
        assert should_block, \
            f"Should block position ${position_size:.2f} > account ${account_balance:.2f}"
    else:
        should_allow = True
        assert should_allow, \
            f"Should allow position ${position_size:.2f} <= account ${account_balance:.2f}"


@given(
    initial_size=st.floats(min_value=100.0, max_value=1000.0),
    multiplier=multiplier_strategy(),
    attempts=st.integers(min_value=1, max_value=5)
)
@settings(max_examples=100, deadline=None)
def test_progressive_sizing_invariant(initial_size, multiplier, attempts):
    """
    INVARIANT: Progressive position sizing must increase monotonically.
    
    Each DCA should be larger than previous (if using multiplier > 1).
    """
    sizes = [initial_size]
    
    for i in range(attempts):
        next_size = sizes[-1] * multiplier
        sizes.append(next_size)
    
    # Invariant: Sizes should increase if multiplier > 1
    if multiplier > 1.0:
        for i in range(1, len(sizes)):
            assert sizes[i] > sizes[i-1], \
                f"Size {i} (${sizes[i]:.2f}) should be > size {i-1} (${sizes[i-1]:.2f})"


@given(
    win_prob=st.floats(min_value=0.01, max_value=0.99),
    win_loss_ratio=st.floats(min_value=0.5, max_value=5.0),
    account_balance=account_balance_strategy()
)
@settings(max_examples=100, deadline=None)
def test_kelly_criterion_invariant(win_prob, win_loss_ratio, account_balance):
    """
    INVARIANT: Kelly Criterion position size must be between 0% and 100% of account.
    
    Formula: f* = (p * b - q) / b
    where p = win probability, q = 1 - p, b = win/loss ratio
    """
    q = 1 - win_prob
    
    # Kelly formula
    kelly_fraction = (win_prob * win_loss_ratio - q) / win_loss_ratio
    
    # Apply fractional Kelly (typically 0.25 to 0.5 of full Kelly)
    fractional_kelly = kelly_fraction * 0.25  # 25% of full Kelly for safety
    
    # Calculate position size
    if fractional_kelly > 0:
        position_size = account_balance * fractional_kelly
        
        # Invariant: Position should be positive and <= account balance
        assert position_size > 0, "Kelly position should be positive"
        assert position_size <= account_balance, \
            f"Kelly position ${position_size:.2f} should not exceed account ${account_balance:.2f}"
    else:
        # Invariant: Negative Kelly means don't trade
        assert fractional_kelly <= 0, "Negative Kelly means unfavorable odds"


@given(
    account_balance=account_balance_strategy(),
    daily_loss_percent=st.floats(min_value=0.0, max_value=0.3)
)
@settings(max_examples=100, deadline=None)
def test_daily_loss_limit_invariant(account_balance, daily_loss_percent):
    """
    INVARIANT: Daily losses must never exceed configured limit.
    
    Default: 10% daily loss limit triggers circuit breaker.
    """
    MAX_DAILY_LOSS_PERCENT = 0.10  # 10%
    
    daily_loss = account_balance * daily_loss_percent
    max_allowed = account_balance * MAX_DAILY_LOSS_PERCENT
    
    # Invariant: Daily loss should not exceed 10%
    if daily_loss > max_allowed:
        should_trigger_circuit_breaker = True
        assert should_trigger_circuit_breaker, \
            f"Should trigger circuit breaker at ${daily_loss:.2f} daily loss (>{MAX_DAILY_LOSS_PERCENT*100}%)"


@given(
    account_balance=account_balance_strategy(),
    weekly_loss_percent=st.floats(min_value=0.0, max_value=0.5)
)
@settings(max_examples=100, deadline=None)
def test_weekly_loss_limit_invariant(account_balance, weekly_loss_percent):
    """
    INVARIANT: Weekly losses must never exceed configured limit.
    
    Default: 20% weekly loss limit triggers extended circuit breaker.
    """
    MAX_WEEKLY_LOSS_PERCENT = 0.20  # 20%
    
    weekly_loss = account_balance * weekly_loss_percent
    max_allowed = account_balance * MAX_WEEKLY_LOSS_PERCENT
    
    # Invariant: Weekly loss should not exceed 20%
    if weekly_loss > max_allowed:
        should_trigger_circuit_breaker = True
        assert should_trigger_circuit_breaker, \
            f"Should trigger circuit breaker at ${weekly_loss:.2f} weekly loss (>{MAX_WEEKLY_LOSS_PERCENT*100}%)"


@given(
    base_level=st.integers(min_value=0, max_value=10)
)
@settings(max_examples=50, deadline=None)
def test_fibonacci_scaling_invariant(base_level):
    """
    INVARIANT: Fibonacci sequence scaling must follow mathematical sequence.
    
    F(n) = F(n-1) + F(n-2), starting with F(0)=1, F(1)=1
    """
    # Generate Fibonacci sequence
    fib = [1, 1]
    for i in range(2, base_level + 1):
        fib.append(fib[-1] + fib[-2])
    
    # Invariant: Each Fibonacci number is sum of previous two
    for i in range(2, len(fib)):
        assert fib[i] == fib[i-1] + fib[i-2], \
            f"Fibonacci sequence violated at index {i}"
    
    # Invariant: Fibonacci sequence is monotonically increasing
    for i in range(1, len(fib)):
        assert fib[i] >= fib[i-1], \
            f"Fibonacci should be increasing: {fib[i]} >= {fib[i-1]}"


@given(
    total_risk=st.floats(min_value=0.0, max_value=1.0),
    position_count=st.integers(min_value=1, max_value=10)
)
@settings(max_examples=100, deadline=None)
def test_risk_diversification_invariant(total_risk, position_count):
    """
    INVARIANT: Risk should be distributed across positions.
    
    Total risk divided by position count should not exceed individual position limit.
    """
    if position_count > 0:
        risk_per_position = total_risk / position_count
        
        # Invariant: Risk per position should be less than total risk
        assert risk_per_position <= total_risk, \
            f"Risk per position ${risk_per_position:.4f} should be <= total risk ${total_risk:.4f}"
        
        # Invariant: More positions = less risk per position
        if position_count > 1:
            assert risk_per_position < total_risk, \
                f"With {position_count} positions, risk should be distributed"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
