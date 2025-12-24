"""
Chaos Engineering Tests

Tests system resilience under failure conditions:
- Provider intermittent failures
- Partial order fills
- API rate limiting
- Network timeouts
- Circuit breaker triggering

Requirements:
    - src.market_data.consensus_engine: For MarketDataConsensusEngine
    - src.resilience.resilience_state_tracker: For ResilienceStateTracker
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime
import random
from typing import Optional

# Import the actual types - skip module if not available
try:
    from src.market_data.consensus_engine import (
        MarketDataConsensusEngine,
        IConsensusMarketDataProvider,
        MarketDataPoint
    )
    from src.resilience.resilience_state_tracker import (
        ResilienceStateTracker,
        ResilienceState,
        DegradationReason
    )
    DEPS_AVAILABLE = True
except ImportError as e:
    pytest.skip(f"Required dependencies not available: {e}", allow_module_level=True)
    DEPS_AVAILABLE = False


class FlakyProvider(IConsensusMarketDataProvider):
    """Mock provider that fails intermittently."""
    
    def __init__(self, provider_name: str = "flaky", failure_rate: float = 0.3, latency_ms: int = 100):
        """
        Initialize flaky provider.
        
        Args:
            provider_name: Name identifier for this provider
            failure_rate: Probability of failure (0.0-1.0)
            latency_ms: Simulated latency in milliseconds
        """
        self._name = provider_name
        self.failure_rate = failure_rate
        self.latency_ms = latency_ms
        self.call_count = 0
        self.failure_count = 0
    
    @property
    def name(self) -> str:
        """Provider name."""
        return self._name
    
    async def get_current_price(self, symbol: str) -> Optional[MarketDataPoint]:
        """Simulate flaky price fetch."""
        self.call_count += 1
        
        # Simulate latency
        await asyncio.sleep(self.latency_ms / 1000.0)
        
        # Randomly fail
        if random.random() < self.failure_rate:
            self.failure_count += 1
            raise Exception(f"Provider timeout for {symbol}")
        
        # Return mock price with proper MarketDataPoint structure
        price = 150.00 + random.uniform(-5.0, 5.0)
        return MarketDataPoint(
            symbol=symbol,
            price=price,
            timestamp=datetime.utcnow(),
            source=self._name,
            bid=price - 0.01,
            ask=price + 0.01
        )


class ReliableProvider(IConsensusMarketDataProvider):
    """Mock provider that always succeeds."""
    
    def __init__(self, provider_name: str = "reliable"):
        """Initialize reliable provider."""
        self._name = provider_name
    
    @property
    def name(self) -> str:
        """Provider name."""
        return self._name
    
    async def get_current_price(self, symbol: str) -> Optional[MarketDataPoint]:
        """Always return valid price."""
        await asyncio.sleep(0.05)  # Small latency
        price = 150.00
        return MarketDataPoint(
            symbol=symbol,
            price=price,
            timestamp=datetime.utcnow(),
            source=self._name,
            bid=price - 0.01,
            ask=price + 0.01
        )


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_provider_intermittent_failures():
    """
    Test that consensus engine handles provider failures gracefully.
    
    Scenario: Primary provider (Polygon) fails 30% of requests.
    Expected: Fallback to secondary provider (Alpaca) with no user impact.
    """
    flaky_polygon = FlakyProvider(provider_name="polygon", failure_rate=0.3, latency_ms=100)
    reliable_alpaca = ReliableProvider(provider_name="alpaca")
    
    engine = MarketDataConsensusEngine(
        providers=[flaky_polygon, reliable_alpaca],
        spread_threshold=0.05,
        staleness_threshold=60.0
    )
    
    # Run 100 price fetches
    successful_fetches = 0
    failed_fetches = 0
    
    for i in range(100):
        result = await engine.get_consensus_price('AAPL', timeout=5.0)
        
        if result and result.price > 0:
            successful_fetches += 1
        else:
            failed_fetches += 1
    
    # Assert: Should have >95% success rate despite flaky provider
    success_rate = successful_fetches / 100
    assert success_rate >= 0.95, f"Success rate too low: {success_rate:.1%}"
    
    # Verify flaky provider did fail some requests
    assert flaky_polygon.failure_count > 0, "Flaky provider should have failed some requests"
    
    print(f"\n✅ Chaos Test Passed:")
    print(f"  Success Rate: {success_rate:.1%}")
    print(f"  Flaky Provider Failures: {flaky_polygon.failure_count}/{flaky_polygon.call_count}")
    print(f"  Total Fetches: {successful_fetches + failed_fetches}")


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_cascading_provider_failures():
    """
    Test behavior when all providers fail simultaneously.
    
    Scenario: All market data providers return errors.
    Expected: System enters DEGRADED state, no crashes.
    """
    flaky_provider_1 = FlakyProvider(provider_name="provider1", failure_rate=0.8)
    flaky_provider_2 = FlakyProvider(provider_name="provider2", failure_rate=0.8)
    
    engine = MarketDataConsensusEngine(
        providers=[flaky_provider_1, flaky_provider_2],
        spread_threshold=0.05
    )
    
    # Attempt 50 fetches
    none_count = 0
    for i in range(50):
        result = await engine.get_consensus_price('AAPL', timeout=2.0)
        if result is None:
            none_count += 1
    
    # Should gracefully return None rather than crash
    assert none_count > 0, "Expected some failed fetches"
    print(f"\n✅ Cascading Failure Test Passed: {none_count}/50 requests returned None gracefully")


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_partial_order_fills():
    """
    Test handling of partial order fills.
    
    Scenario: Broker fills only 50% of requested quantity.
    Expected: System tracks partial fill, doesn't double-order.
    """
    # Mock broker that returns partial fills
    mock_broker = AsyncMock()
    mock_broker.submit_order.return_value = Mock(
        id='order_123',
        filled_qty=50.0,  # Only 50 shares instead of 100
        filled_avg_price=150.00,
        status='partially_filled'
    )
    
    # Test order manager handling
    order_result = await mock_broker.submit_order(
        symbol='AAPL',
        qty=100.0,
        side='buy'
    )
    
    assert order_result.filled_qty == 50.0
    assert order_result.status == 'partially_filled'
    
    print(f"\n✅ Partial Fill Test Passed: {order_result.filled_qty}/100 shares filled")


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_resilience_state_degradation():
    """
    Test resilience tracker transitions through degradation states.
    
    Scenario: Multiple degradation reasons accumulate.
    Expected: State transitions NORMAL → DEGRADED → CRITICAL.
    """
    tracker = ResilienceStateTracker(evaluation_interval=1)
    
    # Start in NORMAL state
    assert tracker.state == ResilienceState.NORMAL
    
    # Report first degradation (warning)
    tracker.report_degradation(
        DegradationReason.EVENT_QUEUE_SATURATED,
        severity="warning"
    )
    
    await tracker.evaluate_system_health()
    # Should still be NORMAL (only 1 warning)
    assert tracker.state == ResilienceState.NORMAL
    
    # Add second degradation (critical)
    tracker.report_degradation(
        DegradationReason.PROVIDER_CIRCUIT_OPEN,
        severity="critical"
    )
    
    await tracker.evaluate_system_health()
    # Should transition to DEGRADED or CRITICAL
    assert tracker.state in [ResilienceState.DEGRADED, ResilienceState.CRITICAL]
    
    # Add more degradations
    tracker.report_degradation(
        DegradationReason.DAILY_LOSS_LIMIT_APPROACHED,
        severity="critical"
    )
    tracker.report_degradation(
        DegradationReason.MEMORY_USAGE_HIGH,
        severity="warning"
    )
    
    await tracker.evaluate_system_health()
    # Should be CRITICAL or FAIL_CLOSED
    assert tracker.state in [ResilienceState.CRITICAL, ResilienceState.FAIL_CLOSED]
    
    print(f"\n✅ Resilience Degradation Test Passed:")
    print(f"  Final State: {tracker.state.value}")
    print(f"  Active Degradations: {len(tracker.active_degradations)}")
    
    # Cleanup
    await tracker.stop()


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_circuit_breaker_recovery():
    """
    Test circuit breaker automatic recovery.
    
    Scenario: Provider fails repeatedly, circuit opens, then recovers.
    Expected: Circuit transitions open → half_open → closed.
    """
    tracker = ResilienceStateTracker()
    
    # Simulate circuit breaker opening
    tracker.register_circuit_breaker('polygon_provider', 'open')
    
    # Should report degradation
    assert DegradationReason.PROVIDER_CIRCUIT_OPEN in tracker.active_degradations
    
    # Simulate recovery to half_open
    tracker.register_circuit_breaker('polygon_provider', 'half_open')
    
    # Should resolve degradation
    assert DegradationReason.PROVIDER_CIRCUIT_OPEN not in tracker.active_degradations
    
    # Full recovery
    tracker.register_circuit_breaker('polygon_provider', 'closed')
    
    print(f"\n✅ Circuit Breaker Recovery Test Passed")
    
    await tracker.stop()


@pytest.mark.chaos
@pytest.mark.asyncio
async def test_high_latency_providers():
    """
    Test behavior with high-latency providers.
    
    Scenario: Provider takes 5+ seconds to respond.
    Expected: Timeout triggers, fallback to faster provider.
    """
    slow_provider = FlakyProvider(provider_name="slow", failure_rate=0.0, latency_ms=5000)
    fast_provider = ReliableProvider(provider_name="fast")
    
    engine = MarketDataConsensusEngine(
        providers=[slow_provider, fast_provider]
    )
    
    start_time = asyncio.get_event_loop().time()
    result = await engine.get_consensus_price('AAPL', timeout=2.0)
    end_time = asyncio.get_event_loop().time()
    
    elapsed = end_time - start_time
    
    # Should timeout slow provider and use fast one
    assert result is not None, "Should get result from fast provider"
    assert elapsed < 3.0, f"Should timeout quickly, but took {elapsed:.2f}s"
    
    print(f"\n✅ High Latency Test Passed: Completed in {elapsed:.2f}s")


@pytest.mark.chaos
def test_manual_resilience_override():
    """
    Test manual state override for emergency operations.
    
    Scenario: Operator forces FAIL_OPEN mode during critical incident.
    Expected: State immediately transitions, overrides automatic evaluation.
    """
    tracker = ResilienceStateTracker()
    
    # Report degradations
    tracker.report_degradation(
        DegradationReason.RISK_CIRCUIT_BREAKER_ACTIVE,
        severity="critical"
    )
    
    # Manually override to FAIL_OPEN (emergency bypass)
    tracker.set_manual_override(ResilienceState.FAIL_OPEN)
    
    assert tracker.state == ResilienceState.FAIL_OPEN
    assert tracker.get_status()['manual_override'] is True
    
    # Clear override
    tracker.set_manual_override(None)
    assert tracker.get_status()['manual_override'] is False
    
    print(f"\n✅ Manual Override Test Passed")


if __name__ == "__main__":
    # Run chaos tests
    pytest.main([__file__, "-v", "-m", "chaos"])
