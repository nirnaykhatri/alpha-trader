"""
Broker Factory and Manager - Dynamic broker instantiation and multi-broker management.
Provides centralized management for multiple broker connections with symbol routing.
"""

import asyncio
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging

from .broker_interfaces import (
    IBrokerFactory, IBrokerProvider, IBrokerRouter, ITradingClient, 
    IMarketDataProvider, BrokerType, BrokerCredentials, SymbolBrokerMapping,
    UniversalOrder, OrderResponse, Position, AccountInfo, MarketQuote,
    Exchange
)
from .exchange_market_hours import ExchangeAwareMarketHoursManager, IMultiExchangeMarketHoursManager
from ..interfaces import IConfigurationManager
from ..exceptions import TradingException, ConfigurationException
from ..core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass 
class BrokerHealth:
    """Broker health status tracking."""
    broker_type: BrokerType
    is_healthy: bool = True
    last_health_check: Optional[datetime] = None
    consecutive_failures: int = 0
    error_message: Optional[str] = None
    last_successful_operation: Optional[datetime] = None


@dataclass
class BrokerManagerConfig:
    """Configuration for broker manager."""
    health_check_interval_seconds: int = 60
    max_consecutive_failures: int = 3
    enable_failover: bool = True
    symbol_routing_strategy: str = "priority"  # "priority", "round_robin", "load_balance"
    default_broker_type: BrokerType = BrokerType.ALPACA
    
    # Performance settings
    connection_timeout_seconds: int = 30
    operation_timeout_seconds: int = 10
    max_concurrent_operations: int = 50


class BrokerFactory(IBrokerFactory):
    """Factory for creating broker provider instances."""
    
    def __init__(self):
        """Initialize broker factory with registry of supported brokers."""
        self._broker_registry: Dict[BrokerType, type] = {}
        self._register_default_brokers()
    
    def _register_default_brokers(self) -> None:
        """Register default supported broker implementations."""
        # Import broker implementations dynamically to avoid circular imports
        try:
            from ..brokers.alpaca_broker import AlpacaBrokerProvider
            self._broker_registry[BrokerType.ALPACA] = AlpacaBrokerProvider
            logger.debug("✅ Registered Alpaca broker provider")
        except ImportError as e:
            logger.warning(f"⚠️ Could not register Alpaca broker: {e}")
        
        try:
            from ..brokers.mock_broker import MockBrokerProvider
            self._broker_registry[BrokerType.MOCK] = MockBrokerProvider
            logger.debug("✅ Registered Mock broker provider")
        except ImportError as e:
            logger.debug(f"Mock broker not available: {e}")
    
    def register_broker_provider(self, broker_type: BrokerType, provider_class: type) -> None:
        """Register a custom broker provider."""
        self._broker_registry[broker_type] = provider_class
        logger.info(f"✅ Registered custom broker provider: {broker_type.value}")
    
    def create_broker_provider(
        self, 
        broker_type: BrokerType, 
        credentials: BrokerCredentials
    ) -> IBrokerProvider:
        """Create a broker provider instance."""
        if broker_type not in self._broker_registry:
            raise ConfigurationException(f"Unsupported broker type: {broker_type.value}")
        
        provider_class = self._broker_registry[broker_type]
        
        try:
            provider = provider_class()
            logger.info(f"✅ Created {broker_type.value} broker provider")
            return provider
        except Exception as e:
            raise TradingException(f"Failed to create {broker_type.value} provider: {e}")
    
    def get_supported_broker_types(self) -> List[BrokerType]:
        """Get list of supported broker types."""
        return list(self._broker_registry.keys())
    
    def is_broker_supported(self, broker_type: BrokerType) -> bool:
        """Check if a broker type is supported."""
        return broker_type in self._broker_registry


