# Trading Bot Domain Events

This document catalogs all domain events emitted by the trading bot system, including payload schemas, priority levels, and handling semantics.

## Event System Overview

The bot uses an event-driven architecture for loose coupling between components. Events flow through a priority-aware event bus with back-pressure support.

### Event Bus Configuration
- **Implementation**: `src/events/event_bus.py`
- **Max Queue Size**: 1000 events
- **Priority Levels**: 4 (CRITICAL, HIGH, NORMAL, LOW)
- **Back-pressure**: Enabled (drops LOW priority when queue >80% full)
- **Persistence**: None (in-memory only)

---

## Event Priorities

| Priority | Use Case | Drop Policy |
|----------|----------|-------------|
| **CRITICAL** | Order fills, risk breaches, system errors | Never dropped |
| **HIGH** | Signal processing, position changes, DCA execution | Rarely dropped (queue >95% full) |
| **NORMAL** | Trailing stop updates, confidence scoring | Dropped at >80% queue utilization |
| **LOW** | Analytics, cache updates, metric aggregation | Dropped at >50% queue utilization |

---

## Event Catalog

### 1. SignalReceived

**Emitted When**: Webhook receives valid trading signal from TradingView

**Priority**: HIGH

**Payload Schema**:
```python
{
    "event_type": "signal_received",
    "trace_id": str,              # Distributed trace ID
    "timestamp": datetime,        # UTC timestamp
    "symbol": str,                # e.g., "AAPL"
    "action": str,                # "buy" | "sell" | "close"
    "timeframe": str,             # e.g., "15min"
    "signal_source": str,         # "tradingview"
    "hmac_verified": bool,        # Signature validation result
    "metadata": {
        "strategy_name": str,
        "alert_id": str | None
    }
}
```

**Subscribers**:
- `SignalProcessor` → Validates and routes to strategy
- `MetricsCollector` → Increments `signals_received_total`
- `AuditLogger` → Logs signal for compliance

---

### 2. PositionOpened

**Emitted When**: New position successfully opened

**Priority**: HIGH

**Payload Schema**:
```python
{
    "event_type": "position_opened",
    "trace_id": str,
    "timestamp": datetime,
    "position_lifecycle_id": str,  # Unique position identifier
    "symbol": str,
    "direction": str,              # "long" | "short"
    "entry_price": float,
    "quantity": float,
    "entry_size": float,           # USD value
    "timeframe": str,
    "order_id": str,               # Broker order ID
    "strategy": str,               # "long_strategy" | "short_strategy"
}
```

**Subscribers**:
- `PositionManager` → Updates in-memory position cache
- `DatabaseManager` → Persists position to DB
- `RiskManager` → Updates exposure calculations
- `MetricsCollector` → Increments `positions_opened_total`

---

### 3. DCAExecuted

**Emitted When**: Dollar-cost averaging order fills

**Priority**: HIGH

**Payload Schema**:
```python
{
    "event_type": "dca_executed",
    "trace_id": str,
    "timestamp": datetime,
    "position_lifecycle_id": str,
    "symbol": str,
    "dca_attempt": int,            # 1-indexed attempt number
    "dca_price": float,            # Actual fill price
    "dca_quantity": float,
    "dca_size": float,             # USD value
    "new_average_price": float,    # Updated position average
    "total_quantity": float,       # Cumulative quantity
    "trigger_level": float,        # Support/resistance level that triggered DCA
    "is_progressive": bool,        # True if price improved from last DCA
}
```

**Subscribers**:
- `DCAMetadataManager` → Updates DCA history
- `PositionManager` → Recalculates position averages
- `RiskManager` → Validates martingale safety
- `MetricsCollector` → Increments `dca_executed_total`

---

### 4. DCAReject

**Emitted When**: DCA order rejected by safety validators

**Priority**: NORMAL

**Payload Schema**:
```python
{
    "event_type": "dca_rejected",
    "trace_id": str,
    "timestamp": datetime,
    "position_lifecycle_id": str,
    "symbol": str,
    "attempted_price": float,
    "reason": str,                 # See rejection reasons below
    "validator": str,              # Which validator rejected
    "current_attempts": int,
    "max_attempts": int,
    "metadata": dict               # Validator-specific details
}
```

**Rejection Reasons**:
- `NON_PROGRESSIVE_PRICE` - DCA price doesn't improve average
- `MAX_ATTEMPTS_EXCEEDED` - Hit DCA attempt limit
- `SYMBOL_LOSS_LIMIT` - Symbol exposure too high
- `DAILY_LOSS_LIMIT` - Daily loss circuit breaker triggered
- `INSUFFICIENT_BALANCE` - Not enough purchasing power

