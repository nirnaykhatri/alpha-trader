# 📘 Trading Bot User Guide

Welcome to the comprehensive manual for the **Advanced Martingale DCA Trading Bot**. This guide is designed to help you install, configure, and master the operation of your algorithmic trading system.

---

## 📚 Table of Contents

1.  [🚀 Quick Start](#-quick-start)
2.  [🛠️ Installation](#-installation)
3.  [⚙️ Configuration](#-configuration)
4.  [📡 API & Monitoring](#-api--monitoring)
5.  [🧠 Core Strategy](#-core-strategy)
6.  [🔧 Troubleshooting](#-troubleshooting)

---

## 🚀 Quick Start

Get up and running in **3 simple steps**:

1.  **Setup Environment**:
    ```powershell
    .\setup_environment.bat
    ```
2.  **Configure**:
    Run `python configure_bot.py` or edit `config/settings.toml` with your **Alpaca Keys**.
3.  **Launch**:
    ```powershell
    # Local Development
    .\start_trading_bot.bat
    
    # Or deploy to Azure (recommended for production)
    # See docs/AZURE_DEPLOYMENT.md for details
    ```

> **💡 Production Deployment**: For 24/7 operation, deploy to Azure Container Apps. 
> The bot will automatically use the `AZURE_CONTAINER_APP_URL` environment variable 
> for webhook endpoints. See [Azure Deployment Guide](./AZURE_DEPLOYMENT.md).

---

## 🛠️ Installation

### Prerequisites
*   **OS**: Windows, Linux, or macOS.
*   **Python**: Version 3.9 or higher.
*   **Git**: For version control.

### Step-by-Step Setup

1.  **Clone the Repository**
    ```bash
    git clone <repository-url>
    cd Bot
    ```

2.  **Run Automated Setup**
    This script creates a virtual environment and installs all dependencies.
    *   **Windows**: `.\setup_environment.bat`
    *   **Linux/Mac**: `./setup_environment.sh`

3.  **Verify Installation**
    Run the verification script to ensure all components are ready.
    ```bash
    python verify_installation.py
    ```

---

## ⚙️ Configuration

The bot is controlled by TOML configuration files in the `config/` directory.

### 🔑 API Credentials
Required for trading and connectivity.

```yaml
api:
  alpaca:
    api_key: "PK******************"      # Your Alpaca API Key
    secret_key: "********************"   # Your Alpaca Secret Key
    base_url: "https://paper-api.alpaca.markets" # Use paper for testing!
  webhook:
    port: 8080
    security_enabled: true
    secret: "my-secure-webhook-secret"   # Used to sign TradingView alerts
```

### 📉 Trading Parameters
Control how the bot executes trades.

```yaml
trading:
  order_type: "limit"           # Recommended: 'limit' to avoid slippage
  limit_order_offset: 0.001     # 0.1% offset for limit orders
  position_sizing:
    method: "percentage"        # Options: fixed, percentage, risk_based
    percentage: 1.0             # Size per trade (% of Equity)
  
  # Aggressive Order Management
  aggressive_order_timeout_minutes: 5  # Cancel/Retry unfilled orders
  max_price_adjustment_percent: 0.5    # Max price move to chase fills
```

### 🧠 Strategy Configuration
The bot uses distinct strategies for Long and Short positions.

```yaml
strategies:
  # Global DCA Settings
  dca:
    base_threshold_percent: 1.5        # First DCA at 1.5% loss
    progressive_multiplier: 1.8        # Next threshold = Previous * 1.8
    max_threshold_percent: 6.0         # Cap threshold at 6%

  # Long Strategy (Martingale)
  long_strategy:
    enabled: true
    averaging:
      enabled: true
      max_attempts: 3
      position_multiplier: 1.5         # Size = Previous * 1.5
      sizing_method: "martingale"      # Uses loss-based triggers

  # Short Strategy (Martingale)
  short_strategy:
    enabled: true
    resistance_averaging:
      enabled: true
      max_attempts: 3
      position_multiplier: 1.5
      # Triggers on Unrealized Loss % (Martingale Logic)
```

### 🛡️ Risk Management
**Critical safety settings.** Do not disable these.

```yaml
risk:
  max_position_size: 10000      # Max USD per position
  max_daily_loss: 500           # Max USD loss per day (Circuit Breaker)
  max_open_positions: 5         # Max concurrent positions
  max_drawdown_percent: 5.0     # Stop trading if account drops 5%
  
  # Portfolio Protection
  portfolio:
    max_symbol_concentration: 0.20  # Max 20% in one symbol
    enable_scaling: true            # Reduce size if near limits
```

---

## 📡 API & Monitoring

The bot includes a built-in **FastAPI** server that provides real-time monitoring and interactive documentation.

### 📖 Interactive Documentation (Swagger UI)
Once the bot is running, you can access the full API documentation locally:

*   **Swagger UI**: [http://localhost:8080/docs](http://localhost:8080/docs)
    *   *Interactive interface to test API endpoints directly from your browser.*
*   **ReDoc**: [http://localhost:8080/redoc](http://localhost:8080/redoc)
    *   *Clean, organized reference documentation.*

### 🔍 Key Monitoring Endpoints

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/health` | `GET` | **System Status**. Returns 200 OK if the bot is healthy. |
| `/status` | `GET` | **Dashboard Data**. Uptime, active positions, and P&L summary. |
| `/positions` | `GET` | **Live Positions**. Detailed view of all open trades and DCA levels. |
| `/positions/{symbol}` | `GET` | **Position Detail**. Specific details for a single symbol. |
| `/orders` | `GET` | **Order History**. Recent orders and their fill status. |
| `/trades` | `GET` | **Performance**. Historical trade analysis and win/loss metrics. |
| `/dca-orders` | `GET` | **DCA Tracking**. History of all averaging attempts and their triggers. |
| `/portfolio-summary` | `GET` | **Portfolio Metrics**. Aggregate view of exposure and unrealized P&L. |
| `/strategy` | `GET` | **Strategy Config**. Current active strategy settings. |
| `/queue` | `GET` | **Signal Queue**. Current depth of the signal processing queue. |
| `/system` | `GET` | **System Resources**. CPU, memory, and disk usage metrics. |

---

## 🧠 Core Strategy

### 📉 Hybrid Martingale System
The bot employs a **Hybrid Strategy** that adapts based on position direction:

*   **Long Positions (Buying)**: Uses a **Progressive Martingale** approach. DCA orders are triggered by specific **unrealized loss thresholds** (e.g., 1.5%, 2.7%, 4.9%) combined with progressive price improvement rules. This ensures cost-basis reduction without relying on potentially lagging support indicators during crashes.
*   **Short Positions (Selling)**: Uses a **Progressive Martingale** approach. DCA orders are triggered by specific **unrealized loss thresholds** (e.g., 1.5%, 2.7%, 4.9%) combined with progressive price improvement rules. This ensures cost-basis improvement without relying on potentially lagging resistance indicators during spikes.

*Note: While the configuration mentions "Technical Resistance DCA", the current codebase enforces **Martingale Logic** (loss-based triggers) for both directions to ensure consistent averaging behavior. Technical analysis is primarily used for initial entries and trend detection.*

### 📊 Progressive Pricing Rules
Regardless of the trigger (Loss or Resistance), every DCA order must obey **Progressive Pricing**:
*   **Longs**: New Buy Price < Last Buy Price
*   **Shorts**: New Sell Price > Last Sell Price

### 🔄 Market Data Consensus
We don't rely on a single data point. The bot aggregates data from **5 sources** to ensure accuracy:
1.  **Snapshot API** (Primary)
2.  **Latest Trade** (Execution data)
3.  **Latest Quote** (Bid/Ask spread)
4.  **Real-time Bars** (1-min candles)
5.  **Historical Bars** (Fallback)

---

## 🔧 Troubleshooting

### 🛑 Stopping the Bot (Windows Users)
**Note:** `Ctrl+C` is often unreliable on Windows terminals. Use these methods instead:

1.  **Graceful Shutdown** (Recommended):
    ```powershell
    python shutdown_bot.py
    ```
2.  **Force Stop**:
    ```powershell
    .\stop_bot.bat
    ```

### ❓ Common Issues

| Issue | Solution |
| :--- | :--- |
| **Webhook not received** | 1. Verify the webhook URL in TradingView matches your Azure Container App URL.<br>2. Check the `/health` endpoint is responding.<br>3. Ensure webhook secret matches in both TradingView and `settings.toml`. |
| **"Insufficient Buying Power"** | 1. Check your Alpaca account balance.<br>2. Reduce `position_sizing.percentage` in `settings.toml`. |
| **Orders not filling** | 1. Switch `order_type` to `market` in config (for testing).<br>2. If using `limit`, increase `limit_order_offset`. |
| **Database Locked** | 1. Ensure no other bot instances are running.<br>2. Restart the bot to clear stale connections. |

---

*For advanced architectural details, please refer to `ARCHITECTURAL_ENHANCEMENTS_SUMMARY.md`.*
