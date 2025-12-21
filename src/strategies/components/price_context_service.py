"""
Price Context Service

Handles market data aggregation, current price fetching, and snapshot fallback logic.
"""

import logging
from typing import Optional
from src.interfaces import IMarketDataProvider

logger = logging.getLogger(__name__)


class PriceContextService:
    """
    Service for fetching and managing market price data.
    
    Provides current price retrieval with fallback mechanisms.
    """
    
    def __init__(self, market_data: IMarketDataProvider):
        """
        Initialize price context service.
        
        Args:
            market_data: Market data provider interface
        """
        self.market_data = market_data
        logger.info("PriceContextService initialized")
    
    async def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current market price for symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Current price or None if unavailable
        """
        try:
            price = await self.market_data.get_current_price(symbol)
            
            if price and price > 0:
                logger.debug(f"Fetched price for {symbol}: ${price:.2f}")
                return price
            
            logger.warning(f"Invalid price for {symbol}: {price}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to fetch price for {symbol}: {e}")
            return None
    
    async def get_current_price_with_validation(
        self, 
        symbol: str,
        min_price: float = 0.01,
        max_price: Optional[float] = None
    ) -> Optional[float]:
        """
        Get current price with validation bounds.
        
        Args:
            symbol: Trading symbol
            min_price: Minimum acceptable price
            max_price: Maximum acceptable price (optional)
            
        Returns:
            Validated price or None
        """
        price = await self.get_current_price(symbol)
        
        if price is None:
            return None
        
        if price < min_price:
            logger.warning(f"Price ${price:.2f} below minimum ${min_price:.2f}")
            return None
        
        if max_price and price > max_price:
            logger.warning(f"Price ${price:.2f} above maximum ${max_price:.2f}")
            return None
        
        return price
