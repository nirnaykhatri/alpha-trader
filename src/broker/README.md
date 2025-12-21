# Broker Abstraction Layer

This module provides a unified interface for interacting with multiple brokers (Alpaca, Tastytrade, etc.).

## Architecture

- **Interfaces**: Defined in `interfaces.py`. All broker implementations must adhere to these.
- **Router**: `BrokerRouter` (in `router.py`) routes orders and data requests to the appropriate broker based on the symbol.
- **Implementations**:
  - `alpaca_order_executor.py`: Alpaca order execution.
  - `alpaca_account_provider.py`: Alpaca account data.
  - `tastytrade/`: Tastytrade implementation (in progress).

## Usage

The `OrderManager` and `RiskManager` interact with the `BrokerRouter` or specific providers via interfaces, ensuring they are decoupled from specific broker SDKs.

## Configuration

Configure routing in `config.yaml`:

```yaml
trading:
  brokers:
    default: "alpaca"
    routing:
      AAPL: "alpaca"
      SPY: "tastytrade"
```
