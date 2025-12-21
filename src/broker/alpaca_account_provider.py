"""
Alpaca implementation of IBrokerAccountProvider.

This module re-exports the AlpacaAccountProvider from src.trading for the broker
abstraction layer. The implementation lives in src/trading/alpaca_account_provider.py
to avoid code duplication.

Note: The src/trading version implements IAccountProvider while IBrokerAccountProvider
has the same method signatures. Both interfaces are satisfied by the same class.
"""
from src.trading.alpaca_account_provider import AlpacaAccountProvider
from src.broker.interfaces import IBrokerAccountProvider

# Re-export for backward compatibility
# The AlpacaAccountProvider class implements the methods required by IBrokerAccountProvider
# even though it formally inherits from IAccountProvider
__all__ = ["AlpacaAccountProvider"]
