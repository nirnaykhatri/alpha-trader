"""
Azure SignalR Publisher for Real-Time Updates.

Publishes trading events (positions, orders, trades) to connected
web clients via Azure SignalR Service in serverless mode.

Usage:
    publisher = SignalRPublisher(connection_string)
    await publisher.initialize()
    
    # Publish position update
    await publisher.publish_position_update(positions)
    
    # Publish order execution
    await publisher.publish_order_update(order)

Architecture:
    This uses Azure SignalR Service in serverless mode, where the bot
    publishes messages via REST API and clients connect directly to
    SignalR Service. No persistent WebSocket connection is maintained
    on the server side.
    
    Bot (Publisher) --> REST API --> Azure SignalR --> WebSocket --> Clients
"""

import asyncio
import json
import hashlib
import hmac
import base64
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from urllib.parse import urlparse, parse_qs

import aiohttp

from src.core.logging_config import get_logger
from src.interfaces import Position, Order

logger = get_logger(__name__)


@dataclass
class SignalRMessage:
    """Represents a message to publish to SignalR."""
    target: str  # Method name on client
    arguments: List[Any]  # Arguments to pass


class SignalRPublisher:
    """
    Publishes real-time updates to Azure SignalR Service.
    
    Uses serverless mode where the bot publishes via REST API.
    Clients (web dashboard) connect directly to SignalR Service.
    
    Thread-Safety:
        This class is safe for concurrent async operations.
        Uses aiohttp for non-blocking HTTP requests.
    
    Message Types:
        - PositionUpdate: Array of current positions
        - OrderUpdate: Single order status change
        - TradeExecuted: Trade execution notification
        - BotStatus: Bot health/status update
    
    Attributes:
        _connection_string: Azure SignalR connection string
        _hub_name: SignalR hub name (default: 'trading')
    """
    
    # Message targets (method names called on clients)
    TARGET_POSITION_UPDATE = 'PositionUpdate'
    TARGET_ORDER_UPDATE = 'OrderUpdate'
    TARGET_TRADE_EXECUTED = 'TradeExecuted'
    TARGET_BOT_STATUS = 'BotStatus'
    
    def __init__(
        self,
        connection_string: str = None,
        hub_name: str = 'trading',
    ):
        """
        Initialize SignalR publisher.
        
        Args:
            connection_string: Azure SignalR connection string
            hub_name: SignalR hub name
        """
        self._connection_string = connection_string
        self._hub_name = hub_name
        
        # Parse connection string
        self._endpoint: Optional[str] = None
        self._access_key: Optional[str] = None
        self._version: str = '1.0'
        
        if connection_string:
            self._parse_connection_string(connection_string)
        
        # HTTP session for REST API calls
        self._session: Optional[aiohttp.ClientSession] = None
        self._initialized = False
        
        # Message queue for batching
        self._message_queue: List[SignalRMessage] = []
        self._batch_task: Optional[asyncio.Task] = None
        self._batch_interval = 0.5  # seconds
        
        logger.info(f"SignalRPublisher initialized: hub={hub_name}")
    
    @property
    def is_configured(self) -> bool:
        """Check if SignalR is configured."""
        return self._endpoint is not None and self._access_key is not None
    
    def _parse_connection_string(self, connection_string: str) -> None:
        """Parse Azure SignalR connection string."""
        try:
            parts = dict(part.split('=', 1) for part in connection_string.split(';') if '=' in part)
            self._endpoint = parts.get('Endpoint', '').rstrip('/')
            self._access_key = parts.get('AccessKey')
            self._version = parts.get('Version', '1.0')
            
            if not self._endpoint or not self._access_key:
                logger.error("Invalid SignalR connection string: missing Endpoint or AccessKey")
                self._endpoint = None
                self._access_key = None
        except Exception as e:
            logger.error(f"Failed to parse SignalR connection string: {str(e)}")
    
    async def initialize(self) -> None:
        """Initialize HTTP session for SignalR REST API."""
        if not self.is_configured:
            logger.warning("SignalR not configured, skipping initialization")
            return
        
        try:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                headers={
                    'Content-Type': 'application/json',
                }
            )
            self._initialized = True
            logger.info("SignalR publisher initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize SignalR: {str(e)}")
            raise
    
    async def close(self) -> None:
        """Close HTTP session and stop batch task."""
        try:
            if self._batch_task:
                self._batch_task.cancel()
                try:
                    await self._batch_task
                except asyncio.CancelledError:
                    pass
            
            if self._session:
                await self._session.close()
            
            self._initialized = False
            logger.info("SignalR publisher closed")
            
        except Exception as e:
            logger.error(f"Error closing SignalR publisher: {str(e)}")
    
    def _generate_access_token(self, audience: str, expires_in: int = 3600) -> str:
        """
        Generate JWT access token for SignalR REST API.
        
        Args:
            audience: The URL being accessed
            expires_in: Token validity in seconds
            
        Returns:
            JWT token string
        """
        import time
        
        # JWT header
        header = {
            'alg': 'HS256',
            'typ': 'JWT'
        }
        
        # JWT payload
        now = int(time.time())
        payload = {
            'aud': audience,
            'iat': now,
            'exp': now + expires_in,
        }
        
        # Encode header and payload
        header_b64 = base64.urlsafe_b64encode(
            json.dumps(header).encode()
        ).rstrip(b'=').decode()
        
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).rstrip(b'=').decode()
        
        # Create signature
        message = f"{header_b64}.{payload_b64}"
        signature = hmac.new(
            self._access_key.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()
        signature_b64 = base64.urlsafe_b64encode(signature).rstrip(b'=').decode()
        
        return f"{message}.{signature_b64}"
    
    async def _send_to_signalr(
        self,
        target: str,
        arguments: List[Any],
        user_id: Optional[str] = None,
        group_name: Optional[str] = None,
    ) -> bool:
        """
        Send message to SignalR Service via REST API.
        
        Args:
            target: Client method name to invoke
            arguments: Arguments to pass to the method
            user_id: Send to specific user (optional)
            group_name: Send to specific group (optional)
            
        Returns:
            True if message was sent successfully
        """
        if not self.is_configured or not self._session:
            return False
        
        try:
            # Build URL based on target audience
            if user_id:
                url = f"{self._endpoint}/api/v1/hubs/{self._hub_name}/users/{user_id}"
            elif group_name:
                url = f"{self._endpoint}/api/v1/hubs/{self._hub_name}/groups/{group_name}"
            else:
                # Broadcast to all connected clients
                url = f"{self._endpoint}/api/v1/hubs/{self._hub_name}"
            
            # Generate access token
            token = self._generate_access_token(url)
            
            # Prepare message payload
            payload = {
                'target': target,
                'arguments': arguments,
            }
            
            # Send POST request
            async with self._session.post(
                url,
                json=payload,
                headers={
                    'Authorization': f'Bearer {token}',
                }
            ) as response:
                if response.status in (200, 202):
                    logger.debug(f"SignalR message sent: {target}")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"SignalR error {response.status}: {error_text}")
                    return False
                    
        except asyncio.TimeoutError:
            logger.error("SignalR request timed out")
            return False
        except Exception as e:
            logger.error(f"Error sending to SignalR: {str(e)}")
            return False
    
    async def publish_position_update(self, positions: List[Position]) -> bool:
        """
        Publish position update to all connected clients.
        
        Args:
            positions: List of current positions
            
        Returns:
            True if published successfully
        """
        if not positions:
            return True
        
        # Convert positions to serializable format
        position_data = []
        for pos in positions:
            position_data.append({
                'symbol': pos.symbol,
                'direction': 'long' if pos.quantity > 0 else 'short',
                'quantity': abs(pos.quantity),
                'avg_price': float(pos.avg_price),
                'current_price': float(pos.current_price),
                'unrealized_pnl': float(pos.unrealized_pnl),
                'unrealized_pnl_pct': float(
                    (pos.unrealized_pnl / (abs(pos.quantity) * pos.avg_price) * 100)
                    if pos.quantity != 0 and pos.avg_price != 0 else 0
                ),
            })
        
        return await self._send_to_signalr(
            target=self.TARGET_POSITION_UPDATE,
            arguments=[position_data],
        )
    
    async def publish_order_update(self, order: Order) -> bool:
        """
        Publish order status update.
        
        Args:
            order: Order with updated status
            
        Returns:
            True if published successfully
        """
        order_data = {
            'order_id': order.order_id,
            'symbol': order.symbol,
            'side': order.side.value,
            'quantity': float(order.quantity),
            'price': float(order.price) if order.price else None,
            'status': order.status.value,
            'timestamp': datetime.utcnow().isoformat(),
        }
        
        return await self._send_to_signalr(
            target=self.TARGET_ORDER_UPDATE,
            arguments=[order_data],
        )
    
    async def publish_trade_executed(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        pnl: Optional[float] = None,
    ) -> bool:
        """
        Publish trade execution notification.
        
        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            quantity: Executed quantity
            price: Execution price
            pnl: Realized P&L (for closing trades)
            
        Returns:
            True if published successfully
        """
        trade_data = {
            'symbol': symbol,
            'side': side,
            'quantity': quantity,
            'price': price,
            'pnl': pnl,
            'timestamp': datetime.utcnow().isoformat(),
        }
        
        return await self._send_to_signalr(
            target=self.TARGET_TRADE_EXECUTED,
            arguments=[trade_data],
        )
    
    async def publish_bot_status(
        self,
        status: str,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Publish bot status update.
        
        Args:
            status: Status string (e.g., 'running', 'paused', 'error')
            message: Optional status message
            details: Optional additional details
            
        Returns:
            True if published successfully
        """
        status_data = {
            'status': status,
            'message': message,
            'details': details or {},
            'timestamp': datetime.utcnow().isoformat(),
        }
        
        return await self._send_to_signalr(
            target=self.TARGET_BOT_STATUS,
            arguments=[status_data],
        )
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Check SignalR connectivity.
        
        Returns:
            Health check result with status
        """
        if not self.is_configured:
            return {
                'healthy': False,
                'error': 'SignalR not configured',
            }
        
        if not self._initialized:
            return {
                'healthy': False,
                'error': 'SignalR not initialized',
            }
        
        # Try to send a test message (no-op on client)
        try:
            start = datetime.utcnow()
            
            # Simple connectivity check via health endpoint
            url = f"{self._endpoint}/api/health"
            async with self._session.get(url) as response:
                latency_ms = (datetime.utcnow() - start).total_seconds() * 1000
                
                return {
                    'healthy': response.status == 200,
                    'endpoint': self._endpoint,
                    'hub_name': self._hub_name,
                    'latency_ms': round(latency_ms, 2),
                }
                
        except Exception as e:
            return {
                'healthy': False,
                'endpoint': self._endpoint,
                'error': str(e),
            }
