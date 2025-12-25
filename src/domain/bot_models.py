"""
Bot Domain Models.

This module provides backward-compatible imports for bot domain models.
The models have been split into separate files for better organization:

- bot_enums.py: All enumeration types
- bot_config.py: Configuration dataclasses
- bot_state.py: Bot entity and state models

All classes are re-exported from this module to maintain backward
compatibility with existing code that imports from bot_models.

Author: Trading Bot Team
Version: 2.0.0

MIGRATION NOTE:
    For new code, prefer importing from the specific modules:
    
    from src.domain.bot_enums import BotType, BotState
    from src.domain.bot_config import DCAConfig, BotConfiguration
    from src.domain.bot_state import Bot, BotPerformance
"""

# =============================================================================
# Re-export all enums from bot_enums
# =============================================================================
from .bot_enums import (
    BotType,
    BotState,
    BotOperationalPhase,
    BotAction,
    PositionMode,
    MarginMode,
    BotStartCondition,
    BotOrderType,
    TakeProfitType,
    PriceReference,
    IndicatorType,
    IndicatorTimeframe,
    QuickSetupPreset,
)

# =============================================================================
# Re-export all config classes from bot_config
# =============================================================================
from .bot_config import (
    IndicatorConfig,
    SignalConfig,
    TradingViewWebhookConfig,
    PriceConditionConfig,
    BotStartSettings,
    AveragingOrdersConfig,
    TakeProfitConfig,
    StopLossConfig,
    RiskManagementConfig,
    DCAConfig,
    BotConfiguration,
)

# =============================================================================
# Re-export all state classes from bot_state
# =============================================================================
from .bot_state import (
    BotPerformance,
    BotOrder,
    Bot,
    BotHistoryEntry,
)

# =============================================================================
# Define __all__ for explicit exports
# =============================================================================
__all__ = [
    # Enums
    "BotType",
    "BotState",
    "BotOperationalPhase",
    "BotAction",
    "PositionMode",
    "MarginMode",
    "BotStartCondition",
    "BotOrderType",
    "TakeProfitType",
    "PriceReference",
    "IndicatorType",
    "IndicatorTimeframe",
    "QuickSetupPreset",
    # Config classes
    "IndicatorConfig",
    "SignalConfig",
    "TradingViewWebhookConfig",
    "PriceConditionConfig",
    "BotStartSettings",
    "AveragingOrdersConfig",
    "TakeProfitConfig",
    "StopLossConfig",
    "RiskManagementConfig",
    "DCAConfig",
    "BotConfiguration",
    # State classes
    "BotPerformance",
    "BotOrder",
    "Bot",
    "BotHistoryEntry",
]
