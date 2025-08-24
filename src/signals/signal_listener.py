"""
Signal listener implementation for TradingView webhooks.
Handles incoming webhook signals and processes them for trading execution.
"""

import asyncio
import json
import hashlib
import hmac
from typing import Dict, Any, Callable, Optional
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
from ..interfaces import ISignalListener, IConfigurationManager, IMarketDataProvider
from ..exceptions import SignalProcessingException, ValidationException
from ..core.logging_config import get_logger
from .. import TradingSignal, SignalType


logger = get_logger(__name__)


class TradingViewSignalListener(ISignalListener):
    """
    Listens for TradingView webhook signals and processes them.
    Provides authentication, validation, and signal processing.
    """
    
    def __init__(self, config: IConfigurationManager, 
                 signal_callback: Callable[[TradingSignal], None],
                 market_data: Optional[IMarketDataProvider] = None,
                 bot_instance=None):
        """
        Initialize signal listener.
        
        Args:
            config: Configuration manager instance
            signal_callback: Callback function to handle processed signals
            market_data: Market data provider (not used since advanced strategy fetches current prices)
            bot_instance: Reference to the trading bot instance for status endpoints
        """
        self._config = config
        self._signal_callback = signal_callback
        self._market_data = market_data
        self._bot_instance = bot_instance
        self._app = FastAPI(title="TradingView Signal Listener")
        self._server = None
        self._is_running = False
        
        # Configuration
        self._host = config.get_config("api.webhook.host", "0.0.0.0")
        self._port = config.get_config("api.webhook.port", 8080)
        self._security_enabled = config.get_config("api.webhook.security_enabled", True)
        self._secret = config.get_config("api.webhook.secret", "")
        
        # Validate security configuration
        if self._security_enabled and not self._secret:
            raise SignalProcessingException(
                "Webhook secret is required when security is enabled. "
                "Either set 'api.webhook.secret' or disable security with 'api.webhook.security_enabled: false'"
            )
        
        if not self._security_enabled:
            logger.warning("⚠️  WEBHOOK SECURITY DISABLED - This should only be used for development!")
        
        # Setup routes
        self._setup_routes()
        
        logger.info(f"TradingView signal listener initialized on {self._host}:{self._port}")
    
    def _setup_routes(self) -> None:
        """Setup FastAPI routes for webhook handling."""
        
        @self._app.post("/webhook/{secret}")
        async def webhook_handler(secret: str, request: Request):
            """Handle incoming webhook signals with secret verification."""
            try:
                # Verify secret from URL path (only if security is enabled)
                if self._security_enabled and not self._verify_secret(secret):
                    raise HTTPException(status_code=401, detail="Invalid webhook secret")
                
                # Get request body
                body = await request.body()
                
                # Parse JSON payload
                try:
                    signal_data = json.loads(body.decode())
                except json.JSONDecodeError as e:
                    raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
                
                # Process signal with timeout
                try:
                    signal = await asyncio.wait_for(
                        self.process_signal(signal_data),
                        timeout=5.0  # 5 second timeout for signal processing
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Signal processing timed out for {signal_data.get('symbol', 'unknown')}")
                    raise HTTPException(status_code=500, detail="Signal processing timed out")
                
                # Respond immediately with signal ID
                response_content = {"status": "success", "signal_id": signal.signal_id}
                
                # Call callback asynchronously (fire-and-forget)
                if self._signal_callback:
                    # Don't await - truly fire-and-forget to prevent blocking webhook response
                    asyncio.create_task(self._call_callback_safely(signal))
                
                logger.info(f"Signal processed successfully: {signal.signal_id}")
                return JSONResponse(content=response_content)
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error processing webhook: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
        
        @self._app.post("/webhook")
        async def webhook_handler_legacy(request: Request):
            """Legacy webhook handler with optional security."""
            try:
                # Get raw body
                body = await request.body()
                
                # Only check security if enabled
                if self._security_enabled:
                    # Try signature verification if X-Signature header exists
                    signature = request.headers.get("X-Signature", "")
                    if signature:
                        if not self._verify_signature(body, signature):
                            raise HTTPException(status_code=401, detail="Invalid signature")
                    else:
                        # If no signature, check for secret in body
                        try:
                            signal_data = json.loads(body.decode())
                            body_secret = signal_data.get("secret", "")
                            if not self._verify_secret(body_secret):
                                raise HTTPException(status_code=401, detail="Invalid or missing secret")
                        except json.JSONDecodeError:
                            raise HTTPException(status_code=401, detail="No authentication provided")
                
                # Parse JSON for processing (if not already done)
                if 'signal_data' not in locals():
                    signal_data = json.loads(body.decode())
                
                # Process signal with timeout
                try:
                    signal = await asyncio.wait_for(
                        self.process_signal(signal_data),
                        timeout=5.0  # 5 second timeout for signal processing
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Signal processing timed out for {signal_data.get('symbol', 'unknown')}")
                    raise HTTPException(status_code=500, detail="Signal processing timed out")
                
                # Respond immediately with signal ID
                response_content = {"status": "success", "signal_id": signal.signal_id}
                
                # Call callback asynchronously (fire-and-forget)
                if self._signal_callback:
                    # Don't await - truly fire-and-forget to prevent blocking webhook response
                    asyncio.create_task(self._call_callback_safely(signal))
                
                logger.info(f"Signal processed successfully: {signal.signal_id}")
                return JSONResponse(content=response_content)
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error processing webhook: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
        
        @self._app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
        
        @self._app.get("/")
        async def root():
            """Root endpoint."""
            return {"message": "TradingView Signal Listener", "version": "1.0.0"}
        
        @self._app.post("/admin/shutdown")
        async def admin_shutdown(request: Request):
            """Admin endpoint to trigger bot shutdown."""
            try:
                # Only allow from localhost for security
                client_host = request.client.host if request.client else "unknown"
                if client_host not in ["127.0.0.1", "localhost", "::1"]:
                    raise HTTPException(status_code=403, detail="Shutdown only allowed from localhost")
                
                logger.info("Shutdown requested via admin endpoint")
                
                # Stop the server
                if self._server:
                    self._server.should_exit = True
                
                return {"status": "shutdown_initiated", "message": "Bot shutdown initiated"}
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error in shutdown endpoint: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Shutdown error: {str(e)}")

        @self._app.get("/status")
        async def get_bot_status(request: Request):
            """Get current bot status including positions and orders."""
            try:
                # Only allow from localhost for security
                client_host = request.client.host if request.client else "unknown"
                if client_host not in ["127.0.0.1", "localhost", "::1"]:
                    raise HTTPException(status_code=403, detail="Status endpoint only accessible from localhost")
                
                # Get status from the callback if available
                if hasattr(self, '_bot_instance') and self._bot_instance:
                    status = await self._bot_instance.get_status()
                    return JSONResponse(content=status)
                else:
                    return JSONResponse(content={
                        "error": "Bot instance not available",
                        "message": "Bot may not be fully initialized"
                    })
                
            except Exception as e:
                logger.error(f"Error getting bot status: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Status error: {str(e)}")

        @self._app.get("/positions")
        async def get_positions(request: Request):
            """Get all current positions with enhanced DCA tracking and transparency."""
            try:
                # Only allow from localhost for security
                client_host = request.client.host if request.client else "unknown"
                if client_host not in ["127.0.0.1", "localhost", "::1"]:
                    raise HTTPException(status_code=403, detail="Positions endpoint only accessible from localhost")
                
                # Get enhanced positions with DCA details
                if hasattr(self, '_bot_instance') and self._bot_instance:
                    
                    # Try to get enhanced DCA positions if available
                    if hasattr(self._bot_instance, 'enhanced_db') and hasattr(self._bot_instance, 'dca_metadata_manager'):
                        try:
                            from ..database.view_manager import PositionSummaryView
                            
                            session = self._bot_instance.enhanced_db.db._session_factory()
                            try:
                                # Get comprehensive position summaries with DCA details
                                positions_data = PositionSummaryView.get_position_summary(session)
                                
                                return JSONResponse(content={
                                    "status": "success",
                                    "timestamp": datetime.utcnow().isoformat(),
                                    "data": {
                                        "positions": positions_data,
                                        "summary": {
                                            "total_positions": len(positions_data),
                                            "total_symbols": len(set(p['symbol'] for p in positions_data)),
                                            "positions_with_dca": len([p for p in positions_data if p['dca_details']['total_attempts'] > 0]),
                                            "total_unrealized_pnl": sum(p['pnl']['unrealized'] for p in positions_data),
                                            "progressive_dca_compliance": sum(1 for p in positions_data if p['dca_details']['progressive_rate'] == 100.0) / len(positions_data) * 100 if positions_data else 0
                                        }
                                    }
                                })
                                
                            finally:
                                session.close()
                                
                        except Exception as enhanced_error:
                            logger.warning(f"Enhanced DCA tracking not available: {enhanced_error}, falling back to basic positions")
                    
                    # Fallback to basic positions if enhanced tracking not available
                    positions = await self._bot_instance.get_positions()
                    positions_data = []
                    
                    for pos in positions:
                        # Determine position side from quantity (positive = long, negative = short)
                        side = "long" if pos.quantity > 0 else "short" if pos.quantity < 0 else "flat"
                        market_value = abs(pos.quantity) * pos.current_price
                        cost_basis = abs(pos.quantity) * pos.avg_price
                        
                        positions_data.append({
                            "position_id": getattr(pos, 'position_id', f"{pos.symbol}_{int(datetime.utcnow().timestamp())}"),
                            "symbol": pos.symbol,
                            "direction": side,
                            "status": "active",
                            "current": {
                                "quantity": abs(pos.quantity),
                                "signed_quantity": pos.quantity,
                                "average_price": pos.avg_price,
                                "market_price": pos.current_price,
                                "market_value": market_value,
                                "cost_basis": cost_basis
                            },
                            "pnl": {
                                "unrealized": pos.unrealized_pnl,
                                "unrealized_percent": (pos.unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0,
                                "realized": pos.realized_pnl
                            },
                            "dca_details": {
                                "total_attempts": 0,
                                "filled_attempts": 0,
                                "pending_attempts": 0,
                                "progressive_rate": 0,
                                "average_improvement_percent": 0,
                                "note": "Enhanced DCA tracking not available - upgrade to see DCA details"
                            },
                            "created_at": pos.created_at.isoformat() if pos.created_at else None
                        })
                    
                    return JSONResponse(content={
                        "status": "success",
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": {
                            "positions": positions_data,
                            "summary": {
                                "total_positions": len(positions_data),
                                "total_symbols": len(set(p['symbol'] for p in positions_data)),
                                "total_unrealized_pnl": sum(p['pnl']['unrealized'] for p in positions_data)
                            }
                        }
                    })
                else:
                    return JSONResponse(content={
                        "status": "error",
                        "message": "Bot instance not available",
                        "data": {"positions": []}
                    })
                
            except Exception as e:
                logger.error(f"Error getting positions: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Positions error: {str(e)}")

        @self._app.get("/positions/{symbol}")
        async def get_position_detail(symbol: str, request: Request):
            """Get detailed information for a specific position including complete DCA history."""
            try:
                # Only allow from localhost for security
                client_host = request.client.host if request.client else "unknown"
                if client_host not in ["127.0.0.1", "localhost", "::1"]:
                    raise HTTPException(status_code=403, detail="Position detail endpoint only accessible from localhost")
                
                if hasattr(self, '_bot_instance') and self._bot_instance:
                    
                    # Try enhanced DCA tracking first
                    if hasattr(self._bot_instance, 'enhanced_db') and hasattr(self._bot_instance, 'dca_metadata_manager'):
                        try:
                            from ..database.enhanced_schema import EnhancedPositionRecord, DCAOrderRecord
                            
                            session = self._bot_instance.enhanced_db.db._session_factory()
                            try:
                                # Get position with all DCA orders
                                position = session.query(EnhancedPositionRecord).filter_by(
                                    symbol=symbol.upper(),
                                    status='active'
                                ).first()
                                
                                if not position:
                                    return JSONResponse(content={
                                        "status": "not_found",
                                        "message": f"No active position found for {symbol}",
                                        "timestamp": datetime.utcnow().isoformat()
                                    }, status_code=404)
                                
                                # Get all DCA orders for this position
                                dca_orders = session.query(DCAOrderRecord).filter_by(
                                    position_id=position.position_id
                                ).order_by(DCAOrderRecord.dca_attempt_number).all()
                                
                                # Calculate performance metrics
                                filled_orders = [d for d in dca_orders if d.status == 'filled']
                                improvements = [d.progression_improvement_pct for d in filled_orders if d.progression_improvement_pct is not None]
                                
                                performance_metrics = {
                                    'total_orders': len(dca_orders),
                                    'filled_orders': len(filled_orders),
                                    'execution_rate': (len(filled_orders) / len(dca_orders) * 100) if dca_orders else 0,
                                    'progressive_rate': (len([d for d in filled_orders if d.is_progressive]) / len(filled_orders) * 100) if filled_orders else 0,
                                    'average_improvement': sum(improvements) / len(improvements) if improvements else 0,
                                    'best_dca_improvement': max(improvements) if improvements else 0,
                                    'worst_dca_improvement': min(improvements) if improvements else 0,
                                    'position_age_hours': (datetime.utcnow() - position.created_at).total_seconds() / 3600 if position.created_at else 0
                                }
                                
                                # Build detailed response
                                response = {
                                    'status': 'success',
                                    'timestamp': datetime.utcnow().isoformat(),
                                    'data': {
                                        'position': position.to_api_dict(),
                                        'dca_analysis': {
                                            'total_attempts': len(dca_orders),
                                            'filled_attempts': len(filled_orders),
                                            'pending_attempts': len([d for d in dca_orders if d.status == 'pending']),
                                            'progressive_compliance': {
                                                'all_progressive': all(d.is_progressive for d in dca_orders if d.status == 'filled'),
                                                'non_progressive_count': len([d for d in dca_orders if d.status == 'filled' and not d.is_progressive]),
                                                'average_improvement': sum(d.progression_improvement_pct or 0 for d in dca_orders if d.status == 'filled') / len([d for d in dca_orders if d.status == 'filled']) if any(d.status == 'filled' for d in dca_orders) else 0
                                            },
                                            'price_progression': [
                                                {
                                                    'attempt': d.dca_attempt_number,
                                                    'requested_price': float(d.price_requested) if d.price_requested else None,
                                                    'filled_price': float(d.average_fill_price) if d.average_fill_price else None,
                                                    'improvement_vs_last': float(d.progression_improvement_pct) if d.progression_improvement_pct else None,
                                                    'is_progressive': d.is_progressive,
                                                    'status': d.status,
                                                    'technical_reason': d.technical_reason,
                                                    'placed_at': d.placed_at.isoformat() if d.placed_at else None,
                                                    'filled_at': d.filled_at.isoformat() if d.filled_at else None
                                                }
                                                for d in dca_orders
                                            ]
                                        },
                                        'technical_context': [
                                            {
                                                'attempt': d.dca_attempt_number,
                                                'reason': d.technical_reason,
                                                'level': float(d.technical_level) if d.technical_level else None,
                                                'confidence': float(d.technical_confidence) if d.technical_confidence else None,
                                                'timeframe': d.timeframe_used,
                                                'filled': d.status == 'filled'
                                            }
                                            for d in dca_orders
                                        ],
                                        'performance_metrics': performance_metrics
                                    }
                                }
                                
                                return JSONResponse(content=response)
                                
                            finally:
                                session.close()
                                
                        except Exception as enhanced_error:
                            logger.warning(f"Enhanced position detail not available: {enhanced_error}")
                    
                    # Fallback to basic position info
                    positions = await self._bot_instance.get_positions()
                    for pos in positions:
                        if pos.symbol.upper() == symbol.upper():
                            side = "long" if pos.quantity > 0 else "short" if pos.quantity < 0 else "flat"
                            market_value = abs(pos.quantity) * pos.current_price
                            cost_basis = abs(pos.quantity) * pos.avg_price
                            
                            return JSONResponse(content={
                                "status": "success",
                                "timestamp": datetime.utcnow().isoformat(),
                                "data": {
                                    "position": {
                                        "symbol": pos.symbol,
                                        "direction": side,
                                        "current": {
                                            "quantity": abs(pos.quantity),
                                            "average_price": pos.avg_price,
                                            "market_price": pos.current_price,
                                            "market_value": market_value,
                                            "cost_basis": cost_basis
                                        },
                                        "pnl": {
                                            "unrealized": pos.unrealized_pnl,
                                            "unrealized_percent": (pos.unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0
                                        }
                                    },
                                    "note": "Enhanced DCA tracking not available - basic position info only"
                                }
                            })
                    
                    return JSONResponse(content={
                        "status": "not_found",
                        "message": f"No position found for {symbol}",
                        "timestamp": datetime.utcnow().isoformat()
                    }, status_code=404)
                
                else:
                    return JSONResponse(content={
                        "status": "error",
                        "message": "Bot instance not available",
                        "timestamp": datetime.utcnow().isoformat()
                    }, status_code=500)
                
            except Exception as e:
                logger.error(f"Error getting position detail for {symbol}: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Position detail error: {str(e)}")

        @self._app.get("/orders")
        async def get_open_orders(request: Request):
            """Get all open orders."""
            try:
                # Only allow from localhost for security
                client_host = request.client.host if request.client else "unknown"
                if client_host not in ["127.0.0.1", "localhost", "::1"]:
                    raise HTTPException(status_code=403, detail="Orders endpoint only accessible from localhost")
                
                # Get orders from the callback if available
                if hasattr(self, '_bot_instance') and self._bot_instance:
                    orders = await self._bot_instance.get_open_orders()
                    # Convert Order objects to dictionaries for JSON serialization
                    orders_data = []
                    for order in orders:
                        orders_data.append({
                            "order_id": str(order.order_id),  # Convert UUID to string
                            "symbol": order.symbol,
                            "quantity": order.quantity,
                            "order_type": order.order_type.value if hasattr(order.order_type, 'value') else str(order.order_type),
                            "side": order.side.value if hasattr(order.side, 'value') else str(order.side),  # Handle enum
                            "price": order.price,
                            "status": order.status.value if hasattr(order.status, 'value') else str(order.status),
                            "created_at": order.created_at.isoformat() if order.created_at else None
                        })
                    return JSONResponse(content={"orders": orders_data})
                else:
                    return JSONResponse(content={
                        "error": "Bot instance not available",
                        "orders": []
                    })
                
            except Exception as e:
                logger.error(f"Error getting orders: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Orders error: {str(e)}")

        @self._app.get("/trades")
        async def get_trading_summary(request: Request):
            """Get comprehensive trading summary with DCA orders, open/closed trades and performance metrics."""
            try:
                # Only allow from localhost for security
                client_host = request.client.host if request.client else "unknown"
                if client_host not in ["127.0.0.1", "localhost", "::1"]:
                    raise HTTPException(status_code=403, detail="Trades endpoint only accessible from localhost")
                
                if hasattr(self, '_bot_instance') and self._bot_instance:
                    
                    # Try enhanced DCA tracking first
                    if hasattr(self._bot_instance, 'enhanced_db') and hasattr(self._bot_instance, 'dca_metadata_manager'):
                        try:
                            from ..database.view_manager import PositionSummaryView
                            from ..database.enhanced_schema import DCAOrderRecord, EnhancedPositionRecord
                            
                            session = self._bot_instance.enhanced_db.db._session_factory()
                            try:
                                # Get portfolio metrics
                                portfolio_metrics = PositionSummaryView.get_portfolio_metrics(session)
                                
                                # Get recent DCA activity
                                recent_dca_activity = PositionSummaryView.get_recent_dca_activity(session, hours=24)
                                
                                # Get all DCA orders for detailed analysis
                                dca_orders = session.query(DCAOrderRecord).join(EnhancedPositionRecord).order_by(
                                    DCAOrderRecord.placed_at.desc()
                                ).limit(50).all()
                                
                                dca_orders_data = []
                                for order in dca_orders:
                                    dca_orders_data.append({
                                        "order_id": order.order_id,
                                        "symbol": session.query(EnhancedPositionRecord.symbol).filter_by(
                                            position_id=order.position_id
                                        ).scalar(),
                                        "dca_attempt": order.dca_attempt_number,
                                        "status": order.status,
                                        "price_requested": float(order.price_requested) if order.price_requested else None,
                                        "price_filled": float(order.average_fill_price) if order.average_fill_price else None,
                                        "quantity": float(order.quantity_requested) if order.quantity_requested else None,
                                        "quantity_filled": float(order.quantity_filled) if order.quantity_filled else None,
                                        "is_progressive": order.is_progressive,
                                        "improvement_percent": float(order.progression_improvement_pct) if order.progression_improvement_pct else None,
                                        "technical_reason": order.technical_reason,
                                        "placed_at": order.placed_at.isoformat() if order.placed_at else None,
                                        "filled_at": order.filled_at.isoformat() if order.filled_at else None
                                    })
                                
                                return JSONResponse(content={
                                    "status": "success",
                                    "timestamp": datetime.utcnow().isoformat(),
                                    "data": {
                                        "portfolio_summary": portfolio_metrics,
                                        "dca_orders": {
                                            "recent_activity": recent_dca_activity,
                                            "all_orders": dca_orders_data,
                                            "summary": {
                                                "total_orders": len(dca_orders_data),
                                                "filled_orders": len([o for o in dca_orders_data if o['status'] == 'filled']),
                                                "pending_orders": len([o for o in dca_orders_data if o['status'] == 'pending']),
                                                "progressive_orders": len([o for o in dca_orders_data if o['is_progressive']]),
                                                "average_improvement": sum(o['improvement_percent'] or 0 for o in dca_orders_data if o['improvement_percent']) / len([o for o in dca_orders_data if o['improvement_percent']]) if any(o['improvement_percent'] for o in dca_orders_data) else 0
                                            }
                                        }
                                    }
                                })
                                
                            finally:
                                session.close()
                                
                        except Exception as enhanced_error:
                            logger.warning(f"Enhanced trading summary not available: {enhanced_error}, falling back to basic summary")
                    
                    # Fallback to basic trading summary
                    summary = await self._bot_instance.get_trading_summary()
                    
                    # Add note about enhanced features
                    if isinstance(summary, dict):
                        summary["note"] = "Enhanced DCA tracking not available - upgrade to see detailed DCA order analysis"
                    
                    return JSONResponse(content={
                        "status": "success",
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": summary
                    })
                else:
                    return JSONResponse(content={
                        "status": "error",
                        "message": "Bot instance not available",
                        "data": {
                            "open_trades": [],
                            "recent_trades": [],
                            "performance": {}
                        }
                    })
                
            except Exception as e:
                logger.error(f"Error getting trading summary: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Trading summary error: {str(e)}")

        @self._app.get("/dca-orders")
        async def get_dca_orders(request: Request):
            """Get all DCA orders with complete details and filtering options."""
            try:
                # Only allow from localhost for security
                client_host = request.client.host if request.client else "unknown"
                if client_host not in ["127.0.0.1", "localhost", "::1"]:
                    raise HTTPException(status_code=403, detail="DCA orders endpoint only accessible from localhost")
                
                # Get query parameters
                symbol = request.query_params.get('symbol', None)
                status = request.query_params.get('status', None)
                limit = int(request.query_params.get('limit', 100))
                
                if hasattr(self, '_bot_instance') and self._bot_instance:
                    
                    # Try enhanced DCA tracking
                    if hasattr(self._bot_instance, 'enhanced_db') and hasattr(self._bot_instance, 'dca_metadata_manager'):
                        try:
                            from ..database.enhanced_schema import DCAOrderRecord, EnhancedPositionRecord
                            
                            session = self._bot_instance.enhanced_db.db._session_factory()
                            try:
                                query = session.query(DCAOrderRecord, EnhancedPositionRecord.symbol).join(
                                    EnhancedPositionRecord, DCAOrderRecord.position_id == EnhancedPositionRecord.position_id
                                )
                                
                                if symbol:
                                    query = query.filter(EnhancedPositionRecord.symbol == symbol.upper())
                                
                                if status:
                                    query = query.filter(DCAOrderRecord.status == status.lower())
                                
                                results = query.order_by(DCAOrderRecord.placed_at.desc()).limit(limit).all()
                                
                                dca_orders_data = []
                                for dca_order, symbol_name in results:
                                    dca_orders_data.append({
                                        "order_id": dca_order.order_id,
                                        "position_id": dca_order.position_id,
                                        "symbol": symbol_name,
                                        "dca_attempt_number": dca_order.dca_attempt_number,
                                        "status": dca_order.status,
                                        "price_requested": float(dca_order.price_requested) if dca_order.price_requested else None,
                                        "quantity_requested": float(dca_order.quantity_requested) if dca_order.quantity_requested else None,
                                        "average_fill_price": float(dca_order.average_fill_price) if dca_order.average_fill_price else None,
                                        "quantity_filled": float(dca_order.quantity_filled) if dca_order.quantity_filled else None,
                                        "is_progressive": dca_order.is_progressive,
                                        "progression_improvement_pct": float(dca_order.progression_improvement_pct) if dca_order.progression_improvement_pct else None,
                                        "technical_reason": dca_order.technical_reason,
                                        "technical_level": float(dca_order.technical_level) if dca_order.technical_level else None,
                                        "technical_confidence": float(dca_order.technical_confidence) if dca_order.technical_confidence else None,
                                        "timeframe_used": dca_order.timeframe_used,
                                        "placed_at": dca_order.placed_at.isoformat() if dca_order.placed_at else None,
                                        "filled_at": dca_order.filled_at.isoformat() if dca_order.filled_at else None,
                                        "age_minutes": (datetime.utcnow() - dca_order.placed_at).total_seconds() / 60 if dca_order.placed_at else None
                                    })
                                
                                # Calculate summary statistics
                                filled_orders = [o for o in dca_orders_data if o['status'] == 'filled']
                                progressive_orders = [o for o in filled_orders if o['is_progressive']]
                                improvements = [o['progression_improvement_pct'] for o in progressive_orders if o['progression_improvement_pct'] is not None]
                                
                                response = {
                                    'status': 'success',
                                    'timestamp': datetime.utcnow().isoformat(),
                                    'filters': {
                                        'symbol': symbol,
                                        'status': status,
                                        'limit': limit
                                    },
                                    'data': {
                                        'dca_orders': dca_orders_data,
                                        'summary': {
                                            'total_orders': len(dca_orders_data),
                                            'filled_orders': len(filled_orders),
                                            'pending_orders': len([o for o in dca_orders_data if o['status'] == 'pending']),
                                            'cancelled_orders': len([o for o in dca_orders_data if o['status'] == 'cancelled']),
                                            'progressive_orders': len(progressive_orders),
                                            'progressive_percentage': (len(progressive_orders) / len(filled_orders) * 100) if filled_orders else 0,
                                            'average_improvement': sum(improvements) / len(improvements) if improvements else 0,
                                            'best_improvement': max(improvements) if improvements else 0,
                                            'worst_improvement': min(improvements) if improvements else 0,
                                            'unique_symbols': len(set(o['symbol'] for o in dca_orders_data)),
                                            'unique_positions': len(set(o['position_id'] for o in dca_orders_data))
                                        }
                                    }
                                }
                                
                                return JSONResponse(content=response)
                                
                            finally:
                                session.close()
                                
                        except Exception as enhanced_error:
                            logger.warning(f"Enhanced DCA orders not available: {enhanced_error}")
                    
                    # Fallback response
                    return JSONResponse(content={
                        "status": "success",
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": {
                            "dca_orders": [],
                            "summary": {
                                "total_orders": 0,
                                "note": "Enhanced DCA tracking not available - upgrade to see DCA order details"
                            }
                        }
                    })
                
                else:
                    return JSONResponse(content={
                        "status": "error",
                        "message": "Bot instance not available",
                        "timestamp": datetime.utcnow().isoformat()
                    }, status_code=500)
                
            except Exception as e:
                logger.error(f"Error getting DCA orders: {str(e)}")
                raise HTTPException(status_code=500, detail=f"DCA orders error: {str(e)}")

        @self._app.get("/portfolio-summary")
        async def get_portfolio_summary(request: Request):
            """Get comprehensive portfolio summary with DCA effectiveness and risk analysis."""
            try:
                # Only allow from localhost for security
                client_host = request.client.host if request.client else "unknown"
                if client_host not in ["127.0.0.1", "localhost", "::1"]:
                    raise HTTPException(status_code=403, detail="Portfolio summary endpoint only accessible from localhost")
                
                if hasattr(self, '_bot_instance') and self._bot_instance:
                    
                    # Try enhanced portfolio analytics
                    if hasattr(self._bot_instance, 'enhanced_db') and hasattr(self._bot_instance, 'dca_metadata_manager'):
                        try:
                            from ..database.view_manager import PositionSummaryView
                            
                            session = self._bot_instance.enhanced_db.db._session_factory()
                            try:
                                # Get comprehensive portfolio metrics
                                portfolio_metrics = PositionSummaryView.get_portfolio_metrics(session)
                                
                                # Get position breakdown
                                positions_summary = PositionSummaryView.get_position_summary(session)
                                
                                # Add position breakdown to response
                                portfolio_metrics['position_breakdown'] = [
                                    {
                                        'symbol': p['symbol'],
                                        'direction': p['direction'],
                                        'unrealized_pnl': p['pnl']['unrealized'],
                                        'unrealized_pnl_percent': p['pnl']['unrealized_percent'],
                                        'dca_attempts': p['dca_details']['total_attempts'],
                                        'progressive_rate': p['dca_details']['progressive_rate'],
                                        'market_value': p['current']['market_value'],
                                        'exposure_percent': (p['current']['cost_basis'] / portfolio_metrics['portfolio_overview']['total_invested'] * 100) if portfolio_metrics['portfolio_overview']['total_invested'] > 0 else 0
                                    }
                                    for p in positions_summary
                                ]
                                
                                return JSONResponse(content={
                                    "status": "success",
                                    "timestamp": datetime.utcnow().isoformat(),
                                    "data": portfolio_metrics
                                })
                                
                            finally:
                                session.close()
                                
                        except Exception as enhanced_error:
                            logger.warning(f"Enhanced portfolio summary not available: {enhanced_error}, falling back to basic summary")
                    
                    # Fallback to basic portfolio calculation
                    positions = await self._bot_instance.get_positions()
                    
                    total_unrealized_pnl = sum(pos.unrealized_pnl for pos in positions)
                    total_market_value = sum(abs(pos.quantity) * pos.current_price for pos in positions)
                    total_cost_basis = sum(abs(pos.quantity) * pos.avg_price for pos in positions)
                    
                    basic_summary = {
                        "portfolio_overview": {
                            "total_positions": len(positions),
                            "unique_symbols": len(set(pos.symbol for pos in positions)),
                            "total_invested": total_cost_basis,
                            "total_market_value": total_market_value,
                            "total_unrealized_pnl": total_unrealized_pnl,
                            "total_unrealized_pnl_percent": (total_unrealized_pnl / total_cost_basis * 100) if total_cost_basis > 0 else 0
                        },
                        "risk_analysis": {
                            "positions_in_profit": len([p for p in positions if p.unrealized_pnl > 0]),
                            "positions_in_loss": len([p for p in positions if p.unrealized_pnl < 0]),
                            "max_single_gain": max((p.unrealized_pnl for p in positions), default=0),
                            "max_single_loss": min((p.unrealized_pnl for p in positions), default=0)
                        },
                        "position_breakdown": [
                            {
                                "symbol": pos.symbol,
                                "direction": "long" if pos.quantity > 0 else "short",
                                "unrealized_pnl": pos.unrealized_pnl,
                                "unrealized_pnl_percent": (pos.unrealized_pnl / (abs(pos.quantity) * pos.avg_price) * 100) if pos.quantity != 0 and pos.avg_price != 0 else 0,
                                "market_value": abs(pos.quantity) * pos.current_price,
                                "exposure_percent": (abs(pos.quantity) * pos.avg_price / total_cost_basis * 100) if total_cost_basis > 0 else 0
                            }
                            for pos in positions
                        ],
                        "note": "Enhanced DCA analytics not available - upgrade for detailed DCA effectiveness metrics"
                    }
                    
                    return JSONResponse(content={
                        "status": "success",
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": basic_summary
                    })
                
                else:
                    return JSONResponse(content={
                        "status": "error",
                        "message": "Bot instance not available",
                        "timestamp": datetime.utcnow().isoformat()
                    }, status_code=500)
                
            except Exception as e:
                logger.error(f"Error getting portfolio summary: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Portfolio summary error: {str(e)}")

        @self._app.get("/strategy")
        async def get_strategy_details(request: Request):
            """Get detailed strategy information including trailing and averaging status."""
            try:
                # Only allow from localhost for security
                client_host = request.client.host if request.client else "unknown"
                if client_host not in ["127.0.0.1", "localhost", "::1"]:
                    raise HTTPException(status_code=403, detail="Strategy endpoint only accessible from localhost")
                
                # Get strategy details from the bot instance
                if hasattr(self, '_bot_instance') and self._bot_instance and hasattr(self._bot_instance, 'advanced_strategy'):
                    strategy = self._bot_instance.advanced_strategy
                    
                    # Get detailed position summary
                    position_summary = strategy.get_position_summary()
                    
                    return JSONResponse(content={
                        "positions": position_summary,
                        "strategy_config": {
                            "long_enabled": strategy.long_config['enabled'],
                            "short_enabled": strategy.short_config['enabled'],
                            "profit_target_pct": strategy.long_config['activation_threshold'] * 100,
                            "trailing_pct": strategy.long_config['trailing_percentage'] * 100,
                            "averaging_enabled": strategy.long_config['averaging_enabled'],
                            "max_averaging_attempts": strategy.long_config['max_averaging_attempts'],
                            "averaging_loss_threshold_pct": strategy.long_config['averaging_loss_threshold'] * 100
                        }
                    })
                else:
                    return JSONResponse(content={
                        "error": "Strategy instance not available",
                        "positions": {},
                        "strategy_config": {}
                    })
                
            except Exception as e:
                logger.error(f"Error getting strategy details: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Strategy error: {str(e)}")

    async def start_listening(self) -> None:
        """Start the webhook server."""
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
            
            logger.info(f"Starting webhook server on {self._host}:{self._port}")
            
            # Display monitoring URLs to user
            print("\n" + "="*70)
            print("📊 ENHANCED BOT MONITORING ENDPOINTS AVAILABLE")
            print("="*70)
            print(f"🏠 Health Check:      http://{self._host}:{self._port}/health")
            print(f"📈 Positions:         http://{self._host}:{self._port}/positions") 
            print(f"🔍 Position Detail:   http://{self._host}:{self._port}/positions/{{symbol}}")
            print(f"📊 Bot Status:        http://{self._host}:{self._port}/status")
            print(f"🎯 Strategy Details:  http://{self._host}:{self._port}/strategy")
            print(f"📋 Recent Orders:     http://{self._host}:{self._port}/orders")
            print(f"💰 Trading Summary:   http://{self._host}:{self._port}/trades")
            print(f"🔄 DCA Orders:        http://{self._host}:{self._port}/dca-orders")
            print(f"📊 Portfolio Summary: http://{self._host}:{self._port}/portfolio-summary")
            print("="*70)
            print("💡 Enhanced DCA Tracking: Upgrade to see progressive pricing validation,")
            print("   technical analysis context, and comprehensive position analytics!")
            print("="*70)
            print()
            print("💡 TIP: Bookmark these URLs to monitor your bot!")
            print("📱 Access from any browser or API client")
            print("="*60)
            
            # Start the server and handle shutdown gracefully
            try:
                await self._server.serve()
            finally:
                # Ensure we mark as not running when server stops
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
                # Set the should_exit flag first
                self._server.should_exit = True
                
                # Force shutdown immediately
                if hasattr(self._server, 'force_exit'):
                    self._server.force_exit = True
                
                # Give the server a moment to clean up
                try:
                    await asyncio.wait_for(self._server.shutdown(), timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning("Server shutdown timed out, proceeding anyway")
                
            self._is_running = False
            logger.info("Webhook server stopped successfully")
            
        except Exception as e:
            logger.error(f"Error stopping webhook server: {str(e)}")
            # Don't raise the exception - we want shutdown to continue
            self._is_running = False
    
    async def process_signal(self, signal_data: Dict[str, Any]) -> TradingSignal:
        """
        Process incoming signal data and convert to TradingSignal.
        
        Args:
            signal_data: Raw signal data from webhook
            
        Returns:
            Processed TradingSignal object
            
        Raises:
            SignalProcessingException: If signal processing fails
        """
        try:
            logger.debug(f"Processing signal data: {signal_data}")
            
            # Validate required fields
            self._validate_signal_data(signal_data)
            
            # Extract signal information
            symbol = signal_data.get("ticker", signal_data.get("symbol", "")).upper()
            action = signal_data.get("signal", signal_data.get("action", "")).lower()
            
            # Get actual current market price
            if "price" in signal_data:
                price = float(signal_data["price"])
                price_source = "signal"
            else:
                # Fetch current market price if not provided in signal
                if self._market_data:
                    try:
                        price = await self._market_data.get_current_price(symbol)
                        price_source = "market_data"
                        logger.info(f"Fetched current price for {symbol}: ${price:.2f}")
                    except Exception as e:
                        logger.error(f"Failed to fetch current price for {symbol}: {e}")
                        raise SignalProcessingException(f"Unable to determine price for {symbol}: {e}")
                else:
                    logger.error(f"No market data provider available to fetch price for {symbol}")
                    raise SignalProcessingException(f"No market data provider available for pricing {symbol}")
            
            # Validate that we have a valid price
            if price <= 0:
                raise SignalProcessingException(f"Invalid price for {symbol}: ${price:.2f}")
            
            quantity = signal_data.get("quantity")
            
            # Extract interval from TradingView webhook (if available)
            interval = self._extract_interval(signal_data)
            
            # Convert action to signal type
            signal_type = self._convert_action_to_signal_type(action)
            
            # Enhance metadata with extracted information
            enhanced_metadata = signal_data.copy()
            if interval:
                enhanced_metadata["interval"] = interval
                logger.debug(f"Extracted interval '{interval}' from signal for {symbol}")
            
            # Create TradingSignal object
            signal = TradingSignal(
                signal_id=None,  # Will be auto-generated
                symbol=symbol,
                signal_type=signal_type,
                price=price,
                quantity=float(quantity) if quantity else None,
                timestamp=datetime.utcnow(),
                metadata=enhanced_metadata
            )
            
            logger.info(f"Signal processed: {signal.symbol} {signal.signal_type.value} @ ${signal.price:.2f} ({price_source})"
                       f"{f' (interval: {interval})' if interval else ''}")
            return signal
            
        except Exception as e:
            logger.error(f"Failed to process signal: {str(e)}")
            raise SignalProcessingException(f"Failed to process signal: {str(e)}")
    
    def _verify_signature(self, body: bytes, signature: str) -> bool:
        """
        Verify webhook signature for security.
        
        Args:
            body: Request body bytes
            signature: Signature from request header
            
        Returns:
            True if signature is valid or security is disabled
        """
        # If security is disabled, always return True
        if not self._security_enabled:
            return True
            
        if not signature:
            logger.warning("No signature provided")
            return False
        
        try:
            # Generate expected signature
            expected_signature = hmac.new(
                self._secret.encode(),
                body,
                hashlib.sha256
            ).hexdigest()
            
            # Compare signatures
            provided_signature = signature.replace("sha256=", "")
            is_valid = hmac.compare_digest(expected_signature, provided_signature)
            
            if not is_valid:
                logger.warning("Invalid webhook signature")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Error verifying signature: {str(e)}")
            return False
    
    def _verify_secret(self, provided_secret: str) -> bool:
        """
        Verify webhook secret for URL path or body authentication.
        
        Args:
            provided_secret: Secret provided in URL path or request body
            
        Returns:
            True if secret is valid or security is disabled
        """
        # If security is disabled, always return True
        if not self._security_enabled:
            return True
            
        if not provided_secret:
            logger.warning("No secret provided")
            return False
        
        try:
            # Use constant-time comparison to prevent timing attacks
            is_valid = hmac.compare_digest(self._secret, provided_secret)
            
            if not is_valid:
                logger.warning("Invalid webhook secret")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Error verifying secret: {str(e)}")
            return False

    def _validate_signal_data(self, signal_data: Dict[str, Any]) -> None:
        """
        Validate signal data structure and content.
        
        Args:
            signal_data: Signal data to validate
            
        Raises:
            ValidationException: If validation fails
        """
        # Required fields - price is optional since advanced strategy uses current market price
        required_fields = ["ticker", "signal"]
        
        for field in required_fields:
            if field not in signal_data:
                raise ValidationException(f"Missing required field: {field}")
        
        # Validate ticker/symbol (accept either)
        symbol = signal_data.get("ticker") or signal_data.get("symbol", "")
        if not symbol or not isinstance(symbol, str):
            raise ValidationException("Ticker/symbol must be a non-empty string")
        
        # Validate signal/action (accept either)
        action = signal_data.get("signal") or signal_data.get("action", "")
        valid_actions = ["buy", "sell", "close", "long", "short"]
        if action.lower() not in valid_actions:
            raise ValidationException(f"Invalid signal: {action}")
        
        # Validate price if present (optional - used only for logging/auditing)
        if "price" in signal_data:
            try:
                price = float(signal_data.get("price", 0))
                if price <= 0:
                    raise ValidationException("Price must be positive")
            except (ValueError, TypeError):
                raise ValidationException("Price must be a valid number")
        
        # Validate quantity if provided
        quantity = signal_data.get("quantity")
        if quantity is not None:
            try:
                qty = float(quantity)
                if qty <= 0:
                    raise ValidationException("Quantity must be positive")
            except (ValueError, TypeError):
                raise ValidationException("Quantity must be a valid number")
    
    def _extract_interval(self, signal_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract interval from TradingView webhook data.
        
        TradingView webhooks can include interval information in various formats:
        - "interval": "1h" (direct field from {{interval}})
        - "timeframe": "1H" (alternative field name for backwards compatibility)
        - "tf": "60" (numeric minutes)
        - Embedded in message or alert name
        
        Args:
            signal_data: Raw signal data from webhook
            
        Returns:
            Normalized interval string (e.g., '1h', '4h', '1d') or None
        """
        try:
            # Try direct interval field first (primary TradingView field)
            interval = signal_data.get("interval")
            if interval:
                return self._normalize_interval(interval)
            
            # Try alternative field names for backwards compatibility
            timeframe = signal_data.get("timeframe") or signal_data.get("tf")
            if timeframe:
                return self._normalize_interval(timeframe)
            
            # Try to extract from message or alert name
            message = signal_data.get("message", "")
            alert_name = signal_data.get("alert_name", "")
            
            # Look for interval patterns in message
            interval_from_message = self._extract_interval_from_text(message + " " + alert_name)
            if interval_from_message:
                return interval_from_message
            
            # Default to configured interval if none found
            default_interval = self._config.get_config("strategies.averaging_down.timeframe", "1h")
            logger.debug(f"No interval found in signal data, using default: {default_interval}")
            return default_interval
            
        except Exception as e:
            logger.warning(f"Error extracting interval: {str(e)}")
            return None
    
    def _normalize_interval(self, interval: str) -> str:
        """
        Normalize interval to standard format.
        
        Args:
            interval: Raw interval string
            
        Returns:
            Normalized interval string
        """
        interval = str(interval).strip().lower()
        
        # Handle numeric minutes
        if interval.isdigit():
            minutes = int(interval)
            if minutes < 60:
                return f"{minutes}m"
            elif minutes < 1440:
                hours = minutes // 60
                return f"{hours}h"
            else:
                days = minutes // 1440
                return f"{days}d"
        
        # Common interval mappings
        interval_map = {
            "1": "1m", "1m": "1m", "1min": "1m",
            "5": "5m", "5m": "5m", "5min": "5m",
            "15": "15m", "15m": "15m", "15min": "15m",
            "30": "30m", "30m": "30m", "30min": "30m",
            "60": "1h", "1h": "1h", "1hour": "1h", "h1": "1h",
            "240": "4h", "4h": "4h", "4hour": "4h", "h4": "4h",
            "1440": "1d", "1d": "1d", "1day": "1d", "d1": "1d", "daily": "1d",
            "10080": "1w", "1w": "1w", "1week": "1w", "w1": "1w", "weekly": "1w"
        }
        
        return interval_map.get(interval, interval)
    
    def _extract_interval_from_text(self, text: str) -> Optional[str]:
        """
        Extract interval from text using pattern matching.
        
        Args:
            text: Text to search for interval patterns
            
        Returns:
            Extracted interval or None
        """
        import re
        
        text = text.lower()
        
        # Pattern for intervals like "1h", "4h", "1d", etc.
        patterns = [
            r'\b(\d+)([mhd])\b',  # 1h, 4h, 1d, etc.
            r'\b(\d+)\s?(min|hour|day)s?\b',  # 1 hour, 5 minutes, etc.
            r'\btf[:\s]*(\d+[mhd]?)\b',  # tf: 1h, tf 4h, etc.
            r'\binterval[:\s]*(\d+[mhd]?)\b',  # interval: 1h, etc.
            r'\btimeframe[:\s]*(\d+[mhd]?)\b'  # timeframe: 1h, etc.
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                if len(match.groups()) == 2:
                    # Number + unit format
                    number, unit = match.groups()
                    unit_map = {
                        'm': 'm', 'min': 'm', 'minute': 'm',
                        'h': 'h', 'hour': 'h',
                        'd': 'd', 'day': 'd'
                    }
                    normalized_unit = unit_map.get(unit, unit)
                    return f"{number}{normalized_unit}"
                else:
                    # Direct interval format
                    return self._normalize_interval(match.group(1))
        
        return None

    def _convert_action_to_signal_type(self, action: str) -> SignalType:
        """
        Convert action string to SignalType enum.
        
        Args:
            action: Action string from signal
            
        Returns:
            Corresponding SignalType
        """
        action_mapping = {
            "buy": SignalType.BUY,
            "long": SignalType.BUY,
            "sell": SignalType.SELL,
            "short": SignalType.SELL,
            "close": SignalType.CLOSE,
            "exit": SignalType.CLOSE
        }
        
        return action_mapping.get(action.lower(), SignalType.BUY)
    
    async def _call_callback_safely(self, signal: TradingSignal) -> None:
        """
        Call the signal callback safely with error handling.
        Uses fire-and-forget approach to prevent blocking webhook response.
        
        Args:
            signal: Processed signal to pass to callback
        """
        try:
            if asyncio.iscoroutinefunction(self._signal_callback):
                # Use create_task for fire-and-forget execution
                # This prevents the webhook response from being blocked
                task = asyncio.create_task(self._signal_callback(signal))
                # Add a done callback to log any exceptions
                task.add_done_callback(self._handle_callback_completion)
            else:
                # For sync callbacks, run in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                loop.run_in_executor(None, self._signal_callback, signal)
        except Exception as e:
            logger.error(f"Error in signal callback setup: {str(e)}")
            # Don't re-raise to avoid failing the webhook response
    
    def _handle_callback_completion(self, task: asyncio.Task) -> None:
        """
        Handle completion of fire-and-forget callback tasks.
        
        Args:
            task: Completed asyncio task
        """
        try:
            # Check if task had an exception
            exception = task.exception()
            if exception:
                logger.error(f"Error in signal callback execution: {str(exception)}")
            else:
                logger.debug("Signal callback completed successfully")
        except Exception as e:
            logger.error(f"Error checking callback task completion: {str(e)}")

    @property
    def is_running(self) -> bool:
        """Check if the listener is currently running."""
        return self._is_running

    def set_bot_instance(self, bot_instance):
        """Set the bot instance reference for status endpoints."""
        self._bot_instance = bot_instance
