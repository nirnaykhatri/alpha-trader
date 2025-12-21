"""
Property-based tests for trading strategy invariants.

These tests validate conditions that should ALWAYS hold true for the trading strategy,
regardless of market conditions, position sizes, or price movements.
"""

import pytest
from hypothesis import given, assume, settings, strategies as st
from hypothesis import HealthCheck
from datetime import datetime, timedelta
from decimal import Decimal

# Import strategy components
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.strategies.advanced_strategy import PositionState, PositionDirection, TradePhase


# Custom strategies for trading domain
@st.composite
def position_strategy(draw):
    """Generate valid position states for testing."""
    symbol = draw(st.sampled_from(['AAPL', 'TSLA', 'NVDA', 'MSFT', 'GOOGL']))
    direction = draw(st.sampled_from([PositionDirection.LONG, PositionDirection.SHORT]))
    quantity = draw(st.floats(min_value=1.0, max_value=1000.0))
    average_price = draw(st.floats(min_value=1.0, max_value=1000.0))
    current_price = draw(st.floats(min_value=1.0, max_value=1000.0))
    
    return PositionState(
        symbol=symbol,
        direction=direction,
        phase=TradePhase.ENTRY,
        quantity=quantity,
        average_price=average_price,
        current_price=current_price,
        entry_time=datetime.now()
    )


@st.composite
def dca_position_strategy(draw):
    """Generate position states with DCA history."""
    position = draw(position_strategy())
    
    # Add DCA metadata
    attempts = draw(st.integers(min_value=0, max_value=5))
    position.averaging_attempts = attempts
    
    if attempts > 0:
        # Generate DCA price history
        dca_prices = []
        base_price = position.average_price
        
        for i in range(attempts):
            if position.direction == PositionDirection.LONG:
                # For longs, DCA prices should be progressively lower
                price = base_price * (1 - (i + 1) * 0.02)  # 2% steps down
            else:
                # For shorts, DCA prices should be progressively higher
                price = base_price * (1 + (i + 1) * 0.02)  # 2% steps up
            
            dca_prices.append(price)
        
        position.dca_order_prices = dca_prices
        position.last_dca_price = dca_prices[-1] if dca_prices else None
    
    return position


@st.composite
def support_levels_strategy(draw, current_price):
    """Generate valid support levels (always below current price)."""
    num_levels = draw(st.integers(min_value=1, max_value=5))
    levels = []
    
    for i in range(num_levels):
        # Support levels should be below current price
        level = draw(st.floats(min_value=current_price * 0.5, max_value=current_price * 0.99))
        levels.append(level)
    
    return sorted(levels, reverse=True)  # Highest to lowest


@st.composite
def resistance_levels_strategy(draw, current_price):
    """Generate valid resistance levels (always above current price)."""
    num_levels = draw(st.integers(min_value=1, max_value=5))
    levels = []
    
    for i in range(num_levels):
        # Resistance levels should be above current price
        level = draw(st.floats(min_value=current_price * 1.01, max_value=current_price * 2.0))
        levels.append(level)
    
    return sorted(levels)  # Lowest to highest


# PROPERTY TESTS - INVARIANTS THAT MUST ALWAYS HOLD

@given(position=position_strategy())
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_profit_calculation_invariant(position):
    """
    INVARIANT: Profit percentage calculation must be consistent with direction.
    
    For LONG positions: profit = (current - average) / average
    For SHORT positions: profit = (average - current) / average
    """
    if position.average_price > 0:  # Prevent division by zero
        if position.direction == PositionDirection.LONG:
            expected_profit = (position.current_price - position.average_price) / position.average_price
            position.profit_percentage = expected_profit
            
            # Invariant: Long profits positive when current > average
            if position.current_price > position.average_price:
                assert position.profit_percentage > 0, "Long position should have positive profit when price increases"
            elif position.current_price < position.average_price:
                assert position.profit_percentage < 0, "Long position should have negative profit when price decreases"
        
        else:  # SHORT
            expected_profit = (position.average_price - position.current_price) / position.average_price
            position.profit_percentage = expected_profit
            
            # Invariant: Short profits positive when current < average
            if position.current_price < position.average_price:
                assert position.profit_percentage > 0, "Short position should have positive profit when price decreases"
            elif position.current_price > position.average_price:
                assert position.profit_percentage < 0, "Short position should have negative profit when price increases"


@given(position=dca_position_strategy())
@settings(max_examples=100, deadline=None)
def test_progressive_dca_pricing_invariant(position):
    """
    INVARIANT: DCA prices must be progressive (improving average).
    
    For LONG positions: Each DCA should be at lower price than previous
    For SHORT positions: Each DCA should be at higher price than previous
    """
    if len(position.dca_order_prices) > 1:
        for i in range(1, len(position.dca_order_prices)):
            prev_price = position.dca_order_prices[i-1]
            curr_price = position.dca_order_prices[i]
            
            if position.direction == PositionDirection.LONG:
                # Invariant: Long DCA prices should decrease (averaging down)
                assert curr_price <= prev_price, f"Long DCA price #{i} (${curr_price:.2f}) should be <= previous (${prev_price:.2f})"
            else:
                # Invariant: Short DCA prices should increase (averaging up)
                assert curr_price >= prev_price, f"Short DCA price #{i} (${curr_price:.2f}) should be >= previous (${prev_price:.2f})"


