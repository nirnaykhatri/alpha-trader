---
applyTo: "src/**/*"
---

# Trading Bot Business Logic & Patterns

## System Overview
Production-grade Python 3.9+ trading bot that processes TradingView webhooks and executes trades via Alpaca API. The core innovation is a **technical analysis-based DCA strategy** that triggers on support/resistance levels rather than percentage losses.

**Critical Philosophy**: Position decisions driven by market structure (technical levels), not arbitrary thresholds. Every DCA order must improve position average (progressive pricing).

## Clean Architecture - Extracted Services

### Service Layer (November 2025 Refactoring)
The orchestrator has been refactored to extract focused services following SOLID principles:

**ExitPlanner** (`src/trading/exit_planner.py`)
- Centralizes ALL exit order computation logic
- Used by: _handle_close_signal, manual_close_position, _execute_profit_taking
- Pattern: `exit_plan = await self._exit_planner.plan_exit(position, reason="...")`

**TradeService** (`src/trading/trade_service.py`)
- Manages trade lifecycle and completion
- Handles externally closed positions
- Pattern: `await self._trade_service.handle_externally_closed_position(symbol, qty)`

**PositionMonitor** (`src/trading/position_monitor.py`)
- Encapsulates position monitoring loop
- Parallel price fetching with bounded concurrency
- Pattern: Callback-based monitoring with `on_profit_opportunity` handler

**BoundedFetcher** (`src/utils/bounded_gather.py`)
- Bounded concurrency for async operations
- Prevents API rate limiting
- Pattern: `price_dict = await self._price_fetcher.fetch_all(symbols, fetch_fn)`

**CRITICAL**: When adding position/exit logic, use these services instead of adding to orchestrator.

## Critical Code Patterns

### 1. DCA Strategy - Technical Levels (NOT Percentages)
```python
# ✅ CORRECT: Technical analysis-based DCA
support_levels = await self.support_calculator.calculate_support_levels(
    position.symbol, 
    position.timeframe  # PRESERVE from original signal
)
if current_price <= support_levels[0]:
    await self._execute_technical_dca(position, level=support_levels[0])

# ❌ WRONG: Percentage-based triggers (legacy anti-pattern)
if position.unrealized_pnl_percent < -2:  # DON'T DO THIS
    await self._execute_dca()
```

### 2. Progressive DCA Validation
```python
# CRITICAL: Each DCA must improve average price
if position.last_dca_price:
    if position.direction == PositionDirection.LONG:
        # Long: New DCA must be LOWER than last
        if new_price >= position.last_dca_price:
            logger.warning(f"DCA rejected: ${new_price} >= ${position.last_dca_price}")
            return  # Block non-progressive DCA
    else:
        # Short: New DCA must be HIGHER than last
        if new_price <= position.last_dca_price:
            return  # Block non-progressive DCA
```

### 3. Async Webhook Pattern (Non-Blocking)
```python
# ✅ CORRECT: Fire-and-forget pattern
@router.post("/webhook")
async def process_webhook(request: Request, background_tasks: BackgroundTasks):
    signal_data = await request.json()
    
    # Validate immediately (fast)
    if not self._validate_webhook_signature(request):
        raise HTTPException(status_code=401)
    
    # Process async without blocking response
    background_tasks.add_task(self._process_signal_async, signal_data)
    
    return {"status": "accepted"}  # Return in <1 second
```

### 4. Order Fill Tracking (Critical for DCA)
```python
# Fill-based DCA metadata updates (accurate)
async def on_order_filled(self, order: Order):
    """Update DCA metadata ONLY on actual fills."""
    if order.is_dca_order:
        position.averaging_attempts += 1
        position.last_dca_price = order.filled_avg_price  # Actual fill
        position.dca_order_prices.append(order.filled_avg_price)
        
        # CRITICAL: Save to prevent order history pollution
        await self._save_position_dca_metadata(
            symbol=position.symbol,
            attempts=position.averaging_attempts,
            prices=position.dca_order_prices,
            last_price=position.last_dca_price
        )
```

### 5. Martingale Safety Integration
```python
# ALWAYS validate DCA against 6 safety checks
from src.risk.martingale_validator import MartingaleSafetyManager

safety_check = await self.martingale_safety.check_safety(
    symbol=position.symbol,
    loss_amount=potential_loss,
    consecutive_losses=position.averaging_attempts
)

if not safety_check['safe']:
    logger.critical(f"🛑 MARTINGALE SAFETY: {safety_check['reason']}")
    return  # ABORT DCA order
```

