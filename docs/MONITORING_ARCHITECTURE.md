# Monitoring Architecture

## Overview
The bot uses two concurrent monitoring loops with clearly defined responsibilities.

## PositionMonitor Service

**File**: `src/trading/position_monitor.py`

**Primary Responsibility**: Position-level monitoring and profit-taking

### Monitoring Cycle
```python
async def _monitor_positions_cycle(self):
    # 1. Check for fills (via OrderManager.check_and_update_fills)
    newly_filled_orders = await check_fills_callback()
    for filled_order in newly_filled_orders:
        await on_fill_detected(filled_order)
    
    # 2. Update market data (parallel price fetching)
    # 3. Check profit-taking conditions
    # 4. Update trailing stops
```

### Responsibilities
- ✅ **Fill Detection**: Continuously checks ALL pending orders for fills
- ✅ **Market Data Updates**: Parallel price fetching with bounded concurrency
- ✅ **Profit-Taking**: Detects profit opportunities and triggers execution
- ✅ **Trailing Stop Management**: Updates trailing profit conditions
- ✅ **Position Status Logging**: Reports position P&L and status

### NOT Responsible For
- ❌ Order timeouts (handled by OrderMonitor)
- ❌ Order cancellations (handled by OrderMonitor)
- ❌ Order execution (handled by OrderManager)

## OrderMonitor Loop

**File**: `src/trading_bot.py` - `_monitor_orders()` method

**Primary Responsibility**: Order timeout and cancellation management

### Monitoring Cycle
```python
async def _monitor_orders(self):
    open_orders = await order_manager.get_open_orders()
    
    for order in open_orders:
        # 1. Check order status
        current_status = await order_manager.get_order_status(order.order_id)
        
        # 2. Handle state changes
        if current_status == OrderStatus.FILLED:
            await _handle_order_fill(order)
        elif current_status == OrderStatus.CANCELED:
            await _handle_order_cancel(order)
        
        # 3. Check for timeouts (implicit in get_order_status)
```

### Responsibilities
- ✅ **Order Timeout Management**: Cancels stale orders
- ✅ **Order State Transitions**: Handles canceled/rejected orders
- ✅ **Fallback Fill Detection**: Secondary fill detection (redundant safety)
- ✅ **Order Lifecycle Cleanup**: Moves completed orders to history

### NOT Responsible For
- ❌ Position monitoring (handled by PositionMonitor)
- ❌ Profit-taking decisions (handled by PositionMonitor)
- ❌ Market data updates (handled by PositionMonitor)

## Fill Detection - Dual Architecture (Redundant Safety)

### Primary: PositionMonitor
- Called via `check_and_update_fills()` callback
- Checks ALL pending orders in a single batch
- More efficient (bulk status check)
- Fires `OrderFillEvent` callbacks immediately

### Secondary: OrderMonitor (Fallback)
- Checks individual order status via `get_order_status()`
- Ensures fills aren't missed if PositionMonitor cycle is delayed
- Provides redundant safety net
- Less efficient (per-order API calls)

### Why Both?
**Defense in Depth**: If one loop has issues (delayed, crashed), the other catches fills.

**Trade-off**: Slight API overhead for significantly improved reliability.

## Potential Optimization (Future)

### Option 1: Single Fill Detection Point
Remove fill detection from `_monitor_orders`, make it purely timeout/cancellation focused.

**Pros**:
- Eliminates duplication
- Clearer separation of concerns
- Reduced API calls

**Cons**:
- Less redundancy
- Single point of failure for fill detection

### Option 2: Extract OrderMonitor Service
Create dedicated `OrderMonitor` service similar to `PositionMonitor`.

**Structure**:
```python
class OrderMonitor:
    async def start_monitoring(
        self,
        shutdown_event,
        on_order_timeout,
        on_order_canceled
    ):
        # Order timeout and cancellation logic
        pass
```

**Benefits**:
- Clearer architecture
- Better testability
- Parallel to PositionMonitor design
- ~50-100 line reduction in orchestrator

**Status**: Optional enhancement (orchestrator currently at 1320 lines)

## Current Assessment

**Status**: Architecture is sound and production-ready

**Code Quality**: 9.6/10

**Recommendation**: No changes required unless orchestrator grows beyond 1500 lines.

---

*Last Updated: November 2025*
*Author: Trading Bot Team*
