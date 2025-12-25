"""
Component Initializer - Handles initialization of trading bot components.

Extracted from TradingBotOrchestrator to follow Single Responsibility Principle.
This class is responsible for creating and initializing all trading bot subsystems.

Author: Trading Bot Team
Version: 1.0.0
"""

import os
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable, TYPE_CHECKING

from src.core import ConfigurationManager, setup_logging, get_logger
from src.signals import TradingViewSignalListener
from src.trading import OrderManager, ExitPlanner, TradeService, PositionMonitor
from src.broker.subsystem import BrokerSubsystem
from src.strategies import DCAStrategy, TrailingManager
from src.risk import RiskManager
from src.position import PositionManager
from src.database import CosmosDBManager
from src.utils import BoundedFetcher
from src.services.fill_processor import FillProcessor
from src import TradingSignal

if TYPE_CHECKING:
    from src.trading_bot import TradingBotOrchestrator


logger = get_logger(__name__)


class ComponentInitializer:
    """
    Initializes all trading bot components in the correct order.
    
    Responsibilities:
    - Creating component instances with proper dependencies
    - Establishing database connections
    - Initializing broker subsystems
    - Setting up bounded concurrency utilities
    
    This class follows the Factory pattern for component creation
    and ensures proper dependency injection.
    
    Usage:
        initializer = ComponentInitializer(config)
        components = await initializer.initialize_all(signal_callback, bot_instance)
    """
    
    def __init__(self, config: Optional[ConfigurationManager] = None):
        """
        Initialize the component initializer.
        
        Args:
            config: Configuration manager instance. If None, creates singleton.
        """
        self._config = config or ConfigurationManager()
        logger.debug("ComponentInitializer created")
    
    @property
    def config(self) -> ConfigurationManager:
        """Get the configuration manager."""
        return self._config
    
    async def initialize_all(
        self,
        signal_callback: Callable[[TradingSignal], Awaitable[None]],
        bot_instance: "TradingBotOrchestrator"
    ) -> "InitializedComponents":
        """
        Initialize all trading bot components.
        
        Args:
            signal_callback: Callback for handling incoming trading signals
            bot_instance: Reference to the bot orchestrator for status endpoints
            
        Returns:
            InitializedComponents containing all initialized components
        """
        logger.info("Initializing components...")
        
        # Setup logging
        setup_logging(
            level=self._config.get_config("logging.level", "INFO"),
            format_type=self._config.get_config("logging.format", "json"),
            log_file=self._config.get_config("logging.file")
        )
        
        # Initialize database
        database = await self._initialize_database()
        
        # Initialize Broker Subsystem
        broker_subsystem = await self._initialize_broker_subsystem()
        
        # Initialize managers
        position_manager = self._create_position_manager(database, broker_subsystem)
        risk_manager = self._create_risk_manager(position_manager, broker_subsystem)
        order_manager = self._create_order_manager(broker_subsystem)
        
        # Initialize strategies (NOTE: These need BotConfiguration from database)
        trailing_manager = None  # TrailingManager needs BotConfiguration
        dca_strategy = None  # DCAStrategy needs BotConfiguration from database
        
        # Initialize signal listener
        signal_listener = self._create_signal_listener(
            signal_callback, 
            broker_subsystem, 
            bot_instance
        )
        
        # Initialize bounded concurrency utilities
        price_fetcher = self._create_price_fetcher()
        
        # Initialize services
        exit_planner = ExitPlanner(self._config, broker_subsystem.market_data)
        trade_service = TradeService(database, order_manager)
        
        position_monitor = PositionMonitor(
            config=self._config,
            position_manager=position_manager,
            broker_subsystem=broker_subsystem,
            trailing_manager=trailing_manager,
            price_fetcher=price_fetcher,
            advanced_strategy=dca_strategy
        )
        
        fill_processor = FillProcessor(
            order_manager=order_manager,
            position_manager=position_manager,
            database=database,
            strategy=dca_strategy
        )
        
        logger.info("All components initialized successfully")
        
        return InitializedComponents(
            config=self._config,
            database=database,
            broker_subsystem=broker_subsystem,
            position_manager=position_manager,
            risk_manager=risk_manager,
            order_manager=order_manager,
            trailing_manager=trailing_manager,
            dca_strategy=dca_strategy,
            signal_listener=signal_listener,
            price_fetcher=price_fetcher,
            exit_planner=exit_planner,
            trade_service=trade_service,
            position_monitor=position_monitor,
            fill_processor=fill_processor
        )
    
    async def _initialize_database(self) -> CosmosDBManager:
        """Initialize and connect to the database."""
        database = CosmosDBManager(self._config)
        await database.initialize()
        logger.debug("Database initialized")
        return database
    
    async def _initialize_broker_subsystem(self) -> BrokerSubsystem:
        """Initialize the broker subsystem."""
        broker_subsystem = BrokerSubsystem(self._config)
        await broker_subsystem.initialize()
        logger.debug("Broker subsystem initialized")
        return broker_subsystem
    
    def _create_position_manager(
        self, 
        database: CosmosDBManager, 
        broker_subsystem: BrokerSubsystem
    ) -> PositionManager:
        """Create position manager with dependencies."""
        return PositionManager(
            self._config, 
            database, 
            broker_subsystem.router
        )
    
    def _create_risk_manager(
        self, 
        position_manager: PositionManager, 
        broker_subsystem: BrokerSubsystem
    ) -> RiskManager:
        """Create risk manager with dependencies."""
        return RiskManager(
            self._config, 
            position_manager, 
            broker_subsystem.primary_account_provider
        )
    
    def _create_order_manager(self, broker_subsystem: BrokerSubsystem) -> OrderManager:
        """Create order manager with dependencies."""
        return OrderManager(self._config, broker_subsystem.router)
    
    def _create_signal_listener(
        self,
        signal_callback: Callable[[TradingSignal], Awaitable[None]],
        broker_subsystem: BrokerSubsystem,
        bot_instance: "TradingBotOrchestrator"
    ) -> TradingViewSignalListener:
        """Create signal listener with dependencies."""
        return TradingViewSignalListener(
            self._config,
            signal_callback,
            broker_subsystem.market_data,
            bot_instance=bot_instance
        )
    
    def _create_price_fetcher(self) -> BoundedFetcher:
        """Create bounded price fetcher."""
        max_concurrent = self._config.get_config(
            "performance.max_concurrent_orders", 5
        )
        return BoundedFetcher(max_concurrency=max_concurrent)


@dataclass
class InitializedComponents:
    """
    Container for all initialized trading bot components.
    
    This is a dataclass that holds references to all initialized components.
    It enables clean dependency passing without large parameter lists.
    
    Using @dataclass provides:
    - Auto-generated __init__, __repr__, __eq__
    - Cleaner definition without boilerplate
    - Better IDE support and type checking
    """
    
    config: ConfigurationManager
    database: CosmosDBManager
    broker_subsystem: BrokerSubsystem
    position_manager: PositionManager
    risk_manager: RiskManager
    order_manager: OrderManager
    trailing_manager: Optional[TrailingManager]
    dca_strategy: Optional[DCAStrategy]
    signal_listener: TradingViewSignalListener
    price_fetcher: BoundedFetcher
    exit_planner: ExitPlanner
    trade_service: TradeService
    position_monitor: PositionMonitor
    fill_processor: FillProcessor
