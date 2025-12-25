"""
Indicator API Router.

Provides REST endpoints for technical indicator calculations to support
bot creation UI and real-time indicator monitoring.

Endpoints:
- GET /indicators/{symbol} - Calculate indicators for a symbol
- GET /indicators/{symbol}/combined - Calculate combined signals
- GET /indicators/{symbol}/current/{indicator_type} - Get current indicator value

Author: Trading Bot Team
Version: 1.0.0
"""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field

from src.core.logging_config import get_logger
from src.constants import HTTPStatus
from src.domain.bot_enums import IndicatorType, IndicatorTimeframe
from src.services.indicator_service import (
    IIndicatorService,
    IndicatorResult,
    CombinedSignalResult,
    IndicatorCalculationException,
)
from src.signals.routers.base_router import handle_route_errors, ApiResponse


logger = get_logger(__name__)


# =============================================================================
# Request/Response Models
# =============================================================================

class IndicatorRequest(BaseModel):
    """Request model for indicator calculation."""
    
    indicator_type: str = Field(
        default="rsi",
        description="Indicator type: rsi, macd, stochastic"
    )
    timeframe: str = Field(
        default="1h",
        description="Timeframe: 1m, 5m, 15m, 30m, 1h, 4h, 1d"
    )
    lookback_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Number of days to analyze"
    )


class IndicatorConfigItem(BaseModel):
    """Single indicator configuration for combined request."""
    
    type: str = Field(..., description="Indicator type: rsi, macd, stochastic")
    timeframe: str = Field(default="1m", description="Timeframe")
    enabled: bool = Field(default=True, description="Whether enabled")


class CombinedIndicatorsRequest(BaseModel):
    """Request model for combined indicator calculation."""
    
    indicators: List[IndicatorConfigItem] = Field(
        ...,
        min_items=1,
        max_items=10,
        description="List of indicators to calculate"
    )
    lookback_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Number of days to analyze"
    )


class IndicatorValueResponse(BaseModel):
    """Response model for current indicator value."""
    
    timestamp: str
    value: float
    signal: str
    components: dict = Field(default_factory=dict)


class IndicatorResultResponse(BaseModel):
    """Response model for single indicator calculation."""
    
    indicator_type: str = Field(alias="indicatorType")
    timeframe: str
    current_value: IndicatorValueResponse = Field(alias="currentValue")
    signal_count_buy: int = Field(alias="signalCountBuy")
    signal_count_sell: int = Field(alias="signalCountSell")
    
    class Config:
        populate_by_name = True


class CombinedSignalsResponse(BaseModel):
    """Response model for combined indicator calculation."""
    
    symbol: str
    indicators: List[IndicatorResultResponse]
    combined_signal_count: int = Field(alias="combinedSignalCount")
    aligned_buy_signals: int = Field(alias="alignedBuySignals")
    aligned_sell_signals: int = Field(alias="alignedSellSignals")
    lookback_days: int = Field(alias="lookbackDays")
    
    class Config:
        populate_by_name = True


# =============================================================================
# Indicator Router
# =============================================================================

