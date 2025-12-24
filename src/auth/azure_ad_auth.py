"""
Azure AD Authentication Service.

Provides JWT token validation for Azure AD authentication in the trading terminal.
Uses MSAL and PyJWT for robust token validation with JWKS key rotation.

Security Features:
    - Validates issuer, audience, and signature
    - Fetches public keys from Azure AD JWKS endpoint
    - Caches keys with automatic refresh
    - Supports multiple tenants

Usage:
    auth_service = AzureADAuthService(tenant_id, client_id)
    await auth_service.initialize()
    
    # Validate token
    claims = await auth_service.validate_token(token)
    if claims:
        user_id = claims.get("oid")

Author: Trading Bot Team
Version: 1.0.0
"""

import asyncio
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

import aiohttp

from src.core.logging_config import get_logger

logger = get_logger(__name__)


# Try to import JWT library
try:
    import jwt
    from jwt import PyJWKClient
    JWT_AVAILABLE = True
except ImportError:
    JWT_AVAILABLE = False
    logger.warning("PyJWT not installed. Token validation disabled.")


@dataclass
class JWKSCache:
    """Cache for JSON Web Key Sets."""
    
    keys: Dict[str, Any] = field(default_factory=dict)
    last_refresh: Optional[datetime] = None
    refresh_interval: timedelta = field(default_factory=lambda: timedelta(hours=24))
    
    def is_stale(self) -> bool:
        """Check if cache needs refresh."""
        if self.last_refresh is None:
            return True
        return datetime.utcnow() - self.last_refresh > self.refresh_interval


@dataclass
class TokenClaims:
    """Validated token claims."""
    
    user_id: str  # oid claim
    tenant_id: str  # tid claim
    email: Optional[str] = None
    name: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    raw_claims: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_admin(self) -> bool:
        """Check if user has admin role."""
        return "Admin" in self.roles or "TradingAdmin" in self.roles
    
    @property
    def is_trader(self) -> bool:
        """Check if user has trader role."""
        return "Trader" in self.roles or self.is_admin
    
    @property
    def is_viewer(self) -> bool:
        """Check if user has any valid role."""
        return bool(self.roles) or self.is_admin or self.is_trader


class IAuthService(ABC):
    """Interface for authentication services."""
    
    @abstractmethod
    async def validate_token(self, token: str) -> Optional[TokenClaims]:
        """
        Validate a JWT token.
        
        Args:
            token: JWT token string (without "Bearer " prefix)
            
        Returns:
            TokenClaims if valid, None otherwise
        """
        pass
    
    @abstractmethod
    async def is_authorized(self, token: str, required_role: Optional[str] = None) -> bool:
        """
        Check if token is valid and has required role.
        
        Args:
            token: JWT token string
            required_role: Optional required role (Admin, Trader, Viewer)
            
        Returns:
            True if authorized
        """
        pass