class BrokerRouter(IBrokerRouter):
    """Routes symbols to appropriate brokers based on configuration."""
    
    def __init__(self, default_broker_type: BrokerType = BrokerType.ALPACA):
        """Initialize broker router."""
        self._symbol_mappings: Dict[str, SymbolBrokerMapping] = {}
        self._default_broker_type = default_broker_type
        self._broker_providers: Dict[BrokerType, IBrokerProvider] = {}
    
    def set_broker_providers(self, broker_providers: Dict[BrokerType, IBrokerProvider]) -> None:
        """Set available broker providers."""
        self._broker_providers = broker_providers
        logger.info(f"✅ Broker router configured with {len(broker_providers)} providers")
    
    async def get_broker_for_symbol(self, symbol: str) -> BrokerType:
        """Get the appropriate broker for a symbol."""
        # Check if symbol has specific mapping
        if symbol in self._symbol_mappings:
            mapping = self._symbol_mappings[symbol]
            
            # Check if the broker is available and healthy
            if mapping.broker_type in self._broker_providers:
                provider = self._broker_providers[mapping.broker_type]
                
                try:
                    is_healthy = await provider.health_check()
                    if is_healthy and provider.supports_symbol(symbol):
                        return mapping.broker_type
                except Exception as e:
                    logger.warning(f"⚠️ Health check failed for {mapping.broker_type.value}: {e}")
        
        # Fallback to default broker
        return self._default_broker_type
    
    async def get_trading_client_for_symbol(self, symbol: str) -> ITradingClient:
        """Get trading client for a specific symbol."""
        broker_type = await self.get_broker_for_symbol(symbol)
        
        if broker_type not in self._broker_providers:
            raise TradingException(f"No provider available for broker type: {broker_type.value}")
        
        return self._broker_providers[broker_type].trading_client
    
    async def get_market_data_provider_for_symbol(self, symbol: str) -> IMarketDataProvider:
        """Get market data provider for a specific symbol."""
        broker_type = await self.get_broker_for_symbol(symbol)
        
        if broker_type not in self._broker_providers:
            raise TradingException(f"No provider available for broker type: {broker_type.value}")
        
        return self._broker_providers[broker_type].market_data_provider
    
    def add_symbol_mapping(self, mapping: SymbolBrokerMapping) -> None:
        """Add or update symbol-to-broker mapping."""
        self._symbol_mappings[mapping.symbol] = mapping
        logger.info(f"✅ Added symbol mapping: {mapping.symbol} → {mapping.broker_type.value}")
    
    def remove_symbol_mapping(self, symbol: str) -> None:
        """Remove symbol-to-broker mapping."""
        if symbol in self._symbol_mappings:
            removed_mapping = self._symbol_mappings.pop(symbol)
            logger.info(f"✅ Removed symbol mapping: {symbol} (was {removed_mapping.broker_type.value})")
    
    def get_all_mappings(self) -> List[SymbolBrokerMapping]:
        """Get all symbol-to-broker mappings."""
        return list(self._symbol_mappings.values())


