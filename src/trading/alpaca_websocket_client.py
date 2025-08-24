"""
Alpaca WebSocket client for high-frequency trading.
Provides real-time market data and trade updates via WebSocket connections.
"""

import asyncio
import json
from typing import Dict, Any, Callable, Optional, List
from datetime import datetime
from alpaca.data.live import StockDataStream
from alpaca.trading.stream import TradingStream
from alpaca.trading.enums import OrderSide
from alpaca.common.exceptions import APIError
from ..interfaces import IConfigurationManager
from ..exceptions import APIException, ConnectionException
from ..core.logging_config import get_logger
from .. import Order, OrderStatus, TradingSignal


logger = get_logger(__name__)


class AlpacaWebSocketClient:
    """
    WebSocket client for Alpaca API providing real-time market data and trade updates.
    Designed for high-frequency trading scenarios requiring low latency.
    """
    
    def __init__(self, config: IConfigurationManager):
        """
        Initialize Alpaca WebSocket client.
        
        Args:
            config: Configuration manager instance
        """
        self._config = config
        self._market_data_stream = None
        self._trading_stream = None
        self._is_connected = False
        self._subscribed_symbols = set()
        
        # Configuration
        self._api_key = config.get_config("api.alpaca.api_key")
        self._secret_key = config.get_config("api.alpaca.secret_key")
        self._base_url = config.get_config("api.alpaca.base_url")
        self._feed = config.get_config("api.alpaca.websocket.market_data_feed", "iex")
        self._auto_reconnect = config.get_config("api.alpaca.websocket.auto_reconnect", True)
        self._heartbeat_interval = config.get_config("api.alpaca.websocket.heartbeat_interval", 30)
        self._max_reconnect_attempts = config.get_config("api.alpaca.websocket.max_reconnect_attempts", 10)
        self._reconnect_delay = config.get_config("api.alpaca.websocket.reconnect_delay", 5)
        
        # Callbacks
        self._market_data_callbacks: List[Callable] = []
        self._trade_update_callbacks: List[Callable] = []
        self._error_callbacks: List[Callable] = []
        
        # Connection tracking
        self._reconnect_attempts = 0
        self._last_heartbeat = None
        
        if not self._api_key or not self._secret_key:
            raise APIException("Alpaca API credentials are required for WebSocket connection")
        
        logger.info(f"AlpacaWebSocketClient initialized with feed: {self._feed}")
    
    async def connect(self) -> None:
        """
        Establish WebSocket connections for market data and trading updates.
        
        Raises:
            ConnectionException: If connection fails
        """
        try:
            logger.info("Connecting to Alpaca WebSocket streams...")
            
            # Initialize market data stream
            self._market_data_stream = StockDataStream(
                api_key=self._api_key,
                secret_key=self._secret_key,
                feed=self._feed,
                url_override=self._get_market_data_url()
            )
            
            # Initialize trading stream
            self._trading_stream = TradingStream(
                api_key=self._api_key,
                secret_key=self._secret_key,
                url_override=self._get_trading_url()
            )
            
            # Set up handlers
            self._setup_market_data_handlers()
            self._setup_trading_handlers()
            
            # Start streams
            await asyncio.gather(
                self._start_market_data_stream(),
                self._start_trading_stream()
            )
            
            self._is_connected = True
            self._reconnect_attempts = 0
            self._last_heartbeat = datetime.utcnow()
            
            logger.info("Successfully connected to Alpaca WebSocket streams")
            
        except Exception as e:
            logger.error(f"Failed to connect to Alpaca WebSocket: {str(e)}")
            await self._handle_connection_error(e)
            raise ConnectionException(f"WebSocket connection failed: {str(e)}")
    
    async def disconnect(self) -> None:
        """Disconnect from WebSocket streams."""
        try:
            logger.info("Disconnecting from Alpaca WebSocket streams...")
            
            if self._market_data_stream:
                await self._market_data_stream.stop_ws()
            
            if self._trading_stream:
                await self._trading_stream.stop_ws()
            
            self._is_connected = False
            self._subscribed_symbols.clear()
            
            logger.info("Successfully disconnected from Alpaca WebSocket streams")
            
        except Exception as e:
            logger.error(f"Error during WebSocket disconnection: {str(e)}")
    
    async def subscribe_to_symbol(self, symbol: str) -> None:
        """
        Subscribe to real-time market data for a symbol.
        
        Args:
            symbol: Stock symbol to subscribe to
        """
        try:
            if not self._is_connected:
                await self.connect()
            
            if symbol not in self._subscribed_symbols:
                logger.info(f"Subscribing to market data for {symbol}")
                
                # Subscribe to trades, quotes, and bars
                self._market_data_stream.subscribe_trades(self._on_trade, symbol)
                self._market_data_stream.subscribe_quotes(self._on_quote, symbol)
                self._market_data_stream.subscribe_bars(self._on_bar, symbol)
                
                self._subscribed_symbols.add(symbol)
                logger.info(f"Successfully subscribed to {symbol}")
            
        except Exception as e:
            logger.error(f"Failed to subscribe to {symbol}: {str(e)}")
            raise APIException(f"Subscription failed for {symbol}: {str(e)}")
    
    async def unsubscribe_from_symbol(self, symbol: str) -> None:
        """
        Unsubscribe from real-time market data for a symbol.
        
        Args:
            symbol: Stock symbol to unsubscribe from
        """
        try:
            if symbol in self._subscribed_symbols:
                logger.info(f"Unsubscribing from market data for {symbol}")
                
                # Unsubscribe from all data types
                self._market_data_stream.unsubscribe_trades(symbol)
                self._market_data_stream.unsubscribe_quotes(symbol)
                self._market_data_stream.unsubscribe_bars(symbol)
                
                self._subscribed_symbols.remove(symbol)
                logger.info(f"Successfully unsubscribed from {symbol}")
            
        except Exception as e:
            logger.error(f"Failed to unsubscribe from {symbol}: {str(e)}")
    
    def add_market_data_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Add callback for market data updates.
        
        Args:
            callback: Function to call when market data is received
        """
        self._market_data_callbacks.append(callback)
    
    def add_trade_update_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Add callback for trade updates.
        
        Args:
            callback: Function to call when trade updates are received
        """
        self._trade_update_callbacks.append(callback)
    
    def add_error_callback(self, callback: Callable[[Exception], None]) -> None:
        """
        Add callback for error handling.
        
        Args:
            callback: Function to call when errors occur
        """
        self._error_callbacks.append(callback)
    
    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._is_connected
    
    @property
    def subscribed_symbols(self) -> set:
        """Get currently subscribed symbols."""
        return self._subscribed_symbols.copy()
    
    def _setup_market_data_handlers(self) -> None:
        """Set up handlers for market data stream."""
        pass  # Handlers are set during subscription
    
    def _setup_trading_handlers(self) -> None:
        """Set up handlers for trading stream."""
        # Subscribe to trade updates
        self._trading_stream.subscribe_trade_updates(self._on_trade_update)
    
    async def _start_market_data_stream(self) -> None:
        """Start the market data WebSocket stream."""
        try:
            await self._market_data_stream.run()
        except Exception as e:
            logger.error(f"Market data stream error: {str(e)}")
            if self._auto_reconnect:
                await self._attempt_reconnect()
    
    async def _start_trading_stream(self) -> None:
        """Start the trading WebSocket stream."""
        try:
            await self._trading_stream.run()
        except Exception as e:
            logger.error(f"Trading stream error: {str(e)}")
            if self._auto_reconnect:
                await self._attempt_reconnect()
    
    async def _on_trade(self, trade_data: Any) -> None:
        """
        Handle incoming trade data.
        
        Args:
            trade_data: Trade data from Alpaca
        """
        try:
            data = {
                "type": "trade",
                "symbol": trade_data.symbol,
                "price": float(trade_data.price),
                "size": int(trade_data.size),
                "timestamp": trade_data.timestamp,
                "conditions": getattr(trade_data, 'conditions', [])
            }
            
            await self._notify_market_data_callbacks(data)
            
        except Exception as e:
            logger.error(f"Error processing trade data: {str(e)}")
            await self._notify_error_callbacks(e)
    
    async def _on_quote(self, quote_data: Any) -> None:
        """
        Handle incoming quote data.
        
        Args:
            quote_data: Quote data from Alpaca
        """
        try:
            data = {
                "type": "quote",
                "symbol": quote_data.symbol,
                "bid_price": float(quote_data.bid_price),
                "bid_size": int(quote_data.bid_size),
                "ask_price": float(quote_data.ask_price),
                "ask_size": int(quote_data.ask_size),
                "timestamp": quote_data.timestamp
            }
            
            await self._notify_market_data_callbacks(data)
            
        except Exception as e:
            logger.error(f"Error processing quote data: {str(e)}")
            await self._notify_error_callbacks(e)
    
    async def _on_bar(self, bar_data: Any) -> None:
        """
        Handle incoming bar data.
        
        Args:
            bar_data: Bar data from Alpaca
        """
        try:
            data = {
                "type": "bar",
                "symbol": bar_data.symbol,
                "open": float(bar_data.open),
                "high": float(bar_data.high),
                "low": float(bar_data.low),
                "close": float(bar_data.close),
                "volume": int(bar_data.volume),
                "timestamp": bar_data.timestamp,
                "timeframe": getattr(bar_data, 'timeframe', '1Min')
            }
            
            await self._notify_market_data_callbacks(data)
            
        except Exception as e:
            logger.error(f"Error processing bar data: {str(e)}")
            await self._notify_error_callbacks(e)
    
    async def _on_trade_update(self, trade_update: Any) -> None:
        """
        Handle incoming trade updates.
        
        Args:
            trade_update: Trade update from Alpaca
        """
        try:
            order_data = trade_update.order
            data = {
                "type": "trade_update",
                "event": trade_update.event,
                "order_id": order_data.id,
                "symbol": order_data.symbol,
                "side": order_data.side.value,
                "order_type": order_data.order_type.value,
                "status": order_data.status.value,
                "quantity": float(order_data.qty),
                "filled_quantity": float(order_data.filled_qty or 0),
                "filled_price": float(order_data.filled_avg_price or 0),
                "timestamp": trade_update.timestamp
            }
            
            await self._notify_trade_update_callbacks(data)
            
        except Exception as e:
            logger.error(f"Error processing trade update: {str(e)}")
            await self._notify_error_callbacks(e)
    
    async def _notify_market_data_callbacks(self, data: Dict[str, Any]) -> None:
        """Notify all market data callbacks."""
        for callback in self._market_data_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                logger.error(f"Error in market data callback: {str(e)}")
    
    async def _notify_trade_update_callbacks(self, data: Dict[str, Any]) -> None:
        """Notify all trade update callbacks."""
        for callback in self._trade_update_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                logger.error(f"Error in trade update callback: {str(e)}")
    
    async def _notify_error_callbacks(self, error: Exception) -> None:
        """Notify all error callbacks."""
        for callback in self._error_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(error)
                else:
                    callback(error)
            except Exception as e:
                logger.error(f"Error in error callback: {str(e)}")
    
    async def _attempt_reconnect(self) -> None:
        """Attempt to reconnect to WebSocket streams."""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error("Maximum reconnection attempts reached")
            return
        
        self._reconnect_attempts += 1
        logger.info(f"Attempting reconnection {self._reconnect_attempts}/{self._max_reconnect_attempts}")
        
        await asyncio.sleep(self._reconnect_delay)
        
        try:
            await self.disconnect()
            await self.connect()
            
            # Re-subscribe to symbols
            for symbol in self._subscribed_symbols.copy():
                await self.subscribe_to_symbol(symbol)
            
        except Exception as e:
            logger.error(f"Reconnection attempt {self._reconnect_attempts} failed: {str(e)}")
            if self._reconnect_attempts < self._max_reconnect_attempts:
                await self._attempt_reconnect()
    
    async def _handle_connection_error(self, error: Exception) -> None:
        """Handle connection errors."""
        self._is_connected = False
        await self._notify_error_callbacks(error)
        
        if self._auto_reconnect and self._reconnect_attempts < self._max_reconnect_attempts:
            await self._attempt_reconnect()
    
    def _get_market_data_url(self) -> Optional[str]:
        """Get market data WebSocket URL based on environment."""
        if "paper" in self._base_url.lower():
            return None  # Use default paper trading URL
        return None  # Use default live trading URL
    
    def _get_trading_url(self) -> Optional[str]:
        """Get trading WebSocket URL based on environment."""
        if "paper" in self._base_url.lower():
            return None  # Use default paper trading URL
        return None  # Use default live trading URL
