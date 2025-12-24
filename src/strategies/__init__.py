"""
Strategies module initialization.

This module exports the core strategy components used by the bot_engine architecture.

Strategy Pattern Implementation:
- ITradingStrategy: Interface all strategies implement (in src/interfaces.py)
- DCAStrategy: Full DCA implementation
- GridStrategy: Grid trading (placeholder)
- SpotLoopStrategy: Spot loop trading (placeholder)
- ComboStrategy: Combined strategies (placeholder)
- FuturesDCAStrategy: Futures DCA (placeholder)
- FuturesComboStrategy: Futures combo (placeholder)
- StrategyFactory: Creates strategy instances based on BotType

Usage:
    from src.strategies import StrategyFactory, DCAStrategy
    from src.domain.bot_models import BotType
    
    # Create via factory (recommended)
    strategy = StrategyFactory.create(
        bot_type=BotType.DCA,
        order_manager=order_mgr,
        market_data=market_data,
        risk_manager=risk_mgr,
        bot_config=config
    )
    
    # Or instantiate directly
    strategy = DCAStrategy(order_mgr, market_data, risk_mgr, config)
"""

# Main strategy implementation
from src.strategies.dca_strategy import DCAStrategy

# Placeholder strategies
from src.strategies.base_strategy import (
    BaseStrategy,
    NotImplementedStrategy,
    GridStrategy,
    SpotLoopStrategy,
    ComboStrategy,
    FuturesDCAStrategy,
    FuturesComboStrategy,
)

# Strategy factory
from src.strategies.strategy_factory import StrategyFactory, create_strategy

# Supporting components
from src.strategies.dca_planner import DCAPlanner
from src.strategies.entry_executor import EntrySignalExecutor
from src.strategies.trailing_manager import TrailingManager
from src.strategies.phase_manager import PhaseManager
from src.strategies.position_state import PositionState, PositionDirection, TradePhase

__all__ = [
    # Main strategy
    "DCAStrategy",
    
    # Placeholder strategies
    "BaseStrategy",
    "NotImplementedStrategy",
    "GridStrategy",
    "SpotLoopStrategy",
    "ComboStrategy",
    "FuturesDCAStrategy",
    "FuturesComboStrategy",
    
    # Factory
    "StrategyFactory",
    "create_strategy",
    
    # Supporting components
    "DCAPlanner",
    "EntrySignalExecutor",
    "TrailingManager",
    "PhaseManager",
    "PositionState",
    "PositionDirection",
    "TradePhase",
]
