"""
Tastytrade session management.

Updated for tastytrade v11.x which uses OAuth authentication.
Requires client_secret and refresh_token instead of username/password.

To set up OAuth:
1. Create an OAuth application at https://my.tastytrade.com/app.html#/manage/api-access/oauth-applications
2. Generate a refresh token from the same page (OAuth Applications > Manage > Create Grant)
3. Store client_secret and refresh_token in Azure Key Vault or environment variables

For sandbox accounts, use https://developer.tastytrade.com/sandbox/ to create an account,
then run: from tastytrade.oauth import login; login(is_test=True)
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
from tastytrade import Session
from src.interfaces import IConfigurationManager, IAsyncContextManager
from src.core.logging_config import get_logger
from src.exceptions import ConfigurationException, BrokerAPIException
from src.utils import run_blocking

logger = get_logger(__name__)


class TastytradeSessionManager(IAsyncContextManager):
    """
    Manages Tastytrade API sessions using OAuth authentication.
    
    The tastytrade SDK v11.x requires OAuth credentials:
    - client_secret: From your OAuth application setup
    - refresh_token: Generated via OAuth grant (never expires)
    
    Handles session creation and automatic token refreshing.
    Supports both Production and Certification (Sandbox) environments.
    """
    
    # =========================================================================
    # Timing Constants
    # =========================================================================
    _KEEP_ALIVE_INTERVAL_SECONDS: int = 10 * 60  # 10 minutes between checks
    _EXPIRATION_BUFFER_MINUTES: int = 2  # Refresh if within 2 min of expiration
    _ERROR_RETRY_SECONDS: int = 60  # Retry delay after keep-alive error
    
    def __init__(self, config: IConfigurationManager):
        """
        Initialize the session manager.
        
        Args:
            config: Configuration manager containing Tastytrade OAuth credentials.
                    Required keys:
                    - api.tastytrade.client_secret: OAuth client secret
                    - api.tastytrade.refresh_token: OAuth refresh token
                    - api.tastytrade.is_sandbox: Boolean for sandbox/production mode
        """
        self._config = config
        self._session: Optional[Session] = None
        # Always stored as UTC-aware datetime (or None)
        self._last_refresh: Optional[datetime] = None
        self._refresh_task: Optional[asyncio.Task] = None
        self._is_sandbox = config.get_config("api.tastytrade.is_sandbox", True)
        self._auth_lock = asyncio.Lock()  # Prevents race condition during concurrent authentication
    
    @staticmethod
    def _normalize_to_utc(dt: datetime) -> datetime:
        """
        Normalize a datetime to UTC timezone.
        
        Handles both timezone-aware and naive datetimes:
        - Timezone-aware: Converts to UTC
        - Naive: Assumes UTC and adds timezone info
        
        Args:
            dt: The datetime to normalize.
            
        Returns:
            A UTC-aware datetime.
        """
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc)
        # Assume naive datetime is in UTC
        return dt.replace(tzinfo=timezone.utc)
        
    async def start(self) -> None:
        """
        Start the session manager by authenticating with Tastytrade.
        
        Raises:
            BrokerAPIException: If authentication fails.
        """
        try:
            await self.get_session()
        except Exception as e:
            logger.error(f"Failed to start Tastytrade session: {e}")
            # Re-raise so higher-level components (e.g. BrokerSubsystem) can decide
            # whether to continue without Tastytrade.
            raise

    async def stop(self) -> None:
        """Stop the session manager."""
        await self.close()

    async def get_session(self) -> Session:
        """
        Get a valid, authenticated session.
        
        If no session exists, creates one. If session is about to expire, refreshes it.
        Uses a lock to prevent race conditions during concurrent authentication.
        
        Returns:
            Session: Active Tastytrade session.
            
        Raises:
            APIException: If authentication fails.
        """
        async with self._auth_lock:
            if self._session is None:
                await self._authenticate()
            elif self._is_session_expired():
                # Refresh the session token if it's about to expire
                logger.info("Session token expiring soon, refreshing...")
                await run_blocking(self._session.refresh)
                self._last_refresh = datetime.now(timezone.utc)
            
        return self._session
    
    def _is_session_expired(self) -> bool:
        """Check if the session token is expired or about to expire."""
        if self._session is None:
            return True
        try:
            session_expiration = self._session.session_expiration
            if session_expiration is None:
                return False
            
            now_utc = datetime.now(timezone.utc)
            exp_utc = self._normalize_to_utc(session_expiration)
            
            # Consider expired if within buffer time of expiration
            return now_utc >= exp_utc - timedelta(minutes=self._EXPIRATION_BUFFER_MINUTES)
        except AttributeError:
            # If session_expiration doesn't exist, assume session is valid
            return False
        
    async def _authenticate(self):
        """
        Authenticate with Tastytrade API using OAuth credentials.
        
        Requires client_secret and refresh_token to be configured.
        These credentials can be obtained from the Tastytrade OAuth application setup.
        """
        try:
            client_secret = self._config.get_config("api.tastytrade.client_secret")
            refresh_token = self._config.get_config("api.tastytrade.refresh_token")
            
            if not client_secret or not refresh_token:
                raise ConfigurationException(
                    "Tastytrade OAuth credentials not configured. "
                    "Required: api.tastytrade.client_secret and api.tastytrade.refresh_token. "
                    "See https://tastyworks-api.readthedocs.io/en/latest/sessions.html for setup instructions."
                )
                
            logger.info(f"Authenticating with Tastytrade ({'Sandbox' if self._is_sandbox else 'Production'}) via OAuth...")
            
            # Create session with OAuth credentials
            # is_test=True for sandbox/certification environment
            self._session = await run_blocking(
                Session, 
                client_secret, 
                refresh_token,
                is_test=self._is_sandbox
            )
                
            self._last_refresh = datetime.now(timezone.utc)
            logger.info("Successfully authenticated with Tastytrade.")
            
            # Start refresh task if not running
            if self._refresh_task is None or self._refresh_task.done():
                self._refresh_task = asyncio.create_task(self._keep_alive())
                
        except Exception as e:
            logger.error(f"Tastytrade authentication failed: {str(e)}")
            raise BrokerAPIException(f"Tastytrade authentication failed: {str(e)}")
            
    async def _keep_alive(self):
        """
        Background task to keep the session alive by refreshing the access token.
        
        The OAuth access token expires after 15 minutes, but refresh tokens never expire.
        This task checks session expiration and calls refresh() when needed.
        """
        while True:
            try:
                await asyncio.sleep(self._KEEP_ALIVE_INTERVAL_SECONDS)
                
                if self._session:
                    # Check if session token is about to expire
                    session_expiration = self._session.session_expiration
                    if session_expiration is None:
                        # No expiration info available, skip refresh check
                        continue
                    
                    now_utc = datetime.now(timezone.utc)
                    exp_utc = self._normalize_to_utc(session_expiration)
                    
                    if now_utc >= exp_utc - timedelta(minutes=self._EXPIRATION_BUFFER_MINUTES):
                        logger.info("Refreshing Tastytrade session token...")
                        await run_blocking(self._session.refresh)
                        self._last_refresh = datetime.now(timezone.utc)
                        logger.info("Successfully refreshed Tastytrade session token.")
                         
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in Tastytrade keep-alive: {str(e)}")
                await asyncio.sleep(self._ERROR_RETRY_SECONDS)

    async def close(self):
        """Close the session and cleanup."""
        if self._refresh_task:
            self._refresh_task.cancel()
            try:
                await self._refresh_task
            except asyncio.CancelledError:
                pass
                
        if self._session:
            try:
                # Close the httpx clients
                self._session.sync_client.close()
                await self._session.async_client.aclose()
            except Exception as e:
                logger.warning(f"Error closing Tastytrade session clients: {e}")
            self._session = None
