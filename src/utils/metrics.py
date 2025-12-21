"""
Prometheus Metrics Infrastructure

Structured metrics collection for observability with p95/p99 latency tracking.

Prometheus histograms automatically track:
- p50 (median): _bucket{le="0.5"}
- p95: _bucket{le="0.95"}  
- p99: _bucket{le="0.99"}

Query examples:
- p95 DCA latency: histogram_quantile(0.95, rate(trading_bot_dca_decision_latency_seconds_bucket[5m]))
- p99 DCA latency: histogram_quantile(0.99, rate(trading_bot_dca_decision_latency_seconds_bucket[5m]))
"""

from prometheus_client import Counter, Histogram, Gauge, Info
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)

# DCA Metrics
dca_attempts_total = Counter(
    'trading_bot_dca_attempts_total',
    'Total DCA evaluation attempts',
    ['symbol', 'result']  # result: executed, rejected, error
)

dca_executed_total = Counter(
    'trading_bot_dca_executed_total',
    'Total DCA orders actually executed',
    ['symbol', 'direction']  # direction: long, short
)

dca_rejections_total = Counter(
    'trading_bot_dca_rejections_total',
    'Total DCA rejections',
    ['symbol', 'reason']  # reason: risk_limit, no_improvement, etc.
)

dca_decision_latency_seconds = Histogram(
    'trading_bot_dca_decision_latency_seconds',
    'DCA decision pipeline latency in seconds (p50/p95/p99 observable)',
    ['symbol'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Order Metrics
orders_placed_total = Counter(
    'trading_bot_orders_placed_total',
    'Total orders placed',
    ['symbol', 'side', 'order_type']
)

orders_filled_total = Counter(
    'trading_bot_orders_filled_total',
    'Total orders filled',
    ['symbol', 'side']
)

orders_canceled_total = Counter(
    'trading_bot_orders_canceled_total',
    'Total orders canceled',
    ['symbol', 'reason']
)

order_placement_latency_seconds = Histogram(
    'trading_bot_order_placement_latency_seconds',
    'Order placement latency in seconds',
    ['symbol'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0]
)

order_fill_latency_seconds = Histogram(
    'trading_bot_order_fill_latency_seconds',
    'Time from order placement to fill',
    ['symbol'],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

# Position Metrics
active_positions_gauge = Gauge(
    'trading_bot_active_positions',
    'Number of active positions',
    ['symbol']
)

position_pnl_gauge = Gauge(
    'trading_bot_position_unrealized_pnl',
    'Unrealized P&L for active positions',
    ['symbol']
)

positions_opened_total = Counter(
    'trading_bot_positions_opened_total',
    'Total positions opened',
    ['symbol', 'direction']
)

positions_closed_total = Counter(
    'trading_bot_positions_closed_total',
    'Total positions closed',
    ['symbol', 'exit_reason']  # exit_reason: profit, loss, manual
)

# Signal Metrics
signals_received_total = Counter(
    'trading_bot_signals_received_total',
    'Total signals received',
    ['symbol', 'action']  # action: entry, exit, dca
)

signals_processed_total = Counter(
    'trading_bot_signals_processed_total',
    'Total signals successfully processed',
    ['symbol', 'action']
)

signals_rejected_total = Counter(
    'trading_bot_signals_rejected_total',
    'Total signals rejected',
    ['symbol', 'reason']
)

webhook_latency_seconds = Histogram(
    'trading_bot_webhook_processing_latency_seconds',
    'Webhook processing latency',
    ['endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0]
)

# Risk Metrics
risk_checks_total = Counter(
    'trading_bot_risk_checks_total',
    'Total risk validation checks',
    ['check_type', 'result']  # result: passed, failed
)

risk_circuit_breaker_triggers = Counter(
    'trading_bot_risk_circuit_breaker_triggers_total',
    'Total circuit breaker activations',
    ['breaker_type']  # daily_loss, weekly_loss, consecutive_loss, etc.
)

dca_pause_events_total = Counter(
    'trading_bot_dca_pause_events_total',
    'Total DCA pause events due to resilience state',
    ['state']  # state: critical, fail_closed, etc.
)

# Confidence Metrics
confidence_scores_histogram = Histogram(
    'trading_bot_confidence_scores',
    'Distribution of confidence scores',
    ['factor_name'],
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)

confidence_factor_latency_seconds = Histogram(
    'trading_bot_confidence_factor_latency_seconds',
    'Latency of individual confidence factor evaluation in seconds (p50/p95/p99)',
    ['factor_name'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5]
)

# Volatility Regime Metrics
volatility_regime_changes_total = Counter(
    'trading_bot_volatility_regime_changes_total',
    'Total volatility regime transitions',
    ['symbol', 'from_regime', 'to_regime']
)

volatility_regime_gauge = Gauge(
    'trading_bot_current_volatility_regime',
    'Current volatility regime (0=ULTRA_LOW, 1=LOW, 2=NORMAL, 3=ELEVATED, 4=HIGH, 5=EXTREME)',
    ['symbol']
)

dca_spacing_multiplier_gauge = Gauge(
    'trading_bot_dca_spacing_multiplier',
    'Current DCA spacing multiplier based on volatility regime',
    ['symbol', 'regime']
)

# System Metrics
api_calls_total = Counter(
    'trading_bot_api_calls_total',
    'Total external API calls',
    ['provider', 'endpoint', 'status']  # status: success, error
)

api_call_latency_seconds = Histogram(
    'trading_bot_api_call_latency_seconds',
    'External API call latency',
    ['provider', 'endpoint'],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0]
)

cache_operations_total = Counter(
    'trading_bot_cache_operations_total',
    'Total cache operations',
    ['operation', 'result']  # operation: get, set; result: hit, miss, error
)

database_operations_total = Counter(
    'trading_bot_database_operations_total',
    'Total database operations',
    ['operation', 'table', 'status']
)

database_query_latency_seconds = Histogram(
    'trading_bot_database_query_latency_seconds',
    'Database query latency',
    ['operation', 'table'],
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
)

# Bot Info
bot_info = Info(
    'trading_bot_info',
    'Trading bot version and configuration info'
)


class MetricsRecorder:
    """
    Helper class for recording metrics with consistent labeling.
    
    Example:
        recorder = MetricsRecorder()
        recorder.record_dca_attempt(symbol="AAPL", result="executed")
        recorder.record_dca_latency(symbol="AAPL", latency_seconds=0.234)
    """
    
    @staticmethod
    def record_dca_attempt(symbol: str, result: str):
        """Record DCA attempt."""
        dca_attempts_total.labels(symbol=symbol, result=result).inc()
    
    @staticmethod
    def record_dca_execution(symbol: str, direction: str):
        """Record DCA execution."""
        dca_executed_total.labels(symbol=symbol, direction=direction).inc()
    
    @staticmethod
    def record_dca_rejection(symbol: str, reason: str):
        """Record DCA rejection."""
        dca_rejections_total.labels(symbol=symbol, reason=reason).inc()
    
    @staticmethod
    def record_dca_latency(symbol: str, latency_seconds: float):
        """Record DCA decision latency."""
        dca_decision_latency_seconds.labels(symbol=symbol).observe(latency_seconds)
    
    @staticmethod
    def record_order_placed(symbol: str, side: str, order_type: str):
        """Record order placement."""
        orders_placed_total.labels(
            symbol=symbol,
            side=side,
            order_type=order_type
        ).inc()
    
    @staticmethod
    def record_order_filled(symbol: str, side: str):
        """Record order fill."""
        orders_filled_total.labels(symbol=symbol, side=side).inc()
    
    @staticmethod
    def record_order_latency(symbol: str, latency_seconds: float):
        """Record order placement latency."""
        order_placement_latency_seconds.labels(symbol=symbol).observe(latency_seconds)
    
    @staticmethod
    def record_confidence_score(factor_name: str, score: float):
        """Record confidence factor score."""
        confidence_scores_histogram.labels(factor_name=factor_name).observe(score)
    
    @staticmethod
    def record_risk_check(check_type: str, passed: bool):
        """Record risk check result."""
        result = "passed" if passed else "failed"
        risk_checks_total.labels(check_type=check_type, result=result).inc()
    
    @staticmethod
    def record_circuit_breaker(breaker_type: str):
        """Record circuit breaker trigger."""
        risk_circuit_breaker_triggers.labels(breaker_type=breaker_type).inc()
    
    @staticmethod
    def set_active_positions(symbol: str, count: int):
        """Set active position count for symbol."""
        active_positions_gauge.labels(symbol=symbol).set(count)
    
    @staticmethod
    def set_position_pnl(symbol: str, pnl: float):
        """Set unrealized P&L for position."""
        position_pnl_gauge.labels(symbol=symbol).set(pnl)
    
    @staticmethod
    def record_signal_received(symbol: str, action: str):
        """Record signal receipt."""
        signals_received_total.labels(symbol=symbol, action=action).inc()
    
    @staticmethod
    def record_webhook_latency(endpoint: str, latency_seconds: float):
        """Record webhook processing latency."""
        webhook_latency_seconds.labels(endpoint=endpoint).observe(latency_seconds)
    
    @staticmethod
    def record_api_call(provider: str, endpoint: str, success: bool, latency_seconds: Optional[float] = None):
        """Record external API call."""
        status = "success" if success else "error"
        api_calls_total.labels(
            provider=provider,
            endpoint=endpoint,
            status=status
        ).inc()
        
        if latency_seconds is not None:
            api_call_latency_seconds.labels(
                provider=provider,
                endpoint=endpoint
            ).observe(latency_seconds)
    
    @staticmethod
    def record_cache_operation(operation: str, hit: bool):
        """Record cache operation."""
        result = "hit" if hit else "miss"
        cache_operations_total.labels(operation=operation, result=result).inc()


# Global instance
metrics = MetricsRecorder()
