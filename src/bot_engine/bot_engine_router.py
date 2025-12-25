"""
Bot Engine API Router - REST API for Multi-Bot Management.

Provides endpoints for managing bot instances via the BotEngineManager:
- Start/stop/pause/resume individual bots
- Get bot status and statistics
- Manage bot configuration
- Bulk operations for multiple bots

All endpoints integrate with the multi-bot async architecture.

Author: Trading Bot Team
Version: 1.0.0
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Query, Depends, Request

from src.core.logging_config import get_logger
from src.constants import HTTPStatus
from src.bot_engine.interfaces import BotEngineConfig, BotStatus
from src.bot_engine.exceptions import (
    BotEngineException,
    BotAlreadyRunningError,
    BotNotRunningError,
    BotNotFoundError,
    ResourceLimitError,
)

# Type checking imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.bot_engine.bot_engine_manager import BotEngineManager
    from src.database.database_interface import IBotRepository

logger = get_logger(__name__)


# =============================================================================
# Request/Response DTOs
# =============================================================================

class BotStartRequest(BaseModel):
    """Request model for starting a bot."""
    
    bot_id: str = Field(..., description="Bot ID to start")


class BotStartResponse(BaseModel):
    """Response model for bot start operation."""
    
    status: str
    bot_id: str
    message: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class BotStopRequest(BaseModel):
    """Request model for stopping a bot."""
    
    bot_id: str = Field(..., description="Bot ID to stop")
    close_position: bool = Field(default=False, description="Close open position before stopping")


class BotStopResponse(BaseModel):
    """Response model for bot stop operation."""
    
    status: str
    bot_id: str
    message: str
    position_closed: bool = False
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class BotStatusResponse(BaseModel):
    """Response model for bot status."""
    
    bot_id: str
    bot_name: str
    user_id: str
    is_running: bool
    state: str
    operational_phase: str
    symbol: str
    exchange: str
    bot_type: str
    has_position: bool
    position_size: Optional[str] = None
    avg_entry_price: Optional[str] = None
    current_price: Optional[str] = None
    unrealized_pnl: Optional[str] = None
    unrealized_pnl_percent: Optional[str] = None
    total_pnl: Optional[str] = None
    completed_deals: int = 0
    safety_orders_used: int = 0
    max_safety_orders: int = 0
    started_at: Optional[str] = None
    last_activity_at: Optional[str] = None
    error_message: Optional[str] = None
    error_count: int = 0


class EngineStatsResponse(BaseModel):
    """Response model for engine statistics."""
    
    is_running: bool
    started_at: Optional[str]
    total_running_bots: int
    max_concurrent_bots: int
    capacity_used_percent: float
    unique_users: int
    unique_symbols: int
    user_bot_counts: Dict[str, int]
    symbol_bot_counts: Dict[str, int]


class BulkStartRequest(BaseModel):
    """Request model for starting multiple bots."""
    
    bot_ids: List[str] = Field(..., description="List of bot IDs to start")


class BulkStopRequest(BaseModel):
    """Request model for stopping multiple bots."""
    
    bot_ids: List[str] = Field(..., description="List of bot IDs to stop")
    close_positions: bool = Field(default=False, description="Close positions before stopping")


class BulkOperationResponse(BaseModel):
    """Response model for bulk operations."""
    
    status: str
    total_requested: int
    successful: int
    failed: int
    results: Dict[str, str]
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class CapacityResponse(BaseModel):
    """Response model for capacity information."""
    
    total_available: int
    max_per_user: int
    max_per_symbol: int
    current_running: int
    
    
class UserCapacityResponse(BaseModel):
    """Response model for user capacity information."""
    
    user_id: str
    bots_running: int
    max_allowed: int
    available: int


# =============================================================================
# Bot Engine Router
# =============================================================================

class BotEngineRouter:
    """
    FastAPI router for bot engine management endpoints.
    
    Provides REST API for:
    - Individual bot lifecycle (start, stop, pause, resume)
    - Bulk bot operations
    - Status and monitoring
    - Capacity management
    
    All operations are delegated to the BotEngineManager.
    """
    
    def __init__(
        self,
        bot_engine_manager: "BotEngineManager",
        bot_repository: "BotRepository",
    ):
        """
        Initialize the router.
        
        Args:
            bot_engine_manager: Bot engine manager instance
            bot_repository: Bot repository for database access
        """
        self._engine = bot_engine_manager
        self._repository = bot_repository
        
        self.router = APIRouter(
            prefix="/bots",
            tags=["bots"],
            responses={
                HTTPStatus.UNAUTHORIZED.value: {"description": "Unauthorized"},
                HTTPStatus.INTERNAL_SERVER_ERROR.value: {"description": "Internal server error"},
            }
        )
        
        self._register_routes()
        logger.info("BotEngineRouter initialized")
    
    def _register_routes(self) -> None:
        """Register all API routes."""
        
        # Individual bot operations
        self.router.add_api_route(
            "/{bot_id}/start",
            self.start_bot,
            methods=["POST"],
            response_model=BotStartResponse,
            summary="Start a bot",
            description="Start a bot instance by its ID",
        )
        
        self.router.add_api_route(
            "/{bot_id}/stop",
            self.stop_bot,
            methods=["POST"],
            response_model=BotStopResponse,
            summary="Stop a bot",
            description="Stop a running bot instance",
        )
        
        self.router.add_api_route(
            "/{bot_id}/pause",
            self.pause_bot,
            methods=["POST"],
            response_model=Dict[str, Any],
            summary="Pause a bot",
            description="Pause a running bot (keeps position)",
        )
        
        self.router.add_api_route(
            "/{bot_id}/resume",
            self.resume_bot,
            methods=["POST"],
            response_model=Dict[str, Any],
            summary="Resume a bot",
            description="Resume a paused bot",
        )
        
        self.router.add_api_route(
            "/{bot_id}/status",
            self.get_bot_status,
            methods=["GET"],
            response_model=BotStatusResponse,
            summary="Get bot status",
            description="Get detailed status of a specific bot",
        )
        
        # Bulk operations
        self.router.add_api_route(
            "/bulk/start",
            self.bulk_start_bots,
            methods=["POST"],
            response_model=BulkOperationResponse,
            summary="Start multiple bots",
            description="Start multiple bots in a single request",
        )
        
        self.router.add_api_route(
            "/bulk/stop",
            self.bulk_stop_bots,
            methods=["POST"],
            response_model=BulkOperationResponse,
            summary="Stop multiple bots",
            description="Stop multiple bots in a single request",
        )
        
        # Status and monitoring
        self.router.add_api_route(
            "/",
            self.list_running_bots,
            methods=["GET"],
            response_model=List[BotStatusResponse],
            summary="List running bots",
            description="Get status of all running bots",
        )
        
        self.router.add_api_route(
            "/user/{user_id}",
            self.list_user_bots,
            methods=["GET"],
            response_model=List[BotStatusResponse],
            summary="List user's bots",
            description="Get status of all bots for a specific user",
        )
        
        self.router.add_api_route(
            "/symbol/{symbol}",
            self.list_symbol_bots,
            methods=["GET"],
            response_model=List[BotStatusResponse],
            summary="List bots by symbol",
            description="Get status of all bots trading a specific symbol",
        )
        
        # Engine management
        self.router.add_api_route(
            "/engine/stats",
            self.get_engine_stats,
            methods=["GET"],
            response_model=EngineStatsResponse,
            summary="Get engine statistics",
            description="Get overall engine statistics and resource usage",
        )
        
        self.router.add_api_route(
            "/engine/capacity",
            self.get_capacity,
            methods=["GET"],
            response_model=CapacityResponse,
            summary="Get capacity info",
            description="Get available capacity for new bots",
        )
        
        self.router.add_api_route(
            "/engine/capacity/{user_id}",
            self.get_user_capacity,
            methods=["GET"],
            response_model=UserCapacityResponse,
            summary="Get user capacity",
            description="Get available capacity for a specific user",
        )
        
        # User operations
        self.router.add_api_route(
            "/user/{user_id}/stop-all",
            self.stop_all_user_bots,
            methods=["POST"],
            response_model=BulkOperationResponse,
            summary="Stop all user bots",
            description="Stop all bots for a specific user",
        )
    
    # =========================================================================
    # Individual Bot Operations
    # =========================================================================
    
    async def start_bot(self, bot_id: str) -> BotStartResponse:
        """
        Start a bot instance.
        
        Args:
            bot_id: Bot identifier
            
        Returns:
            BotStartResponse with operation result
        """
        try:
            # Get bot from repository
            bot = await self._repository.get_by_id(bot_id)
            if not bot:
                raise HTTPException(
                    status_code=HTTPStatus.NOT_FOUND.value,
                    detail=f"Bot {bot_id} not found"
                )
            
            # Start via engine manager
            await self._engine.start_bot(bot)
            
            return BotStartResponse(
                status="success",
                bot_id=bot_id,
                message=f"Bot {bot.name} started successfully"
            )
            
        except BotAlreadyRunningError as e:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT.value,
                detail=str(e)
            )
        except ResourceLimitError as e:
            raise HTTPException(
                status_code=HTTPStatus.TOO_MANY_REQUESTS.value,
                detail=str(e)
            )
        except BotEngineException as e:
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value,
                detail=str(e)
            )
    
    async def stop_bot(
        self, 
        bot_id: str,
        close_position: bool = Query(default=False, description="Close open position")
    ) -> BotStopResponse:
        """
        Stop a running bot.
        
        Args:
            bot_id: Bot identifier
            close_position: Whether to close open position
            
        Returns:
            BotStopResponse with operation result
        """
        try:
            await self._engine.stop_bot(bot_id, close_position=close_position)
            
            return BotStopResponse(
                status="success",
                bot_id=bot_id,
                message=f"Bot stopped successfully",
                position_closed=close_position
            )
            
        except BotNotRunningError as e:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND.value,
                detail=str(e)
            )
        except BotEngineException as e:
            raise HTTPException(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value,
                detail=str(e)
            )
    
    async def pause_bot(self, bot_id: str) -> Dict[str, Any]:
        """
        Pause a running bot.
        
        Args:
            bot_id: Bot identifier
            
        Returns:
            Operation result
        """
        try:
            await self._engine.pause_bot(bot_id)
            
            return {
                "status": "success",
                "bot_id": bot_id,
                "message": "Bot paused successfully",
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except BotNotRunningError as e:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND.value,
                detail=str(e)
            )
    
    async def resume_bot(self, bot_id: str) -> Dict[str, Any]:
        """
        Resume a paused bot.
        
        Args:
            bot_id: Bot identifier
            
        Returns:
            Operation result
        """
        try:
            await self._engine.resume_bot(bot_id)
            
            return {
                "status": "success",
                "bot_id": bot_id,
                "message": "Bot resumed successfully",
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except BotNotRunningError as e:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND.value,
                detail=str(e)
            )
    
    async def get_bot_status(self, bot_id: str) -> BotStatusResponse:
        """
        Get status of a specific bot.
        
        Args:
            bot_id: Bot identifier
            
        Returns:
            BotStatusResponse with detailed status
        """
        status = self._engine.get_bot_status(bot_id)
        
        if not status:
            # Check if bot exists but isn't running
            bot = await self._repository.get_by_id(bot_id)
            if bot:
                return BotStatusResponse(
                    bot_id=bot.id,
                    bot_name=bot.name,
                    user_id=bot.user_id,
                    is_running=False,
                    state=bot.state.value,
                    operational_phase=bot.operational_phase.value,
                    symbol=bot.symbol,
                    exchange=bot.exchange,
                    bot_type=bot.bot_type.value,
                    has_position=False,
                    completed_deals=bot.completed_deals,
                )
            
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND.value,
                detail=f"Bot {bot_id} not found"
            )
        
        return self._status_to_response(status)
    
    # =========================================================================
    # Bulk Operations
    # =========================================================================
    
    async def bulk_start_bots(self, request: BulkStartRequest) -> BulkOperationResponse:
        """
        Start multiple bots.
        
        Args:
            request: Request with list of bot IDs
            
        Returns:
            BulkOperationResponse with results
        """
        results = {}
        successful = 0
        failed = 0
        
        for bot_id in request.bot_ids:
            try:
                bot = await self._repository.get_by_id(bot_id)
                if not bot:
                    results[bot_id] = "not_found"
                    failed += 1
                    continue
                
                await self._engine.start_bot(bot)
                results[bot_id] = "started"
                successful += 1
                
            except Exception as e:
                results[bot_id] = str(e)
                failed += 1
        
        return BulkOperationResponse(
            status="completed",
            total_requested=len(request.bot_ids),
            successful=successful,
            failed=failed,
            results=results
        )
    
    async def bulk_stop_bots(self, request: BulkStopRequest) -> BulkOperationResponse:
        """
        Stop multiple bots.
        
        Args:
            request: Request with list of bot IDs and options
            
        Returns:
            BulkOperationResponse with results
        """
        results = {}
        successful = 0
        failed = 0
        
        for bot_id in request.bot_ids:
            try:
                await self._engine.stop_bot(bot_id, close_position=request.close_positions)
                results[bot_id] = "stopped"
                successful += 1
            except Exception as e:
                results[bot_id] = str(e)
                failed += 1
        
        return BulkOperationResponse(
            status="completed",
            total_requested=len(request.bot_ids),
            successful=successful,
            failed=failed,
            results=results
        )
    
    async def stop_all_user_bots(
        self,
        user_id: str,
        close_positions: bool = Query(default=False, description="Close all positions")
    ) -> BulkOperationResponse:
        """
        Stop all bots for a user.
        
        Args:
            user_id: User identifier
            close_positions: Whether to close all positions
            
        Returns:
            BulkOperationResponse with results
        """
        results = await self._engine.stop_all_user_bots(
            user_id, 
            close_positions=close_positions
        )
        
        successful = sum(1 for v in results.values() if v == "stopped")
        failed = len(results) - successful
        
        return BulkOperationResponse(
            status="completed",
            total_requested=len(results),
            successful=successful,
            failed=failed,
            results=results
        )
    
    # =========================================================================
    # Status & Monitoring
    # =========================================================================
    
    async def list_running_bots(
        self,
        skip: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500)
    ) -> List[BotStatusResponse]:
        """
        List all running bots.
        
        Args:
            skip: Number of bots to skip (pagination)
            limit: Maximum number of bots to return
            
        Returns:
            List of BotStatusResponse
        """
        all_statuses = self._engine.get_all_statuses()
        
        # Apply pagination
        paginated = all_statuses[skip:skip + limit]
        
        return [self._status_to_response(s) for s in paginated]
    
    async def list_user_bots(self, user_id: str) -> List[BotStatusResponse]:
        """
        List all bots for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of BotStatusResponse
        """
        statuses = self._engine.get_user_bots(user_id)
        return [self._status_to_response(s) for s in statuses]
    
    async def list_symbol_bots(self, symbol: str) -> List[BotStatusResponse]:
        """
        List all bots trading a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            List of BotStatusResponse
        """
        statuses = self._engine.get_symbol_bots(symbol.upper())
        return [self._status_to_response(s) for s in statuses]
    
    async def get_engine_stats(self) -> EngineStatsResponse:
        """
        Get engine statistics.
        
        Returns:
            EngineStatsResponse with engine stats
        """
        stats = self._engine.get_engine_stats()
        
        return EngineStatsResponse(
            is_running=stats["is_running"],
            started_at=stats["started_at"],
            total_running_bots=stats["total_running_bots"],
            max_concurrent_bots=stats["max_concurrent_bots"],
            capacity_used_percent=stats["capacity_used_percent"],
            unique_users=stats["unique_users"],
            unique_symbols=stats["unique_symbols"],
            user_bot_counts=stats["user_bot_counts"],
            symbol_bot_counts=stats["symbol_bot_counts"],
        )
    
    async def get_capacity(self) -> CapacityResponse:
        """
        Get available capacity.
        
        Returns:
            CapacityResponse with capacity info
        """
        capacity = self._engine.get_available_capacity()
        
        return CapacityResponse(
            total_available=capacity["total_available"],
            max_per_user=capacity["max_per_user"],
            max_per_symbol=capacity["max_per_symbol"],
            current_running=self._engine.running_bot_count,
        )
    
    async def get_user_capacity(self, user_id: str) -> UserCapacityResponse:
        """
        Get user's available capacity.
        
        Args:
            user_id: User identifier
            
        Returns:
            UserCapacityResponse with user's capacity
        """
        available = self._engine.get_user_available_capacity(user_id)
        user_bots = self._engine.get_user_bots(user_id)
        
        return UserCapacityResponse(
            user_id=user_id,
            bots_running=len(user_bots),
            max_allowed=self._engine.config.max_bots_per_user,
            available=available,
        )
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _status_to_response(self, status: BotStatus) -> BotStatusResponse:
        """Convert BotStatus to BotStatusResponse."""
        return BotStatusResponse(
            bot_id=status.bot_id,
            bot_name=status.bot_name,
            user_id=status.user_id,
            is_running=status.is_running,
            state=status.state,
            operational_phase=status.operational_phase,
            symbol=status.symbol,
            exchange=status.exchange,
            bot_type=status.bot_type,
            has_position=status.has_position,
            position_size=str(status.position_size) if status.position_size else None,
            avg_entry_price=str(status.avg_entry_price) if status.avg_entry_price else None,
            current_price=str(status.current_price) if status.current_price else None,
            unrealized_pnl=str(status.unrealized_pnl) if status.unrealized_pnl else None,
            unrealized_pnl_percent=str(status.unrealized_pnl_percent) if status.unrealized_pnl_percent else None,
            total_pnl=str(status.total_pnl) if status.total_pnl else None,
            completed_deals=status.completed_deals,
            safety_orders_used=status.safety_orders_used,
            max_safety_orders=status.max_safety_orders,
            started_at=status.started_at.isoformat() if status.started_at else None,
            last_activity_at=status.last_activity_at.isoformat() if status.last_activity_at else None,
            error_message=status.error_message,
            error_count=status.error_count,
        )
