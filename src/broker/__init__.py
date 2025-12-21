"""
Broker abstraction layer.

This package provides a unified interface for interacting with multiple brokers
(e.g., Alpaca, Tastytrade) through a common set of interfaces and a routing mechanism.
"""

from src.broker.interfaces import (
    BrokerType,
    IBrokerAccountProvider,
    IBrokerOrderExecutor,
    IBrokerMarketDataProvider,
    IBrokerRouter
)
from src.broker.router import BrokerRouter
from src.broker.alpaca_account_provider import AlpacaAccountProvider
from src.broker.alpaca_order_executor import AlpacaOrderExecutor

__all__ = [
    "BrokerType",
    "IBrokerAccountProvider",
    "IBrokerOrderExecutor",
    "IBrokerMarketDataProvider",
    "IBrokerRouter",
    "BrokerRouter",
    "AlpacaAccountProvider",
    "AlpacaOrderExecutor"
]
