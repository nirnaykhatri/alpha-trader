# Tastytrade Integration Setup

This guide explains how to configure and use the Tastytrade integration for the trading bot.

## Overview

The bot now supports multi-broker trading, allowing you to execute trades on both **Alpaca** and **Tastytrade** simultaneously. You can route specific symbols to Tastytrade while keeping others on Alpaca.

**Important**: Each broker uses its **own market data provider**:
- Trades routed to Alpaca use Alpaca market data
- Trades routed to Tastytrade use Tastytrade market data (via DXFeed)

This ensures data consistency and accuracy for each broker's trades.

## Prerequisites

*   A **Tastytrade** account (Open one at [tastytrade.com](https://tastytrade.com/)).
*   **Tastytrade Credentials**: OAuth client secret and refresh token (see [OAuth Setup](#oauth-setup)).
*   **Python 3.9+** environment with `tastytrade` SDK v11.x installed (included in `requirements.txt`).

## OAuth Setup

Tastytrade SDK v11.x uses OAuth authentication instead of username/password:

1. Go to [https://my.tastytrade.com/app.html#/manage/api-access/oauth-applications](https://my.tastytrade.com/app.html#/manage/api-access/oauth-applications)
2. Create an OAuth application
3. Generate a refresh token from the same page (OAuth Applications > Manage > Create Grant)
4. Configure the `client_secret` and `refresh_token` in your settings

For sandbox accounts:
1. Create an account at [https://developer.tastytrade.com/sandbox/](https://developer.tastytrade.com/sandbox/)
2. Use the OAuth flow with `is_sandbox = true`

## Configuration

### 1. Interactive Setup (Recommended)

Run the configuration script:

```powershell
python configure_bot.py
```

Follow the prompts to enter your Tastytrade details:
*   **Client Secret**: Your OAuth application's client secret.
*   **Refresh Token**: Your OAuth refresh token (never expires).
*   **Account ID**: Your account identifier (e.g., `5TX...`).
*   **Mode**: Choose **Sandbox** (Certification) for testing or **Live** for real trading.

### 2. Manual Configuration

Edit `config/settings.toml` directly:

```toml
[api.tastytrade]
client_secret = "YOUR_CLIENT_SECRET"
refresh_token = "YOUR_REFRESH_TOKEN"
account_id = "YOUR_ACCOUNT_ID"
is_sandbox = true  # Set to false for live trading

# Optional: Legacy username (for display purposes only)
username = "YOUR_USERNAME"

[data.tastytrade]
cache_duration = 30  # Cache market data for 30 seconds
use_streaming = false  # Set to true for real-time streaming quotes
```

## Routing Symbols

You can configure the bot to route specific symbols to Tastytrade. By default, all symbols are routed to Alpaca.

To route a symbol (e.g., SPY) to Tastytrade, update the `trading.brokers.routing` section in `config/settings.toml`:

```toml
[trading.brokers]
default = "alpaca"

[trading.brokers.routing]
SPY = "tastytrade"
IWM = "tastytrade"
# All other symbols will go to "alpaca"
```

## Market Data

The Tastytrade integration includes a dedicated market data provider (`TastytradeMarketDataProvider`) that:

- Fetches real-time prices from Tastytrade's DXFeed data source
- Supports **pre-market** (4:00 AM - 9:30 AM ET) and **after-hours** (4:00 PM - 8:00 PM ET) data
- Can use streaming WebSocket quotes for real-time updates (optional)
- Falls back to REST API calls for on-demand pricing
- Validates prices are non-zero before returning (raises `ValueError` for invalid data)
- Caches prices with configurable TTL to reduce API calls

### Extended Hours Support

Both pre-market and after-hours trading data is fully supported:

| Session | Hours (ET) | Support |
|---------|-----------|---------|
| Pre-market | 4:00 AM - 9:30 AM | ✅ Full support |
| Regular | 9:30 AM - 4:00 PM | ✅ Full support |
| After-hours | 4:00 PM - 8:00 PM | ✅ Full support |

### Streaming Mode

Enable real-time streaming for lower latency price updates:

```toml
[data.tastytrade]
use_streaming = true
```

When enabled, the provider maintains a persistent WebSocket connection to DXFeed for continuous quote updates. The streaming connection includes automatic reconnection with exponential backoff (up to 5 attempts) if the connection drops.

## Architecture

The Tastytrade broker is implemented following Clean Architecture and SOLID principles:

```
src/broker/tastytrade_broker/
├── __init__.py                 # Package exports
├── session_manager.py          # OAuth session lifecycle with keep-alive
├── account_mixin.py            # Shared account retrieval (DRY pattern)
├── account_provider.py         # Account data (equity, buying power)
├── order_executor.py           # Order execution with retry logic
└── market_data_provider.py     # Market data with caching & streaming
```

### Key Patterns

**TastytradeAccountMixin**: Shared mixin class that eliminates code duplication between `order_executor.py` and `account_provider.py`. Both inherit account retrieval logic from this mixin.

**Async-First Design**: All I/O operations use `asyncio`. Synchronous SDK calls are wrapped with `asyncio.to_thread()` via the `run_blocking` helper.

**Thread-Safe Caching**: Account object caching uses `asyncio.Lock` to prevent race conditions during concurrent requests.

**Timezone-Aware Datetimes**: All timestamps use `datetime.now(timezone.utc)` for consistency across time zones.

## Features Supported

The Tastytrade integration supports:

| Feature | Status | Notes |
|---------|--------|-------|
| Equity Trading | ✅ Supported | Buy/sell stocks |
| Account Data | ✅ Supported | Equity, buying power, cash |
| Position Management | ✅ Supported | Track open positions |
| Market Data | ✅ Supported | **Dedicated Tastytrade data provider** |
| Extended Hours Data | ✅ Supported | Pre-market and after-hours |
| Streaming Quotes | ✅ Supported | Real-time via DXFeed |

## Known Limitations

The following features are **not yet implemented** or have limitations for Tastytrade:

| Feature | Status | Impact |
|---------|--------|--------|
| Options Trading | ❌ Not Supported | Only equity (stock) trading is supported. Multi-leg option orders are skipped. |
| Historical Bars | ⚠️ Limited | Tastytrade API has limited OHLCV historical data. Use Alpaca for historical analysis. |
| Multi-leg Orders | ⚠️ Skipped | Options spreads and multi-leg orders are logged but not converted to domain orders. |

> **Note on Order Tracking**: The `get_open_orders` method IS implemented and returns live single-leg equity orders from Tastytrade. Complex multi-leg orders (options spreads) are skipped with a debug log message.

## Troubleshooting

*   **Authentication Failed**: Check your client_secret and refresh_token. Ensure you selected the correct mode (Sandbox vs. Live). The session manager uses OAuth with automatic token refresh.
*   **Account Not Found**: Verify your Account ID matches exactly what is shown in the Tastytrade platform.
*   **Order Rejected**: Check if you have sufficient buying power or if the market is open. Order quantity must be > 0.
*   **Market Data Timeout**: If streaming mode is slow to start, try with `use_streaming = false` first.
*   **Zero Price Error**: If you see `ValueError: Received zero price`, this indicates the market data API returned invalid data. Check if the symbol is valid and the market is open.
*   **NameError: asyncio not defined**: Ensure all broker modules have `import asyncio` at the top. This is required for `asyncio.Lock` and other async operations.

## Security Note

Your credentials are stored in `config/.secrets.toml`. Ensure this file is **never committed to version control** (it is ignored by `.gitignore` by default).
