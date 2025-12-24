"""
Services module for trading bot admin functionality.

Provides service interfaces and implementations for admin operations,
following Interface Segregation Principle (ISP) and Dependency Inversion (DIP).

Author: Trading Bot Team
Version: 1.0.0
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
    # Implementations
    "BotOrderService",
    "BotPositionService",
    "BotLifecycleService",
    "BotConfigService",
    "BotRiskValidationService",
    "BotFundService",
    "BotService",
    "MockBotService",
]
