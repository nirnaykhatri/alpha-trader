"""
Admin API Routers Package.

Provides modular routers for the trading terminal admin API:
- OrderRouter: Order management (place, cancel, list)
- PositionRouter: Position management (close, list)
- BotLifecycleRouter: Bot lifecycle (start, stop, pause, resume)
- BotManagementRouter: Bot CRUD operations
- ConfigRouter: Configuration management
- FundRouter: Fund allocation and tracking
- AnalyticsRouter: Analytics and metrics

Author: Trading Bot Team
Version: 2.0.0
"""

from src.signals.routers.base_router import BaseAdminRouter, TokenClaims
from src.signals.routers.order_router import OrderRouter
from src.signals.routers.position_router import PositionRouter
from src.signals.routers.bot_lifecycle_router import BotLifecycleRouter
from src.signals.routers.bot_management_router import BotManagementRouter
from src.signals.routers.config_router import ConfigRouter
from src.signals.routers.fund_router import FundRouter
from src.signals.routers.analytics_router import AnalyticsRouter
from src.signals.routers.dca_preview_router import DCAPreviewRouter
from src.signals.routers.admin_router_composite import (
    AdminRouterComposite,
    create_admin_router
)


# =============================================================================
# Backward Compatibility Alias
# =============================================================================

class AdminRouter(AdminRouterComposite):
    """
    Backward-compatible alias for AdminRouterComposite.
    
    Maintains the same interface as the original admin_router.py for
    existing code that imports AdminRouter directly.
    
    Usage:
        # Old code continues to work:
        from src.signals.routers import AdminRouter
        admin = AdminRouter(bot_instance, config_manager)
        app.include_router(admin.router)
    
    Note:
        New code should use AdminRouterComposite or create_admin_router()
        for clearer intent.
    """
    
    def __init__(self, bot_instance=None, config_manager=None, **kwargs):
        """
        Initialize AdminRouter with legacy signature.
        
        Args:
            bot_instance: Bot instance for accessing trading functionality
            config_manager: Configuration manager (stored for legacy compat)
            **kwargs: Additional service arguments passed to AdminRouterComposite
        """
        # Store config_manager for legacy access patterns
        self._config_manager = config_manager
        
        # Initialize composite with bot_instance
        super().__init__(bot_instance=bot_instance, **kwargs)


__all__ = [
    "BaseAdminRouter",
    "TokenClaims",
    "OrderRouter",
    "PositionRouter",
    "BotLifecycleRouter",
    "BotManagementRouter",
    "ConfigRouter",
    "FundRouter",
    "AnalyticsRouter",
    "DCAPreviewRouter",
    "AdminRouterComposite",
    "create_admin_router",
    # Backward compatibility
    "AdminRouter",
]