class AzureADAuthService(IAuthService):
    """
    Azure AD authentication service using JWT validation.
    
    Validates tokens against Azure AD public keys and enforces
    issuer, audience, and role claims.
    
    Thread Safety:
        This class is safe for concurrent async operations.
        Uses locks to prevent cache race conditions.
    
    Example:
        >>> auth = AzureADAuthService(
        ...     tenant_id="your-tenant-id",
        ...     client_id="your-client-id"
        ... )
        >>> await auth.initialize()
        >>> claims = await auth.validate_token(token)
    """
    
    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        allowed_issuers: Optional[List[str]] = None,
        validate_audience: bool = True,
        require_https_issuer: bool = True
    ):
        """
        Initialize Azure AD auth service.
        
        Args:
            tenant_id: Azure AD tenant ID (GUID)
            client_id: Application (client) ID from Azure AD app registration
            allowed_issuers: Additional allowed issuer URLs
            validate_audience: Whether to validate audience claim
            require_https_issuer: Require HTTPS for issuer URLs
        """
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._validate_audience = validate_audience
        self._require_https_issuer = require_https_issuer
        
        # JWKS endpoint for Azure AD
        self._jwks_url = f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys"
        self._openid_config_url = f"https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration"
        
        # Allowed issuers (Azure AD standard formats)
        self._allowed_issuers = allowed_issuers or [
            f"https://login.microsoftonline.com/{tenant_id}/v2.0",
            f"https://sts.windows.net/{tenant_id}/",
        ]
        
        # Key cache
        self._jwks_cache = JWKSCache()
        self._cache_lock = asyncio.Lock()
        self._initialized = False
        
        # PyJWKClient for key management
        self._jwk_client: Optional['PyJWKClient'] = None
        
        logger.info(f"Azure AD auth service created for tenant {tenant_id[:8]}...")
    
    async def initialize(self) -> bool:
        """
        Initialize the auth service by fetching JWKS.
        
        Returns:
            True if initialization successful
        """
        if not JWT_AVAILABLE:
            logger.error("PyJWT not installed. Cannot initialize Azure AD auth.")
            return False
        
        try:
            # Initialize PyJWKClient
            self._jwk_client = PyJWKClient(self._jwks_url)
            
            # Verify we can fetch keys
            await self._refresh_keys()
            
            self._initialized = True
            logger.info("✅ Azure AD auth service initialized")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Azure AD auth: {e}")
            return False
    
    async def _refresh_keys(self) -> None:
        """Refresh JWKS keys from Azure AD."""
        async with self._cache_lock:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self._jwks_url) as response:
                        if response.status == 200:
                            data = await response.json()
                            self._jwks_cache.keys = {
                                key.get("kid"): key for key in data.get("keys", [])
                            }
                            self._jwks_cache.last_refresh = datetime.utcnow()
                            logger.debug(f"Refreshed {len(self._jwks_cache.keys)} keys from Azure AD")
                        else:
                            logger.error(f"Failed to fetch JWKS: HTTP {response.status}")
            except Exception as e:
                logger.error(f"Error refreshing JWKS: {e}")
    
    async def validate_token(self, token: str) -> Optional[TokenClaims]:
        """
        Validate a JWT token from Azure AD.
        
        Args:
            token: JWT token string (without "Bearer " prefix)
            
        Returns:
            TokenClaims if valid, None otherwise
        """
        if not JWT_AVAILABLE or not self._jwk_client:
            logger.warning("JWT validation not available")
            return None
        
        if not token or not isinstance(token, str):
            logger.debug("Invalid token format")
            return None
        
        try:
            # Refresh keys if cache is stale
            if self._jwks_cache.is_stale():
                await self._refresh_keys()
            
            # Get signing key from token header
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            
            # Decode and validate token
            decode_options = {
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "require": ["exp", "iat", "iss", "sub"],
            }
            
            if self._validate_audience:
                decode_options["verify_aud"] = True
                audience = self._client_id
            else:
                decode_options["verify_aud"] = False
                audience = None
            
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=audience,
                issuer=self._allowed_issuers,
                options=decode_options
            )
            
            # Extract and return claims
            return TokenClaims(
                user_id=claims.get("oid", claims.get("sub", "")),
                tenant_id=claims.get("tid", self._tenant_id),
                email=claims.get("email") or claims.get("preferred_username"),
                name=claims.get("name"),
                roles=claims.get("roles", []),
                raw_claims=claims
            )
            
        except jwt.ExpiredSignatureError:
            logger.debug("Token has expired")
            return None
        except jwt.InvalidAudienceError:
            logger.debug("Invalid audience claim")
            return None
        except jwt.InvalidIssuerError:
            logger.debug("Invalid issuer claim")
            return None
        except jwt.InvalidSignatureError:
            logger.warning("Invalid token signature")
            return None
        except Exception as e:
            logger.warning(f"Token validation error: {e}")
            return None
    
    async def is_authorized(
        self,
        token: str,
        required_role: Optional[str] = None
    ) -> bool:
        """
        Check if token is valid and has required role.
        
        Args:
            token: JWT token string
            required_role: Optional required role (Admin, Trader, Viewer)
            
        Returns:
            True if authorized
        """
        claims = await self.validate_token(token)
        if not claims:
            return False
        
        if not required_role:
            return True
        
        # Check role hierarchy
        if required_role == "Admin":
            return claims.is_admin
        elif required_role == "Trader":
            return claims.is_trader
        elif required_role == "Viewer":
            return claims.is_viewer
        else:
            return required_role in claims.roles


class LocalDevAuthService(IAuthService):
    """
    Local development auth service.
    
    Allows all requests from localhost without real token validation.
    Only use in development environments.
    """
    
    def __init__(self):
        """Initialize local dev auth service."""
        logger.warning("⚠️ Using LocalDevAuthService - NOT FOR PRODUCTION")
    
    async def validate_token(self, token: str) -> Optional[TokenClaims]:
        """
        Mock token validation for local development.
        
        Returns:
            Mock claims for any token
        """
        if not token:
            return None
        
        return TokenClaims(
            user_id="local-dev-user",
            tenant_id="local-dev-tenant",
            email="dev@localhost",
            name="Local Developer",
            roles=["Admin", "Trader"],
            raw_claims={"dev_mode": True}
        )
    
    async def is_authorized(
        self,
        token: str,
        required_role: Optional[str] = None
    ) -> bool:
        """
        Always authorize in dev mode.
        
        Returns:
            True for any request
        """
        return True


def create_auth_service(
    config_manager,
    allow_dev_mode: bool = False
) -> IAuthService:
    """
    Factory function to create appropriate auth service.
    
    Args:
        config_manager: Configuration manager with Azure settings
        allow_dev_mode: Whether to allow LocalDevAuthService
        
    Returns:
        Configured auth service
    """
    # Get Azure AD settings from config
    tenant_id = config_manager.get_config("azure.tenant_id", "")
    client_id = config_manager.get_config("azure.client_id", "")
    
    # Also check environment variables
    import os
    tenant_id = tenant_id or os.environ.get("AZURE_TENANT_ID", "")
    client_id = client_id or os.environ.get("AZURE_CLIENT_ID", "")
    
    # Check if running in Azure (Container Apps sets this)
    is_azure = os.environ.get("WEBSITE_SITE_NAME") or os.environ.get("CONTAINER_APP_NAME")
    
    if tenant_id and client_id and JWT_AVAILABLE:
        logger.info("Creating Azure AD auth service")
        return AzureADAuthService(tenant_id=tenant_id, client_id=client_id)
    elif allow_dev_mode and not is_azure:
        logger.warning("Azure AD not configured, using local dev auth")
        return LocalDevAuthService()
    else:
        raise ValueError(
            "Azure AD authentication required but not configured. "
            "Set AZURE_TENANT_ID and AZURE_CLIENT_ID environment variables."
        )