class IndicatorRouter:
    """
    FastAPI router for technical indicator endpoints.
    
    Provides REST API access to indicator calculations for:
    - Bot creation UI: Historical signal counts
    - Real-time monitoring: Current indicator values
    - Charting: Historical indicator data
    
    Example:
        router = IndicatorRouter(indicator_service)
        app.include_router(router.router, prefix="/api/v1")
    """
    
    def __init__(self, indicator_service: IIndicatorService):
        """
        Initialize indicator router.
        
        Args:
            indicator_service: Service for indicator calculations
        """
        self._indicator_service = indicator_service
        self.router = APIRouter(prefix="/indicators", tags=["indicators"])
        
        self._register_routes()
        
        logger.info("IndicatorRouter initialized")
    
    def _register_routes(self) -> None:
        """Register all API routes."""
        
        @self.router.get(
            "/{symbol}",
            response_model=IndicatorResultResponse,
            summary="Calculate single indicator",
            description="Calculate a technical indicator for a symbol"
        )
        @handle_route_errors(operation_name="calculate_indicator")
        async def calculate_indicator(
            symbol: str = Path(..., description="Trading symbol (e.g., AAPL)"),
            indicator_type: str = Query(
                default="rsi",
                description="Indicator type: rsi, macd, stochastic"
            ),
            timeframe: str = Query(
                default="1h",
                description="Timeframe: 1m, 5m, 15m, 30m, 1h, 4h, 1d"
            ),
            lookback_days: int = Query(
                default=30,
                ge=1,
                le=365,
                description="Number of days to analyze"
            ),
        ) -> IndicatorResultResponse:
            """
            Calculate a single technical indicator for a symbol.
            
            Returns the current indicator value, signal state, and
            signal counts over the lookback period.
            """
            # Validate indicator type
            try:
                ind_type = IndicatorType(indicator_type.lower())
            except ValueError:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=f"Invalid indicator type: {indicator_type}. "
                           f"Valid options: rsi, macd, stochastic"
                )
            
            # Validate timeframe
            try:
                tf = IndicatorTimeframe(timeframe.lower())
            except ValueError:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=f"Invalid timeframe: {timeframe}. "
                           f"Valid options: 1m, 5m, 15m, 30m, 1h, 4h, 1d"
                )
            
            try:
                result = await self._indicator_service.calculate_indicator(
                    symbol=symbol.upper(),
                    indicator_type=ind_type,
                    timeframe=tf,
                    lookback_days=lookback_days,
                )
                
                return IndicatorResultResponse(
                    indicatorType=result.indicator_type.value,
                    timeframe=result.timeframe.value,
                    currentValue=IndicatorValueResponse(
                        timestamp=result.current_value.timestamp.isoformat(),
                        value=result.current_value.value,
                        signal=result.current_value.signal,
                        components=result.current_value.components,
                    ),
                    signalCountBuy=result.signal_count_buy,
                    signalCountSell=result.signal_count_sell,
                )
                
            except IndicatorCalculationException as e:
                raise HTTPException(
                    status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    detail=str(e)
                )
        
        @self.router.post(
            "/{symbol}/combined",
            response_model=CombinedSignalsResponse,
            summary="Calculate combined indicators",
            description="Calculate multiple indicators and combine signals"
        )
        @handle_route_errors(operation_name="calculate_combined_signals")
        async def calculate_combined_signals(
            symbol: str = Path(..., description="Trading symbol"),
            request: CombinedIndicatorsRequest = ...,
        ) -> CombinedSignalsResponse:
            """
            Calculate multiple indicators and combine their signals.
            
            Used by the bot creation UI to show the "Combined signals last 30d"
            count based on user-selected indicators.
            """
            # Parse indicators
            indicators = []
            for ind in request.indicators:
                if not ind.enabled:
                    continue
                    
                try:
                    ind_type = IndicatorType(ind.type.lower())
                    tf = IndicatorTimeframe(ind.timeframe.lower())
                    indicators.append((ind_type, tf))
                except ValueError as e:
                    logger.warning(f"Skipping invalid indicator config: {e}")
            
            if not indicators:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail="At least one enabled indicator is required"
                )
            
            try:
                result = await self._indicator_service.calculate_combined_signals(
                    symbol=symbol.upper(),
                    indicators=indicators,
                    lookback_days=request.lookback_days,
                )
                
                # Convert to response model
                indicator_responses = []
                for ind_result in result.indicators:
                    indicator_responses.append(IndicatorResultResponse(
                        indicatorType=ind_result.indicator_type.value,
                        timeframe=ind_result.timeframe.value,
                        currentValue=IndicatorValueResponse(
                            timestamp=ind_result.current_value.timestamp.isoformat(),
                            value=ind_result.current_value.value,
                            signal=ind_result.current_value.signal,
                            components=ind_result.current_value.components,
                        ),
                        signalCountBuy=ind_result.signal_count_buy,
                        signalCountSell=ind_result.signal_count_sell,
                    ))
                
                return CombinedSignalsResponse(
                    symbol=result.symbol,
                    indicators=indicator_responses,
                    combinedSignalCount=result.combined_signal_count,
                    alignedBuySignals=result.aligned_buy_signals,
                    alignedSellSignals=result.aligned_sell_signals,
                    lookbackDays=result.lookback_days,
                )
                
            except IndicatorCalculationException as e:
                raise HTTPException(
                    status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    detail=str(e)
                )
        
        @self.router.get(
            "/{symbol}/current/{indicator_type}",
            response_model=IndicatorValueResponse,
            summary="Get current indicator value",
            description="Get the current (real-time) indicator value"
        )
        @handle_route_errors(operation_name="get_current_indicator")
        async def get_current_indicator(
            symbol: str = Path(..., description="Trading symbol"),
            indicator_type: str = Path(..., description="Indicator type"),
            timeframe: str = Query(
                default="1h",
                description="Timeframe for calculation"
            ),
        ) -> IndicatorValueResponse:
            """
            Get the current indicator value for real-time evaluation.
            
            Used by the bot engine to check if indicator conditions
            are met for starting a new deal.
            """
            try:
                ind_type = IndicatorType(indicator_type.lower())
            except ValueError:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=f"Invalid indicator type: {indicator_type}"
                )
            
            try:
                tf = IndicatorTimeframe(timeframe.lower())
            except ValueError:
                raise HTTPException(
                    status_code=HTTPStatus.BAD_REQUEST,
                    detail=f"Invalid timeframe: {timeframe}"
                )
            
            try:
                result = await self._indicator_service.get_current_indicator_status(
                    symbol=symbol.upper(),
                    indicator_type=ind_type,
                    timeframe=tf,
                )
                
                return IndicatorValueResponse(
                    timestamp=result.timestamp.isoformat(),
                    value=result.value,
                    signal=result.signal,
                    components=result.components,
                )
                
            except IndicatorCalculationException as e:
                raise HTTPException(
                    status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                    detail=str(e)
                )


# =============================================================================
# Factory Function
# =============================================================================

def create_indicator_router(indicator_service: IIndicatorService) -> APIRouter:
    """
    Factory function to create indicator router.
    
    Args:
        indicator_service: Indicator calculation service
        
    Returns:
        Configured FastAPI router
    """
    router_instance = IndicatorRouter(indicator_service)
    return router_instance.router


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    "IndicatorRouter",
    "create_indicator_router",
    "IndicatorRequest",
    "CombinedIndicatorsRequest",
    "IndicatorResultResponse",
    "CombinedSignalsResponse",
]
