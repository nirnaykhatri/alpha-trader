# Property-Based Testing with Hypothesis

This directory contains property-based tests using the [Hypothesis](https://hypothesis.readthedocs.io/) library.

## What is Property-Based Testing?

Property-based testing validates **invariants** - conditions that should ALWAYS be true regardless of input values. Instead of writing specific test cases with hardcoded values, you define properties and let Hypothesis generate hundreds or thousands of random test cases automatically.

## Installation

```bash
pip install hypothesis
```

## Test Files

### `test_strategy_invariants.py` (320 lines)
Tests trading strategy invariants:
- ✅ **Profit Calculation**: Profit percentage consistent with position direction
- ✅ **Progressive DCA Pricing**: Long DCA prices decrease, short DCA prices increase
- ✅ **Support Levels**: Support always below current price for longs
- ✅ **Resistance Levels**: Resistance always above current price for shorts
- ✅ **Average Price Calculation**: New average is weighted correctly after DCA
- ✅ **DCA Improves Average**: DCA at better price improves position average
- ✅ **Position Value**: Always positive regardless of direction
- ✅ **DCA Limits**: Never exceeds configured maximum attempts

### `test_risk_invariants.py` (310 lines)
Tests risk management invariants:
- ✅ **Consecutive Loss Limits**: Never exceeds configured maximum
- ✅ **Symbol Loss Limits**: Per-symbol loss never exceeds 25% of account
- ✅ **Individual Loss Limits**: Single trade loss never exceeds 10% of account
- ✅ **Multiplier Limits**: Martingale multiplier never exceeds maximum
- ✅ **Position Size Limits**: Position never exceeds account balance without margin
- ✅ **Progressive Sizing**: DCA sizes increase monotonically with multiplier > 1
- ✅ **Kelly Criterion**: Position size between 0% and 100% of account
- ✅ **Daily Loss Limits**: Daily losses never exceed 10% (circuit breaker)
- ✅ **Weekly Loss Limits**: Weekly losses never exceed 20% (circuit breaker)
- ✅ **Fibonacci Scaling**: Follows mathematical sequence F(n) = F(n-1) + F(n-2)
- ✅ **Risk Diversification**: Total risk distributed across positions

## Running Property Tests

### Run all property tests
```bash
pytest tests/property/ -v
```

### Run specific test file
```bash
pytest tests/property/test_strategy_invariants.py -v
pytest tests/property/test_risk_invariants.py -v
```

### Run specific test
```bash
pytest tests/property/test_strategy_invariants.py::test_progressive_dca_pricing_invariant -v
```

### Run with more examples (default is 100)
```bash
pytest tests/property/ -v --hypothesis-show-statistics
```

## Example Output

```
tests/property/test_strategy_invariants.py::test_profit_calculation_invariant PASSED [100 examples]
tests/property/test_strategy_invariants.py::test_progressive_dca_pricing_invariant PASSED [100 examples]
tests/property/test_strategy_invariants.py::test_support_levels_invariant PASSED [50 examples]
tests/property/test_risk_invariants.py::test_consecutive_loss_limit_invariant PASSED [100 examples]
tests/property/test_risk_invariants.py::test_kelly_criterion_invariant PASSED [100 examples]
```

## Custom Strategies

The tests define custom Hypothesis strategies for trading domain objects:

- `position_strategy()`: Generate valid PositionState objects
- `dca_position_strategy()`: Generate positions with DCA history
- `support_levels_strategy()`: Generate support levels (always below current price)
- `resistance_levels_strategy()`: Generate resistance levels (always above current price)
- `account_balance_strategy()`: Generate realistic account balances ($1K - $1M)
- `loss_amount_strategy()`: Generate loss amounts relative to account
- `position_size_strategy()`: Generate position sizes relative to account
- `multiplier_strategy()`: Generate martingale multipliers (1.1x - 3.0x)

## Benefits

1. **Catches Edge Cases**: Finds bugs that manual testing misses
2. **Automatic Test Generation**: Hypothesis generates diverse test inputs
3. **Regression Prevention**: Shrinks failing cases to minimal reproducible examples
4. **Documentation**: Properties serve as executable specifications
5. **Confidence**: Hundreds of randomized tests provide strong validation

## Integration with CI/CD

Add to your CI pipeline:

```yaml
# .github/workflows/tests.yml
- name: Run property-based tests
  run: pytest tests/property/ --hypothesis-show-statistics
```

## Configuration

Hypothesis settings can be customized:

```python
from hypothesis import settings

@given(position=position_strategy())
@settings(
    max_examples=500,  # Run 500 random examples
    deadline=None,      # No time limit per test
    print_blob=True     # Print reproducible test data
)
def test_my_invariant(position):
    # Test code
```

## Debugging Failed Tests

When a property test fails, Hypothesis automatically shrinks the failing input to the simplest case:

```
Falsifying example:
    position = PositionState(
        symbol='AAPL',
        quantity=1.0,
        average_price=100.0,
        current_price=99.0,
        ...
    )
```

This makes debugging much easier than traditional randomized testing.

## Further Reading

- [Hypothesis Documentation](https://hypothesis.readthedocs.io/)
- [Property-Based Testing Guide](https://increment.com/testing/in-praise-of-property-based-testing/)
- [Hypothesis Best Practices](https://hypothesis.readthedocs.io/en/latest/quickstart.html)
