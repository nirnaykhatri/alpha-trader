"""
Phase-Level Latency Metrics

Provides granular latency tracking for decision pipeline phases with
p95/p99 percentile observability.
"""

import logging
import functools
from time import perf_counter
from typing import Callable, TypeVar, ParamSpec, Awaitable
from contextlib import asynccontextmanager
from prometheus_client import Histogram

logger = logging.getLogger(__name__)

# Type variables for generic decorator
P = ParamSpec('P')
T = TypeVar('T')


# Phase-tagged latency histogram
phase_latency_seconds = Histogram(
    'trading_bot_decision_phase_latency_seconds',
    'Latency per decision pipeline phase (p95/p99 observable)',
    ['phase', 'symbol'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)


class DecisionPhase:
    """Enumeration of decision pipeline phases."""
    
    # Market data phases
    MARKET_DATA_FETCH = "market_data_fetch"
    CONSENSUS_RESOLUTION = "consensus_resolution"
    
    # Analysis phases
    TECHNICAL_ANALYSIS = "technical_analysis"
    CONFIDENCE_CALCULATION = "confidence_calculation"
    
    # Decision phases
    RISK_VALIDATION = "risk_validation"
    POSITION_SIZING = "position_sizing"
    DCA_EVALUATION = "dca_evaluation"
    
    # Execution phases
    ORDER_PLACEMENT = "order_placement"
    ORDER_FILL_WAIT = "order_fill_wait"
    
    # Complete pipeline
    TOTAL_DECISION = "total_decision"


def timed_phase(phase: str, symbol: str = "unknown"):
    """
    Decorator to time async function execution with phase labeling.
    
    Args:
        phase: Phase name (use DecisionPhase constants)
        symbol: Trading symbol for correlation
    
    Example:
        @timed_phase(DecisionPhase.CONFIDENCE_CALCULATION, symbol="AAPL")
        async def calculate_confidence(context):
            # ... confidence logic
            return score
    """
    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            start = perf_counter()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                latency = perf_counter() - start
                phase_latency_seconds.labels(phase=phase, symbol=symbol).observe(latency)
                
                if latency > 1.0:
                    logger.warning(
                        f"Slow phase execution: {phase} for {symbol} took {latency:.3f}s"
                    )
        
        return wrapper
    return decorator


@asynccontextmanager
async def track_phase(phase: str, symbol: str = "unknown"):
    """
    Context manager to track phase execution time.
    
    Args:
        phase: Phase name (use DecisionPhase constants)
        symbol: Trading symbol for correlation
    
    Example:
        async with track_phase(DecisionPhase.RISK_VALIDATION, symbol="AAPL"):
            envelope = await risk_calculator.calculate(context)
            # ... validation logic
    """
    start = perf_counter()
    try:
        yield
    finally:
        latency = perf_counter() - start
        phase_latency_seconds.labels(phase=phase, symbol=symbol).observe(latency)
        
        if latency > 1.0:
            logger.warning(
                f"Slow phase execution: {phase} for {symbol} took {latency:.3f}s"
            )


class PhaseTimer:
    """
    Manual phase timer for non-decorator/context-manager scenarios.
    
    Example:
        timer = PhaseTimer(DecisionPhase.DCA_EVALUATION, symbol="AAPL")
        timer.start()
        
        # ... DCA logic
        
        timer.stop()  # Automatically records metric
    """
    
    def __init__(self, phase: str, symbol: str = "unknown"):
        """
        Initialize phase timer.
        
        Args:
            phase: Phase name (use DecisionPhase constants)
            symbol: Trading symbol for correlation
        """
        self.phase = phase
        self.symbol = symbol
        self._start_time: float | None = None
    
    def start(self) -> None:
        """Start timing the phase."""
        self._start_time = perf_counter()
    
    def stop(self) -> float:
        """
        Stop timing and record metric.
        
        Returns:
            Elapsed time in seconds
        """
        if self._start_time is None:
            logger.error(f"PhaseTimer.stop() called before start() for phase {self.phase}")
            return 0.0
        
        latency = perf_counter() - self._start_time
        phase_latency_seconds.labels(phase=self.phase, symbol=self.symbol).observe(latency)
        
        if latency > 1.0:
            logger.warning(
                f"Slow phase execution: {self.phase} for {self.symbol} took {latency:.3f}s"
            )
        
        self._start_time = None
        return latency
    
    def __enter__(self):
        """Support synchronous context manager usage."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Support synchronous context manager usage."""
        self.stop()
        return False


# Prometheus query examples for documentation
QUERY_EXAMPLES = """
# p95 latency per phase
histogram_quantile(0.95, rate(trading_bot_decision_phase_latency_seconds_bucket[5m]))

# p99 latency for confidence calculation
histogram_quantile(0.99, rate(trading_bot_decision_phase_latency_seconds_bucket{phase="confidence_calculation"}[5m]))

# p95 latency by symbol
histogram_quantile(0.95, 
  sum by (symbol, le) (rate(trading_bot_decision_phase_latency_seconds_bucket[5m]))
)

# Phase slowness comparison (avg latency)
avg by (phase) (rate(trading_bot_decision_phase_latency_seconds_sum[5m]) 
  / rate(trading_bot_decision_phase_latency_seconds_count[5m]))
"""