### 6. Unified Risk Envelope Calculation
```python
# ✅ CORRECT: Use consolidated risk calculator
from src.risk.risk_envelope_calculator import RiskEnvelopeCalculator
from src.domain import DecisionContext

calculator = RiskEnvelopeCalculator()

envelope = await calculator.calculate(
    context=DecisionContext.from_position(position, current_price),
    proposed_size=5000.0,
    account_balance=50000.0
)

if envelope.safe:
    execute_order(size=envelope.effective_limit)
else:
    logger.warning(f"Risk denied: {envelope.primary_constraint.value}")
```

### 7. Unified Position Sizing with SizingService
```python
# ✅ CORRECT: Use centralized sizing service
from src.strategies.sizing_service import SizingService

sizing_service = SizingService(config, risk_calculator)

# Initial entry
result = await sizing_service.compute_initial_entry(
    context=DecisionContext.from_position(position, current_price),
    account_balance=50000.0
)
```

### 8. Dynamic Confidence Calibration
```python
# ✅ CORRECT: Adaptive confidence weighting based on outcomes
from src.strategies.confidence.calibration_store import ConfidenceCalibrationStore

# Use dynamic weights in confidence pipeline
async def calculate_confidence(context: DecisionContext) -> float:
    factor_scores = {}
    for factor in self.factors:
        raw_score = await factor.calculate(context)
        weight = self.calibration_store.get_dynamic_weight(factor.name)
        factor_scores[factor.name] = raw_score * weight
    return sum(factor_scores.values()) / len(factor_scores)
```

### 9. DCA Pause Guard (Resilience Integration)
```python
# ✅ CORRECT: Check pause state before DCA execution
from src.resilience.dca_pause_guard import DcaPauseGuard

if self.dca_pause_guard:
    pause_decision = await self.dca_pause_guard.evaluate()
    if not pause_decision.allow_dca:
        logger.warning(f"🛑 DCA paused for {position.symbol}: {pause_decision.reason}")
        return  # Skip DCA execution
```

### 10. Portfolio Proportional Scaling
```python
# ✅ CORRECT: Proportional scaling instead of hard deny
from src.risk.portfolio_exposure_validator import PortfolioExposureValidator

# Sizing with portfolio scaling
result = await sizing_service.compute(
    context=decision_context,
    account_balance=50000.0,
    current_positions={'AAPL': 8000.0, 'MSFT': 7500.0}
)

if result.approved:
    execute_order(size=result.effective)
```

### 11. Broker-Specific Market Data (Multi-Broker Pattern)
```python
# ✅ CORRECT: Each broker uses its own market data provider
# Trades routed to Alpaca use Alpaca market data
# Trades routed to Tastytrade use Tastytrade market data

from src.broker.tastytrade_broker import TastytradeMarketDataProvider

# Market data provider validates prices
price = await market_data.get_current_price(symbol)
# Raises ValueError if price is zero (invalid data)

# Extended hours support (pre-market 4 AM - 9:30 AM ET, after-hours 4 PM - 8 PM ET)
market_status = market_data.get_market_status()
if market_status in ['PRE_MARKET', 'AFTER_HOURS']:
    # Use extended hours pricing
    pass
```

### 12. Mixin Pattern for Code Reuse
```python
# ✅ CORRECT: Use mixins to eliminate duplication
class TastytradeAccountMixin:
    """Shared account retrieval logic."""
    
    async def _get_account_object(self) -> Account:
        async with self._account_lock:  # Thread-safe
            if self._cached_account is None:
                session = await self._session_manager.get_session()
                self._cached_account = await run_blocking(
                    Account.async_get_account, session, self._account_number
                )
            return self._cached_account

# Classes inherit shared functionality
class TastytradeOrderExecutor(TastytradeAccountMixin, IOrderExecutor):
    pass

class TastytradeAccountProvider(TastytradeAccountMixin, IAccountProvider):
    pass
```

## Component-Specific Guidelines

### When modifying `advanced_strategy.py`:
- Preserve the technical analysis foundation.
- Maintain position-aware logic.
- Never introduce percentage-based triggers.
- Keep timeframe consistency throughout.
- Use `asyncio.gather()` for parallel data fetches.

### When modifying risk management:
- Use `RiskEnvelopeCalculator` for all risk assessments.
- Add custom validators via `calculator.add_validator()`.
- Never bypass safety checks without explicit configuration flag.
- Always return `RiskEnvelope` from domain layer.
