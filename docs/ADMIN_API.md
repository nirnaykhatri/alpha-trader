# Admin API Reference

This document provides comprehensive documentation for the Trading Bot's Admin API, including authentication, endpoints, and usage examples.

## Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
  - [Azure AD JWT Authentication](#azure-ad-jwt-authentication)
  - [Local Development Mode](#local-development-mode)
  - [Roles and Permissions](#roles-and-permissions)
- [Base URL](#base-url)
- [API Endpoints](#api-endpoints)
  - [Bot Lifecycle](#bot-lifecycle)
  - [Order Management](#order-management)
  - [Position Management](#position-management)
  - [Configuration](#configuration)
  - [Fund Management](#fund-management)
  - [SignalR Negotiate](#signalr-negotiate)
- [Error Handling](#error-handling)
- [TypeScript Client](#typescript-client)
- [Health and Readiness](#health-and-readiness)

---

## Overview

The Admin API provides authenticated endpoints for controlling the trading bot, managing orders, positions, configuration, and funds. All admin endpoints require proper authentication and are protected by role-based access control.

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Trading Terminal UI                         │
│                   (trading-terminal/lib/)                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Admin API Client                             │
│               (trading-terminal/lib/admin-api.ts)                │
│   • Typed requests/responses                                     │
│   • Token provider pattern                                       │
│   • Automatic header injection                                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Admin Router                         │
│                 (src/signals/admin_router.py)                    │
│   • Azure AD JWT validation                                      │
│   • Role-based authorization                                     │
│   • Risk validation on orders                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Service Layer                               │
│                 (src/services/admin_services.py)                 │
│   • IOrderService, IPositionService                              │
│   • IBotLifecycleService, IConfigService                         │
│   • IRiskValidationService, IFundService                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Authentication

### Azure AD JWT Authentication

In production, the Admin API uses Azure Active Directory for authentication. Tokens are validated against Azure AD's JWKS endpoint.

**Required Configuration** (in `settings.toml` or Azure App Configuration):

```toml
[azure.auth]
tenant_id = "your-tenant-id"           # Azure AD tenant
client_id = "your-client-id"           # App registration client ID
audience = "api://your-api-audience"   # Token audience
```

**Token Validation:**

1. **Signature Verification**: Validates JWT signature using Azure AD's JWKS keys
2. **Issuer Check**: Validates the `iss` claim matches Azure AD
3. **Audience Check**: Validates the `aud` claim matches the configured API
4. **Expiration Check**: Validates the token is not expired
5. **Role Check**: Validates the user has required roles

**Request Header:**

```
Authorization: Bearer eyJ0eXAiOiJKV1QiLC...
```

### Local Development Mode

For local development, set `azure.auth.allow_dev_mode = true`:

```toml
[azure.auth]
allow_dev_mode = true
dev_user_id = "dev-user"
dev_user_roles = ["Admin", "Trader"]
```

> **Warning**: Never enable dev mode in production.

### Roles and Permissions

| Role | Permissions |
|------|-------------|
| `Admin` | Full access to all endpoints |
| `Trader` | Place/cancel orders, manage positions |
| `Viewer` | Read-only access to status and configuration |

---

## Base URL

| Environment | Base URL |
|-------------|----------|
| Local Development | `http://localhost:8080` |
| Azure Container Apps | `https://<app-name>.<region>.azurecontainerapps.io` |

---

## API Endpoints

### Bot Lifecycle

#### GET /admin/bot/state

Get current bot status and state information.

**Response:**

```json
{
  "success": true,
  "data": {
    "is_running": true,
    "is_paused": false,
    "positions_count": 3,
    "pending_orders_count": 1,
    "uptime_seconds": 3600,
    "last_signal_time": "2024-01-15T10:30:00Z"
  }
}
```

#### POST /admin/bot/start

Start the trading bot.

**Response:**

```json
{
  "success": true,
  "message": "Bot started successfully"
}
```

#### POST /admin/bot/pause

Pause the trading bot (stops new trades but maintains positions).

**Response:**

```json
{
  "success": true,
  "message": "Bot paused successfully"
}
```

#### POST /admin/bot/stop

Stop the trading bot completely.

**Response:**

```json
{
  "success": true,
  "message": "Bot stopped successfully"
}
```

---

### Order Management

#### POST /admin/orders

Place a new order.

**Request Body:**

```json
{
  "symbol": "AAPL",
  "side": "buy",
  "quantity": 10,
  "order_type": "market",
  "limit_price": null,
  "stop_price": null,
  "time_in_force": "day"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `symbol` | string | Yes | Trading symbol (e.g., "AAPL") |
| `side` | string | Yes | "buy" or "sell" |
| `quantity` | number | Yes | Number of shares |
| `order_type` | string | No | "market", "limit", "stop", "stop_limit" (default: "market") |
| `limit_price` | number | No | Limit price for limit orders |
| `stop_price` | number | No | Stop price for stop orders |
| `time_in_force` | string | No | "day", "gtc", "ioc", "fok" (default: "day") |

**Risk Validation:**

Before order placement, the following risk checks are performed:
- Position size limits
- Portfolio concentration limits
- Daily trading limits
- Available capital checks

**Response:**

```json
{
  "success": true,
  "order_id": "abc123",
  "message": "Order placed successfully"
}
```

#### DELETE /admin/orders/{order_id}

Cancel a pending order.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `order_id` | string | Order ID to cancel |

**Response:**

```json
{
  "success": true,
  "message": "Order cancelled successfully"
}
```

#### GET /admin/orders/pending

Get all pending orders.

**Response:**

```json
{
  "success": true,
  "orders": [
    {
      "order_id": "abc123",
      "symbol": "AAPL",
      "side": "buy",
      "quantity": 10,
      "order_type": "limit",
      "limit_price": 175.00,
      "status": "pending",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

---

### Position Management

#### POST /admin/positions/{symbol}/close

Close a specific position.

**Parameters:**

| Name | Type | Description |
|------|------|-------------|
| `symbol` | string | Symbol of position to close |

**Request Body (Optional):**

```json
{
  "percentage": 100
}
```

**Response:**

```json
{
  "success": true,
  "order_id": "xyz789",
  "message": "Position close order placed"
}
```

#### POST /admin/positions/close-all

Close all open positions.

**Response:**

```json
{
  "success": true,
  "closed_count": 5,
  "message": "All positions closed"
}
```

---

### Configuration

#### GET /admin/config

Get current bot configuration.

**Response:**

```json
{
  "success": true,
  "config": {
    "trading": {
      "max_position_size": 10000,
      "max_positions": 10,
      "risk_per_trade": 0.02
    },
    "strategy": {
      "dca_enabled": true,
      "dca_levels": 5,
      "martingale_factor": 1.5
    }
  }
}
```

#### PUT /admin/config

Update bot configuration.

**Request Body:**

```json
{
  "trading.max_position_size": 15000,
  "strategy.dca_levels": 7
}
```

**Response:**

```json
{
  "success": true,
  "message": "Configuration updated",
  "updated_keys": ["trading.max_position_size", "strategy.dca_levels"]
}
```

---

### Fund Management

#### GET /admin/funds/summary

Get fund summary including deposits, withdrawals, and current balance.

**Response:**

```json
{
  "success": true,
  "summary": {
    "total_deposited": 50000.00,
    "total_withdrawn": 5000.00,
    "current_equity": 52500.00,
    "total_profit_loss": 7500.00,
    "roi_percentage": 16.67
  }
}
```

#### POST /admin/funds/deposit

Record a deposit.

**Request Body:**

```json
{
  "amount": 10000.00,
  "notes": "Monthly investment"
}
```

**Response:**

```json
{
  "success": true,
  "message": "Deposit recorded",
  "new_balance": 62500.00
}
```

#### POST /admin/funds/withdraw

Record a withdrawal.

**Request Body:**

```json
{
  "amount": 5000.00,
  "notes": "Profit taking"
}
```

**Response:**

```json
{
  "success": true,
  "message": "Withdrawal recorded",
  "new_balance": 57500.00
}
```

#### POST /admin/funds/allocate

Allocate funds between strategies.

**Request Body:**

```json
{
  "allocations": {
    "aggressive": 0.3,
    "moderate": 0.5,
    "conservative": 0.2
  }
}
```

---

### SignalR Negotiate

#### POST /admin/signalr/negotiate

Get SignalR connection information for real-time updates.

**Response:**

```json
{
  "success": true,
  "url": "https://your-signalr.service.signalr.net/client/?hub=trading",
  "accessToken": "eyJ0eXAiOiJKV1QiLC..."
}
```

**Usage:**

```typescript
import * as signalR from '@microsoft/signalr';
import { negotiateSignalR } from './admin-api';

const negotiation = await negotiateSignalR();
const connection = new signalR.HubConnectionBuilder()
  .withUrl(negotiation.url, {
    accessTokenFactory: () => negotiation.accessToken
  })
  .build();

await connection.start();
```

---

## Error Handling

All error responses follow this structure:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid symbol format",
    "details": {
      "field": "symbol",
      "value": "invalid123"
    }
  }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `UNAUTHORIZED` | 401 | Missing or invalid authentication token |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `NOT_FOUND` | 404 | Resource not found |
| `VALIDATION_ERROR` | 400 | Request validation failed |
| `RISK_LIMIT_EXCEEDED` | 400 | Order violates risk limits |
| `INTERNAL_ERROR` | 500 | Internal server error |

---

## TypeScript Client

The Trading Terminal includes a typed TypeScript client for all admin endpoints.

### Installation

The client is located at `trading-terminal/lib/admin-api.ts`.

### Setup

```typescript
import { setTokenProvider, setBaseUrl } from './admin-api';

// Configure base URL
setBaseUrl('https://your-api.azurecontainerapps.io');

// Configure token provider for Azure AD authentication
setTokenProvider(async () => {
  // Return Azure AD access token
  return await msalInstance.acquireTokenSilent({
    scopes: ['api://your-api/.default']
  }).then(result => result.accessToken);
});
```

### Usage Examples

```typescript
import {
  getBotState,
  placeOrder,
  closePosition,
  getConfig,
  negotiateSignalR
} from './admin-api';

// Get bot status
const state = await getBotState();
console.log(`Bot running: ${state.is_running}`);

// Place an order
const order = await placeOrder({
  symbol: 'AAPL',
  side: 'buy',
  quantity: 10,
  order_type: 'market'
});
console.log(`Order placed: ${order.order_id}`);

// Close a position
await closePosition('AAPL');

// Get configuration
const config = await getConfig();
console.log(`Max position size: ${config.trading.max_position_size}`);

// Connect to SignalR for real-time updates
const signalr = await negotiateSignalR();
// Use signalr.url and signalr.accessToken to connect
```

---

## Health and Readiness

The API exposes health check endpoints for container orchestration.

### GET /health

Basic health check. Returns 200 if the service is alive.

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### GET /ready

Readiness check with dependency status. Returns 200 only if all critical dependencies are healthy.

```json
{
  "status": "ready",
  "dependencies": {
    "signalr": {
      "healthy": true,
      "configured": true,
      "message": "SignalR configured",
      "hub_name": "trading"
    },
    "azure_config": {
      "healthy": true,
      "configured": true,
      "azure_connected": true,
      "message": "Azure App Config connected"
    },
    "database": {
      "healthy": true,
      "message": "Database connected"
    }
  }
}
```

**Dependency Checks:**

| Dependency | Required | Description |
|------------|----------|-------------|
| `signalr` | No | SignalR connection string configuration |
| `azure_config` | No | Azure App Configuration availability |
| `database` | Yes | Database connection status |

---

## Azure App Configuration Integration

The ConfigurationManager now supports Azure App Configuration for centralized settings management.

### Initialization

```python
from src.config import ConfigurationManager

config = ConfigurationManager()
await config.initialize_azure_config()
```

### Async Config Retrieval

```python
# Azure-first with local fallback
value = await config.get_config_async("trading.max_position_size", 10000)
```

### Configuration Hierarchy

1. **Azure App Configuration** (if connected) - Highest priority
2. **Environment Variables** 
3. **Local settings.toml** - Lowest priority

---

## Related Documentation

- [User Guide](./USER_GUIDE.md)
- [Configuration Guide](./CONFIGURATION.md)
- [Azure Deployment](./AZURE_DEPLOYMENT.md)
- [Monitoring Architecture](./MONITORING_ARCHITECTURE.md)
