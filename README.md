<div align="center">

# 🤖 Advanced Trading Bot

### *Production-Grade Algorithmic Trading with Martingale DCA*

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Alpaca API](https://img.shields.io/badge/Broker-Alpaca-yellow.svg?style=for-the-badge&logo=alpacadotmarkets&logoColor=white)](https://alpaca.markets/)
[![Tastytrade API](https://img.shields.io/badge/Broker-Tastytrade-red.svg?style=for-the-badge&logo=tastytrade&logoColor=white)](https://tastytrade.com/)
[![TradingView](https://img.shields.io/badge/Signals-TradingView-black.svg?style=for-the-badge&logo=tradingview&logoColor=white)](https://www.tradingview.com/)
[![License MIT](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)

---

*A professional-grade algorithmic trading bot for **Alpaca** and **Tastytrade**.*  
*Executes sophisticated **Martingale-based DCA strategies** via **TradingView webhooks**.*

</div>

---

## 📑 Table of Contents

- [🚀 Quick Start Guide](#-quick-start-guide)
- [☁️ Azure Cloud Deployment](#️-azure-cloud-deployment)
- [🌟 Key Features](#-key-features)
- [🏗️ Architecture](#️-architecture)
- [📊 How It Works](#-how-it-works)
- [📚 Documentation](#-documentation)
- [⚠️ Disclaimer](#️-disclaimer)

---

## 🚀 Quick Start Guide

Get your bot running in minutes with this step-by-step guide.

```mermaid
flowchart LR
    subgraph Setup["⚙️ Setup Process"]
        A["1️⃣ Install"] --> B["2️⃣ Configure"]
        B --> C["3️⃣ Validate"]
        C --> D["4️⃣ Launch"]
    end
    
    style D fill:#90EE90
```

---

### 1️⃣ Prerequisites

| Requirement | Description |
|:------------|:------------|
| 🐍 **Python 3.9+** | Installed and added to PATH |
| 📦 **Git** | For cloning the repository |
| 🏦 **Broker Account** | Alpaca (Paper/Live) and/or Tastytrade |

---

### 2️⃣ Installation

Clone the repository and run the automated setup script:

```powershell
# Clone the repository
git clone <repository-url>
cd Bot

# Run the automated setup script (Windows)
.\setup_environment.bat
```

> 💡 *For Linux/Mac, use `./setup_environment.sh`*

---

### 3️⃣ Configuration

The bot uses a **CLI-based configuration system** with TOML files:

```powershell
# Initialize configuration (creates .secrets.toml from template)
python -m src.config.cli init

# Edit your credentials
# Open: config/.secrets.toml

# Validate your configuration
python -m src.config.cli validate
```

```mermaid
flowchart TB
    subgraph Config["📁 Configuration Files"]
        INIT["python -m src.config.cli init"]
        EDIT["Edit config/.secrets.toml<br/><i>Add API credentials</i>"]
        VALIDATE["python -m src.config.cli validate"]
    end
    
    INIT --> EDIT --> VALIDATE
    
    style VALIDATE fill:#90EE90
```

> 📖 See **[Configuration Guide](docs/CONFIGURATION.md)** for detailed setup instructions.

---

### 4️⃣ Launch 🚀

#### ☁️ Production (Azure Deployment - Recommended)

Deploy to Azure Container Apps for 24/7 operation with a stable HTTPS endpoint:

```mermaid
flowchart LR
    subgraph Azure["☁️ Azure Deployment"]
        GH["GitHub Push"] --> CI["CI/CD Pipeline"]
        CI --> ACA["Azure Container Apps"]
    end
    
    TV["TradingView"] -->|"Webhook"| ACA
    ACA --> BOT["🤖 Trading Bot"]
```

See **[Azure Deployment Guide](docs/AZURE_DEPLOYMENT.md)** for complete instructions.

#### 💻 Local Development

For local testing:

```mermaid
flowchart LR
    subgraph Launch["🚀 Local Development"]
        T1["Terminal<br/>start_trading_bot.bat"]
    end
    
    T1 -->|"Runs on localhost:8080"| BOT["🤖 Trading Bot"]
```

| Step | Command | Description |
|:----:|:--------|:------------|
| 1️⃣ | `.\start_trading_bot.bat` | Start bot locally |
| 2️⃣ | Access `http://localhost:8080/docs` | View API documentation |

---

### 5️⃣ Stopping the Bot 🛑

```mermaid
flowchart TB
    subgraph Scripts["🛑 Shutdown Options"]
        S1["stop_bot_only.bat<br/><i>Graceful stop</i>"]
        S2["quick_shutdown.bat<br/><i>Emergency kill</i>"]
    end
    
    S1 --> R1["♻️ Clean shutdown"]
    S2 --> R2["⚠️ Emergency only"]
    
    style S1 fill:#90EE90
    style S2 fill:#FFB6C1
```

| Script | Description | Use Case |
|:-------|:------------|:---------|
| `stop_bot_only.bat` | Graceful shutdown | ♻️ Normal stop |
| `quick_shutdown.bat` | Force kill | ⚠️ Emergency stop |

**Recommended workflow:**
```powershell
.\stop_bot_only.bat        # Graceful shutdown
.\start_bot_no_ngrok.bat   # Restart bot
```

---

## ☁️ Azure Cloud Deployment

Deploy the trading bot to Azure for **24/7 operation** without ngrok hassles. Estimated cost: **~$15/month**.

```mermaid
flowchart TB
    subgraph Azure["☁️ Azure Cloud (~$15/month)"]
        subgraph Ingress["🌐 Entry Points"]
            TV["📈 TradingView<br/>Webhooks"]
            UI["🖥️ Trading Terminal<br/>Next.js + shadcn/ui"]
        end
        
        subgraph Compute["⚡ Compute"]
            CA["🐳 Container Apps<br/>Trading Bot<br/><i>Always-on</i>"]
        end
        
        subgraph Data["💾 Data Layer"]
            CDB["🌍 Cosmos DB<br/>Free Tier<br/><i>25GB + 1000 RU/s</i>"]
            KV["🔐 Key Vault<br/>Secrets"]
            AC["⚙️ App Config<br/>Hot-Reload"]
        end
        
        subgraph RealTime["📡 Real-Time"]
            SR["🔌 SignalR<br/>WebSocket<br/><i>20K msg/day</i>"]
        end
    end
    
    TV -->|"HTTPS"| CA
    UI -->|"API Proxy"| CA
    CA <-->|"Read/Write"| CDB
    CA -->|"Secrets"| KV
    CA -->|"Config"| AC
    CA -->|"Push Updates"| SR
    SR -->|"WebSocket"| UI
    
    style CA fill:#4CAF50,color:#fff
    style CDB fill:#0078D4,color:#fff
    style SR fill:#FF6B35,color:#fff
```

### Quick Deploy

```powershell
# Clone and deploy
cd infra
.\deploy.ps1 -Environment demo -Location westus2

# Or with Bash
./deploy.sh --environment demo --location westus2
```

### Cost Breakdown

| Service | Tier | Monthly Cost |
|:--------|:-----|-------------:|
| Container Apps | Consumption (min=1) | ~$10 |
| Cosmos DB | Free Tier | $0 |
| SignalR | Free Tier | $0 |
| Static Web Apps | Free Tier | $0 |
| Key Vault | Standard | ~$1 |
| App Configuration | Free Tier | $0 |
| Container Registry | Basic | ~$5 |
| **Total** | | **~$16** |

> 📖 See **[Azure Deployment Guide](docs/AZURE_DEPLOYMENT.md)** for complete setup instructions, architecture details, and CI/CD configuration.

---

## 🌟 Key Features

```mermaid
mindmap
  root((🤖 Trading Bot))
    🔄 Multi-Broker
      Alpaca
      Tastytrade
      Symbol Routing
    🧠 Strategy
      Martingale DCA
      Progressive Averaging
      6+ Safety Checks
    🛡️ Risk Management
      Portfolio Limits
      Daily Loss Caps
      Circuit Breakers
    📊 Market Data
      5 Data Sources
      Extended Hours
      Smart Caching
    🔧 Architecture
      Clean Architecture
      Dependency Injection
      Interface-Based
```

---

### 🔄 Multi-Broker Support

Trade on **Alpaca** and **Tastytrade** simultaneously with intelligent symbol routing:

```mermaid
flowchart LR
    subgraph Signals["📨 Incoming Signals"]
        S1["BUY AAPL"]
        S2["BUY SPY"]
        S3["BUY MSFT"]
    end
    
    subgraph Router["🔀 BrokerRouter"]
        R["Symbol Routing"]
    end
    
    subgraph Brokers["🏦 Brokers"]
        A["🦙 Alpaca"]
        T["🍒 Tastytrade"]
    end
    
    S1 --> R
    S2 --> R
    S3 --> R
    R -->|"AAPL, MSFT"| A
    R -->|"SPY"| T
    
    style A fill:#FFE4B5
    style T fill:#FFB6C1
```

---

### 🧠 Martingale DCA Strategy

Intelligent position averaging with **6+ safety mechanisms**:

| Safety Check | Description |
|:-------------|:------------|
| 🔢 **Max Attempts Cap** | Hard limit on averaging attempts (default: 3-4) |
| 💰 **Position Size Limits** | Maximum % of portfolio per position |
| 📉 **Price Improvement** | Each DCA must be at a better price |
| 🛑 **Daily Loss Limit** | Auto-stop when daily loss threshold hit |
| ⚖️ **Portfolio Exposure** | Caps on total market exposure |
| 🔌 **Circuit Breakers** | Auto-shutdown on critical failures |

---

### 📊 Broker-Specific Market Data

Each broker uses **its own dedicated market data provider** for consistency:

```mermaid
flowchart TB
    subgraph Alpaca["🦙 Alpaca (5-Source Fallback)"]
        A1["📸 StockSnapshot"]
        A2["💬 StockLatestQuote"]
        A3["📈 StockLatestTrade"]
        A4["📊 StockLatestBar"]
        A5["📉 StockBars"]
        A1 --> AP["Price Resolution"]
        A2 --> AP
        A3 --> AP
        A4 --> AP
        A5 --> AP
    end
    
    subgraph Tastytrade["🍒 Tastytrade (DXFeed)"]
        T1["🔴 Streaming Quotes"]
        T2["📡 REST API"]
        T1 --> TP["Price Resolution"]
        T2 --> TP
    end
    
    AP --> PRICE["✅ Best Available Price"]
    TP --> PRICE
    
    style PRICE fill:#90EE90
```

| Broker | Data Sources | Extended Hours |
|:-------|:-------------|:---------------|
| **Alpaca** | 5 endpoints with smart fallback | ✅ Pre-market & After-hours |
| **Tastytrade** | DXFeed streaming + REST | ✅ Pre-market & After-hours |

---

## 🏗️ Architecture

The bot follows **Clean Architecture** principles with strict separation of concerns:

```mermaid
flowchart TB
    subgraph Presentation["🌐 Presentation Layer"]
        WH["Webhook Handlers"]
        SL["Signal Listener"]
    end
    
    subgraph Application["⚙️ Application Layer"]
        ORCH["TradingBotOrchestrator<br/><i>~1337 lines</i>"]
        STRAT["DCAStrategy"]
        EXIT["ExitPlanner"]
        TRADE["TradeService"]
    end
    
    subgraph Domain["🎯 Domain Layer"]
        OM["OrderManager"]
        PM["PositionManager"]
        RM["RiskEnvelopeCalculator"]
    end
    
    subgraph Infrastructure["🔧 Infrastructure Layer"]
        BS["BrokerSubsystem"]
        DB["DatabaseManager"]
        MD["MarketDataProvider"]
    end
    
    Presentation --> Application
    Application --> Domain
    Domain --> Infrastructure
    
    style ORCH fill:#E3F2FD
    style Domain fill:#FFF3E0
```

---

### 🎯 Core Services

| Service | File | Responsibility |
|:--------|:-----|:---------------|
| **TradingBotOrchestrator** | `src/trading_bot.py` | Composition root (~1337 lines) |
| **BrokerSubsystem** | `src/broker/subsystem.py` | Multi-broker abstraction |
| **OrderManager** | `src/trading/order_manager.py` | Order lifecycle & fill tracking |
| **PositionManager** | `src/position/position_manager.py` | Position tracking & reconciliation |
| **RiskEnvelopeCalculator** | `src/risk/risk_envelope_calculator.py` | Risk validation & portfolio limits |
| **DCAStrategy** | `src/strategies/dca_strategy.py` | DCA with progressive averaging |

---

### 🔧 Extracted Services (Clean Code)

```mermaid
flowchart LR
    subgraph Extracted["📦 Extracted Services"]
        EP["ExitPlanner<br/><i>Exit order computation</i>"]
        TS["TradeService<br/><i>Trade lifecycle</i>"]
        PM["PositionMonitor<br/><i>Monitoring loop</i>"]
        BF["BoundedFetcher<br/><i>Concurrency control</i>"]
    end
    
    EP --> |"SRP"| CLEAN["✅ Single Responsibility"]
    TS --> CLEAN
    PM --> CLEAN
    BF --> CLEAN
```

| Service | File | Purpose |
|:--------|:-----|:--------|
| **ExitPlanner** | `src/trading/exit_planner.py` | Centralized exit logic |
| **TradeService** | `src/trading/trade_service.py` | Trade completion & audit |
| **PositionMonitor** | `src/trading/position_monitor.py` | Parallel price fetching |
| **BoundedFetcher** | `src/utils/bounded_gather.py` | API rate limiting |

---

### 🎨 Design Patterns

```mermaid
mindmap
  root((🎨 Patterns))
    Strategy
      Pluggable strategies
      DCA behaviors
    Router
      Multi-broker dispatch
      Symbol routing
    Service Layer
      Extracted services
      SRP compliance
    DI
      Constructor injection
      Testability
    Interfaces
      Programming to abstractions
      Loose coupling
```

---

## 📊 How It Works

```mermaid
sequenceDiagram
    participant TV as 📺 TradingView
    participant WH as 🌐 Webhook
    participant BOT as 🤖 Bot
    participant STRAT as 🧠 Strategy
    participant RISK as 🛡️ Risk
    participant BROKER as 🏦 Broker
    
    TV->>WH: Alert Signal (BUY AAPL)
    WH->>BOT: Parse & Validate
    BOT->>STRAT: Process Signal
    STRAT->>RISK: Check Limits
    RISK-->>STRAT: ✅ Approved
    STRAT->>BROKER: Place Order
    BROKER-->>BOT: Order Filled
    BOT->>BOT: Update Position
    BOT->>BOT: Monitor for Exit
```

---

## 📚 Documentation

| Document | Description |
|:---------|:------------|
| 📖 **[User Guide](docs/USER_GUIDE.md)** | Complete manual for configuration & usage |
| ⚙️ **[Configuration Guide](docs/CONFIGURATION.md)** | TOML config system & CLI commands |
| 🔌 **[Admin API Reference](docs/ADMIN_API.md)** | Admin endpoints, authentication & TypeScript client |
| ☁️ **[Azure Deployment](docs/AZURE_DEPLOYMENT.md)** | Cloud hosting with Container Apps & Cosmos DB |
| 🍒 **[Tastytrade Setup](docs/TASTYTRADE_SETUP.md)** | OAuth setup for Tastytrade |
| 🧠 **[Martingale Safety](docs/MARTINGALE_SAFETY_SUMMARY.md)** | Strategy math & safety mechanisms |
| 🔌 **[Adapters Index](docs/ADAPTERS_INDEX.md)** | External integrations reference |

---

## ⚠️ Disclaimer

<div align="center">

### ⚠️ **USE AT YOUR OWN RISK** ⚠️

</div>

This software is for **educational and research purposes only**. Algorithmic trading involves substantial risk of financial loss.

| ⚠️ Warning | Description |
|:-----------|:------------|
| 📉 **Risk of Loss** | Past performance does not guarantee future results |
| 🧪 **Test First** | Always use Paper Trading before real funds |
| 🎰 **Martingale Risk** | Strategy carries specific risks (see docs) |
| 📜 **No Liability** | Authors assume no responsibility for losses |

---

<div align="center">

**Built with ❤️ for algorithmic traders**

[![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python&logoColor=white)](https://python.org)
[![Architecture](https://img.shields.io/badge/Architecture-Clean-green)](docs/ADAPTERS_INDEX.md)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

</div>
