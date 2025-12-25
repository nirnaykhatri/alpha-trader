"""
Services module for trading bot functionality.

Provides service interfaces and implementations for:
- Admin operations (orders, positions, lifecycle)
- Execution policy (profit-taking, order adjustment)
- Reconciliation (broker/database sync)
- Trading summaries (performance, reporting)

Following Interface Segregation Principle (ISP) and Dependency Inversion (DIP).

Author: Trading Bot Team
Version: 1.1.0
"""

from src.services.admin_interfaces import (
    IOrderService,
    IPositionService,
    IBotLifecycleService,
    IConfigService,
    IRiskValidationService,
    IFundService,
    OrderDTO,
    PositionDTO,
    BotStatus,
    BotState,
)

from src.services.admin_services import (
    BotOrderService,
    BotPositionService,
    BotLifecycleService,
    BotConfigService,
    BotRiskValidationService,
    BotFundService,
)

from src.services.bot_service_interface import IBotService

from src.services.bot_service import (
    BotService,
    MockBotService,
)

from src.services.fill_processor import FillProcessor

from src.services.execution_policy_service import (
    ExecutionPolicyService,
    ProfitTakingDecision,
    OrderAdjustmentDecision,
    create_execution_policy_service,
)

from src.services.reconciliation_service import (
    ReconciliationService,
    PositionReconciliationResult,
    ReconciliationSummary,
    create_reconciliation_service,
)

from src.services.trading_summary_service import (
    TradingSummaryService,
    TradingSummary,
    PerformanceMetrics,
    PositionSummary,
    create_trading_summary_service,
)

__all__ = [
    # Interfaces
    "IOrderService",
    "IPositionService",
    "IBotLifecycleService",
    "IConfigService",
    "IRiskValidationService",
    "IFundService",
    "IBotService",
    # DTOs
    "OrderDTO",
    "PositionDTO",
    "BotStatus",
    "BotState",
    # Admin Service Implementations
    "BotOrderService",
    "BotPositionService",
    "BotLifecycleService",
    "BotConfigService",
    "BotRiskValidationService",
    "BotFundService",
    "BotService",
    "MockBotService",
    # Core Services
    "FillProcessor",
    # Execution Policy Service
    "ExecutionPolicyService",
    "ProfitTakingDecision",
    "OrderAdjustmentDecision",
    "create_execution_policy_service",
    # Reconciliation Service
    "ReconciliationService",
    "PositionReconciliationResult",
    "ReconciliationSummary",
    "create_reconciliation_service",
    # Trading Summary Service
    "TradingSummaryService",
    "TradingSummary",
    "PerformanceMetrics",
    "PositionSummary",
    "create_trading_summary_service",
]
