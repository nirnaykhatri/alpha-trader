# ☁️ Azure Cloud Deployment Guide

<div align="center">

### *Production-Grade Cloud Hosting for Alpha-Trader*

[![Azure](https://img.shields.io/badge/Azure-Cloud-0089D6?style=for-the-badge&logo=microsoft-azure&logoColor=white)](https://azure.microsoft.com/)
[![Container Apps](https://img.shields.io/badge/Container_Apps-Serverless-326CE5?style=for-the-badge&logo=docker&logoColor=white)](https://azure.microsoft.com/en-us/products/container-apps)
[![Cosmos DB](https://img.shields.io/badge/Cosmos_DB-NoSQL-00A4EF?style=for-the-badge&logo=azure-cosmos-db&logoColor=white)](https://azure.microsoft.com/en-us/products/cosmos-db)

---

*Deploy your trading bot to Azure with enterprise-grade reliability, real-time updates via SignalR, and a professional trading terminal.*

**Estimated Monthly Cost: ~$15/month** *(mostly free-tier services)*

</div>

---

## 📑 Table of Contents

- [🎯 Overview](#-overview)
- [🏗️ Architecture](#️-architecture)
- [💰 Cost Breakdown](#-cost-breakdown)
- [🔧 Prerequisites](#-prerequisites)
- [🚀 Deployment Guide](#-deployment-guide)
- [⚡ Real-Time Updates (SignalR)](#-real-time-updates-signalr)
- [🔄 Configuration Hot-Reload](#-configuration-hot-reload)
- [🔐 Security](#-security)
- [🛠️ CI/CD Pipeline](#️-cicd-pipeline)
- [📊 Monitoring](#-monitoring)
- [🔧 Troubleshooting](#-troubleshooting)

---

## 🎯 Overview

This guide migrates the trading bot from local ngrok-based hosting to Azure cloud deployment, replacing the unstable ngrok tunnel with a permanent Azure HTTPS endpoint.

### Why Azure?

| Challenge (Local) | Solution (Azure) |
|:------------------|:-----------------|
| 🔄 Ngrok URL changes | ✅ Permanent HTTPS endpoint |
| 💾 SQLite file-based | ✅ Cosmos DB managed NoSQL |
| 🔒 Manual secret management | ✅ Azure Key Vault |
| 📊 No monitoring | ✅ Azure Monitor + Alerts |
| 🚀 Manual deployment | ✅ GitHub Actions CI/CD |
| 📱 No management UI | ✅ Professional trading terminal |

### Migration Benefits

```mermaid
flowchart LR
    subgraph Before["❌ Before (Local)"]
        direction TB
        N["ngrok tunnel<br/><i>unstable URLs</i>"]
        S["SQLite<br/><i>file-based</i>"]
        M["Manual start<br/><i>no monitoring</i>"]
    end
    
    subgraph After["✅ After (Azure)"]
        direction TB
        CA["Container Apps<br/><i>permanent URL</i>"]
        CD["Cosmos DB<br/><i>managed NoSQL</i>"]
        AM["Azure Monitor<br/><i>alerts & metrics</i>"]
    end
    
    Before -->|"Migration"| After
    
    style Before fill:#FFCDD2
    style After fill:#C8E6C9
```

---

## 🏗️ Architecture

### High-Level Architecture

```mermaid
flowchart TB
    subgraph External["🌐 External Services"]
        TV["📺 TradingView<br/>Webhook Alerts"]
        ALP["🦙 Alpaca<br/>Broker API"]
        TT["🍒 Tastytrade<br/>Broker API"]
    end
    
    subgraph Azure["☁️ Azure Cloud"]
        subgraph CAE["Container Apps Environment"]
            BOT["🤖 Trading Bot<br/>Container Apps<br/><i>Always-On (min=1)</i>"]
        end
        
        subgraph Data["💾 Data Services"]
            COSMOS["🗄️ Cosmos DB<br/>Free Tier<br/><i>1,000 RU/s + 25GB</i>"]
            KV["🔐 Key Vault<br/>Secrets"]
            AC["⚙️ App Configuration<br/>Settings + Hot-Reload"]
        end
        
        subgraph Realtime["⚡ Real-Time"]
            SIGNALR["📡 SignalR Service<br/>Free Tier<br/><i>20K msg/day</i>"]
        end
        
        subgraph Frontend["🖥️ Frontend"]
            SWA["🌐 Static Web Apps<br/>Trading Terminal<br/><i>Next.js + shadcn/ui</i>"]
        end
        
        subgraph Monitoring["📊 Monitoring"]
            MON["📈 Azure Monitor<br/>Basic (Free)"]
        end
    end
    
    TV -->|"webhook"| BOT
    BOT <-->|"trades"| ALP
    BOT <-->|"trades"| TT
    BOT -->|"read/write"| COSMOS
    BOT -->|"secrets"| KV
    BOT -->|"config"| AC
    BOT -->|"publish events"| SIGNALR
    SIGNALR -->|"WebSocket"| SWA
    SWA -->|"API proxy"| BOT
    BOT -->|"metrics"| MON
    
    style BOT fill:#E3F2FD
    style COSMOS fill:#E8F5E9
    style SIGNALR fill:#FFF3E0
    style SWA fill:#FCE4EC
```

### Container Architecture

```mermaid
flowchart TB
    subgraph Container["🐳 Trading Bot Container"]
        direction TB
        
        subgraph API["🌐 FastAPI Server"]
            WH["/webhook<br/><i>TradingView signals</i>"]
            POS["/positions<br/><i>List positions</i>"]
            ORD["/orders<br/><i>Order management</i>"]
            CFG["/config<br/><i>Hot-reload config</i>"]
            BOT_API["/bot/start, /bot/stop<br/><i>Bot control</i>"]
            HEALTH["/health, /ready<br/><i>Probes</i>"]
        end
        
        subgraph Workers["⚙️ Background Workers"]
            PM["📊 Price Monitor<br/><i>Trailing stops</i>"]
            PS["🔄 Position Sync<br/><i>Broker reconciliation</i>"]
            CW["👁️ Config Watcher<br/><i>Hot-reload listener</i>"]
        end
        
        subgraph SignalR["📡 SignalR Publisher"]
            PUB["Event Publisher<br/><i>position-updated</i><br/><i>order-filled</i><br/><i>price-changed</i>"]
        end
    end
    
    API --> Workers
    Workers --> SignalR
```

### Data Flow

```mermaid
sequenceDiagram
    participant TV as 📺 TradingView
    participant BOT as 🤖 Container Apps
    participant COSMOS as 🗄️ Cosmos DB
    participant SIGNALR as 📡 SignalR
    participant UI as 🖥️ Trading Terminal
    participant BROKER as 🏦 Broker
    
    TV->>BOT: POST /webhook (BUY AAPL)
    BOT->>BOT: Validate & Process Signal
    BOT->>BROKER: Place Order
    BROKER-->>BOT: Order Filled
    BOT->>COSMOS: Save Position
    BOT->>SIGNALR: Publish "position-updated"
    SIGNALR->>UI: WebSocket Push
    UI->>UI: Update Dashboard (instant)
    
    Note over BOT,SIGNALR: Real-time updates via SignalR
```

---

## 💰 Cost Breakdown

### Monthly Cost Estimate

| Service | Tier | Monthly Cost | Notes |
|:--------|:-----|:-------------|:------|
| **Container Apps** | Consumption (min=1) | ~$10 | Always-on for price monitoring |
| **Cosmos DB** | Free Tier | **$0** | 1,000 RU/s + 25GB (lifetime free) |
| **Static Web Apps** | Free Tier | **$0** | 100GB bandwidth |
| **SignalR Service** | Free Tier | **$0** | 20K messages/day, 20 connections |
| **Key Vault** | Standard | **$0** | 10K ops (12-month free) |
| **App Configuration** | Free Tier | **$0** | 1,000 requests/day |
| **Azure AD** | Free Tier | **$0** | Single admin user |
| **Azure Monitor** | Basic | **$0** | Free metrics + alerts |
| **Container Registry** | Basic | ~$5 | CI/CD image storage |
| **Total** | | **~$15/month** | |

### Free Tier Limits

```mermaid
pie title Azure Free Tier Allocation
    "Container Apps (180K vCPU-sec)" : 30
    "Cosmos DB (1,000 RU/s)" : 25
    "SignalR (20K msg/day)" : 20
    "Static Web Apps (100GB)" : 15
    "Other Free Services" : 10
```

> 💡 **Tip**: Enable Cosmos DB Free Tier when creating the account—it cannot be enabled later.

---

## 🔧 Prerequisites

### Required Tools

| Tool | Version | Installation |
|:-----|:--------|:-------------|
| **Azure CLI** | 2.50+ | `winget install Microsoft.AzureCLI` |
| **Docker Desktop** | Latest | [Download](https://www.docker.com/products/docker-desktop/) |
| **Node.js** | 18+ | `winget install OpenJS.NodeJS.LTS` |
| **Bicep CLI** | Latest | Included with Azure CLI |

### Azure Account Setup

```powershell
# Login to Azure
az login

# Set subscription (if you have multiple)
az account set --subscription "<subscription-name-or-id>"

# Register required providers
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.DocumentDB
az provider register --namespace Microsoft.SignalRService
az provider register --namespace Microsoft.Web
```

---

## 🚀 Deployment Guide

### Quick Deploy

```powershell
# Navigate to infrastructure directory
cd infra

# Deploy all resources (first time)
.\deploy.ps1 -Environment demo -Location eastus

# Deploy with custom resource group
.\deploy.ps1 -Environment demo -Location eastus -ResourceGroup my-trading-bot-rg
```

### Step-by-Step Deployment

```mermaid
flowchart TB
    subgraph Steps["🚀 Deployment Steps"]
        S1["1️⃣ Create Resource Group"]
        S2["2️⃣ Deploy Infrastructure<br/><i>Bicep modules</i>"]
        S3["3️⃣ Configure Secrets<br/><i>Key Vault</i>"]
        S4["4️⃣ Build & Push Container<br/><i>ACR</i>"]
        S5["5️⃣ Deploy Container App"]
        S6["6️⃣ Deploy Trading Terminal<br/><i>Static Web Apps</i>"]
        S7["7️⃣ Configure TradingView<br/><i>Update webhook URL</i>"]
    end
    
    S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7
    
    style S7 fill:#C8E6C9
```

#### Step 1: Create Resource Group

```powershell
$resourceGroup = "rg-alpha-trader-demo"
$location = "eastus"

az group create --name $resourceGroup --location $location
```

#### Step 2: Deploy Infrastructure

```powershell
# Deploy all Azure resources using Bicep
az deployment group create `
    --resource-group $resourceGroup `
    --template-file infra/main.bicep `
    --parameters environment=demo `
    --parameters location=$location
```

#### Step 3: Configure Secrets

```powershell
# Get Key Vault name from deployment output
$keyVaultName = (az deployment group show `
    --resource-group $resourceGroup `
    --name main `
    --query properties.outputs.keyVaultName.value -o tsv)

# Add secrets
az keyvault secret set --vault-name $keyVaultName --name "alpaca-api-key" --value "<your-key>"
az keyvault secret set --vault-name $keyVaultName --name "alpaca-secret-key" --value "<your-secret>"
az keyvault secret set --vault-name $keyVaultName --name "webhook-secret" --value "<your-webhook-secret>"

# Optional: Tastytrade credentials
az keyvault secret set --vault-name $keyVaultName --name "tastytrade-username" --value "<username>"
az keyvault secret set --vault-name $keyVaultName --name "tastytrade-password" --value "<password>"
```

#### Step 4: Build & Push Container

```powershell
# Get ACR name
$acrName = (az deployment group show `
    --resource-group $resourceGroup `
    --name main `
    --query properties.outputs.containerRegistryName.value -o tsv)

# Login to ACR
az acr login --name $acrName

# Build and push
docker build -t $acrName.azurecr.io/trading-bot:latest .
docker push $acrName.azurecr.io/trading-bot:latest
```

#### Step 5: Deploy Container App

```powershell
# Update container app with new image
az containerapp update `
    --name ca-alpha-trader-demo `
    --resource-group $resourceGroup `
    --image $acrName.azurecr.io/trading-bot:latest
```

#### Step 6: Deploy Trading Terminal

```powershell
cd trading-terminal

# Build Next.js app
npm run build

# Deploy to Static Web Apps (via GitHub Actions or CLI)
az staticwebapp create `
    --name swa-alpha-trader-demo `
    --resource-group $resourceGroup `
    --source https://github.com/<your-repo> `
    --branch main `
    --app-location "trading-terminal" `
    --output-location ".next"
```

#### Step 7: Configure TradingView

Update your TradingView alerts to use the new Azure endpoint:

```
https://ca-alpha-trader-demo.<region>.azurecontainerapps.io/webhook/<your-secret>
```

---

## ⚡ Real-Time Updates (SignalR)

### Architecture

```mermaid
flowchart LR
    subgraph Bot["🤖 Trading Bot"]
        PM["Position Manager"]
        OM["Order Manager"]
        PrM["Price Monitor"]
    end
    
    subgraph SignalR["📡 Azure SignalR"]
        HUB["Trading Hub"]
    end
    
    subgraph Terminal["🖥️ Trading Terminal"]
        DASH["Dashboard"]
        POS["Positions Table"]
        ORD["Orders Panel"]
    end
    
    PM -->|"position-updated"| HUB
    OM -->|"order-filled"| HUB
    PrM -->|"price-changed"| HUB
    
    HUB -->|"WebSocket"| DASH
    HUB -->|"WebSocket"| POS
    HUB -->|"WebSocket"| ORD
    
    style HUB fill:#FFF3E0
```

### SignalR Events

| Event | Trigger | Payload |
|:------|:--------|:--------|
| `position-updated` | Position change | `{ symbol, quantity, avgPrice, pnl }` |
| `order-filled` | Order execution | `{ orderId, symbol, side, filledPrice }` |
| `price-changed` | Market data update | `{ symbol, price, change }` |
| `bot-status` | Start/stop/error | `{ status, uptime, activePositions }` |
| `config-changed` | Hot-reload | `{ setting, oldValue, newValue }` |

### Client Integration

```typescript
// trading-terminal/lib/signalr.ts
import { HubConnectionBuilder } from '@microsoft/signalr';

const connection = new HubConnectionBuilder()
  .withUrl('/api/signalr')
  .withAutomaticReconnect()
  .build();

connection.on('position-updated', (position) => {
  // Update Zustand store
  usePositionStore.getState().updatePosition(position);
});

connection.on('order-filled', (order) => {
  // Show toast notification
  toast.success(`Order filled: ${order.symbol} @ $${order.filledPrice}`);
});
```

---

## 🔄 Configuration Hot-Reload

### How It Works

```mermaid
sequenceDiagram
    participant UI as 🖥️ Trading Terminal
    participant API as 🌐 API Route
    participant BOT as 🤖 Container Apps
    participant AC as ⚙️ App Configuration
    participant EB as 📢 Event Bus
    participant SIGNALR as 📡 SignalR
    
    UI->>API: PUT /api/config { dca.maxAttempts: 5 }
    API->>BOT: Proxy request
    BOT->>BOT: Validate config (Pydantic)
    BOT->>AC: Update App Configuration
    BOT->>EB: Publish ConfigChangedEvent
    EB->>BOT: Notify subscribers
    Note over BOT: Strategy, Risk, Position managers refresh
    BOT->>SIGNALR: Broadcast "config-changed"
    SIGNALR->>UI: WebSocket push
    UI->>UI: Update config editor (confirmed)
```

### Configurable Settings

| Category | Settings | Hot-Reload |
|:---------|:---------|:-----------|
| **DCA Strategy** | maxAttempts, dropPercent, progressiveMultiplier | ✅ Immediate |
| **Risk Limits** | maxPositionSize, dailyLossLimit, portfolioExposure | ✅ Immediate |
| **Trailing Stop** | activationPercent, trailPercent | ✅ Immediate |
| **Profit Taking** | targetPercent, partialExitPercent | ✅ Immediate |
| **Bot Control** | enabled, paperTrading | ✅ Immediate |

---

## 🔐 Security

### Security Architecture

```mermaid
flowchart TB
    subgraph Internet["🌐 Internet"]
        TV["TradingView"]
        ADMIN["Admin User"]
    end
    
    subgraph Azure["☁️ Azure"]
        subgraph Public["Public Endpoints"]
            SWA["Static Web Apps<br/><i>Azure AD Auth</i>"]
            CA["Container Apps<br/><i>Webhook secret</i>"]
        end
        
        subgraph Private["Private (Managed Identity)"]
            KV["Key Vault"]
            COSMOS["Cosmos DB"]
            AC["App Configuration"]
        end
    end
    
    TV -->|"HTTPS + Secret"| CA
    ADMIN -->|"Azure AD SSO"| SWA
    SWA -->|"API Proxy"| CA
    CA -->|"Managed Identity"| KV
    CA -->|"Managed Identity"| COSMOS
    CA -->|"Managed Identity"| AC
    
    style KV fill:#FFE0B2
    style Private fill:#E8F5E9
```

### Security Checklist

- [x] **HTTPS Only**: All endpoints enforce HTTPS
- [x] **Azure AD Authentication**: Trading terminal requires login
- [x] **Managed Identity**: No credentials in code/config
- [x] **Key Vault**: Secrets stored securely
- [x] **Webhook Secret**: TradingView signals authenticated
- [x] **Network Isolation**: Private endpoints for data services
- [x] **RBAC**: Least privilege access

### Secrets in Key Vault

| Secret Name | Description |
|:------------|:------------|
| `alpaca-api-key` | Alpaca API key |
| `alpaca-secret-key` | Alpaca secret key |
| `tastytrade-username` | Tastytrade username |
| `tastytrade-password` | Tastytrade password |
| `webhook-secret` | TradingView webhook authentication |

---

## 🛠️ CI/CD Pipeline

### GitHub Actions Workflows

```mermaid
flowchart LR
    subgraph Trigger["🎯 Triggers"]
        PUSH["Push to main"]
        PR["Pull Request"]
    end
    
    subgraph BotPipeline["🤖 Bot Pipeline"]
        B1["Build Docker Image"]
        B2["Run Tests"]
        B3["Push to ACR"]
        B4["Deploy Container App"]
    end
    
    subgraph UIPipeline["🖥️ UI Pipeline"]
        U1["Install Dependencies"]
        U2["Build Next.js"]
        U3["Deploy to Static Web Apps"]
    end
    
    PUSH --> BotPipeline
    PUSH --> UIPipeline
    PR --> B1 --> B2
    B2 --> B3 --> B4
    U1 --> U2 --> U3
```

### Workflow Files

| File | Trigger | Actions |
|:-----|:--------|:--------|
| `.github/workflows/deploy-bot.yml` | Push to `main` | Build, test, push ACR, deploy |
| `.github/workflows/deploy-ui.yml` | Push to `main` | Build Next.js, deploy SWA |
| `.github/workflows/pr-check.yml` | Pull request | Build, test, lint |

---

## 📊 Monitoring

### Azure Monitor Dashboard

```mermaid
flowchart TB
    subgraph Metrics["📈 Metrics"]
        CPU["CPU Usage"]
        MEM["Memory Usage"]
        REQ["Request Count"]
        LAT["Response Latency"]
        ERR["Error Rate"]
    end
    
    subgraph Alerts["🚨 Alerts"]
        A1["CPU > 80%"]
        A2["Memory > 85%"]
        A3["Error Rate > 5%"]
        A4["Response Time > 5s"]
    end
    
    Metrics --> Alerts
    
    Alerts -->|"Email/SMS"| NOTIFY["📧 Notifications"]
```

### Recommended Alerts

| Alert | Condition | Severity |
|:------|:----------|:---------|
| High CPU | CPU > 80% for 5 min | Warning |
| High Memory | Memory > 85% for 5 min | Warning |
| Error Spike | Error rate > 5% | Critical |
| Slow Response | P95 latency > 5s | Warning |
| Container Restart | Restart count > 3/hour | Critical |

---

## 🔧 Troubleshooting

### Common Issues

#### Container Won't Start

```powershell
# Check container logs
az containerapp logs show `
    --name ca-alpha-trader-demo `
    --resource-group rg-alpha-trader-demo `
    --follow

# Check revision status
az containerapp revision list `
    --name ca-alpha-trader-demo `
    --resource-group rg-alpha-trader-demo
```

#### SignalR Connection Issues

```powershell
# Check SignalR health
az signalr show `
    --name signalr-alpha-trader-demo `
    --resource-group rg-alpha-trader-demo `
    --query "hostName"

# Test connection
curl -I https://signalr-alpha-trader-demo.service.signalr.net/client/
```

#### Cosmos DB Throttling

```powershell
# Check RU consumption
az cosmosdb sql database throughput show `
    --account-name cosmos-alpha-trader-demo `
    --resource-group rg-alpha-trader-demo `
    --name trading-bot
```

### Health Check Endpoints

| Endpoint | Expected Response | Description |
|:---------|:------------------|:------------|
| `/health` | `200 OK` | Container is running |
| `/ready` | `200 OK` | All dependencies connected |
| `/status` | JSON with bot status | Detailed bot information |

---

## 📁 Infrastructure Files

```
infra/
├── main.bicep                    # Main orchestration
├── modules/
│   ├── container-apps.bicep      # Container Apps + Environment
│   ├── cosmos-db.bicep           # Cosmos DB account + containers
│   ├── signalr.bicep             # SignalR Service
│   ├── key-vault.bicep           # Key Vault + RBAC
│   ├── app-configuration.bicep   # App Configuration
│   ├── static-web-app.bicep      # Static Web Apps
│   ├── container-registry.bicep  # Azure Container Registry
│   └── monitoring.bicep          # Azure Monitor + Alerts
├── parameters/
│   ├── demo.bicepparam           # Demo environment parameters
│   └── live.bicepparam           # Live environment parameters
├── deploy.ps1                    # PowerShell deployment script
└── deploy.sh                     # Bash deployment script
```

---

<div align="center">

**Ready to deploy? Run `.\infra\deploy.ps1 -Environment demo`**

[![Azure](https://img.shields.io/badge/Deploy_to-Azure-0089D6?style=for-the-badge&logo=microsoft-azure)](https://portal.azure.com)

</div>
