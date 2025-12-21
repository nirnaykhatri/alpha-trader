"""
Webhook handler module for TradingView signal processing.
Handles incoming webhook signals with security verification.
"""

import asyncio
import json
from typing import Callable, Optional, TYPE_CHECKING
from datetime import datetime
from fastapi import Request, HTTPException, APIRouter
from fastapi.responses import JSONResponse

from src.interfaces import IConfigurationManager, IMarketDataProvider
from src.exceptions import SignalProcessingException
from src.core.logging_config import get_logger
from src import TradingSignal
from src.constants import HTTPStatus, APIConstants
from src.signals.signal_processor import SignalProcessor

if TYPE_CHECKING:
    from src.signals.signal_listener import TradingViewSignalListener

logger = get_logger(__name__)


class WebhookHandler:
    """
    Handles TradingView webhook signal processing.
    Provides authentication, validation, and signal processing.
    """
    
    def __init__(
        self, 
        config: IConfigurationManager, 
        signal_callback: Callable[[TradingSignal], None],
        signal_processor: SignalProcessor,
        market_data: Optional[IMarketDataProvider] = None
    ):
        """
        Initialize webhook handler.
        
        Args:
            config: Configuration manager instance
            signal_callback: Callback function to handle processed signals
            signal_processor: Signal processor instance for signal processing
            market_data: Market data provider (optional)
        """
        self._config = config
        self._signal_callback = signal_callback
        self._signal_processor = signal_processor
        self._market_data = market_data
        
        # Create router for webhook endpoints
        self.router = APIRouter(
            prefix="",
            tags=["webhooks"]
        )
        
        # Setup routes
        self._setup_routes()
        
        logger.info("Webhook handler initialized")
    
    def _setup_routes(self) -> None:
        """Setup webhook routes."""
        
        @self.router.post("/webhook/{secret}")
        async def webhook_handler_with_secret(secret: str, request: Request):
            """
            Handle incoming webhook signals with secret verification.
            
            Args:
                secret: Secret token from URL path
                request: FastAPI request object
                
            Returns:
                JSON response with status and signal_id
                
            Raises:
                HTTPException: If authentication fails or processing errors occur
            """
            try:
                # Verify secret from URL path (only if security is enabled)
                if not self._signal_processor.verify_secret(secret):
                    logger.warning(f"Invalid webhook secret attempt from {request.client.host if request.client else 'unknown'}")
                    raise HTTPException(
                        status_code=HTTPStatus.UNAUTHORIZED, 
                        detail="Invalid webhook secret"
                    )
                
                # Get request body
                body = await request.body()
                
                # Parse JSON payload
                try:
                    signal_data = json.loads(body.decode())
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON payload: {str(e)}")
                    raise HTTPException(
                        status_code=HTTPStatus.BAD_REQUEST, 
                        detail=f"Invalid JSON: {str(e)}"
                    )
                
                # Process signal with timeout
                try:
                    signal = await asyncio.wait_for(
                        self._signal_processor.process_signal(signal_data),
                        timeout=APIConstants.WEBHOOK_PROCESSING_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Signal processing timed out for {signal_data.get('symbol', 'unknown')}")
                    raise HTTPException(
                        status_code=HTTPStatus.INTERNAL_ERROR, 
                        detail="Signal processing timed out"
                    )
                
                # Respond immediately with signal ID
                response_content = {
                    "status": "success", 
                    "signal_id": signal.signal_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                # Call callback asynchronously (fire-and-forget)
                if self._signal_callback:
                    # Don't await - truly fire-and-forget to prevent blocking webhook response
                    asyncio.create_task(self._call_callback_safely(signal))
                
                logger.info(f"Signal processed successfully: {signal.signal_id} for {signal_data.get('symbol', 'unknown')}")
                return JSONResponse(content=response_content)
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR, 
                    detail=f"Internal error: {str(e)}"
                )
        
        @self.router.post("/webhook")
        async def webhook_handler_legacy(request: Request):
            """
            Legacy webhook handler with optional security.
            Supports signature verification and secret in payload.
            
            Args:
                request: FastAPI request object
                
            Returns:
                JSON response with status and signal_id
                
            Raises:
                HTTPException: If authentication fails or processing errors occur
            """
            try:
                # Get raw body
                body = await request.body()
                
                # Only check security if enabled
                # Try signature verification if X-Signature header exists
                signature = request.headers.get("X-Signature", "")
                if signature:
                    if not self._signal_processor.verify_signature(body, signature):
                        logger.warning(f"Invalid signature from {request.client.host if request.client else 'unknown'}")
                        raise HTTPException(
                            status_code=HTTPStatus.UNAUTHORIZED, 
                            detail="Invalid signature"
                        )
                else:
                    # If no signature, check for secret in body
                    try:
                        signal_data = json.loads(body.decode())
                        body_secret = signal_data.get("secret", "")
                        if not self._signal_processor.verify_secret(body_secret):
                            logger.warning(f"Invalid or missing secret from {request.client.host if request.client else 'unknown'}")
                            raise HTTPException(
                                status_code=HTTPStatus.UNAUTHORIZED, 
                                detail="Invalid or missing secret"
                            )
                    except json.JSONDecodeError:
                        logger.error("No authentication provided and invalid JSON")
                        raise HTTPException(
                            status_code=HTTPStatus.UNAUTHORIZED, 
                            detail="No authentication provided"
                        )
                
                # Parse JSON for processing (if not already done)
                if 'signal_data' not in locals():
                    try:
                        signal_data = json.loads(body.decode())
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON payload: {str(e)}")
                        raise HTTPException(
                            status_code=HTTPStatus.BAD_REQUEST, 
                            detail=f"Invalid JSON: {str(e)}"
                        )
                
                # Process signal with timeout
                try:
                    signal = await asyncio.wait_for(
                        self._signal_processor.process_signal(signal_data),
                        timeout=APIConstants.WEBHOOK_PROCESSING_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Signal processing timed out for {signal_data.get('symbol', 'unknown')}")
                    raise HTTPException(
                        status_code=HTTPStatus.INTERNAL_ERROR, 
                        detail="Signal processing timed out"
                    )
                
                # Respond immediately with signal ID
                response_content = {
                    "status": "success", 
                    "signal_id": signal.signal_id,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                # Call callback asynchronously (fire-and-forget)
                if self._signal_callback:
                    # Don't await - truly fire-and-forget to prevent blocking webhook response
                    asyncio.create_task(self._call_callback_safely(signal))
                
                logger.info(f"Signal processed successfully: {signal.signal_id} for {signal_data.get('symbol', 'unknown')}")
                return JSONResponse(content=response_content)
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
                raise HTTPException(
                    status_code=HTTPStatus.INTERNAL_ERROR, 
                    detail=f"Internal error: {str(e)}"
                )
    
    async def _call_callback_safely(self, signal: TradingSignal) -> None:
        """
        Call signal callback with error handling.
        
        Args:
            signal: Processed trading signal
        """
        try:
            if asyncio.iscoroutinefunction(self._signal_callback):
                await self._signal_callback(signal)
            else:
                self._signal_callback(signal)
        except Exception as e:
            logger.error(f"Error in signal callback: {str(e)}", exc_info=True)
