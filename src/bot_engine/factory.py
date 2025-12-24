"""
Bot Engine Factory - Bootstrap the Multi-Bot Execution System.

Provides factory functions to create and wire up all components
of the bot engine architecture with proper dependency injection.

Usage:
    from src.bot_engine.factory import create_bot_engine
    
    engine, router = await create_bot_engine(config, bot_repository)
    await engine.start_engine()
    
    # Add router to FastAPI app
    app.include_router(router.router)

Author: Trading Bot Team
Version: 1.0.0
"""

from typing import Optional, Tuple, TYPE_CHECKING

from src.core.logging_config import get_logger
from src.bot_engine.interfaces import BotEngineConfig
from src.bot_engine.bot_engine_manager import BotEngineManager
from src.bot_engine.market_data_hub import MarketDataHub
from src.bot_engine.signal_router import SignalRouter
from src.bot_engine.broker_connection_pool import BrokerConnectionPool
from src.bot_engine.bot_engine_router import BotEngineRouter

if TYPE_CHECKING:
    from src.interfaces import IConfigurationManager
    from src.database.bot_repository import BotRepository

logger = get_logger(__name__)


async def create_bot_engine(
    config_manager: "IConfigurationManager",
    bot_repository: "BotRepository",
    engine_config: Optional[BotEngineConfig] = None,
) -> Tuple[BotEngineManager, BotEngineRouter]:
    """
    Create and wire up the bot engine system.
    
    This factory function creates all components of the multi-bot
    architecture and wires them together with proper dependency
    injection.
    
    Args:
        config_manager: Application configuration manager
        bot_repository: Database repository for bots
        engine_config: Optional custom engine configuration
        
    Returns:
        Tuple of (BotEngineManager, BotEngineRouter)
        
    Example:
        engine, router = await create_bot_engine(config, repo)
        await engine.start_engine()
        app.include_router(router.router)
    """
    logger.info("Creating bot engine system...")
    
    # Create engine configuration
    if engine_config is None:
        engine_config = BotEngineConfig(
            max_concurrent_bots=config_manager.get_config(
                "bot_engine.max_concurrent_bots", 500
            ),
            max_bots_per_user=config_manager.get_config(
                "bot_engine.max_bots_per_user", 100
            ),
            max_bots_per_symbol=config_manager.get_config(
                "bot_engine.max_bots_per_symbol", 50
            ),
            event_loop_tick_ms=config_manager.get_config(
                "bot_engine.event_loop_tick_ms", 100
            ),
            state_persist_interval_seconds=config_manager.get_config(
                "bot_engine.state_persist_interval_seconds", 5
            ),
            health_check_interval_seconds=config_manager.get_config(
                "bot_engine.health_check_interval_seconds", 30
            ),
            share_market_data=True,
            share_broker_connections=True,
            shutdown_timeout_seconds=30,
        )
    
    logger.info(f"Engine config: max_bots={engine_config.max_concurrent_bots}")
    
    # Create shared components
    market_data_hub = MarketDataHub(
        poll_interval_seconds=config_manager.get_config(
            "bot_engine.price_poll_interval", 1.0
        )
    )
    
    signal_router = SignalRouter()
    
    broker_pool = BrokerConnectionPool()
    
    # Configure broker connections from settings
    _configure_broker_pool(broker_pool, config_manager)
    
    # Create the engine manager
    engine_manager = BotEngineManager(
        config=engine_config,
        market_data_hub=market_data_hub,
        signal_router=signal_router,
        broker_pool=broker_pool,
        bot_repository=bot_repository,
    )
    
    # Create API router
    api_router = BotEngineRouter(
        bot_engine_manager=engine_manager,
        bot_repository=bot_repository,
    )
    
    logger.info("Bot engine system created successfully")
    
    return engine_manager, api_router


def _configure_broker_pool(
    pool: BrokerConnectionPool, 
    config: "IConfigurationManager"
) -> None:
    """
    Configure broker connections from application settings.
    
    Args:
        pool: Broker connection pool to configure
        config: Application configuration manager
    """
    # Configure Alpaca if credentials present
    alpaca_key = config.get_config("alpaca.api_key", "")
    alpaca_secret = config.get_config("alpaca.api_secret", "")
    
    if alpaca_key and alpaca_secret:
        pool.configure_broker(
            broker_type="alpaca",
            api_key=alpaca_key,
            api_secret=alpaca_secret,
            paper_trading=config.get_config("alpaca.paper_trading", True),
            max_connections=config.get_config("bot_engine.alpaca_max_connections", 3),
        )
        logger.info("Configured Alpaca broker in connection pool")
    
    # Configure TastyTrade if credentials present
    tastytrade_user = config.get_config("tastytrade.username", "")
    tastytrade_pass = config.get_config("tastytrade.password", "")
    
    if tastytrade_user and tastytrade_pass:
        pool.configure_broker(
            broker_type="tastytrade",
            api_key=tastytrade_user,
            api_secret=tastytrade_pass,
            paper_trading=config.get_config("tastytrade.paper_trading", True),
            max_connections=config.get_config("bot_engine.tastytrade_max_connections", 2),
        )
        logger.info("Configured TastyTrade broker in connection pool")
    
    # Always configure paper broker for testing
    pool.configure_broker(
        broker_type="paper",
        api_key="paper",
        api_secret="paper",
        paper_trading=True,
        max_connections=1,
    )
    logger.info("Configured Paper broker in connection pool")


async def create_standalone_bot_engine(
    alpaca_api_key: str,
    alpaca_api_secret: str,
    paper_trading: bool = True,
    max_bots: int = 100,
) -> BotEngineManager:
    """
    Create a standalone bot engine for testing or simple deployments.
    
    This is a simplified factory that creates a bot engine without
    needing the full application configuration system.
    
    Args:
        alpaca_api_key: Alpaca API key
        alpaca_api_secret: Alpaca API secret
        paper_trading: Whether to use paper trading
        max_bots: Maximum concurrent bots
        
    Returns:
        BotEngineManager instance
        
    Example:
        engine = await create_standalone_bot_engine(
            "ALPACA_KEY", "ALPACA_SECRET"
        )
        await engine.start_engine()
    """
    # Create minimal configuration
    config = BotEngineConfig(
        max_concurrent_bots=max_bots,
        max_bots_per_user=max_bots,
        max_bots_per_symbol=max_bots,
    )
    
    # Create components
    market_data_hub = MarketDataHub()
    signal_router = SignalRouter()
    broker_pool = BrokerConnectionPool()
    
    # Configure broker
    broker_pool.configure_broker(
        broker_type="alpaca",
        api_key=alpaca_api_key,
        api_secret=alpaca_api_secret,
        paper_trading=paper_trading,
    )
    
    # Create a mock repository for standalone use
    # In production, you'd inject a real repository
    class MockBotRepository:
        async def update(self, bot): pass
        async def get_by_id(self, bot_id): return None
        async def get_by_state(self, state): return []
    
    engine = BotEngineManager(
        config=config,
        market_data_hub=market_data_hub,
        signal_router=signal_router,
        broker_pool=broker_pool,
        bot_repository=MockBotRepository(),
    )
    
    return engine
