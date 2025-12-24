"""
Strategy Factory - Creates strategy instances based on bot type.

Implements the Factory Pattern to instantiate the correct ITradingStrategy
implementation based on the bot's BotType configuration.

This factory centralizes strategy creation logic and ensures:
- Correct strategy type for each bot type
- Consistent dependency injection
- Easy addition of new strategies
- Clear error messages for unsupported types

Usage:
    factory = StrategyFactory()
    strategy = factory.create(
        bot_type=BotType.DCA,
        order_manager=order_mgr,
        market_data=market_data,
        risk_manager=risk_mgr,
        bot_config=config
    )
    await strategy.initialize()

Author: Trading Bot Team
Version: 1.0.0
"""

from typing import Dict, Type, Optional
from src.interfaces import (
    IOrderManager, IMarketDataProvider, IRiskManager, ITradingStrategy
)
from src.domain.bot_models import BotConfiguration, BotType
from src.core.logging_config import get_logger

# Strategy imports
from src.strategies.dca_strategy import DCAStrategy
from src.strategies.base_strategy import (
    GridStrategy,
    SpotLoopStrategy,
    ComboStrategy,
    FuturesDCAStrategy,
    FuturesComboStrategy
)

logger = get_logger(__name__)


class StrategyFactory:
    """
    Factory for creating trading strategy instances.
    
    Maps BotType enum values to their corresponding ITradingStrategy
    implementations and handles dependency injection.
    
    Example:
        factory = StrategyFactory()
        
        # Create DCA strategy (fully implemented)
        dca = factory.create(BotType.DCA, order_mgr, market_data, risk_mgr, config)
        
        # Create Grid strategy (placeholder)
        grid = factory.create(BotType.GRID, order_mgr, market_data, risk_mgr, config)
    
    Thread Safety:
        This class is stateless and thread-safe. Multiple threads can
        safely call create() concurrently.
    """
    
    # Strategy type registry: Maps BotType to strategy class
    _STRATEGY_REGISTRY: Dict[BotType, Type[ITradingStrategy]] = {
        BotType.DCA: DCAStrategy,
        BotType.GRID: GridStrategy,
        BotType.SPOT_LOOP: SpotLoopStrategy,
        BotType.COMBO: ComboStrategy,
        BotType.FUTURES_DCA: FuturesDCAStrategy,
        BotType.FUTURES_COMBO: FuturesComboStrategy,
    }
    
    # Strategies that are fully implemented (not placeholders)
    _IMPLEMENTED_STRATEGIES = {BotType.DCA}
    
    @classmethod
    def create(
        cls,
        bot_type: BotType,
        order_manager: IOrderManager,
        market_data: IMarketDataProvider,
        risk_manager: IRiskManager,
        bot_config: BotConfiguration,
        position_manager=None,
        resilience_tracker=None
    ) -> ITradingStrategy:
        """
        Create a strategy instance for the given bot type.
        
        Args:
            bot_type: Type of bot/strategy to create
            order_manager: Order execution manager
            market_data: Market data provider
            risk_manager: Risk management service
            bot_config: Bot's configuration from database
            position_manager: Optional position tracking manager
            resilience_tracker: Optional resilience tracking service
            
        Returns:
            ITradingStrategy instance for the requested bot type
            
        Raises:
            ValueError: If bot_type is not supported
            TypeError: If required dependencies are missing
        """
        # Validate inputs
        if bot_type is None:
            raise ValueError("bot_type is required")
        if order_manager is None:
            raise TypeError("order_manager is required")
        if market_data is None:
            raise TypeError("market_data is required")
        if risk_manager is None:
            raise TypeError("risk_manager is required")
        if bot_config is None:
            raise TypeError("bot_config is required")
        
        # Get strategy class from registry
        strategy_class = cls._STRATEGY_REGISTRY.get(bot_type)
        
        if strategy_class is None:
            supported = ", ".join(t.value for t in cls._STRATEGY_REGISTRY.keys())
            raise ValueError(
                f"Unsupported bot type: {bot_type.value}. "
                f"Supported types: {supported}"
            )
        
        # Log if using placeholder
        if bot_type not in cls._IMPLEMENTED_STRATEGIES:
            logger.warning(
                f"⚠️ Creating placeholder strategy for {bot_type.value}. "
                f"This strategy is not yet implemented and will not execute trades. "
                f"Use DCA strategy for production trading."
            )
        else:
            logger.info(f"✅ Creating {bot_type.value} strategy")
        
        # Instantiate strategy with dependencies
        strategy = strategy_class(
            order_manager=order_manager,
            market_data=market_data,
            risk_manager=risk_manager,
            bot_config=bot_config,
            position_manager=position_manager,
            resilience_tracker=resilience_tracker
        )
        
        return strategy
    
    @classmethod
    def get_supported_types(cls) -> list[BotType]:
        """
        Get list of all supported bot types.
        
        Returns:
            List of BotType values that have registered strategies
        """
        return list(cls._STRATEGY_REGISTRY.keys())
    
    @classmethod
    def get_implemented_types(cls) -> list[BotType]:
        """
        Get list of fully implemented (non-placeholder) bot types.
        
        Returns:
            List of BotType values with full implementations
        """
        return list(cls._IMPLEMENTED_STRATEGIES)
    
    @classmethod
    def is_implemented(cls, bot_type: BotType) -> bool:
        """
        Check if a bot type has a full implementation.
        
        Args:
            bot_type: The bot type to check
            
        Returns:
            True if fully implemented, False if placeholder
        """
        return bot_type in cls._IMPLEMENTED_STRATEGIES
    
    @classmethod
    def register_strategy(
        cls,
        bot_type: BotType,
        strategy_class: Type[ITradingStrategy],
        is_implemented: bool = True
    ) -> None:
        """
        Register a new strategy type.
        
        This allows runtime registration of custom strategies
        without modifying this class.
        
        Args:
            bot_type: BotType enum value for the strategy
            strategy_class: Class implementing ITradingStrategy
            is_implemented: Whether this is a full implementation
            
        Example:
            StrategyFactory.register_strategy(
                BotType.CUSTOM,
                MyCustomStrategy,
                is_implemented=True
            )
        """
        if not issubclass(strategy_class, ITradingStrategy):
            raise TypeError(
                f"strategy_class must implement ITradingStrategy, "
                f"got {strategy_class.__name__}"
            )
        
        cls._STRATEGY_REGISTRY[bot_type] = strategy_class
        
        if is_implemented:
            cls._IMPLEMENTED_STRATEGIES.add(bot_type)
        elif bot_type in cls._IMPLEMENTED_STRATEGIES:
            cls._IMPLEMENTED_STRATEGIES.remove(bot_type)
        
        logger.info(
            f"Registered strategy {strategy_class.__name__} "
            f"for {bot_type.value} (implemented={is_implemented})"
        )


def create_strategy(
    bot_type: BotType,
    order_manager: IOrderManager,
    market_data: IMarketDataProvider,
    risk_manager: IRiskManager,
    bot_config: BotConfiguration,
    position_manager=None,
    resilience_tracker=None
) -> ITradingStrategy:
    """
    Convenience function to create a strategy without instantiating factory.
    
    This is a module-level shortcut for StrategyFactory.create().
    
    Args:
        bot_type: Type of bot/strategy to create
        order_manager: Order execution manager
        market_data: Market data provider
        risk_manager: Risk management service
        bot_config: Bot's configuration from database
        position_manager: Optional position tracking manager
        resilience_tracker: Optional resilience tracking service
        
    Returns:
        ITradingStrategy instance for the requested bot type
    """
    return StrategyFactory.create(
        bot_type=bot_type,
        order_manager=order_manager,
        market_data=market_data,
        risk_manager=risk_manager,
        bot_config=bot_config,
        position_manager=position_manager,
        resilience_tracker=resilience_tracker
    )
