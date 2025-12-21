"""
Tastytrade implementation of the account provider interface.

Updated for tastytrade v11.x API.
"""
from typing import List, Optional
from tastytrade import Account
from src.broker.interfaces import IBrokerAccountProvider
from src.broker.tastytrade_broker.session_manager import TastytradeSessionManager
from src.broker.tastytrade_broker.account_mixin import TastytradeAccountMixin
from src.interfaces import Position
from src.exceptions import BrokerAPIException, BrokerPermissionException
from src.core.logging_config import get_logger
from src.utils import run_blocking

logger = get_logger(__name__)

class TastytradeAccountProvider(TastytradeAccountMixin, IBrokerAccountProvider):
    """
    Tastytrade implementation of the account provider interface.
    
    This class handles fetching account information such as equity, buying power,
    cash, and open positions from the Tastytrade API. It manages the retrieval
    of the specific account to use (e.g. based on account number in config).
    
    Inherits account retrieval functionality from TastytradeAccountMixin.
    """
    
    def __init__(self, session_manager: TastytradeSessionManager, account_number: Optional[str] = None):
        """
        Initialize the Tastytrade account provider.
        
        Args:
            session_manager: Manager for Tastytrade API sessions.
            account_number: Specific account number to use. If None, uses the first available account.
        """
        TastytradeAccountMixin.__init__(self, session_manager, account_number)
        
    async def get_account_value(self) -> float:
        """
        Get current account equity value.
        
        Returns:
            float: Total account equity (net liquid value).
            
        Raises:
            BrokerAPIException: If account data cannot be retrieved.
        """
        try:
            balances = await self._get_balances()
            return float(balances.net_liquidating_value or 0.0)
        except Exception as e:
            logger.error(f"Error getting account value from Tastytrade: {str(e)}")
            raise BrokerAPIException(f"Failed to get account value: {str(e)}")
    
    async def get_buying_power(self) -> float:
        """
        Get available buying power.
        
        Returns:
            float: Available buying power for new orders (equity buying power).
            
        Raises:
            BrokerAPIException: If account data cannot be retrieved.
        """
        try:
            balances = await self._get_balances()
            return float(balances.equity_buying_power or 0.0)
        except Exception as e:
            logger.error(f"Error getting buying power from Tastytrade: {str(e)}")
            raise BrokerAPIException(f"Failed to get buying power: {str(e)}")
    
    async def get_cash(self) -> float:
        """
        Get available cash.
        
        Returns:
            float: Settled cash available for withdrawal or trading.
            
        Raises:
            BrokerAPIException: If account data cannot be retrieved.
        """
        try:
            balances = await self._get_balances()
            return float(balances.cash_balance or 0.0)
        except Exception as e:
            logger.error(f"Error getting cash from Tastytrade: {str(e)}")
            raise BrokerAPIException(f"Failed to get cash: {str(e)}")
            
    async def get_positions(self) -> List[Position]:
        """
        Get all open positions from Tastytrade.
        
        Returns:
            List[Position]: List of open positions converted to domain objects.
            
        Raises:
            BrokerAPIException: If positions cannot be retrieved.
        """
        try:
            account = await self._get_account_object()
            session = await self._session_manager.get_session()
            
            # Fetch positions using the SDK
            tt_positions = await run_blocking(account.get_positions, session)
            
            positions = []
            for p in tt_positions:
                # Tastytrade positions are detailed. We need to aggregate or map them correctly.
                # This simple mapping assumes stock/equity positions. 
                # Options would need more complex handling (symbol parsing etc).
                
                # Check if it's an equity position
                instrument_type = str(p.instrument_type) if p.instrument_type else ''
                if instrument_type == 'Equity' or instrument_type == 'InstrumentType.EQUITY':
                    mark_price = float(p.mark_price) if p.mark_price else 0.0
                    avg_price = float(p.average_open_price) if p.average_open_price else 0.0
                    qty = float(p.quantity) if p.quantity else 0.0
                    
                    pos = Position(
                        symbol=p.symbol,
                        quantity=qty,
                        avg_price=avg_price,
                        current_price=mark_price,
                        unrealized_pnl=qty * (mark_price - avg_price),
                        realized_pnl=float(p.realized_day_gain) if p.realized_day_gain else 0.0,
                        broker="tastytrade"
                    )
                    positions.append(pos)
                # TODO: Add support for Options/Futures if needed
                
            return positions
        except Exception as e:
            logger.error(f"Error getting positions from Tastytrade: {str(e)}")
            raise BrokerAPIException(f"Failed to get positions: {str(e)}")

    # Note: _get_account_object is inherited from TastytradeAccountMixin

    async def _get_balances(self):
        """
        Get account balances.
        
        Returns:
            AccountBalance: Pydantic model with balance information.
        """
        account = await self._get_account_object()
        session = await self._session_manager.get_session()
        
        balances = await run_blocking(account.get_balances, session)
        return balances
