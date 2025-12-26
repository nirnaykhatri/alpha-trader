"""
Signal listener implementation for TradingView webhooks.
Refactored modular version using separated components.
"""

import asyncio
import os
from typing import Dict, Any, Callable, Optional
from datetime import datetime
from fastapi import FastAPI, APIRouter
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from src.interfaces import ISignalListener, IConfigurationManager, IMarketDataProvider, IAsyncContextManager
from src.exceptions import SignalProcessingException
from src.core.logging_config import get_logger
from src import TradingSignal

from src.signals.signal_processor import SignalProcessor
from src.signals.webhook_handlers import WebhookHandler
from src.signals.monitoring_router import MonitoringRouter
from src.signals.routers import AdminRouter
from src.signals.routers.indicator_router import create_indicator_router
from src.services.indicator_service import IndicatorService


logger = get_logger(__name__)


class TradingViewSignalListener(ISignalListener, IAsyncContextManager):
    """
    Listens for TradingView webhook signals and processes them.
    Refactored to use modular components for better maintainability.
    
    Components:
    - SignalProcessor: Handles signal validation and parsing
    - WebhookHandler: Manages webhook endpoints and security
    - MonitoringRouter: Provides monitoring and analytics endpoints
    """
    
    def __init__(
        self,
        config: IConfigurationManager,
        signal_callback: Callable[[TradingSignal], None],
        market_data: Optional[IMarketDataProvider] = None,
        bot_instance=None
    ):
        """
        Initialize signal listener with modular components.
        
        Args:
            config: Configuration manager instance
            signal_callback: Callback function to handle processed signals
            market_data: Market data provider for price fetching
            bot_instance: Reference to the trading bot instance for status endpoints
        """
        self._config = config
        self._signal_callback = signal_callback
        self._market_data = market_data
        self._bot_instance = bot_instance
        
        # Initialize modular components
        self._signal_processor = SignalProcessor(config, market_data)
        self._webhook_handler = WebhookHandler(
            config,
            signal_callback,
            self._signal_processor,
            market_data
        )
        self._monitoring_router = MonitoringRouter(bot_instance)
        self._admin_router = AdminRouter(bot_instance, config)
        
        # Initialize indicator service and router (if market data available)
        self._indicator_service = None
        self._indicator_router = None
        if market_data:
            self._indicator_service = IndicatorService(market_data)
            self._indicator_router = create_indicator_router(self._indicator_service)
        
        # Initialize FastAPI with comprehensive OpenAPI documentation
        self._app = FastAPI(
            title="TradingView Trading Bot API",
            description=(
                "Advanced DCA Trading Bot with technical analysis-based position management. "
                "Receives TradingView webhook signals and executes trades through Alpaca API. "
                "Features position-aware DCA strategy that eliminates arbitrary loss thresholds."
            ),
            version="1.0.0",
            docs_url="/docs",
            redoc_url="/redoc",
            openapi_tags=[
                {
                    "name": "webhooks",
                    "description": "TradingView webhook endpoints for receiving trading signals"
                },
                {
                    "name": "positions",
                    "description": "Position management and tracking endpoints"
                },
                {
                    "name": "orders",
                    "description": "Order management and history endpoints"
                },
                {
                    "name": "indicators",
                    "description": "Technical indicator calculations (RSI, MACD, Stochastic)"
                },
                {
                    "name": "analytics",
                    "description": "Trading analytics and performance metrics"
                },
                {
                    "name": "admin",
                    "description": "Administrative endpoints (localhost only)"
                },
                {
                    "name": "health",
                    "description": "Health check and status endpoints"
                }
            ],
            contact={
                "name": "Trading Bot Support",
                "email": "support@example.com"
            },
            license_info={
                "name": "MIT",
                "url": "https://opensource.org/licenses/MIT"
            }
        )
        
        # Add CORS middleware to allow frontend requests
        # Origins are configurable via CORS_ORIGINS env var (comma-separated)
        # Default: localhost for development; configure for production
        cors_origins_str = config.get_config(
            "api.cors.origins", 
            os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
        )
        cors_origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]
        
        self._app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Create a versioned API router to match frontend expectations
        # Frontend expects endpoints at /api/v1/* (see trading-terminal/lib/types/api-types.ts)
        api_v1_router = APIRouter(prefix="/api/v1")
        
        # Include modular routers under the versioned prefix
        api_v1_router.include_router(self._webhook_handler.router)
        api_v1_router.include_router(self._monitoring_router.router)
        api_v1_router.include_router(self._admin_router.router)
        
        # Include indicator router if available
        if self._indicator_router:
            api_v1_router.include_router(self._indicator_router)
        
        # Mount the versioned router on the app
        self._app.include_router(api_v1_router)
        
        # DUAL MOUNT: Also include the monitoring router at root level for container health checks.
        # 
        # Why dual mounting?
        # 1. The /api/v1/health endpoint is the canonical API endpoint for frontend clients
        # 2. The root-level /health endpoint is for infrastructure health checks:
        #    - Azure Container Apps readiness/liveness probes expect /health at root
        #    - Kubernetes health probes typically check root-level endpoints
        #    - Load balancers (Azure Front Door, Application Gateway) check root paths
        # 
        # This follows the "same logic, multiple entry points" pattern common in
        # containerized applications where infrastructure needs differ from API design.
        self._app.include_router(self._monitoring_router.router)
        
        # Register dependency checks for readiness probe
        self._register_dependency_checks()
        
        self._server = None
        self._is_running = False
        
        # Configuration
        self._host = config.get_config("api.webhook.host", "0.0.0.0")
        self._port = config.get_config("api.webhook.port", 8080)
        
        logger.info(f"✅ TradingView signal listener initialized (refactored modular version)")
        logger.info(f"📍 Server will run on {self._host}:{self._port}")
        logger.info(f"🔐 Security: {'enabled' if config.get_config('api.webhook.security_enabled', True) else 'DISABLED'}")
    
    async def start(self) -> None:
        """Start the signal listener (IAsyncContextManager implementation)."""
        await self.start_listening()

    async def stop(self) -> None:
        """Stop the signal listener (IAsyncContextManager implementation)."""
        await self.stop_listening()

    async def start_listening(self) -> None:
        """Start the webhook server with all registered routers."""
        if self._is_running:
            logger.warning("Signal listener is already running")
            return
        
        try:
            config = uvicorn.Config(
                app=self._app,
                host=self._host,
                port=self._port,
                log_level="info",
                access_log=True
            )
            
            self._server = uvicorn.Server(config)
            self._is_running = True
            
            logger.info(f"🚀 Starting webhook server on {self._host}:{self._port}")
            
            # Display monitoring URLs
            self._display_endpoints()
            
            # Start the server and handle shutdown gracefully
            try:
                await self._server.serve()
            finally:
                self._is_running = False
                logger.info("Webhook server has stopped")
            
        except Exception as e:
            logger.error(f"Failed to start webhook server: {str(e)}")
            self._is_running = False
            raise SignalProcessingException(f"Failed to start webhook server: {str(e)}")
    
    async def stop_listening(self) -> None:
        """Stop the webhook server."""
        if not self._is_running:
            logger.debug("Signal listener is not running")
            return
        
        try:
            if self._server:
                logger.info("Stopping webhook server...")
                self._server.should_exit = True
                
                if hasattr(self._server, 'force_exit'):
                    self._server.force_exit = True
                
                try:
                    await asyncio.wait_for(self._server.shutdown(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning("Server shutdown timed out, proceeding anyway")
                
            self._is_running = False
            logger.info("✅ Webhook server stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping webhook server: {str(e)}")
            self._is_running = False
    
    async def process_signal(self, signal_data: Dict[str, Any]) -> TradingSignal:
        """
        Process incoming signal data using the signal processor.
        
        Args:
            signal_data: Raw signal data from webhook
            
        Returns:
            Processed TradingSignal object
            
        Raises:
            SignalProcessingException: If signal processing fails
        """
        return await self._signal_processor.process_signal(signal_data)
    
    @property
    def is_running(self) -> bool:
        """Check if the listener is currently running."""
        return self._is_running
    
    def set_bot_instance(self, bot_instance):
        """
        Set the bot instance reference for monitoring and admin endpoints.
        
        Args:
            bot_instance: Trading bot instance
        """
        self._bot_instance = bot_instance
        self._monitoring_router.set_bot_instance(bot_instance)
        self._admin_router.set_bot_instance(bot_instance)
        logger.info("Bot instance reference updated for monitoring and admin endpoints")
    
    def _register_dependency_checks(self) -> None:
        """
        Register dependency checks with monitoring router for /ready endpoint.
        
        Validates critical dependencies at startup and during health checks:
        - SignalR connection string configuration
        - Azure App Configuration availability  
        - Database connection status
        
        These checks are exposed via /ready endpoint for Container Apps health probes.
        """
        # Check SignalR configuration
        async def check_signalr() -> dict:
            """Validate SignalR connection string is configured."""
            signalr_conn = self._config.get_config("azure.signalr_connection_string", "")
            hub_name = self._config.get_config("azure.signalr_hub_name", "trading")
            
            if not signalr_conn:
                return {
                    "healthy": False,
                    "configured": False,
                    "message": "SignalR connection string not configured",
                    "hub_name": hub_name
                }
            
            # Basic validation - check connection string format
            is_valid_format = "Endpoint=" in signalr_conn and "AccessKey=" in signalr_conn
            return {
                "healthy": is_valid_format,
                "configured": True,
                "message": "SignalR configured" if is_valid_format else "Invalid SignalR connection string format",
                "hub_name": hub_name
            }
        
        # Check Azure App Configuration
        async def check_azure_config() -> dict:
            """Validate Azure App Configuration availability."""
            azure_endpoint = self._config.get_config("azure.app_config_endpoint", "")
            
            if not azure_endpoint:
                # Not required - local config is fine
                return {
                    "healthy": True,
                    "configured": False,
                    "message": "Using local configuration (Azure App Config not configured)"
                }
            
            # Check if ConfigurationManager has Azure config initialized
            azure_initialized = getattr(self._config, '_azure_config_initialized', False)
            return {
                "healthy": True,  # Not a hard failure if Azure config unavailable
                "configured": True,
                "azure_connected": azure_initialized,
                "message": "Azure App Config connected" if azure_initialized else "Azure App Config configured but not connected"
            }
        
        # Check database connectivity
        async def check_database() -> dict:
            """Validate database connection status."""
            if not self._bot_instance:
                return {
                    "healthy": False,
                    "message": "Bot instance not initialized"
                }
            
            try:
                # Access the database manager through bot instance
                db_manager = getattr(self._bot_instance, 'db_manager', None)
                if not db_manager:
                    return {
                        "healthy": False,
                        "message": "Database manager not available"
                    }
                
                # Try to verify DB is accessible
                is_connected = getattr(db_manager, 'is_connected', True)
                return {
                    "healthy": is_connected,
                    "message": "Database connected" if is_connected else "Database disconnected"
                }
            except Exception as e:
                return {
                    "healthy": False,
                    "message": f"Database check failed: {str(e)}"
                }
        
        # Register all checks with monitoring router
        self._monitoring_router.register_dependency_check("signalr", check_signalr)
        self._monitoring_router.register_dependency_check("azure_config", check_azure_config)
        self._monitoring_router.register_dependency_check("database", check_database)
        
        logger.info("📋 Registered 3 dependency checks: signalr, azure_config, database")
    
    def _display_endpoints(self) -> None:
        """Display available endpoints to the user."""
        base_url = f"http://{self._host}:{self._port}"
        api_url = f"{base_url}/api/v1"
        
        print("\n" + "="*70)
        print("📊 TRADING BOT API ENDPOINTS (v1)")
        print("="*70)
        print("\n🔍 MONITORING (Read-Only)")
        print(f"  🏠 Health Check:      {api_url}/health")
        print(f"  📈 Positions:         {api_url}/positions")
        print(f"  📋 Recent Orders:     {api_url}/orders")
        print(f"  📊 Portfolio Summary: {api_url}/portfolio-summary")
        print(f"  📚 API Docs:          {base_url}/docs")
        print("\n🎮 ADMIN (Trading Terminal)")
        print(f"  📝 Place Order:       POST {api_url}/admin/orders")
        print(f"  🚫 Cancel Order:      DELETE {api_url}/admin/orders/{{id}}")
        print(f"  📤 Close Position:    POST {api_url}/admin/positions/{{symbol}}/close")
        print(f"  🚀 Start Bot:         POST {api_url}/admin/bot/start")
        print(f"  ⏸️  Pause Bot:         POST {api_url}/admin/bot/pause")
        print(f"  🛑 Stop Bot:          POST {api_url}/admin/bot/stop")
        print(f"  ⚙️  Get Config:        GET {api_url}/admin/config")
        print(f"  💰 Funds Summary:     GET {api_url}/admin/funds/summary")
        print("="*70)
        print("💡 TIP: Use the Trading Terminal UI for easy access!")
        print("="*70 + "\n")