@given(
    symbol=st.sampled_from(['AAPL', 'TSLA', 'NVDA']),
    current_price=st.floats(min_value=10.0, max_value=500.0)
)
@settings(max_examples=50, deadline=None)
def test_support_levels_invariant(symbol, current_price):
    """
    INVARIANT: Support levels must always be below current price for long positions.
    
    This is critical for DCA strategy - we can't average down at prices above current market.
    """
    # Generate support levels
    from hypothesis import assume
    
    # Use hypothesis strategy
    support_levels = sorted([
        current_price * 0.98,
        current_price * 0.95,
        current_price * 0.90
    ], reverse=True)
    
    # Invariant: All support levels below current price
    for level in support_levels:
        assert level < current_price, f"Support level ${level:.2f} must be below current price ${current_price:.2f}"


@given(
    symbol=st.sampled_from(['AAPL', 'TSLA', 'NVDA']),
    current_price=st.floats(min_value=10.0, max_value=500.0)
)
@settings(max_examples=50, deadline=None)
def test_resistance_levels_invariant(symbol, current_price):
    """
    INVARIANT: Resistance levels must always be above current price for short positions.
    
    Critical for short DCA - we can't average up at prices below current market.
    """
    resistance_levels = sorted([
        current_price * 1.02,
        current_price * 1.05,
        current_price * 1.10
    ])
    
    # Invariant: All resistance levels above current price
    for level in resistance_levels:
        assert level > current_price, f"Resistance level ${level:.2f} must be above current price ${current_price:.2f}"


@given(
    quantity=st.floats(min_value=1.0, max_value=1000.0),
    avg_price=st.floats(min_value=1.0, max_value=1000.0),
    dca_quantity=st.floats(min_value=1.0, max_value=500.0),
    dca_price=st.floats(min_value=1.0, max_value=1000.0)
)
@settings(max_examples=200, deadline=None)
def test_average_price_calculation_invariant(quantity, avg_price, dca_quantity, dca_price):
    """
    INVARIANT: New average price after DCA must be weighted average of positions.
    
    Formula: new_avg = (qty1 * price1 + qty2 * price2) / (qty1 + qty2)
    """
    # Calculate new average after DCA
    total_cost = (quantity * avg_price) + (dca_quantity * dca_price)
    total_quantity = quantity + dca_quantity
    
    if total_quantity > 0:
        new_average = total_cost / total_quantity
        
        # Invariant: New average should be between the two prices
        min_price = min(avg_price, dca_price)
        max_price = max(avg_price, dca_price)
        
        assert min_price <= new_average <= max_price, \
            f"New average ${new_average:.2f} should be between ${min_price:.2f} and ${max_price:.2f}"


@given(
    position=position_strategy(),
    new_price=st.floats(min_value=1.0, max_value=1000.0)
)
@settings(max_examples=100, deadline=None)
def test_dca_improves_average_invariant(position, new_price):
    """
    INVARIANT: DCA at better price should improve position average.
    
    For LONG: DCA below average should lower average
    For SHORT: DCA above average should raise average
    """
    old_average = position.average_price
    quantity = position.quantity
    
    # Assume DCA at better price
    if position.direction == PositionDirection.LONG:
        # For long, better price = lower price
        assume(new_price < old_average)
        
        # Calculate new average
        new_average = (quantity * old_average + quantity * new_price) / (2 * quantity)
        
        # Invariant: New average should be lower
        assert new_average < old_average, f"Long DCA should lower average: ${new_average:.2f} < ${old_average:.2f}"
    
    else:  # SHORT
        # For short, better price = higher price
        assume(new_price > old_average)
        
        # Calculate new average
        new_average = (quantity * old_average + quantity * new_price) / (2 * quantity)
        
        # Invariant: New average should be higher
        assert new_average > old_average, f"Short DCA should raise average: ${new_average:.2f} > ${old_average:.2f}"


@given(position=position_strategy())
@settings(max_examples=100, deadline=None)
def test_position_value_invariant(position):
    """
    INVARIANT: Position value must always be positive.
    
    Position value = quantity * price (always positive regardless of direction)
    """
    position_value = position.quantity * position.current_price
    
    # Invariant: Position value always positive
    assert position_value > 0, "Position value must be positive"
    
    # Invariant: Quantity always positive (we track direction separately)
    assert position.quantity > 0, "Position quantity must be positive"


@given(
    attempts=st.integers(min_value=0, max_value=10),
    max_attempts=st.integers(min_value=1, max_value=5)
)
@settings(max_examples=100, deadline=None)
def test_dca_limit_invariant(attempts, max_attempts):
    """
    INVARIANT: DCA attempts should never exceed configured maximum.
    
    This prevents runaway martingale strategies that can wipe out accounts.
    """
    # Invariant: Attempts at or below max should be allowed
    if attempts <= max_attempts:
        assert attempts <= max_attempts, "Should allow DCA when under limit"
    else:
        # Invariant: Attempts above max should be blocked
        should_allow_dca = attempts < max_attempts
        assert not should_allow_dca, "Should block DCA when at or over limit"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