**Subscribers**:
- `MetricsCollector` → Increments `dca_rejections_total{reason}`
- `AuditLogger` → Logs rejection for analysis

---

### 5. PositionClosed

**Emitted When**: Position fully closed (profit target, stop loss, or manual)

**Priority**: HIGH

**Payload Schema**:
```python
{
    "event_type": "position_closed",
    "trace_id": str,
    "timestamp": datetime,
    "position_lifecycle_id": str,
    "symbol": str,
    "direction": str,
    "entry_price": float,
    "exit_price": float,
    "quantity": float,
    "realized_pnl": float,         # USD profit/loss
    "realized_pnl_percent": float,
    "hold_duration_seconds": int,
    "close_reason": str,           # See close reasons below
    "dca_attempts_used": int,
    "order_id": str,
}
```

**Close Reasons**:
- `PROFIT_TARGET` - Hit profit target
- `TRAILING_STOP` - Trailing stop triggered
- `HARD_STOP` - Fixed stop loss hit
- `MANUAL` - Manually closed via signal
- `RISK_BREACH` - Emergency risk closure

**Subscribers**:
- `PositionManager` → Removes from active positions
- `DatabaseManager` → Marks position as closed
- `RiskManager` → Updates daily/weekly P&L
- `ConfidenceCalibrationStore` → Records outcome for factor tuning
- `MetricsCollector` → Observes `trade_pnl_dollars`, `trade_duration_seconds`

---

### 6. TrailingStopActivated

**Emitted When**: Position enters trailing stop phase (profit threshold reached)

**Priority**: NORMAL

**Payload Schema**:
```python
{
    "event_type": "trailing_stop_activated",
    "trace_id": str,
    "timestamp": datetime,
    "position_lifecycle_id": str,
    "symbol": str,
    "activation_price": float,
    "peak_price": float,
    "trailing_percent": float,
    "current_profit_percent": float,
}
```

**Subscribers**:
- `TrailingStopManager` → Begins tracking peak price
- `MetricsCollector` → Increments `trailing_stops_activated_total`

---

### 7. RiskBreach

**Emitted When**: Any risk limit is breached

**Priority**: CRITICAL

**Payload Schema**:
```python
{
    "event_type": "risk_breach",
    "trace_id": str,
    "timestamp": datetime,
    "breach_type": str,            # See breach types below
    "severity": str,               # "WARNING" | "CRITICAL"
    "current_value": float,
    "limit_value": float,
    "affected_symbols": list[str],
    "action_taken": str,           # "POSITION_CLOSED" | "ORDERS_CANCELLED" | "ALERT_ONLY"
}
```

**Breach Types**:
- `DAILY_LOSS_LIMIT`
- `WEEKLY_LOSS_LIMIT`
- `SYMBOL_LOSS_LIMIT`
- `CONSECUTIVE_LOSS_LIMIT`
- `EMERGENCY_STOP_LOSS`
- `ACCOUNT_DRAWDOWN`

**Subscribers**:
- `RiskManager` → May trigger emergency position closure
- `AlertingService` → Sends critical alert (email/SMS)
- `MetricsCollector` → Increments `risk_breaches_total{type}`
- `AuditLogger` → Logs breach for compliance

---

### 8. OrderFilled

**Emitted When**: Broker confirms order fill

**Priority**: CRITICAL

**Payload Schema**:
```python
{
    "event_type": "order_filled",
    "trace_id": str,
    "timestamp": datetime,
    "order_id": str,
    "position_lifecycle_id": str | None,
    "symbol": str,
    "side": str,                   # "buy" | "sell"
    "filled_qty": float,
    "filled_avg_price": float,
    "order_type": str,             # "market" | "limit" | "stop"
    "is_dca_order": bool,
    "fill_latency_ms": int,        # Time from placement to fill
}
```

**Subscribers**:
- `OrderManager` → Updates order status
- `PositionManager` → Updates position quantity/average
- `DCAMetadataManager` → Records DCA fill (if applicable)
- `MetricsCollector` → Observes `order_fill_latency_ms`

---

### 9. ConfidenceScored

**Emitted When**: Confidence pipeline evaluates signal

**Priority**: LOW

**Payload Schema**:
```python
{
    "event_type": "confidence_scored",
    "trace_id": str,
    "timestamp": datetime,
    "symbol": str,
    "final_score": float,          # 0.0 - 1.0
    "threshold": float,
    "passed": bool,
    "factor_scores": {
        "TechnicalFactor": {"raw": float, "weight": float, "weighted": float},
        "VolumeFactor": {"raw": float, "weight": float, "weighted": float},
        # ... other factors
    },
    "execution_time_ms": int,
}
```

