Research Azure NoSQL free options

Using "Fetch Web Page"

Fetched 4 resources

Using "Fetch Web Page"

Fetched 2 resources

## Plan: Azure Migration for Trading Bot

Migrate the trading bot from local ngrok-based hosting to a production-grade Azure cloud deployment using free-tier services, with a full-featured trading terminal for management and automated CI/CD.

---

### Steps

1. **Refactor code for Azure Container Apps (always-on)**: Modify signal_listener.py to work as a containerized app with Azure-native HTTPS ingress, configure **minimum replicas = 1** to keep the bot running 24/7 for trailing stop and profit-taking price monitoring, and add health/liveness probes for Azure to restart on failures.

2. **Provision free-tier Azure infrastructure**: Deploy **Azure Container Apps** (min=1 replica, ~$10/mo); **Azure Cosmos DB Free Tier** — 1,000 RU/s + 25GB forever free, flexible JSON schema; **Azure Static Web Apps (Free)** — for trading terminal; **Azure Key Vault** — secrets; **Azure App Configuration (Free)** — settings; **Azure AD** — authentication.

3. **Migrate data storage to Cosmos DB NoSQL**: Create a new `src/database/cosmos_manager.py` implementing the same interface as database_manager.py, use `azure-cosmos` async SDK, design containers for `positions`, `orders`, `trades`, `signals` with partition key on `symbol`, and leverage schema-free JSON for evolving data models.

4. **Build full trading terminal web UI**: Create a React dashboard on Azure Static Web Apps with: real-time position/P&L display, manual order entry (buy/sell/close), bot controls (start/stop/pause), configuration editor (DCA settings, risk limits), fund management (deposit tracking, capital allocation), order history and trade log, strategy performance charts — protected by **Azure AD authentication**.

5. **Implement Azure security with Key Vault + Azure AD**: Move all secrets from .secrets.toml to Key Vault, enable Managed Identity for Container Apps, configure Azure AD app registration for the trading terminal with appropriate user roles, and enforce HTTPS-only endpoints.

6. **Set up GitHub Actions CI/CD pipeline**: Create `.github/workflows/azure-deploy.yml` to build Docker image on push to `main`, push to Azure Container Registry, deploy to Container Apps, and run tests before deployment; add separate workflow for Static Web Apps dashboard deployment.

7. **Remove ngrok and configure stable Azure endpoint**: Delete start_ngrok_standalone.py, setup_ngrok_auth.py, check_ngrok_status.py, and related batch files; update src/config/config_manager.py to support Azure App Configuration; configure TradingView webhook to use permanent `https://<app-name>.<region>.azurecontainerapps.io/webhook` URL.

---

### Estimated Monthly Cost

| Service | Free Tier / Pricing | Estimated Cost |
|---------|---------------------|----------------|
| Container Apps (min=1, always-on) | Beyond free tier | **~$10** |
| Cosmos DB Free Tier | 1,000 RU/s + 25GB free | **$0** |
| Static Web Apps | 100GB bandwidth free | **$0** |
| Key Vault | 10K ops (12-mo free) | **$0** |
| App Configuration | 1,000 req/day free | **$0** |
| Azure AD | Free tier for basic auth | **$0** |
| Container Registry (Basic) | For CI/CD images | **~$5** |
| **Total** | | **~$15/month** |

---

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        AZURE CLOUD                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────────┐    webhook     ┌─────────────────────────┐   │
│   │ TradingView  │───────────────▶│  Azure Container Apps   │   │
│   └──────────────┘                │  (Trading Bot - 24/7)   │   │
│                                   │  - FastAPI webhooks     │   │
│                                   │  - Price monitoring     │   │
│                                   │  - Trailing/profit-take │   │
│                                   └───────────┬─────────────┘   │
│                                               │                  │
│   ┌──────────────────────────────────────────┼──────────────┐   │
│   │                                          ▼              │   │
│   │   ┌─────────────┐    ┌─────────────┐   ┌────────────┐  │   │
│   │   │  Key Vault  │    │ App Config  │   │ Cosmos DB  │  │   │
│   │   │  (Secrets)  │    │ (Settings)  │   │  (NoSQL)   │  │   │
│   │   └─────────────┘    └─────────────┘   └────────────┘  │   │
│   │         ▲                   ▲                ▲         │   │
│   │         │     Managed Identity              │         │   │
│   │         └───────────────────┴───────────────┘         │   │
│   └───────────────────────────────────────────────────────┘   │
│                                                                  │
│   ┌─────────────────────────────────────────────────────────┐   │
│   │           Azure Static Web Apps (Trading Terminal)       │   │
│   │   ┌─────────────────────────────────────────────────┐   │   │
│   │   │  React Dashboard (Azure AD Protected)           │   │   │
│   │   │  - Positions & P&L    - Manual Orders           │   │   │
│   │   │  - Bot Start/Stop     - Config Editor           │   │   │
│   │   │  - Fund Management    - Trade History           │   │   │
│   │   └─────────────────────────────────────────────────┘   │   │
│   └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│   ┌──────────────────────┐    ┌──────────────────────────┐      │
│   │  GitHub Actions      │───▶│  Container Registry      │      │
│   │  (CI/CD Pipeline)    │    │  (Docker Images)         │      │
│   └──────────────────────┘    └──────────────────────────┘      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

### Further Considerations

1. **Cosmos DB container design**: Single container with `type` field (position/order/trade) for simplicity, or separate containers per entity for better performance isolation — which approach for your query patterns?

2. **Trading terminal framework**: React with TypeScript (most common, large ecosystem) vs Blazor WebAssembly (C# end-to-end if you prefer .NET) — which frontend stack do you prefer?

3. **Azure AD user management**: Single admin user only, or multiple users with roles (admin/viewer/trader) — who needs access to the trading terminal?

4. **Container Apps environment**: Should the bot run in a dedicated environment (isolated, slightly higher cost) or shared environment (cost-efficient) — do you have other apps to deploy alongside?

5. **Monitoring depth**: Basic Azure Monitor (free metrics + alerts) vs Application Insights with distributed tracing (~$5/mo for logs) — how much observability do you need for debugging production issues?