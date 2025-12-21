"""
Signal listener implementation for TradingView webhooks.
Refactored modular version using separated components.
"""

import asyncio
from typing import Dict, Any, Callable, Optional
from datetime import datetime
from fastapi import FastAPI
import uvicorn

from src.interfaces import ISignalListener, IConfigurationManager, IMarketDataProvider, IAsyncContextManager
from src.exceptions import SignalProcessingException
from src.core.logging_config import get_logger
from src import TradingSignal

from src.signals.signal_processor import SignalProcessor
from src.signals.webhook_handlers import WebhookHandler
from src.signals.monitoring_router import MonitoringRouter


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
        
        # Register routers from modular components
        self._app.include_router(self._webhook_handler.router)
        self._app.include_router(self._monitoring_router.router)
        
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
        Set the bot instance reference for monitoring endpoints.
        
        Args:
            bot_instance: Trading bot instance
        """
        self._bot_instance = bot_instance
        self._monitoring_router.set_bot_instance(bot_instance)
        logger.info("Bot instance reference updated for monitoring endpoints")
    
    def _display_endpoints(self) -> None:
        """Display available endpoints to the user."""
        base_url = f"http://{self._host}:{self._port}"
        
        print("\n" + "="*70)
        print("📊 ENHANCED BOT MONITORING ENDPOINTS AVAILABLE")
        print("="*70)
        print(f"🏠 Health Check:      {base_url}/health")
        print(f"📈 Positions:         {base_url}/positions")
        print(f"🔍 Position Detail:   {base_url}/positions/{{symbol}}")
        print(f"📊 Bot Status:        {base_url}/status")
        print(f"🎯 Strategy Details:  {base_url}/strategy")
        print(f"📋 Recent Orders:     {base_url}/orders")
        print(f"💰 Trading Summary:   {base_url}/trades")
        print(f"🔄 DCA Orders:        {base_url}/dca-orders")
        print(f"📊 Portfolio Summary: {base_url}/portfolio-summary")
        print(f"📚 API Docs:          {base_url}/docs")
        print("="*70)
        print("💡 Enhanced DCA Tracking: Upgrade to see progressive pricing validation,")
        print("   technical analysis context, and comprehensive position analytics!")
        print("="*70)
        print()
        print("💡 TIP: Bookmark these URLs to monitor your bot!")
        print("📱 Access from any browser or API client")
        print("="*70 + "\n")
