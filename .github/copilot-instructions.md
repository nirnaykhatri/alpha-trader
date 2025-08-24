# Trading Bot AI Coding Guidelines

This is a sophisticated Python-based trading bot that receives TradingView webhook signals and executes trades through the Alpaca API. The bot features a revolutionary technical analysis-based DCA (Dollar Cost Averaging) strategy that eliminates arbitrary loss thresholds.

## Architecture Overview

The codebase follows SOLID principles with clear separation of concerns across modular components:

### Core Components
- **`src/trading_bot.py`** - Main orchestrator (TradingBotOrchestrator) that coordinates all components
- **`src/strategies/advanced_strategy.py`** - Position-aware DCA strategy engine (1782 lines)
- **`src/trading/order_manager.py`** - Enhanced order lifecycle management with retry logic
- **`src/signals/`** - TradingView webhook processing and signal validation
- **`src/position/`** - Position tracking with Alpaca broker synchronization
- **`src/data/`** - Market data providers (AlpacaMarketDataProvider)
- **`src/database/`** - Trade persistence and audit trails

### Key Design Patterns
- **Dependency Injection**: All components accept interfaces, not concrete implementations
- **Strategy Pattern**: Multiple DCA calculation methods via `ISupportCalculator`
- **Observer Pattern**: Order fill events trigger position updates and callbacks
- **Circuit Breaker**: API failures use exponential backoff with `tenacity`

## Critical Development Workflows

### Running & Testing
```bash
# Quick setup and validation
python setup_environment.bat        # Windows dependency installation
python verify_installation.py       # Verify all components work
python run_bot.py                   # Start with config validation

# Testing workflows
python run_tests.py unit           # Fast unit tests
python run_tests.py integration    # Full integration tests
python run_tests.py coverage       # Generate coverage reports
```

### Configuration Patterns
- **YAML-based**: All behavior controlled via `config.yaml` (489 lines)
- **Environment overrides**: `TRADING_BOT_NO_NGROK=1` disables tunneling
- **Validation required**: Always call `config.validate_required_config()` before use
- **Paper vs Live**: Determined by `api.alpaca.base_url` (paper-api vs api)

## Project-Specific Conventions

### Technical Analysis DCA Strategy
The bot's core innovation is **position-aware technical DCA** that respects market structure:
- **NO arbitrary percentage thresholds** (traditional "2% loss = DCA" is eliminated)
- **Support/Resistance based**: DCA triggers only when price breaches calculated technical levels
- **Timeframe consistency**: Uses original signal timeframe (1H, 4H, 1D) for all DCA analysis
- **Position direction filtering**: Long positions only DCA at support below avg price, shorts only at resistance above

### Order Management Patterns
```python
# ALWAYS use OrderFillEvent for position updates
@dataclass
class OrderFillEvent:
    is_dca_order: bool = False           # Critical for DCA tracking
    position_lifecycle_id: Optional[str] # Links orders to positions
```

### Database Integration
- **Position lifecycle tracking**: Each position gets unique `position_lifecycle_id`
- **DCA metadata**: Stores technical levels, confidence scores, attempt counts
- **Audit trail**: Complete trade history with actual fill prices (not estimated)

### Error Handling Specifics
- **Rate limiting**: 60-second cooldown between repeated errors per symbol
- **API retries**: 3 attempts with exponential backoff for transient failures
- **Graceful degradation**: System continues on partial failures (e.g., webhook down but trading works)

### Error Handling Specifics
- **Rate limiting**: 60-second cooldown between repeated errors per symbol
- **API retries**: 3 attempts with exponential backoff for transient failures
- **Graceful degradation**: System continues on partial failures (e.g., webhook down but trading works)

## Integration Points

### TradingView Webhooks
- **Endpoints**: `/webhook`, `/webhook/{secret}`, `/status`, `/trades`
- **Required payload fields**: `symbol`, `signal`, `price`, `timeframe` (critical for DCA)
- **Async processing**: Non-blocking webhook handling for high throughput

### Alpaca API Integration
- **Dual clients**: `TradingClient` for orders, `StockHistoricalDataClient` for market data
- **Communication methods**: REST (default) or WebSocket (`api.alpaca.communication_method`)
- **Extended hours**: Pre/post market trading supported via TimeInForce configuration

### Market Data Flow
```python
# Price fetching pattern used throughout
current_price = await self.market_data.get_current_price(symbol)
# ALWAYS handles market closed scenarios gracefully
```

## Component Communication

### Signal → Strategy → Order Flow
1. **TradingViewSignalListener** validates webhook payload
2. **AdvancedTradingStrategy** processes signal with position awareness
3. **TechnicalSupportCalculator** calculates support/resistance levels
4. **OrderManager** executes with retry logic and fill tracking
5. **PositionManager** syncs with Alpaca and updates database

### Configuration Dependencies
- Risk limits checked BEFORE order placement
- Position sizing calculated using account balance + risk parameters
- DCA attempts limited by `strategies.long_strategy.support_averaging.max_attempts`

## Testing Strategy

### Unit Test Patterns
- **Mock external APIs**: All Alpaca calls use `AsyncMock`
- **Configuration fixtures**: `tests/fixtures/test_config.yaml` for consistent test data
- **Async testing**: All tests use `@pytest.mark.asyncio`

### Integration Test Approach
- **Real API connections**: Tests validate against Alpaca paper trading
- **Webhook simulation**: Full request/response cycle testing
- **Database persistence**: Verify audit trail accuracy

### Key Test Commands
```bash
# Test specific functionality
python -m pytest tests/test_enhanced_dca.py -v
python tests/run_webhook_tests.py              # Webhook concurrency
python validate_final_fix.py                   # Market data validation
```

## Debugging Workflows

### Log Analysis
- **Structured logging**: JSON format with `structlog` for production
- **Component tagging**: Each log includes component name for filtering
- **Error tracking**: Rate-limited error logging prevents spam

### Development Tools
```bash
python monitor_bot.py                # Real-time position monitoring
python debug_quote_api.py           # Market data debugging
python emergency_position_sync.py   # Manual position reconciliation
```

When working on this codebase, always consider the bot's core philosophy: **market structure over arbitrary rules**. Every change should respect the technical analysis foundation that drives the DCA strategy.
