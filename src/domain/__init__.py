"""
Domain value objects and types.

Pure domain objects with no external dependencies.
"""

from src.domain.decision_context import DecisionContext, PositionDirection
from src.domain.risk_decision import RiskDecision, RiskDecisionStatus, RiskEnvelope

# Bot domain models (re-exported from bot_models for convenience)
from src.domain.bot_models import (
    # Enums
    BotType,
    BotState,
    BotOperationalPhase,
    BotAction,
    PositionMode,
    MarginMode,
    TakeProfitType,
    # Config classes
    BotConfiguration,
    DCAConfig,
    # Entity classes
    Bot,
    BotPerformance,
)

__all__ = [
    # Decision Context
    'DecisionContext',
    'PositionDirection',
    # Risk Decision
    'RiskDecision',
    'RiskDecisionStatus',
    'RiskEnvelope',
    # Bot Domain Models
    'BotType',
    'BotState',
    'BotOperationalPhase',
    'BotAction',
    'PositionMode',
    'MarginMode',
    'TakeProfitType',
    'BotConfiguration',
    'DCAConfig',
    'Bot',
    'BotPerformance',
]
