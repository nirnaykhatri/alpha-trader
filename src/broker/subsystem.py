"""
Broker Subsystem Module
This module encapsulates the initialization, lifecycle management, and wiring of broker components.
It decouples the main trading bot orchestrator from the specific details of broker instantiation.
"""

from typing import Dict, Optional, Any
import asyncio

# Core imports
from src.core import ConfigurationManager, get_logger
from src.interfaces import IAsyncContextManager

# Broker imports
from src.broker.router import BrokerRouter
from src.broker.interfaces import BrokerType, IBrokerOrderExecutor, IBrokerAccountProvider, IBrokerMarketDataProvider
from src.broker.alpaca_order_executor import AlpacaOrderExecutor
from src.trading.alpaca_account_provider import AlpacaAccountProvider
from src.data import AlpacaMarketDataProvider

# Tastytrade imports
from src.broker.tastytrade_broker import (
    TastytradeSessionManager, 
    TastytradeAccountProvider, 
    TastytradeOrderExecutor,
    TastytradeMarketDataProvider
)

# API clients
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient

# Exceptions
from src.exceptions import ConfigurationException

# Startup mode for consistent broker requirement enforcement
from src.core import StartupMode

logger = get_logger(__name__)


class BrokerSubsystem(IAsyncContextManager):
    """
    Encapsulates the broker layer of the trading bot.
    
    Responsible for initializing, connecting, and managing the lifecycle of
    all broker integrations (Alpaca, Tastytrade, etc.) and the BrokerRouter.
    
    Market Data:
        Each broker has its own IBrokerMarketDataProvider stored in `market_data_providers`.
        The `market_data` property is a convenience for the default Alpaca provider and is
        maintained for backward compatibility. New code should prefer using
        `BrokerRouter.get_market_data_provider(broker)` for broker-specific data access.
    """

    def __init__(self, config: ConfigurationManager):
        """
        Initialize the BrokerSubsystem.

        Args:
            config: The configuration manager instance.
        """
        self.config = config
        self._is_running = False  # Use private var, expose via property
        
        # API Clients
        self.alpaca_trading_client: Optional[TradingClient] = None
        self.alpaca_data_client: Optional[StockHistoricalDataClient] = None
        
        # Tastytrade components
        self.tt_session_manager: Optional[TastytradeSessionManager] = None
        
        # Core Broker Components
        self.router: Optional[BrokerRouter] = None
        # Alpaca-specific market data provider (legacy attribute, see market_data property)
        self._alpaca_market_data: Optional[AlpacaMarketDataProvider] = None
        
        # Providers & Executors maps
        self.executors: Dict[BrokerType, IBrokerOrderExecutor] = {}
        self.account_providers: Dict[BrokerType, IBrokerAccountProvider] = {}
        self.market_data_providers: Dict[BrokerType, IBrokerMarketDataProvider] = {}
        
        # Primary Account Provider (defaults to Alpaca for backward compatibility)
        self.primary_account_provider: Optional[IBrokerAccountProvider] = None
    
    @property
    def is_running(self) -> bool:
        """Check if the subsystem is currently running."""
        return self._is_running
    
    @is_running.setter
    def is_running(self, value: bool) -> None:
        """Set the running state."""
        self._is_running = value

    async def initialize(self) -> None:
        """
        Initialize all broker components and wire them together.
        """
        logger.info("Initializing Broker Subsystem...")
        
        # 1. Initialize Alpaca (Primary)
        await self._initialize_alpaca()
        
        # 2. Initialize Tastytrade (Optional)
        await self._initialize_tastytrade()
        
        # 3. Initialize Router
        self.router = BrokerRouter(
            self.config,
            executors=self.executors,
            account_providers=self.account_providers,
            market_data_providers=self.market_data_providers
        )
        
        logger.info("Broker Subsystem initialized successfully")

    async def _initialize_alpaca(self) -> None:
        """
        Initialize Alpaca components if configured.
        
        NOTE: Alpaca is now OPTIONAL at startup. Users can add broker
        credentials via the web UI after the bot starts. If not configured,
        this method logs a warning and returns gracefully.
        """
        logger.info("Initializing Alpaca components...")
        
        # Use typed config method for consistency
        alpaca_config = self.config.get_alpaca_config()
        
        if not alpaca_config.is_configured:
            startup_mode = StartupMode.from_env()
            if startup_mode.requires_broker_at_startup:
                # HEADLESS mode: broker is required - fail-fast
                raise ConfigurationException(
                    "Alpaca API credentials not configured (STARTUP_MODE=headless requires broker). "
                    "Set ALPACA_API_KEY and ALPACA_SECRET_KEY, or use STARTUP_MODE=ui-config."
                )
            else:
                # UI_CONFIG mode: broker is optional
                logger.warning(
                    "Alpaca API credentials not configured. "
                    "You can add broker credentials via the web UI at /brokers"
                )
                return  # Skip initialization - broker can be added later via UI
        
        # Initialize clients
        self.alpaca_trading_client = TradingClient(
            api_key=alpaca_config.api_key,
            secret_key=alpaca_config.secret_key,
            paper=True if "paper" in alpaca_config.base_url else False
        )
        
        self.alpaca_data_client = StockHistoricalDataClient(
            alpaca_config.api_key, 
            alpaca_config.secret_key
        )
        
        # Initialize providers
        self._alpaca_market_data = AlpacaMarketDataProvider(self.config)
        alpaca_account_provider = AlpacaAccountProvider(self.alpaca_trading_client)
        alpaca_executor = AlpacaOrderExecutor(self.alpaca_trading_client, self.config)
        
        # Register components
        self.executors[BrokerType.ALPACA] = alpaca_executor
        self.account_providers[BrokerType.ALPACA] = alpaca_account_provider
        self.market_data_providers[BrokerType.ALPACA] = self._alpaca_market_data
        
        # Set primary account provider
        self.primary_account_provider = alpaca_account_provider
        
        logger.info("Alpaca components initialized")

    async def _initialize_tastytrade(self) -> None:
        """Initialize Tastytrade components if configured."""
        # OAuth uses client_secret, not username
        if not self.config.get_config("api.tastytrade.client_secret"):
            logger.debug("Tastytrade not configured, skipping initialization")
            return

        try:
            logger.info("Initializing Tastytrade components...")
            self.tt_session_manager = TastytradeSessionManager(self.config)
            tt_account_id = self.config.get_config("api.tastytrade.account_id")
            
            tt_account_provider = TastytradeAccountProvider(self.tt_session_manager, tt_account_id)
            tt_order_executor = TastytradeOrderExecutor(self.tt_session_manager, self.config, tt_account_id)
            
            # Initialize dedicated Tastytrade market data provider
            # This ensures Tastytrade trades use Tastytrade data (not Alpaca)
            tt_market_data_provider = TastytradeMarketDataProvider(
                session_manager=self.tt_session_manager,
                cache_duration_seconds=self.config.get_config("data.tastytrade.cache_duration", 30),
                use_streaming=self.config.get_config("data.tastytrade.use_streaming", False)
            )
            
            # Register components - each broker gets its OWN market data provider
            self.executors[BrokerType.TASTYTRADE] = tt_order_executor
            self.account_providers[BrokerType.TASTYTRADE] = tt_account_provider
            self.market_data_providers[BrokerType.TASTYTRADE] = tt_market_data_provider
            
            logger.info("Tastytrade components initialized with dedicated market data provider")
        except Exception as e:
            logger.error(f"Failed to initialize Tastytrade: {e}")
            # We don't raise here to allow the bot to run with just Alpaca if TT fails

    @property
    def market_data(self) -> Optional[IBrokerMarketDataProvider]:
        """
        Get the default (Alpaca) market data provider.
        
        This property is maintained for backward compatibility.
        New code should prefer using `BrokerRouter.get_market_data_provider(broker)`
        or accessing `market_data_providers` directly for broker-specific data.
        
        Returns:
            The Alpaca market data provider, or None if not initialized.
        """
        return self._alpaca_market_data

    async def start(self) -> None:
        """Start all broker components."""
        logger.info("Starting Broker Subsystem...")
        
        # Start Alpaca Market Data
        if self._alpaca_market_data:
            await self._alpaca_market_data.start()
            
        # Start Tastytrade Session
        if self.tt_session_manager:
            try:
                await self.tt_session_manager.start()
                logger.info("Tastytrade session manager started")
            except Exception as e:
                logger.error(f"Failed to start Tastytrade session manager: {e}")
        
        # Start Tastytrade Market Data Provider (if initialized)
        tt_market_data = self.market_data_providers.get(BrokerType.TASTYTRADE)
        if tt_market_data and hasattr(tt_market_data, 'start'):
            try:
                await tt_market_data.start()
                logger.info("Tastytrade market data provider started")
            except Exception as e:
                logger.error(f"Failed to start Tastytrade market data provider: {e}")
        
        self.is_running = True
        logger.info("Broker Subsystem started")

    async def stop(self) -> None:
        """Stop all broker components."""
        logger.info("Stopping Broker Subsystem...")
        self.is_running = False
        
        # Stop Tastytrade Market Data Provider
        tt_market_data = self.market_data_providers.get(BrokerType.TASTYTRADE)
        if tt_market_data and hasattr(tt_market_data, 'stop'):
            try:
                await tt_market_data.stop()
                logger.info("Tastytrade market data provider stopped")
            except Exception as e:
                logger.error(f"Error stopping Tastytrade market data provider: {e}")
        
        # Stop Tastytrade Session
        if self.tt_session_manager:
            try:
                await self.tt_session_manager.stop()
                logger.info("Tastytrade session manager stopped")
            except Exception as e:
                logger.error(f"Error stopping Tastytrade session manager: {e}")
        
        # Stop Alpaca Market Data
        if self._alpaca_market_data:
            try:
                await self._alpaca_market_data.stop()
                logger.info("Alpaca market data provider stopped")
            except Exception as e:
                logger.error(f"Error stopping Alpaca market data provider: {e}")
                
        logger.info("Broker Subsystem stopped")

    async def validate_connections(self) -> None:
        """Validate connections to all configured brokers."""
        logger.info("Validating broker connections...")
        
        # Validate Alpaca
        if self.alpaca_trading_client:
            try:
                # We use run_blocking if the client is synchronous, but Alpaca's TradingClient 
                # methods are synchronous blocking calls, so we should wrap them if we want async.
                # However, for initialization checks, blocking is acceptable or we can use run_in_executor.
                from src.utils import run_blocking
                account = await run_blocking(self.alpaca_trading_client.get_account)
                logger.info(f"Alpaca API connected - Account: {account.account_number}")
            except Exception as e:
                raise ConfigurationException(f"Alpaca connection failed: {e}")
        
        # Validate Tastytrade (if initialized)
        if self.tt_session_manager:
            # The session manager's start() method handles authentication, 
            # so if we are here and initialized, we assume it's okay or will be checked on start.
            pass
            
        logger.info("Broker connections validated")