**Subscribers**:
- `AuditLogger` → Logs decision breakdown
- `MetricsCollector` → Observes `confidence_score`, `confidence_evaluation_duration_ms`

---

### 10. SystemStartup

**Emitted When**: Bot initializes successfully

**Priority**: HIGH

**Payload Schema**:
```python
{
    "event_type": "system_startup",
    "timestamp": datetime,
    "version": str,
    "config_version": str,
    "components_initialized": list[str],
    "active_strategies": list[str],
    "startup_duration_ms": int,
}
```

**Subscribers**:
- `MetricsCollector` → Records boot time
- `AuditLogger` → Logs startup event

---

### 11. SystemShutdown

**Emitted When**: Bot gracefully shuts down

**Priority**: CRITICAL

**Payload Schema**:
```python
{
    "event_type": "system_shutdown",
    "timestamp": datetime,
    "reason": str,                 # "USER_INITIATED" | "ERROR" | "SIGNAL"
    "active_positions_count": int,
    "pending_orders_count": int,
    "uptime_seconds": int,
}
```

**Subscribers**:
- `DatabaseManager` → Flushes pending writes
- `OrderManager` → Cancels pending orders (if configured)
- `AuditLogger` → Logs shutdown event

---

## Event Flow Examples

### Example 1: Successful Long Entry with DCA

```
1. SignalReceived (TradingView buy alert)
   ↓
2. ConfidenceScored (passed: true, score: 0.85)
   ↓
3. PositionOpened (entry at $150.00)
   ↓
4. OrderFilled (100 shares filled)
   ↓
[Price drops to $145.00 - support level breached]
   ↓
5. DCAExecuted (attempt 1, filled at $144.90)
   ↓
6. OrderFilled (150 shares filled, new avg: $147.00)
   ↓
[Price recovers to $155.00]
   ↓
7. TrailingStopActivated (profit: 5.4%)
   ↓
[Price drops to $152.50]
   ↓
8. PositionClosed (trailing stop triggered, PnL: +$1,375)
   ↓
9. OrderFilled (250 shares sold)
```

### Example 2: DCA Rejection Flow

```
1. SignalReceived
   ↓
2. PositionOpened
   ↓
[Price drops, DCA#1 executes at $95.00]
   ↓
3. DCAExecuted (attempt 1)
   ↓
[Price drops further, DCA#2 executes at $92.00]
   ↓
4. DCAExecuted (attempt 2)
   ↓
[Price drops to $90.00, DCA#3 attempted]
   ↓
5. DCARejected (reason: MAX_ATTEMPTS_EXCEEDED)
   ↓
[Price continues down, triggers stop loss]
   ↓
6. PositionClosed (close_reason: HARD_STOP)
```

---

## Event Bus API

### Publishing Events

```python
from src.events.event_bus import EventBus, EventPriority

# Get singleton instance
event_bus = EventBus()

# Publish event
await event_bus.publish(
    event_type="position_opened",
    priority=EventPriority.HIGH,
    payload={
        "symbol": "AAPL",
        "entry_price": 150.00,
        # ... other fields
    }
)
```

### Subscribing to Events

```python
async def handle_position_opened(event):
    logger.info(f"Position opened: {event['symbol']}")

# Subscribe
event_bus.subscribe("position_opened", handle_position_opened)

# Unsubscribe
event_bus.unsubscribe("position_opened", handle_position_opened)
```

---

## Event Retention & Replay

**Current State**: No persistence (events lost on restart)

**Future Enhancement**: Add optional event store for:
- Audit trail
- Event replay for debugging
- Analytics data pipeline

**Recommended Store**: Append-only JSONL file or dedicated event store (e.g., EventStoreDB)

---

## Monitoring

### Key Metrics

| Metric | Type | Labels | Purpose |
|--------|------|--------|---------|
| `events_published_total` | Counter | `event_type`, `priority` | Event throughput |
| `events_dropped_total` | Counter | `event_type`, `priority` | Back-pressure monitoring |
| `event_processing_duration_seconds` | Histogram | `event_type` | Handler latency |
| `event_bus_queue_size` | Gauge | - | Queue utilization |

### Alerts

- **Queue Saturation**: `event_bus_queue_size > 800` for >5min
- **High Drop Rate**: `rate(events_dropped_total[5m]) > 10`
- **Slow Handler**: `event_processing_duration_seconds{quantile="0.99"} > 1.0`

---

**Last Updated**: 2025-10-29  
**Owner**: Trading Bot Team  
**Review Cadence**: Quarterly
