"""
Authentication module for Azure AD integration.

Provides JWT token validation and role-based access control
for the trading terminal admin API.

Author: Trading Bot Team
Version: 1.0.0
"""

from src.auth.azure_ad_auth import (
    IAuthService,
    AzureADAuthService,
    LocalDevAuthService,
    TokenClaims,
    create_auth_service,
)

__all__ = [
    "IAuthService",
    "AzureADAuthService",
    "LocalDevAuthService",
    "TokenClaims",
    "create_auth_service",
]
