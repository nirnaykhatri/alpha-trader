"""
Admin Router Composite.

Provides backward compatibility by composing all the split routers
into a single router that can be mounted to the FastAPI application.

This module follows the Composite pattern to maintain the same external
interface while internally delegating to specialized routers.

Author: Trading Bot Team
Version: 2.0.0
"""

from typing import Optional, List, TYPE_CHECKING
from fastapi import APIRouter

from src.core.logging_config import get_logger

# Import all routers
from src.signals.routers.order_router import OrderRouter
from src.signals.routers.position_router import PositionRouter
from src.signals.routers.bot_lifecycle_router import BotLifecycleRouter
from src.signals.routers.bot_management_router import BotManagementRouter
from src.signals.routers.config_router import ConfigRouter
from src.signals.routers.fund_router import FundRouter
from src.signals.routers.analytics_router import AnalyticsRouter
from src.signals.routers.dca_preview_router import DCAPreviewRouter
from src.signals.routers.broker_router import BrokerRouter

# Credential store interface (for type hints only)
if TYPE_CHECKING:
    from src.services.broker_credential_store import IBrokerCredentialStore

# Service interfaces
try:
    from src.services.order_service_interface import IOrderService
    from src.services.position_service_interface import IPositionService
    from src.services.bot_lifecycle_service_interface import IBotLifecycleService
    from src.services.bot_service_interface import IBotService
    from src.services.config_service_interface import IConfigService
    from src.services.fund_service_interface import IFundService
    from src.services.analytics_service_interface import IAnalyticsService
    _SERVICE_INTERFACES_AVAILABLE = True
except ImportError:
    IOrderService = None  # type: ignore
    IPositionService = None  # type: ignore
    IBotLifecycleService = None  # type: ignore
    IBotService = None  # type: ignore
    IConfigService = None  # type: ignore
    IFundService = None  # type: ignore
    IAnalyticsService = None  # type: ignore
    _SERVICE_INTERFACES_AVAILABLE = False


logger = get_logger(__name__)

# Log import warnings after logger is initialized
if not _SERVICE_INTERFACES_AVAILABLE:
    logger.warning(
        "Service interfaces failed to import - AdminRouterComposite may have limited functionality. "
        "Ensure all service interface modules exist in src/services/"
    )


