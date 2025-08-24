"""
Mock Broker Implementation - For testing and development.
Provides simulated broker functionality for testing multi-broker scenarios.
"""

import asyncio
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import random

from ..core.broker_interfaces import (
    IBrokerProvider, ITradingClient, IMarketDataProvider, BrokerType, 
    BrokerCredentials, UniversalOrder, OrderResponse, Position, AccountInfo,
    MarketQuote, HistoricalBar, OrderStatus, OrderSide, OrderType, TimeInForce,
    Exchange
)
from ..exceptions import TradingException, MarketDataException
from ..core.logging_config import get_logger

logger = get_logger(__name__)


class MockTradingClient(ITradingClient):
    """Mock trading client for testing."""
    
    def __init__(self):
        """Initialize mock trading client."""
        self._orders: Dict[str, OrderResponse] = {}
        self._positions: Dict[str, Position] = {}
        self._account = AccountInfo(
            account_id="mock_account_123",
            broker_type=BrokerType.MOCK,
            buying_power=100000.0,
            equity=100000.0,
            cash=100000.0,
            portfolio_value=100000.0
        )
        self._order_counter = 1
    
    @property
    def broker_type(self) -> BrokerType:
        """Return mock broker type."""
        return BrokerType.MOCK
    
    async def submit_order(self, order: UniversalOrder) -> OrderResponse:
        """Submit mock order."""
        order_id = f"mock_order_{self._order_counter}"
        self._order_counter += 1
        
        # Simulate order submission
        response = OrderResponse(
            broker_order_id=order_id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side,
            status=OrderStatus.SUBMITTED,
            quantity=order.quantity,
            submitted_at=datetime.now(),
            broker_type=BrokerType.MOCK
        )
        
        self._orders[order_id] = response
        
        # Simulate order filling after short delay
        asyncio.create_task(self._simulate_order_fill(order_id, order))
        
        logger.info(f"✅ Mock order submitted: {order.symbol} {order.side.value} {order.quantity}")
        return response
    
    async def _simulate_order_fill(self, order_id: str, order: UniversalOrder) -> None:
        """Simulate order filling with delay."""
        await asyncio.sleep(0.5)  # Simulate execution delay
        
        if order_id in self._orders:
            response = self._orders[order_id]
            response.status = OrderStatus.FILLED
            response.filled_quantity = order.quantity
            response.average_fill_price = order.limit_price or (100.0 + random.uniform(-5, 5))
            response.filled_at = datetime.now()
            
            # Update position
            self._update_position(order.symbol, order.side, order.quantity, response.average_fill_price)
    
    def _update_position(self, symbol: str, side: OrderSide, quantity: float, price: float) -> None:
        """Update mock position after order fill."""
        if symbol not in self._positions:
            self._positions[symbol] = Position(
                symbol=symbol,
                quantity=0.0,
                average_cost=0.0,
                market_value=0.0,
                unrealized_pnl=0.0,
                broker_type=BrokerType.MOCK
            )
        
        position = self._positions[symbol]
        
        if side == OrderSide.BUY:
            # Calculate new average cost
            total_cost = (position.quantity * position.average_cost) + (quantity * price)
            position.quantity += quantity
            position.average_cost = total_cost / position.quantity if position.quantity > 0 else price
        else:  # SELL
            position.quantity -= quantity
            if position.quantity <= 0:
                position.quantity = 0.0
                position.average_cost = 0.0
        
        # Update market value (use current "price" as market price)
        position.market_value = position.quantity * price
        position.unrealized_pnl = (price - position.average_cost) * position.quantity
    
    async def get_order_status(self, broker_order_id: str) -> OrderResponse:
        """Get mock order status."""
        if broker_order_id not in self._orders:
            raise TradingException(f"Order not found: {broker_order_id}")
        
        return self._orders[broker_order_id]
    
    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel mock order."""
        if broker_order_id in self._orders:
            self._orders[broker_order_id].status = OrderStatus.CANCELLED
            logger.info(f"✅ Mock order cancelled: {broker_order_id}")
            return True
        return False
    
    async def get_positions(self) -> List[Position]:
        """Get all mock positions."""
        return [pos for pos in self._positions.values() if pos.quantity != 0]
    
    async def get_position(self, symbol: str) -> Optional[Position]:
        """Get mock position for symbol."""
        return self._positions.get(symbol) if symbol in self._positions and self._positions[symbol].quantity != 0 else None
    
    async def get_account_info(self) -> AccountInfo:
        """Get mock account info."""
        return self._account
    
    async def close(self) -> None:
        """Close mock trading client."""
        logger.info("✅ Mock trading client closed")


class MockMarketDataProvider(IMarketDataProvider):
    """Mock market data provider for testing."""
    
    def __init__(self):
        """Initialize mock market data provider."""
        self._base_prices = {
            "AAPL": 150.0,
            "GOOGL": 2800.0,
            "MSFT": 300.0,
            "TSLA": 200.0,
            "SPY": 450.0,
            "QQQ": 350.0
        }
    
    @property
    def broker_type(self) -> BrokerType:
        """Return mock broker type."""
        return BrokerType.MOCK
    
    async def get_current_price(self, symbol: str) -> float:
        """Get mock current price."""
        base_price = self._base_prices.get(symbol, 100.0)
        # Add some random variation
        return base_price * (1 + random.uniform(-0.02, 0.02))
    
    async def get_quote(self, symbol: str) -> MarketQuote:
        """Get mock quote."""
        current_price = await self.get_current_price(symbol)
        spread = current_price * 0.001  # 0.1% spread
        
        return MarketQuote(
            symbol=symbol,
            bid_price=current_price - spread/2,
            ask_price=current_price + spread/2,
            bid_size=100,
            ask_size=100,
            last_price=current_price,
            last_size=100,
            timestamp=datetime.now(),
            broker_type=BrokerType.MOCK
        )
    
    async def get_historical_data(
        self,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[HistoricalBar]:
        """Get mock historical data."""
        if end_time is None:
            end_time = datetime.now()
        
        bars = []
        base_price = self._base_prices.get(symbol, 100.0)
        current_time = start_time
        
        # Generate mock bars
        bar_count = min(limit or 100, 100)  # Limit to 100 bars
        for i in range(bar_count):
            if current_time >= end_time:
                break
            
            # Generate realistic OHLC data
            open_price = base_price * (1 + random.uniform(-0.01, 0.01))
            high_price = open_price * (1 + random.uniform(0, 0.02))
            low_price = open_price * (1 - random.uniform(0, 0.02))
            close_price = open_price * (1 + random.uniform(-0.015, 0.015))
            volume = random.randint(10000, 1000000)
            
            bars.append(HistoricalBar(
                symbol=symbol,
                timestamp=current_time,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
                broker_type=BrokerType.MOCK
            ))
            
            # Advance time based on timeframe
            if timeframe == "1Min":
                current_time += timedelta(minutes=1)
            elif timeframe == "5Min":
                current_time += timedelta(minutes=5)
            elif timeframe == "1Hour":
                current_time += timedelta(hours=1)
            else:
                current_time += timedelta(days=1)
        
        return bars
    
    async def close(self) -> None:
        """Close mock market data provider."""
        logger.info("✅ Mock market data provider closed")


class MockBrokerProvider(IBrokerProvider):
    """Complete mock broker provider for testing."""
    
    def __init__(self):
        """Initialize mock broker provider."""
        self._trading_client = MockTradingClient()
        self._market_data_provider = MockMarketDataProvider()
    
    @property
    def broker_type(self) -> BrokerType:
        """Return mock broker type."""
        return BrokerType.MOCK
    
    @property
    def trading_client(self) -> ITradingClient:
        """Get mock trading client."""
        return self._trading_client
    
    @property
    def market_data_provider(self) -> IMarketDataProvider:
        """Get mock market data provider."""
        return self._market_data_provider
    
    async def initialize(self, credentials: BrokerCredentials) -> None:
        """Initialize mock broker."""
        logger.info("✅ Mock broker provider initialized")
    
    async def health_check(self) -> bool:
        """Mock health check - always healthy."""
        return True
    
    async def close(self) -> None:
        """Close mock broker."""
        await self._trading_client.close()
        await self._market_data_provider.close()
        logger.info("✅ Mock broker provider closed")
    
    def supports_extended_hours(self) -> bool:
        """Mock supports extended hours."""
        return True
    
    def supports_symbol(self, symbol: str) -> bool:
        """Mock supports all symbols."""
        return True
    
    def get_supported_order_types(self) -> List[OrderType]:
        """Get mock supported order types."""
        return [OrderType.MARKET, OrderType.LIMIT]
    
    def get_supported_time_in_force(self) -> List[TimeInForce]:
        """Get mock supported time in force."""
        return [TimeInForce.DAY, TimeInForce.GTC]
    
    def get_supported_exchanges(self) -> List[Exchange]:
        """Get exchanges supported by mock broker."""
        return list(Exchange)  # Support all exchanges for testing
    
    def supports_exchange(self, exchange: Exchange) -> bool:
        """Mock broker supports all exchanges."""
        return True
    
    async def get_symbol_exchange(self, symbol: str) -> Optional[Exchange]:
        """Get the exchange for a symbol in mock broker."""
        # Simple mapping for testing
        if symbol.startswith('BTC') or symbol.startswith('ETH'):
            return Exchange.CRYPTO
        elif symbol in ['EURUSD', 'GBPUSD', 'USDJPY']:
            return Exchange.FOREX
        else:
            return Exchange.NYSE  # Default