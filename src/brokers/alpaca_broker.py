"""
Alpaca Broker Implementation - Adapts existing Alpaca code to broker interfaces.
Wraps existing Alpaca functionality in universal broker interfaces.
"""

import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient

from ..core.broker_interfaces import (
    IBrokerProvider, ITradingClient, IMarketDataProvider, BrokerType, 
    BrokerCredentials, UniversalOrder, OrderResponse, Position, AccountInfo,
    MarketQuote, HistoricalBar, OrderStatus, OrderSide, OrderType, TimeInForce,
    Exchange
)
from ..exceptions import TradingException, MarketDataException
from ..core.logging_config import get_logger

# Import existing Alpaca components
from ..data.market_data import AlpacaMarketDataProvider
from ..trading.alpaca_account_provider import AlpacaAccountProvider

logger = get_logger(__name__)


class AlpacaTradingClient(ITradingClient):
    """Alpaca trading client implementation of universal interface."""
    
    def __init__(self):
        """Initialize Alpaca trading client."""
        self._client: Optional[TradingClient] = None
        self._account_provider: Optional[AlpacaAccountProvider] = None
    
    @property
    def broker_type(self) -> BrokerType:
        """Return Alpaca broker type."""
        return BrokerType.ALPACA
    
    async def initialize(self, credentials: BrokerCredentials) -> None:
        """Initialize Alpaca trading client with credentials."""
        try:
            # Create Alpaca trading client
            self._client = TradingClient(
                api_key=credentials.api_key,
                secret_key=credentials.secret_key,
                paper=credentials.environment == "paper",
                url_override=credentials.base_url
            )
            
            # Create account provider for enhanced functionality
            self._account_provider = AlpacaAccountProvider(self._client)
            
            logger.info("✅ Alpaca trading client initialized")
            
        except Exception as e:
            raise TradingException(f"Failed to initialize Alpaca trading client: {e}")
    
    def _convert_universal_order_to_alpaca(self, order: UniversalOrder) -> Dict[str, Any]:
        """Convert universal order to Alpaca order format."""
        alpaca_order = {
            "symbol": order.symbol,
            "qty": order.quantity,
            "side": order.side.value,
            "type": order.type.value,
            "time_in_force": order.time_in_force.value
        }
        
        # Add optional parameters
        if order.limit_price:
            alpaca_order["limit_price"] = order.limit_price
        
        if order.stop_price:
            alpaca_order["stop_price"] = order.stop_price
        
        if order.extended_hours:
            alpaca_order["extended_hours"] = order.extended_hours
        
        if order.client_order_id:
            alpaca_order["client_order_id"] = order.client_order_id
        
        # Add broker-specific parameters
        if order.broker_specific_params:
            alpaca_order.update(order.broker_specific_params)
        
        return alpaca_order
    
    def _convert_alpaca_order_to_response(self, alpaca_order) -> OrderResponse:
        """Convert Alpaca order response to universal format."""
        # Map Alpaca status to universal status
        status_mapping = {
            "new": OrderStatus.SUBMITTED,
            "pending_new": OrderStatus.PENDING,
            "filled": OrderStatus.FILLED,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "cancelled": OrderStatus.CANCELLED,
            "canceled": OrderStatus.CANCELLED,  # Alternative spelling
            "rejected": OrderStatus.REJECTED,
            "expired": OrderStatus.EXPIRED,
        }
        
        return OrderResponse(
            broker_order_id=str(alpaca_order.id),
            client_order_id=alpaca_order.client_order_id,
            symbol=alpaca_order.symbol,
            side=OrderSide(alpaca_order.side.lower()),
            status=status_mapping.get(alpaca_order.status.lower(), OrderStatus.UNKNOWN),
            quantity=float(alpaca_order.qty),
            filled_quantity=float(alpaca_order.filled_qty or 0),
            average_fill_price=float(alpaca_order.filled_avg_price) if alpaca_order.filled_avg_price else None,
            submitted_at=alpaca_order.submitted_at,
            filled_at=alpaca_order.filled_at,
            broker_type=BrokerType.ALPACA,
            raw_response=alpaca_order._raw  # Store raw response for debugging
        )
    
    def _convert_alpaca_position_to_universal(self, alpaca_position) -> Position:
        """Convert Alpaca position to universal format."""
        return Position(
            symbol=alpaca_position.symbol,
            quantity=float(alpaca_position.qty),
            average_cost=float(alpaca_position.avg_entry_price or 0),
            market_value=float(alpaca_position.market_value or 0),
            unrealized_pnl=float(alpaca_position.unrealized_pl or 0),
            realized_pnl=float(alpaca_position.realized_pl or 0),
            broker_type=BrokerType.ALPACA
        )
    
    async def submit_order(self, order: UniversalOrder) -> OrderResponse:
        """Submit order to Alpaca."""
        if not self._client:
            raise TradingException("Alpaca client not initialized")
        
        try:
            alpaca_order_dict = self._convert_universal_order_to_alpaca(order)
            
            # Submit order using thread executor to avoid blocking
            alpaca_order = await asyncio.get_event_loop().run_in_executor(
                None, self._client.submit_order, **alpaca_order_dict
            )
            
            response = self._convert_alpaca_order_to_response(alpaca_order)
            
            logger.info(f"✅ Order submitted to Alpaca: {order.symbol} {order.side.value} {order.quantity}")
            return response
            
        except Exception as e:
            logger.error(f"❌ Failed to submit order to Alpaca: {e}")
            raise TradingException(f"Alpaca order submission failed: {e}")
    
    async def get_order_status(self, broker_order_id: str) -> OrderResponse:
        """Get order status from Alpaca."""
        if not self._client:
            raise TradingException("Alpaca client not initialized")
        
        try:
            alpaca_order = await asyncio.get_event_loop().run_in_executor(
                None, self._client.get_order_by_id, broker_order_id
            )
            
            return self._convert_alpaca_order_to_response(alpaca_order)
            
        except Exception as e:
            logger.error(f"❌ Failed to get order status from Alpaca: {e}")
            raise TradingException(f"Alpaca order status retrieval failed: {e}")
    
    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel order in Alpaca."""
        if not self._client:
            raise TradingException("Alpaca client not initialized")
        
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, self._client.cancel_order_by_id, broker_order_id
            )
            
            logger.info(f"✅ Order cancelled in Alpaca: {broker_order_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to cancel order in Alpaca: {e}")
            return False
    
    async def get_positions(self) -> List[Position]:
        """Get all positions from Alpaca."""
        if not self._client:
            raise TradingException("Alpaca client not initialized")
        
        try:
            alpaca_positions = await asyncio.get_event_loop().run_in_executor(
                None, self._client.get_all_positions
            )
            
            positions = [
                self._convert_alpaca_position_to_universal(pos) 
                for pos in alpaca_positions
            ]
            
            return positions
            
        except Exception as e:
            logger.error(f"❌ Failed to get positions from Alpaca: {e}")
            raise TradingException(f"Alpaca positions retrieval failed: {e}")
    
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get position for specific symbol from Alpaca."""
        if not self._client:
            raise TradingException("Alpaca client not initialized")
        
        try:
            alpaca_position = await asyncio.get_event_loop().run_in_executor(
                None, self._client.get_open_position, symbol
            )
            
            return self._convert_alpaca_position_to_universal(alpaca_position)
            
        except Exception as e:
            # Position not found is normal - return None
            if "position not found" in str(e).lower():
                return None
            
            logger.error(f"❌ Failed to get position for {symbol} from Alpaca: {e}")
            raise TradingException(f"Alpaca position retrieval failed: {e}")
    
    async def get_account_info(self) -> AccountInfo:
        """Get account information from Alpaca."""
        if not self._account_provider:
            raise TradingException("Alpaca account provider not initialized")
        
        try:
            alpaca_account = await self._account_provider.get_account()
            
            return AccountInfo(
                account_id=alpaca_account.id,
                broker_type=BrokerType.ALPACA,
                buying_power=float(alpaca_account.buying_power or 0),
                equity=float(alpaca_account.equity or 0),
                cash=float(alpaca_account.cash or 0),
                portfolio_value=float(alpaca_account.portfolio_value or 0),
                day_trading_buying_power=float(alpaca_account.daytrading_buying_power or 0),
                pattern_day_trader=alpaca_account.pattern_day_trader,
                trade_suspended_by_user=alpaca_account.trade_suspended_by_user,
                trading_blocked=alpaca_account.trading_blocked,
                raw_account_data=alpaca_account._raw
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to get account info from Alpaca: {e}")
            raise TradingException(f"Alpaca account retrieval failed: {e}")
    
    async def close(self) -> None:
        """Close Alpaca trading client."""
        if self._client:
            self._client = None
            logger.info("✅ Alpaca trading client closed")


class AlpacaMarketDataProviderAdapter(IMarketDataProvider):
    """Adapter for existing AlpacaMarketDataProvider to universal interface."""
    
    def __init__(self):
        """Initialize Alpaca market data adapter."""
        self._provider: Optional[AlpacaMarketDataProvider] = None
    
    @property
    def broker_type(self) -> BrokerType:
        """Return Alpaca broker type."""
        return BrokerType.ALPACA
    
    async def initialize(self, config, credentials: BrokerCredentials) -> None:
        """Initialize Alpaca market data provider."""
        try:
            self._provider = AlpacaMarketDataProvider(config)
            logger.info("✅ Alpaca market data provider initialized")
        except Exception as e:
            raise MarketDataException(f"Failed to initialize Alpaca market data: {e}")
    
    async def get_current_price(self, symbol: str) -> float:
        """Get current price from Alpaca."""
        if not self._provider:
            raise MarketDataException("Alpaca market data provider not initialized")
        
        return await self._provider.get_current_price(symbol)
    
    async def get_quote(self, symbol: str) -> MarketQuote:
        """Get current quote from Alpaca."""
        if not self._provider:
            raise MarketDataException("Alpaca market data provider not initialized")
        
        try:
            # Use existing provider's quote functionality
            # This is simplified - actual implementation would use Alpaca's quote API
            current_price = await self._provider.get_current_price(symbol)
            
            return MarketQuote(
                symbol=symbol,
                bid_price=current_price * 0.999,  # Simplified spread
                ask_price=current_price * 1.001,
                bid_size=100,
                ask_size=100,
                last_price=current_price,
                last_size=100,
                timestamp=datetime.now(),
                broker_type=BrokerType.ALPACA
            )
            
        except Exception as e:
            raise MarketDataException(f"Failed to get quote for {symbol}: {e}")
    
    async def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[HistoricalBar]:
        """Get historical data from Alpaca."""
        if not self._provider:
            raise MarketDataException("Alpaca market data provider not initialized")
        
        try:
            # Use existing provider's historical data functionality
            bars = await self._provider.get_historical_data(
                symbol, timeframe, start_time, end_time, limit
            )
            
            # Convert to universal format
            universal_bars = []
            for bar in bars:
                universal_bars.append(HistoricalBar(
                    symbol=symbol,
                    timestamp=bar.timestamp,
                    open_price=float(bar.open),
                    high_price=float(bar.high),
                    low_price=float(bar.low),
                    close_price=float(bar.close),
                    volume=int(bar.volume),
                    vwap=float(bar.vwap) if hasattr(bar, 'vwap') and bar.vwap else None,
                    broker_type=BrokerType.ALPACA
                ))
            
            return universal_bars
            
        except Exception as e:
            raise MarketDataException(f"Failed to get historical data for {symbol}: {e}")
    
    async def close(self) -> None:
        """Close Alpaca market data provider."""
        if self._provider:
            await self._provider.close()
            logger.info("✅ Alpaca market data provider closed")


class AlpacaBrokerProvider(IBrokerProvider):
    """Complete Alpaca broker provider implementation."""
    
    def __init__(self):
        """Initialize Alpaca broker provider."""
        self._trading_client = AlpacaTradingClient()
        self._market_data_provider = AlpacaMarketDataProviderAdapter()
        self._credentials: Optional[BrokerCredentials] = None
        self._config = None
    
    @property
    def broker_type(self) -> BrokerType:
        """Return Alpaca broker type."""
        return BrokerType.ALPACA
    
    @property
    def trading_client(self) -> ITradingClient:
        """Get Alpaca trading client."""
        return self._trading_client
    
    @property
    def market_data_provider(self) -> IMarketDataProvider:
        """Get Alpaca market data provider."""
        return self._market_data_provider
    
    async def initialize(self, credentials: BrokerCredentials) -> None:
        """Initialize Alpaca broker with credentials."""
        from ..core.configuration import ConfigurationManager
        
        try:
            self._credentials = credentials
            self._config = ConfigurationManager()
            
            # Initialize trading client
            await self._trading_client.initialize(credentials)
            
            # Initialize market data provider
            await self._market_data_provider.initialize(self._config, credentials)
            
            logger.info("✅ Alpaca broker provider fully initialized")
            
        except Exception as e:
            raise TradingException(f"Failed to initialize Alpaca broker: {e}")
    
    async def health_check(self) -> bool:
        """Check if Alpaca connection is healthy."""
        try:
            # Simple health check - try to get account info
            await self._trading_client.get_account_info()
            return True
        except Exception as e:
            logger.debug(f"Alpaca health check failed: {e}")
            return False
    
    async def close(self) -> None:
        """Close all Alpaca connections."""
        await self._trading_client.close()
        await self._market_data_provider.close()
        logger.info("✅ Alpaca broker provider closed")
    
    def supports_extended_hours(self) -> bool:
        """Check if Alpaca supports extended hours trading."""
        return True
    
    def supports_symbol(self, symbol: str) -> bool:
        """Check if Alpaca supports trading this symbol."""
        # Basic check - Alpaca supports most US equities
        return len(symbol) <= 5 and symbol.isalpha()
    
    def get_supported_order_types(self) -> List[OrderType]:
        """Get Alpaca supported order types."""
        return [
            OrderType.MARKET,
            OrderType.LIMIT,
            OrderType.STOP,
            OrderType.STOP_LIMIT,
            OrderType.TRAILING_STOP
        ]
    
    def get_supported_time_in_force(self) -> List[TimeInForce]:
        """Get Alpaca supported time in force options."""
        return [
            TimeInForce.DAY,
            TimeInForce.GTC,
            TimeInForce.IOC,
            TimeInForce.FOK
        ]
    
    def get_supported_exchanges(self) -> List[Exchange]:
        """Get exchanges supported by Alpaca."""
        return [Exchange.NYSE, Exchange.NASDAQ]
    
    def supports_exchange(self, exchange: Exchange) -> bool:
        """Check if Alpaca supports trading on this exchange."""
        return exchange in [Exchange.NYSE, Exchange.NASDAQ]
    
    async def get_symbol_exchange(self, symbol: str) -> Optional[Exchange]:
        """Get the exchange where this symbol is traded by Alpaca."""
        # For Alpaca, we can determine exchange by querying asset info
        try:
            if hasattr(self, '_trading_client') and self._trading_client:
                # In practice, would use Alpaca API to get asset info
                # For now, use simple heuristic
                if symbol in ['SPY', 'QQQ', 'AAPL', 'MSFT', 'GOOGL']:
                    return Exchange.NASDAQ
                else:
                    return Exchange.NYSE
        except Exception:
            pass
        
        # Default to NYSE for unknown symbols
        return Exchange.NYSE