class AdminRouterComposite:
    """
    Composite router that combines all admin sub-routers.
    
    This class provides backward compatibility with the original AdminRouter
    while internally delegating to specialized routers that follow the
    Single Responsibility Principle.
    
    Usage:
        # Create composite router with services
        admin_composite = AdminRouterComposite(
            order_service=order_svc,
            position_service=position_svc,
            auth_service=auth_svc
        )
        
        # Mount to FastAPI app
        app.include_router(admin_composite.router)
        
        # Or for legacy compatibility, access individual routers
        order_router = admin_composite.order_router
    
    Attributes:
        router: Combined APIRouter with all admin endpoints
        order_router: Order management router
        position_router: Position management router
        lifecycle_router: Bot lifecycle router
        bot_management_router: Bot CRUD router
        config_router: Configuration router
        fund_router: Fund allocation router
        analytics_router: Analytics router
    """
    
    def __init__(
        self,
        # Service interfaces
        order_service: Optional["IOrderService"] = None,
        position_service: Optional["IPositionService"] = None,
        lifecycle_service: Optional["IBotLifecycleService"] = None,
        bot_service: Optional["IBotService"] = None,
        config_service: Optional["IConfigService"] = None,
        fund_service: Optional["IFundService"] = None,
        analytics_service: Optional["IAnalyticsService"] = None,
        auth_service=None,
        # Legacy support
        bot_instance=None
    ):
        """
        Initialize the composite admin router.
        
        Args:
            order_service: Service for order management
            position_service: Service for position management
            lifecycle_service: Service for bot lifecycle management
            bot_service: Service for bot CRUD operations
            config_service: Service for configuration management
            fund_service: Service for fund allocation
            analytics_service: Service for analytics
            auth_service: Authentication service
            bot_instance: Legacy bot instance for backward compatibility
        """
        self._auth_service = auth_service
        self._bot_instance = bot_instance
        
        # Initialize individual routers
        self.order_router = OrderRouter(
            order_service=order_service,
            auth_service=auth_service,
            bot_instance=bot_instance
        )
        
        self.position_router = PositionRouter(
            position_service=position_service,
            auth_service=auth_service,
            bot_instance=bot_instance
        )
        
        self.lifecycle_router = BotLifecycleRouter(
            lifecycle_service=lifecycle_service,
            auth_service=auth_service,
            bot_instance=bot_instance
        )
        
        self.bot_management_router = BotManagementRouter(
            bot_service=bot_service,
            auth_service=auth_service
        )
        
        self.config_router = ConfigRouter(
            config_service=config_service,
            auth_service=auth_service,
            bot_instance=bot_instance
        )
        
        self.fund_router = FundRouter(
            fund_service=fund_service,
            auth_service=auth_service,
            bot_instance=bot_instance
        )
        
        self.analytics_router = AnalyticsRouter(
            analytics_service=analytics_service,
            auth_service=auth_service,
            bot_instance=bot_instance
        )
        
        # DCA Preview router (stateless, no services needed)
        self.dca_preview_router = DCAPreviewRouter()
        
        # Broker management router (for adding/removing brokers via UI)
        self.broker_router = BrokerRouter(
            auth_service=auth_service,
            bot_instance=bot_instance
        )
        
        # Create combined router
        self.router = APIRouter()
        self._combine_routers()
        
        logger.info("✅ AdminRouterComposite initialized with all sub-routers")
    
    def _combine_routers(self) -> None:
        """Combine all sub-routers into the main router."""
        sub_routers = [
            self.order_router,
            self.position_router,
            self.lifecycle_router,
            self.bot_management_router,
            self.config_router,
            self.fund_router,
            self.analytics_router,
            self.dca_preview_router,
            self.broker_router,
        ]
        
        for sub_router in sub_routers:
            self.router.include_router(sub_router.router)
    
    # ==========================================================================
    # Service setters for late binding
    # ==========================================================================
    
    def set_order_service(self, order_service: "IOrderService") -> None:
        """Set order service."""
        self.order_router.set_order_service(order_service)
    
    def set_position_service(self, position_service: "IPositionService") -> None:
        """Set position service."""
        self.position_router.set_position_service(position_service)
    
    def set_lifecycle_service(self, lifecycle_service: "IBotLifecycleService") -> None:
        """Set lifecycle service."""
        self.lifecycle_router.set_lifecycle_service(lifecycle_service)
    
    def set_bot_service(self, bot_service: "IBotService") -> None:
        """Set bot service."""
        self.bot_management_router.set_bot_service(bot_service)
    
    def set_config_service(self, config_service: "IConfigService") -> None:
        """Set config service."""
        self.config_router.set_config_service(config_service)
    
    def set_fund_service(self, fund_service: "IFundService") -> None:
        """Set fund service."""
        self.fund_router.set_fund_service(fund_service)
    
    def set_analytics_service(self, analytics_service: "IAnalyticsService") -> None:
        """Set analytics service."""
        self.analytics_router.set_analytics_service(analytics_service)
    
    def set_bot_instance(self, bot_instance) -> None:
        """
        Set legacy bot instance for backward compatibility.
        
        This propagates the bot instance to all routers that need it
        for backward compatibility with the legacy system.
        """
        self._bot_instance = bot_instance
        
        # Update all routers that support legacy bot instance
        self.order_router.set_bot_instance(bot_instance)
        self.position_router.set_bot_instance(bot_instance)
        self.lifecycle_router.set_bot_instance(bot_instance)
        self.config_router.set_bot_instance(bot_instance)
        self.fund_router.set_bot_instance(bot_instance)
        self.analytics_router.set_bot_instance(bot_instance)
        self.broker_router.set_bot_instance(bot_instance)
        
        logger.info("Bot instance set for all admin sub-routers")
    
    def set_credential_store(
        self,
        credential_store: "IBrokerCredentialStore",
        user_key: str = "default"
    ) -> None:
        """
        Set the credential store for broker credential persistence.
        
        This enables UI-added broker credentials to be persisted to Azure
        Key Vault and survive container restarts.
        
        Args:
            credential_store: The credential store implementation.
            user_key: User identifier for multi-tenant isolation.
        """
        self.broker_router.set_credential_store(credential_store, user_key)
    
    async def rehydrate_user_brokers(self) -> int:
        """
        Rehydrate UI-added brokers from Key Vault on startup.
        
        This should be called after Azure is initialized to restore broker
        connections that were added via the UI.
        
        Returns:
            Number of brokers successfully rehydrated.
        """
        return await self.broker_router.rehydrate_user_brokers()
    
    # ==========================================================================
    # Health and status
    # ==========================================================================
    
    def get_router_status(self) -> dict:
        """Get status of all sub-routers."""
        return {
            "order_router": "active",
            "position_router": "active",
            "lifecycle_router": "active",
            "bot_management_router": "active",
            "config_router": "active",
            "fund_router": "active",
            "analytics_router": "active",
            "total_endpoints": sum(
                len(r.router.routes) for r in [
                    self.order_router,
                    self.position_router,
                    self.lifecycle_router,
                    self.bot_management_router,
                    self.config_router,
                    self.fund_router,
                    self.analytics_router
                ]
            )
        }


# =============================================================================
# Factory function for easy instantiation
# =============================================================================

def create_admin_router(
    order_service=None,
    position_service=None,
    lifecycle_service=None,
    bot_service=None,
    config_service=None,
    fund_service=None,
    analytics_service=None,
    auth_service=None,
    bot_instance=None
) -> AdminRouterComposite:
    """
    Factory function to create an AdminRouterComposite.
    
    This is the recommended way to create the admin router as it provides
    a clean interface for dependency injection.
    
    Args:
        order_service: Order management service
        position_service: Position management service
        lifecycle_service: Bot lifecycle service
        bot_service: Bot CRUD service
        config_service: Configuration service
        fund_service: Fund allocation service
        analytics_service: Analytics service
        auth_service: Authentication service
        bot_instance: Legacy bot instance
    
    Returns:
        Configured AdminRouterComposite instance
    
    Example:
        admin = create_admin_router(
            order_service=OrderService(),
            position_service=PositionService(),
            auth_service=AzureAuthService()
        )
        app.include_router(admin.router)
    """
    return AdminRouterComposite(
        order_service=order_service,
        position_service=position_service,
        lifecycle_service=lifecycle_service,
        bot_service=bot_service,
        config_service=config_service,
        fund_service=fund_service,
        analytics_service=analytics_service,
        auth_service=auth_service,
        bot_instance=bot_instance
    )
