"""Tastytrade Account Mixin.

Provides shared account retrieval functionality for Tastytrade components.
This mixin eliminates code duplication between order_executor.py and account_provider.py.

Usage:
    class MyClass(TastytradeAccountMixin):
        def __init__(self, session_manager, account_number):
            TastytradeAccountMixin.__init__(self, session_manager, account_number)

        async def my_method(self):
            account = await self._get_account_object()
"""
import asyncio
from typing import Optional

from tastytrade import Account

from src.broker.tastytrade_broker.session_manager import TastytradeSessionManager
from src.exceptions import BrokerPermissionException
from src.core.logging_config import get_logger
from src.utils import run_blocking

logger = get_logger(__name__)


class TastytradeAccountMixin:
    """
    Mixin class providing shared Tastytrade account retrieval functionality.
    
    This mixin encapsulates the common pattern of:
    1. Getting a session from the session manager
    2. Retrieving account object (by number or first available)
    3. Caching the account object for subsequent calls
    
    Classes using this mixin must have:
    - _session_manager: TastytradeSessionManager instance
    - _account_number: Optional[str] for specific account selection
    
    Thread Safety:
        The cached account object is stored per-instance.
        This mixin is designed for asyncio and is not thread-safe.
        
    Example:
        >>> class MyExecutor(TastytradeAccountMixin):
        ...     def __init__(self, session_manager, account_number=None):
        ...         TastytradeAccountMixin.__init__(self, session_manager, account_number)
        ...     
        ...     async def do_something(self):
        ...         account = await self._get_account_object()
        ...         # Use account...
    """
    
    def __init__(
        self, 
        session_manager: TastytradeSessionManager, 
        account_number: Optional[str] = None
    ):
        """
        Initialize the account mixin.
        
        Args:
            session_manager: Manager for Tastytrade API sessions.
            account_number: Specific account number to use. If None,
                           the first available account will be used.
        """
        self._session_manager = session_manager
        self._account_number = account_number
        self._cached_account_obj: Optional[Account] = None
        self._account_lock = asyncio.Lock()  # Prevents race condition during account retrieval

    async def _get_account_object(self) -> Account:
        """
        Get the Tastytrade Account object.
        
        Retrieves the account object, caching it for subsequent calls.
        If a specific account_number was provided during initialization,
        that account is retrieved. Otherwise, the first available account
        is used.
        
        Uses a lock to prevent race conditions during concurrent access.
        
        Returns:
            Account: The Tastytrade Account object.
            
        Raises:
            BrokerPermissionException: If no accounts are found or account is invalid.
            BrokerAPIException: If account retrieval fails.
        """
        async with self._account_lock:
            if self._cached_account_obj:
                return self._cached_account_obj
                
            session = await self._session_manager.get_session()
            
            if self._account_number:
                # Get specific account by number
                logger.debug(f"Retrieving Tastytrade account: {self._account_number}")
                result = await run_blocking(
                    Account.get, session, self._account_number
                )
                # Validate result is an Account instance
                if result is None:
                    raise BrokerPermissionException(
                        f"Tastytrade account '{self._account_number}' not found."
                    )
                if not isinstance(result, Account):
                    logger.warning(
                        f"Unexpected account retrieval result type: {type(result).__name__}"
                    )
                self._cached_account_obj = result
            else:
                # Get all accounts and pick the first one
                logger.debug("Retrieving first available Tastytrade account")
                accounts = await run_blocking(Account.get, session)
                
                # Handle None result
                if accounts is None:
                    raise BrokerPermissionException(
                        "Tastytrade account retrieval returned None. "
                        "Check API credentials and permissions."
                    )
                
                if isinstance(accounts, list):
                    if not accounts:
                        raise BrokerPermissionException("No Tastytrade accounts found.")
                    self._cached_account_obj = accounts[0]
                    logger.debug(f"Using account: {self._cached_account_obj.account_number}")
                elif isinstance(accounts, Account):
                    # Single account returned directly
                    self._cached_account_obj = accounts
                else:
                    # Unexpected type - log warning but attempt to use
                    logger.warning(
                        f"Unexpected accounts result type: {type(accounts).__name__}. "
                        "Attempting to use as-is."
                    )
                    self._cached_account_obj = accounts
                
            return self._cached_account_obj

    def _clear_account_cache(self) -> None:
        """
        Clear the cached account object.
        
        Call this method if you need to force a fresh account
        retrieval (e.g., after detecting stale account data).
        """
        self._cached_account_obj = None
        logger.debug("Tastytrade account cache cleared")
