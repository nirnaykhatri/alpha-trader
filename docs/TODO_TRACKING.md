# TODO Tracking Document

> **Generated**: December 23, 2025  
> **Last Updated**: Code Review Fixes Applied  
> **Purpose**: Track unimplemented features and technical debt identified during code review

---

## Recent Fixes Applied

### Code Review Session - Handler Extraction & Test Fixes

#### 1. BotRunner Handler Extraction (SRP Compliance)
Extracted handler classes from `bot_runner.py` to improve maintainability:

| New File | Purpose | Key Methods |
|----------|---------|-------------|
| [handlers/order_handler.py](../src/bot_engine/handlers/order_handler.py) | Order placement & execution | `place_base_order()`, `place_safety_order()`, `execute_take_profit()`, `execute_stop_loss()`, `close_position()` |
| [handlers/signal_handler.py](../src/bot_engine/handlers/signal_handler.py) | Signal processing | `handle_buy_signal()`, `handle_sell_signal()`, `handle_close_signal()`, `handle_signal()` |
| [handlers/condition_checker.py](../src/bot_engine/handlers/condition_checker.py) | Condition evaluation | `should_take_profit()`, `should_stop_loss()`, `should_place_safety_order()`, `check_price_in_grid_range()` |

**Impact**: `bot_runner.py` now delegates to handlers, improving testability and reducing complexity.

#### 2. Frontend Bot Status Card (Dynamic Values)
- Added `BotStatus` interface to `use-signalr.ts`
- Connected `page.tsx` Bot Status card to real-time SignalR data
- Displays: `isRunning`, `tradesToday`, `lastSignalTime`, `strategyName`

#### 3. Test Collection Fixes

| Issue | Fix Applied |
|-------|-------------|
| Missing `IDatabaseManager` interface | Added to `src/interfaces.py` |
| Property tests require hypothesis | Added `pytest.importorskip("hypothesis")` |
| Soak tests import wrong metric names | Fixed metric aliases in `test_sustained_load.py` |
| Chaos test provider mocks missing `name` | Implemented `IConsensusMarketDataProvider` interface |
| Pytest markers undefined | Added `chaos`, `soak`, `property` markers to `pytest.ini` |
| `IMarketDataProvider` undefined in consensus_engine | Fixed to `IConsensusMarketDataProvider` |
| Obsolete tests referencing removed code | Moved to `tests/legacy/` |

**Test Suite Status**:
- ✅ Unit tests: 81 passing
- ✅ Chaos tests: 7 collecting
- ✅ Soak tests: Skip if psutil unavailable
- ✅ Property tests: Skip if hypothesis unavailable

---

## High Priority (Production Readiness)

### Bot Service - Trading Execution Integration

**File**: [src/services/bot_service.py](../src/services/bot_service.py)

| Line | TODO | Priority | Effort |
|------|------|----------|--------|
| L315 | Integrate with trading execution | High | Medium |
| L358 | Cancel orders if requested | High | Low |
| L359 | Close positions if requested | High | Low |
| L470 | Actually place the averaging order through order manager | High | Medium |
| L514 | Actually adjust margin through broker | Medium | Medium |
| L546 | Actually close position through order manager | High | Medium |
| L578 | Query orders from BotOrderRecord table | Medium | Low |
| L627 | Query from BotHistoryRecord table | Low | Low |
| L647 | Delete from BotHistoryRecord table | Low | Low |
| L663 | Aggregate from BotHistoryRecord table | Low | Low |

---

### Bot Runner - Broker Pool Integration

**File**: [src/bot_engine/bot_runner.py](../src/bot_engine/bot_runner.py)

| Line | TODO | Priority | Effort |
|------|------|----------|--------|
| L232 | Wire up actual services from broker_pool | High | High |
| L235 | Get order_manager from broker_pool | High | Medium |
| L236 | Get market_data from market_data_hub | High | Medium |
| L237 | Get risk_manager from services | High | Medium |
| L576 | Remove once all bots use injected strategies | Medium | Low |
| L590 | Remove once all bots use ITradingStrategy injection | Medium | Low |
| L760 | Implement indicator checking via market data hub | Medium | Medium |
| L856 | Execute order via broker pool | High | Medium |
| L872 | Execute safety order via broker pool | High | Medium |
| L883 | Execute via broker pool | High | Medium |
| L896 | Execute via broker pool | High | Medium |
| L914 | Execute close via broker pool | High | Medium |
| L1121 | Implement grid order management | Low | High |

---

## Medium Priority (Frontend Completion)

### Trading Terminal - Order Submission

**File**: [trading-terminal/app/orders/new/page.tsx](../trading-terminal/app/orders/new/page.tsx)

| Line | TODO | Priority | Effort |
|------|------|----------|--------|
| L269 | Implement actual order submission | Medium | Medium |

### Trading Terminal - Config Management

**File**: [trading-terminal/app/config/page.tsx](../trading-terminal/app/config/page.tsx)

| Line | TODO | Priority | Effort |
|------|------|----------|--------|
| L193 | Load preset configuration | Low | Low |

### Trading Terminal - Bot Management

**File**: [trading-terminal/app/bots/page.tsx](../trading-terminal/app/bots/page.tsx)

| Line | TODO | Priority | Effort |
|------|------|----------|--------|
| L591 | Implement actual update via API | Medium | Medium |
| L640 | Implement action handling | Medium | Medium |

---

## Summary

| Priority | Count | Status |
|----------|-------|--------|
| **High** | 14 | ⏳ Pending |
| **Medium** | 7 | ⏳ Pending |
| **Low** | 5 | ⏳ Pending |
| **Total** | 26 | |

---

## Recommended Sprint Plan

### Sprint 1 (Critical Path)
1. Bot Service → Trading Execution Integration (L315, L358, L359)
2. Bot Runner → Broker Pool Wiring (L232-L237)
3. Bot Runner → Order Execution via Broker Pool (L856, L872, L883, L896, L914)

### Sprint 2 (Feature Completion)
1. Bot Service → Position/Order Management (L470, L514, L546)
2. Frontend → Order Submission (orders/new/page.tsx)
3. Frontend → Bot Action Handling (bots/page.tsx)

### Sprint 3 (Tech Debt)
1. Remove legacy strategy fallbacks (L576, L590)
2. Bot History querying (L578, L627, L647, L663)
3. Grid order management (L1121)

---

## Notes

- All TODOs are in active development branches
- High priority items block production trading functionality
- Frontend TODOs are lower priority as backend must be completed first
