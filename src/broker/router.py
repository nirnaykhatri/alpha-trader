"""
Broker router implementation.
"""
from typing import Dict, Optional
from src.broker.interfaces import (
    IBrokerRouter, BrokerType, IBrokerOrderExecutor, 
    IBrokerAccountProvider, IBrokerMarketDataProvider
)
from src.interfaces import IConfigurationManager
from src.core.logging_config import get_logger
from src.exceptions import ConfigurationException

logger = get_logger(__name__)

class BrokerRouter(IBrokerRouter):
    """
    Routes orders and data requests to the appropriate broker based on configuration.
    
    This class acts as a central dispatch for all broker-related operations. It determines
    which broker handles a specific symbol based on configuration and provides access
    to the corresponding executor and provider instances.
    """
    
    def __init__(self, config: IConfigurationManager, 
                 executors: Dict[BrokerType, IBrokerOrderExecutor],
                 account_providers: Dict[BrokerType, IBrokerAccountProvider],
                 market_data_providers: Dict[BrokerType, IBrokerMarketDataProvider]):
        """
        Initialize the broker router.
        
        Args:
            config: Configuration manager for loading routing rules.
            executors: Dictionary mapping BrokerType to order executors.
            account_providers: Dictionary mapping BrokerType to account providers.
            market_data_providers: Dictionary mapping BrokerType to market data providers.
        """
        self._config = config
        self._executors = executors
        self._account_providers = account_providers
        self._market_data_providers = market_data_providers
        
        # Load symbol routing map from config
        self._symbol_map = self._load_symbol_map()
        self._default_broker = self._load_default_broker()
        
    def _load_symbol_map(self) -> Dict[str, BrokerType]:
        """
        Load symbol-to-broker mapping from config.
        
        Reads the 'trading.brokers.routing' configuration section to build a map
        of specific symbols to their assigned brokers.
        
        Returns:
            Dict[str, BrokerType]: Mapping of symbol (uppercase) to BrokerType.
        """
        mapping = {}
        # Config format: trading.brokers.routing = {"AAPL": "alpaca", "SPY": "tastytrade"}
        routing_config = self._config.get_config("trading.brokers.routing", {})
        
        for symbol, broker_name in routing_config.items():
            try:
                broker_type = BrokerType(broker_name.lower())
                mapping[symbol.upper()] = broker_type
            except ValueError:
                logger.warning(f"Invalid broker '{broker_name}' configured for symbol '{symbol}'. Ignoring.")
                
        return mapping
        
    def _load_default_broker(self) -> BrokerType:
        """
        Load default broker from config.
        
        Reads 'trading.brokers.default' from config. Defaults to ALPACA if not set
        or invalid.
        
        Returns:
            BrokerType: The default broker type.
        """
        default_name = self._config.get_config("trading.brokers.default", "alpaca")
        try:
            return BrokerType(default_name.lower())
        except ValueError:
            logger.error(f"Invalid default broker '{default_name}'. Falling back to Alpaca.")
            return BrokerType.ALPACA

    def get_broker_for_symbol(self, symbol: str) -> BrokerType:
        """
        Determine which broker to use for a symbol.
        
        Args:
            symbol: The trading symbol.
            
        Returns:
            BrokerType: The assigned broker for the symbol, or the default broker.
        """
        if not symbol:
            return self._default_broker
            
        return self._symbol_map.get(symbol.upper(), self._default_broker)
        
    def get_order_executor(self, broker: BrokerType) -> IBrokerOrderExecutor:
        """
        Get the order executor for a specific broker.
        
        Args:
            broker: The broker type.
            
        Returns:
            IBrokerOrderExecutor: The registered order executor.
            
        Raises:
            ConfigurationException: If no executor is configured for the broker.
        """
        if broker not in self._executors:
            raise ConfigurationException(f"No order executor configured for broker: {broker.value}")
        return self._executors[broker]
        
    def get_account_provider(self, broker: BrokerType) -> IBrokerAccountProvider:
        """
        Get the account provider for a specific broker.
        
        Args:
            broker: The broker type.
            
        Returns:
            IBrokerAccountProvider: The registered account provider.
            
        Raises:
            ConfigurationException: If no account provider is configured for the broker.
        """
        if broker not in self._account_providers:
            raise ConfigurationException(f"No account provider configured for broker: {broker.value}")
        return self._account_providers[broker]
        
    def get_market_data_provider(self, broker: BrokerType) -> IBrokerMarketDataProvider:
        """
        Get the market data provider for a specific broker.
        
        Args:
            broker: The broker type.
            
        Returns:
            IBrokerMarketDataProvider: The registered market data provider.
            
        Raises:
            ConfigurationException: If no market data provider is configured for the broker.
        """
        if broker not in self._market_data_providers:
            raise ConfigurationException(f"No market data provider configured for broker: {broker.value}")
        return self._market_data_providers[broker]

    def get_registered_brokers(self) -> list[BrokerType]:
        """Get list of all registered brokers."""
        return list(self._account_providers.keys())
