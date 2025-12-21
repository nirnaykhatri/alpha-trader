"""
Alpaca Account Provider
Implements account information access using Alpaca Trading API.
"""

import asyncio
from typing import Optional
from alpaca.trading.client import TradingClient
from src.interfaces import IAccountProvider
from src.core.logging_config import get_logger
from src.utils import run_blocking

logger = get_logger(__name__)


class AlpacaAccountProvider(IAccountProvider):
    """Account provider implementation using Alpaca Trading API."""
    
    def __init__(self, trading_client: TradingClient):
        """
        Initialize the Alpaca account provider.
        
        Args:
            trading_client: Alpaca trading client instance
        """
        self.trading_client = trading_client
        self._cached_account = None
        self._cache_timestamp = None
        self._cache_duration = 30  # Cache account data for 30 seconds
        
        logger.info("AlpacaAccountProvider initialized")
    
    async def get_account_value(self) -> float:
        """Get current account equity value."""
        try:
            logger.info("Fetching account value from Alpaca API...")
            account = await self._get_account()
            # Alpaca returns equity as a string, convert to float
            equity = float(account.equity)
            logger.info(f"✅ Real account equity from Alpaca: ${equity:,.2f}")
            return equity
            
        except Exception as e:
            logger.error(f"❌ Error getting account value from Alpaca API: {str(e)}")
            logger.warning("🚨 Using hardcoded fallback - this should NOT happen in production!")
            # Fallback to configured value
            return 100000.0
    
    async def get_buying_power(self) -> float:
        """Get available buying power."""
        try:
            logger.info("Fetching buying power from Alpaca API...")
            account = await self._get_account()
            buying_power = float(account.buying_power)
            logger.info(f"✅ Real buying power from Alpaca: ${buying_power:,.2f}")
            
            # Also log other account details for debugging
            logger.info(f"📊 Account summary - Equity: ${float(account.equity):,.2f}, "
                       f"Portfolio: ${float(account.portfolio_value):,.2f}, "
                       f"Cash: ${float(account.cash):,.2f}")
            
            return buying_power
            
        except Exception as e:
            logger.error(f"❌ Error getting buying power from Alpaca API: {str(e)}")
            logger.warning("🚨 Using fallback value - this should NOT happen in production!")
            # Fallback to account value
            return await self.get_account_value()
    
    async def get_portfolio_value(self) -> float:
        """Get total portfolio value including positions."""
        try:
            account = await self._get_account()
            portfolio_value = float(account.portfolio_value)
            logger.debug(f"Portfolio value: ${portfolio_value:,.2f}")
            return portfolio_value
            
        except Exception as e:
            logger.error(f"Error getting portfolio value: {str(e)}")
            return await self.get_account_value()
    
    async def get_cash(self) -> float:
        """Get available cash (not including margin)."""
        try:
            logger.debug("Fetching cash from Alpaca API...")
            account = await self._get_account()
            cash = float(account.cash)
            logger.debug(f"Cash available: ${cash:,.2f}")
            return cash
            
        except Exception as e:
            logger.error(f"Error getting cash: {str(e)}")
            # Fallback to half of account value (conservative estimate)
            account_value = await self.get_account_value()
            return account_value * 0.5
    
    async def get_actual_position(self, symbol: str) -> Optional[float]:
        """Get actual position quantity from Alpaca for a symbol."""
        try:
            logger.debug(f"Fetching actual position for {symbol} from Alpaca...")
            positions = await run_blocking(self.trading_client.get_all_positions)
            
            for position in positions:
                if position.symbol == symbol:
                    quantity = float(position.qty)
                    logger.debug(f"✅ Alpaca position for {symbol}: {quantity}")
                    return quantity
            
            logger.debug(f"No position found for {symbol} in Alpaca")
            return 0.0
            
        except Exception as e:
            logger.error(f"Error getting actual position for {symbol}: {str(e)}")
            return None
    
    async def get_positions(self) -> list:
        """
        Get all open positions from Alpaca.
        
        Returns:
            List[Position]: List of open positions.
        """
        try:
            from src.interfaces import Position
            from datetime import datetime
            
            logger.debug("Fetching all positions from Alpaca...")
            alpaca_positions = await run_blocking(self.trading_client.get_all_positions)
            
            positions = []
            for p in alpaca_positions:
                pos = Position(
                    symbol=p.symbol,
                    quantity=float(p.qty),
                    avg_price=float(p.avg_entry_price),
                    current_price=float(p.current_price),
                    unrealized_pnl=float(p.unrealized_pl or 0),
                    realized_pnl=0.0,  # Alpaca doesn't provide realized PnL in positions endpoint
                    created_at=datetime.utcnow(),
                    broker="alpaca"
                )
                positions.append(pos)
                
            return positions
            
        except Exception as e:
            logger.error(f"Error getting positions from Alpaca: {str(e)}")
            return []
    
    async def _get_account(self):
        """Get account information with caching."""
        import time
        
        current_time = time.time()
        
        # Check if we have cached data that's still fresh
        if (self._cached_account is not None and 
            self._cache_timestamp is not None and 
            current_time - self._cache_timestamp < self._cache_duration):
            return self._cached_account
        
        # Fetch fresh account data
        try:
            logger.info(f"🔄 Fetching fresh account data from Alpaca API...")
            account = await run_blocking(self.trading_client.get_account)
            
            # Update cache
            self._cached_account = account
            self._cache_timestamp = current_time
            
            logger.info(f"✅ Account data refreshed successfully!")
            logger.info(f"📊 Account Details:")
            logger.info(f"   💰 Equity: ${float(account.equity):,.2f}")
            logger.info(f"   💵 Cash: ${float(account.cash):,.2f}")
            logger.info(f"   🛒 Buying Power: ${float(account.buying_power):,.2f}")
            logger.info(f"   📈 Portfolio Value: ${float(account.portfolio_value):,.2f}")
            
            return account
            
        except Exception as e:
            logger.error(f"Failed to fetch account data: {str(e)}")
            raise
