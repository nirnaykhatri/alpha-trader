"""
Bot Lifecycle Router.

Handles bot lifecycle endpoints:
- Start/Stop/Pause/Resume bot
- Get bot state
- Emergency controls

Author: Trading Bot Team
Version: 2.0.0
"""

import asyncio
from typing import Optional
from datetime import datetime

from fastapi import Request, HTTPException, Header
from fastapi.responses import JSONResponse

from src.core.logging_config import get_logger
from src.constants import HTTPStatus
from src.services.admin_interfaces import IBotLifecycleService
from src.signals.routers.base_router import (
    BaseAdminRouter,
    BotStateResponse,
)

logger = get_logger(__name__)


class BotLifecycleRouter(BaseAdminRouter):
    """
    Router for bot lifecycle management.
    
    Provides endpoints for:
    - GET /bot/state - Get current bot state
    - POST /bot/start - Start the bot
    - POST /bot/stop - Stop the bot
    - POST /bot/pause - Pause the bot
    - POST /bot/resume - Resume the bot
    """
    
    def __init__(
        self,
        lifecycle_service: Optional[IBotLifecycleService] = None,
        auth_service=None,
        bot_instance=None  # Legacy support
    ):
        """
        Initialize bot lifecycle router.
        
        Args:
            lifecycle_service: Lifecycle management service
            auth_service: Authentication service
            bot_instance: Legacy bot instance (deprecated)
        """
        super().__init__(auth_service=auth_service, prefix="/admin", tags=["lifecycle"])
        
        self._lifecycle_service = lifecycle_service
        self._bot_instance = bot_instance
        
        # State tracking
        self._bot_state = "running"
        self._bot_start_time = datetime.utcnow()
        self._state_lock = asyncio.Lock()
        
        self._setup_routes()
        logger.info("✅ BotLifecycleRouter initialized")
    
    def set_lifecycle_service(self, lifecycle_service: IBotLifecycleService) -> None:
        """Set the lifecycle service."""
        self._lifecycle_service = lifecycle_service
        logger.info("Lifecycle service set for BotLifecycleRouter")
    
    def set_bot_instance(self, bot_instance) -> None:
        """Set bot instance (legacy support)."""
        self._bot_instance = bot_instance
    
    @property
    def bot_state(self) -> str:
        """Get current bot state."""
        return self._bot_state
    
    def _setup_routes(self) -> None:
        """Setup bot lifecycle routes."""
        
        @self.router.get("/bot/state", response_model=BotStateResponse)
        async def get_bot_state(
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Get current bot state and statistics."""
            await self.validate_auth(request, authorization)
            
            uptime = (datetime.utcnow() - self._bot_start_time).total_seconds()
            
            positions_count = 0
            pending_orders = 0
            
            if self._bot_instance:
                try:
                    positions = await self._bot_instance.get_positions()
                    positions_count = len(positions)
                    
                    orders = await self._bot_instance.order_manager.get_open_orders()
                    pending_orders = len(orders)
                except Exception as e:
                    logger.warning(f"Error getting bot stats: {e}")
            
            return BotStateResponse(
                state=self._bot_state,
                uptime_seconds=uptime,
                positions_count=positions_count,
                pending_orders=pending_orders
            )
        
        @self.router.post("/bot/start")
        async def start_bot(
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Start the trading bot."""
            await self.validate_auth(request, authorization)
            
            async with self._state_lock:
                if self._bot_state == "running":
                    return JSONResponse(content={
                        "status": "success",
                        "state": "running",
                        "message": "Bot is already running"
                    })
                
                previous_state = self._bot_state
                self._bot_state = "running"
                self._bot_start_time = datetime.utcnow()
                
                logger.info(f"✅ Bot started (was: {previous_state})")
                
                return JSONResponse(content={
                    "status": "success",
                    "state": "running",
                    "previous_state": previous_state,
                    "message": "Bot started successfully",
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        @self.router.post("/bot/stop")
        async def stop_bot(
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Stop the trading bot."""
            await self.validate_auth(request, authorization)
            
            async with self._state_lock:
                if self._bot_state == "stopped":
                    return JSONResponse(content={
                        "status": "success",
                        "state": "stopped",
                        "message": "Bot is already stopped"
                    })
                
                previous_state = self._bot_state
                self._bot_state = "stopped"
                
                logger.info(f"🛑 Bot stopped (was: {previous_state})")
                
                return JSONResponse(content={
                    "status": "success",
                    "state": "stopped",
                    "previous_state": previous_state,
                    "message": "Bot stopped successfully",
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        @self.router.post("/bot/pause")
        async def pause_bot(
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Pause the trading bot."""
            await self.validate_auth(request, authorization)
            
            async with self._state_lock:
                if self._bot_state == "paused":
                    return JSONResponse(content={
                        "status": "success",
                        "state": "paused",
                        "message": "Bot is already paused"
                    })
                
                if self._bot_state == "stopped":
                    raise HTTPException(
                        status_code=HTTPStatus.BAD_REQUEST,
                        detail="Cannot pause a stopped bot. Start it first."
                    )
                
                previous_state = self._bot_state
                self._bot_state = "paused"
                
                logger.info(f"⏸️ Bot paused (was: {previous_state})")
                
                return JSONResponse(content={
                    "status": "success",
                    "state": "paused",
                    "previous_state": previous_state,
                    "message": "Bot paused successfully",
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        @self.router.post("/bot/resume")
        async def resume_bot(
            request: Request,
            authorization: Optional[str] = Header(None)
        ):
            """Resume the trading bot from paused state."""
            await self.validate_auth(request, authorization)
            
            async with self._state_lock:
                if self._bot_state == "running":
                    return JSONResponse(content={
                        "status": "success",
                        "state": "running",
                        "message": "Bot is already running"
                    })
                
                if self._bot_state == "stopped":
                    raise HTTPException(
                        status_code=HTTPStatus.BAD_REQUEST,
                        detail="Cannot resume a stopped bot. Use start instead."
                    )
                
                previous_state = self._bot_state
                self._bot_state = "running"
                
                logger.info(f"▶️ Bot resumed (was: {previous_state})")
                
                return JSONResponse(content={
                    "status": "success",
                    "state": "running",
                    "previous_state": previous_state,
                    "message": "Bot resumed successfully",
                    "timestamp": datetime.utcnow().isoformat()
                })