class BrokerManager:
    """Centralized manager for multiple broker connections."""
    
    def __init__(
        self, 
        config: IConfigurationManager,
        broker_config: Optional[BrokerManagerConfig] = None,
        market_hours_manager: Optional[IMultiExchangeMarketHoursManager] = None
    ):
        """Initialize broker manager."""
        self._config = config
        self._broker_config = broker_config or BrokerManagerConfig()
        
        # Core components
        self._factory = BrokerFactory()
        self._router = BrokerRouter(self._broker_config.default_broker_type)
        
        # Exchange-aware market hours manager
        self._market_hours_manager = market_hours_manager or ExchangeAwareMarketHoursManager(config, self)
        
        # Broker management
        self._broker_providers: Dict[BrokerType, IBrokerProvider] = {}
        self._broker_health: Dict[BrokerType, BrokerHealth] = {}
        
        # Operational state
        self._is_initialized = False
        self._health_check_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        logger.info("✅ BrokerManager initialized")
    
    async def initialize(self) -> None:
        """Initialize all configured brokers."""
        if self._is_initialized:
            logger.warning("⚠️ BrokerManager already initialized")
            return
        
        logger.info("🚀 Initializing BrokerManager...")
        
        # Load broker configurations from config
        await self._load_broker_configurations()
        
        # Initialize symbol routing
        await self._load_symbol_mappings()
        
        # Start health monitoring
        if self._broker_config.health_check_interval_seconds > 0:
            self._health_check_task = asyncio.create_task(self._health_monitoring_loop())
        
        self._is_initialized = True
        logger.info(f"✅ BrokerManager initialized with {len(self._broker_providers)} brokers")
    
    async def _load_broker_configurations(self) -> None:
        """Load and initialize broker configurations from config."""
        # Get broker configurations
        brokers_config = self._config.get_config("brokers", {})
        
        for broker_name, broker_settings in brokers_config.items():
            try:
                # Parse broker type
                broker_type = BrokerType(broker_name.lower())
                
                # Create credentials
                credentials = BrokerCredentials(
                    broker_type=broker_type,
                    api_key=broker_settings.get("api_key"),
                    secret_key=broker_settings.get("secret_key"),
                    base_url=broker_settings.get("base_url"),
                    environment=broker_settings.get("environment", "paper"),
                    additional_params=broker_settings.get("additional_params", {})
                )
                
                # Create and initialize broker provider
                provider = self._factory.create_broker_provider(broker_type, credentials)
                await provider.initialize(credentials)
                
                # Store provider and initialize health tracking
                self._broker_providers[broker_type] = provider
                self._broker_health[broker_type] = BrokerHealth(broker_type=broker_type)
                
                logger.info(f"✅ Initialized {broker_type.value} broker")
                
            except Exception as e:
                logger.error(f"❌ Failed to initialize {broker_name} broker: {e}")
        
        # Update router with available providers
        self._router.set_broker_providers(self._broker_providers)
    
    async def _load_symbol_mappings(self) -> None:
        """Load symbol-to-broker mappings from configuration."""
        symbol_mappings = self._config.get_config("symbol_broker_mappings", [])
        
        for mapping_config in symbol_mappings:
            try:
                mapping = SymbolBrokerMapping(
                    symbol=mapping_config["symbol"],
                    broker_type=BrokerType(mapping_config["broker_type"]),
                    priority=mapping_config.get("priority", 1),
                    is_primary=mapping_config.get("is_primary", True),
                    extended_hours_enabled=mapping_config.get("extended_hours_enabled", False),
                    max_position_size=mapping_config.get("max_position_size"),
                    broker_specific_settings=mapping_config.get("broker_specific_settings", {})
                )
                
                self._router.add_symbol_mapping(mapping)
                
            except Exception as e:
                logger.error(f"❌ Failed to load symbol mapping {mapping_config}: {e}")
    
    async def _health_monitoring_loop(self) -> None:
        """Background task for monitoring broker health."""
        logger.info("🔄 Starting broker health monitoring...")
        
        try:
            while not self._shutdown_event.is_set():
                await self._perform_health_checks()
                
                # Wait for next health check interval
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(), 
                        timeout=self._broker_config.health_check_interval_seconds
                    )
                    break  # Shutdown event was set
                except asyncio.TimeoutError:
                    continue  # Normal timeout, continue monitoring
                    
        except Exception as e:
            logger.error(f"❌ Health monitoring loop error: {e}")
        
        logger.info("🔄 Broker health monitoring stopped")
    
    async def _perform_health_checks(self) -> None:
        """Perform health checks on all brokers."""
        for broker_type, provider in self._broker_providers.items():
            health = self._broker_health[broker_type]
            
            try:
                is_healthy = await asyncio.wait_for(
                    provider.health_check(),
                    timeout=self._broker_config.connection_timeout_seconds
                )
                
                if is_healthy:
                    health.is_healthy = True
                    health.consecutive_failures = 0
                    health.last_successful_operation = datetime.now()
                    health.error_message = None
                else:
                    health.consecutive_failures += 1
                    
                health.last_health_check = datetime.now()
                
            except Exception as e:
                health.is_healthy = False
                health.consecutive_failures += 1
                health.error_message = str(e)
                health.last_health_check = datetime.now()
                
                logger.warning(f"⚠️ Health check failed for {broker_type.value}: {e}")
                
                # Check if broker should be marked as unhealthy
                if health.consecutive_failures >= self._broker_config.max_consecutive_failures:
                    logger.error(f"❌ {broker_type.value} marked as unhealthy after {health.consecutive_failures} failures")
    
    # ===== PUBLIC API =====
    
    async def submit_order(self, symbol: str, order: UniversalOrder) -> OrderResponse:
        """Submit order using appropriate broker for symbol."""
        trading_client = await self._router.get_trading_client_for_symbol(symbol)
        return await trading_client.submit_order(order)
    
    async def get_current_price(self, symbol: str) -> float:
        """Get current price using appropriate broker for symbol."""
        market_data_provider = await self._router.get_market_data_provider_for_symbol(symbol)
        return await market_data_provider.get_current_price(symbol)
    
    async def get_positions(self, broker_type: Optional[BrokerType] = None) -> List[Position]:
        """Get positions from specific broker or all brokers."""
        if broker_type:
            if broker_type in self._broker_providers:
                return await self._broker_providers[broker_type].trading_client.get_positions()
            else:
                raise TradingException(f"Broker {broker_type.value} not available")
        
        # Get positions from all brokers
        all_positions = []
        for provider in self._broker_providers.values():
            try:
                positions = await provider.trading_client.get_positions()
                all_positions.extend(positions)
            except Exception as e:
                logger.error(f"❌ Failed to get positions from {provider.broker_type.value}: {e}")
        
        return all_positions
    
    async def get_account_info(self, broker_type: Optional[BrokerType] = None) -> List[AccountInfo]:
        """Get account info from specific broker or all brokers."""
        if broker_type:
            if broker_type in self._broker_providers:
                return [await self._broker_providers[broker_type].trading_client.get_account_info()]
            else:
                raise TradingException(f"Broker {broker_type.value} not available")
        
        # Get account info from all brokers
        accounts = []
        for provider in self._broker_providers.values():
            try:
                account = await provider.trading_client.get_account_info()
                accounts.append(account)
            except Exception as e:
                logger.error(f"❌ Failed to get account from {provider.broker_type.value}: {e}")
        
        return accounts
    
    def add_symbol_mapping(self, symbol: str, broker_type: BrokerType, **kwargs) -> None:
        """Add symbol-to-broker mapping."""
        mapping = SymbolBrokerMapping(
            symbol=symbol,
            broker_type=broker_type,
            **kwargs
        )
        self._router.add_symbol_mapping(mapping)
    
    def get_broker_health(self, broker_type: Optional[BrokerType] = None) -> Dict[BrokerType, BrokerHealth]:
        """Get health status of brokers."""
        if broker_type:
            return {broker_type: self._broker_health.get(broker_type)} if broker_type in self._broker_health else {}
        
        return self._broker_health.copy()
    
    def get_available_brokers(self) -> List[BrokerType]:
        """Get list of available and healthy brokers."""
        return [
            broker_type for broker_type, health in self._broker_health.items()
            if health.is_healthy
        ]
    
    async def close(self) -> None:
        """Shutdown broker manager and all connections."""
        logger.info("🔄 Shutting down BrokerManager...")
        
        # Stop health monitoring
        if self._health_check_task:
            self._shutdown_event.set()
            try:
                await asyncio.wait_for(self._health_check_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._health_check_task.cancel()
                logger.warning("⚠️ Health monitoring task did not shutdown gracefully")
        
        # Close all broker providers
        for broker_type, provider in self._broker_providers.items():
            try:
                await provider.close()
                logger.info(f"✅ Closed {broker_type.value} broker connection")
            except Exception as e:
                logger.error(f"❌ Error closing {broker_type.value}: {e}")
        
        self._broker_providers.clear()
        self._broker_health.clear()
        self._is_initialized = False
        
        logger.info("✅ BrokerManager shutdown complete")
    
    @property
    def is_initialized(self) -> bool:
        """Check if broker manager is initialized."""
        return self._is_initialized
    
    @property
    def broker_count(self) -> int:
        """Get number of configured brokers."""
        return len(self._broker_providers)
    
    # ===== EXCHANGE-AWARE METHODS =====
    
    @property
    def market_hours_manager(self) -> IMultiExchangeMarketHoursManager:
        """Get the exchange-aware market hours manager."""
        return self._market_hours_manager
    
    async def get_exchange_for_symbol(self, symbol: str) -> Exchange:
        """Get the exchange for a symbol."""
        return await self._market_hours_manager.get_exchange_for_symbol(symbol)
    
    async def get_market_status_for_symbol(self, symbol: str) -> Any:  # MarketStatus
        """Get market status for a symbol's exchange."""
        return await self._market_hours_manager.get_market_status_for_symbol(symbol)
    
    async def get_market_status_for_exchange(self, exchange: Exchange) -> Any:  # MarketStatus
        """Get market status for a specific exchange."""
        return await self._market_hours_manager.get_market_status_for_exchange(exchange)
    
    async def get_active_exchanges(self) -> List[Exchange]:
        """Get list of currently active (open) exchanges."""
        return await self._market_hours_manager.get_active_exchanges()
    
    async def should_bot_be_active(self) -> bool:
        """Determine if bot should be active based on exchange hours."""
        return await self._market_hours_manager.should_bot_be_active()
    
    def get_supported_exchanges(self) -> List[Exchange]:
        """Get list of all supported exchanges across all brokers."""
        supported_exchanges = set()
        for provider in self._broker_providers.values():
            supported_exchanges.update(provider.get_supported_exchanges())
        return list(supported_exchanges)
    
    async def get_brokers_for_exchange(self, exchange: Exchange) -> List[BrokerType]:
        """Get list of brokers that support trading on the specified exchange."""
        supporting_brokers = []
        for broker_type, provider in self._broker_providers.items():
            if provider.supports_exchange(exchange):
                supporting_brokers.append(broker_type)
        return supporting_brokers