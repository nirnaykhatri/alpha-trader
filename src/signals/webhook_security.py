"""
Centralized webhook security module for TradingView signal authentication.

This module consolidates all webhook authentication and security validation logic
to avoid duplication across signal handlers. Provides standardized secret verification
and HMAC signature validation.

Architectural Rationale (ARCH-02):
- Single source of truth for webhook security
- Consistent authentication across all webhook endpoints
- Easier security audits and updates
- Protection against timing attacks (constant-time comparisons)
"""

import hmac
import hashlib
from typing import Optional
from src.core.logging_config import get_logger

logger = get_logger(__name__)


class WebhookSecurityValidator:
    """
    Validates webhook requests using secret-based authentication or HMAC signatures.
    
    Supports two authentication modes:
    1. Simple secret comparison (URL path or body field)
    2. HMAC-SHA256 signature verification (X-Signature header)
    
    Uses constant-time comparison to prevent timing attacks.
    """
    
    def __init__(self, secret: str, security_enabled: bool = True):
        """
        Initialize webhook security validator.
        
        Args:
            secret: Shared secret for webhook authentication
            security_enabled: Whether to enforce security checks (disable for testing)
        """
        self._secret = secret
        self._security_enabled = security_enabled
        
        if not security_enabled:
            logger.warning("Webhook security is DISABLED - only use in development")
        
        logger.info("Webhook security validator initialized")
    
    def verify_secret(self, provided_secret: str) -> bool:
        """
        Verify webhook secret for URL path or body authentication.
        
        Uses constant-time comparison to prevent timing attacks that could
        leak information about the secret through response time differences.
        
        Args:
            provided_secret: Secret provided in URL path or request body
            
        Returns:
            True if secret is valid or security is disabled, False otherwise
            
        Examples:
            >>> validator = WebhookSecurityValidator(secret="my-secret-key")
            >>> validator.verify_secret("my-secret-key")
            True
            >>> validator.verify_secret("wrong-secret")
            False
        """
        # If security is disabled, always return True (testing mode)
        if not self._security_enabled:
            return True
        
        if not provided_secret:
            logger.warning("No secret provided in webhook request")
            return False
        
        try:
            # Use constant-time comparison to prevent timing attacks
            is_valid = hmac.compare_digest(self._secret, provided_secret)
            
            if not is_valid:
                logger.warning("Invalid webhook secret provided")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Error verifying webhook secret: {str(e)}")
            return False
    
    def verify_signature(self, body: bytes, signature: str) -> bool:
        """
        Verify HMAC-SHA256 signature for webhook request.
        
        Computes expected signature from request body and compares with
        provided signature using constant-time comparison. Supports GitHub-style
        signatures with "sha256=" prefix.
        
        Args:
            body: Raw request body bytes
            signature: Signature from X-Signature header (with or without "sha256=" prefix)
            
        Returns:
            True if signature is valid or security is disabled, False otherwise
            
        Examples:
            >>> validator = WebhookSecurityValidator(secret="my-secret-key")
            >>> body = b'{"symbol": "AAPL", "action": "buy"}'
            >>> expected_sig = hmac.new(b"my-secret-key", body, hashlib.sha256).hexdigest()
            >>> validator.verify_signature(body, f"sha256={expected_sig}")
            True
        """
        # If security is disabled, always return True (testing mode)
        if not self._security_enabled:
            return True
        
        if not signature:
            logger.warning("No signature provided in webhook request")
            return False
        
        try:
            # Generate expected signature using HMAC-SHA256
            expected_signature = hmac.new(
                self._secret.encode(),
                body,
                hashlib.sha256
            ).hexdigest()
            
            # Remove "sha256=" prefix if present (GitHub-style signatures)
            provided_signature = signature.replace("sha256=", "")
            
            # Compare signatures using constant-time comparison
            is_valid = hmac.compare_digest(expected_signature, provided_signature)
            
            if not is_valid:
                logger.warning("Invalid webhook signature provided")
            
            return is_valid
            
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {str(e)}")
            return False
    
    def compute_signature(self, body: bytes) -> str:
        """
        Compute HMAC-SHA256 signature for a given request body.
        
        Useful for testing and generating expected signatures.
        
        Args:
            body: Raw request body bytes
            
        Returns:
            Hexadecimal HMAC-SHA256 signature
            
        Examples:
            >>> validator = WebhookSecurityValidator(secret="my-secret-key")
            >>> body = b'{"symbol": "AAPL"}'
            >>> sig = validator.compute_signature(body)
            >>> len(sig)
            64  # SHA256 hex digest length
        """
        return hmac.new(
            self._secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()


# Convenience functions for backward compatibility
def verify_secret(secret: str, provided_secret: str, security_enabled: bool = True) -> bool:
    """
    Verify webhook secret (convenience function).
    
    Args:
        secret: Expected secret
        provided_secret: Secret provided in request
        security_enabled: Whether to enforce security
        
    Returns:
        True if secret is valid or security is disabled
    """
    validator = WebhookSecurityValidator(secret, security_enabled)
    return validator.verify_secret(provided_secret)


def verify_signature(secret: str, body: bytes, signature: str, security_enabled: bool = True) -> bool:
    """
    Verify webhook HMAC signature (convenience function).
    
    Args:
        secret: Shared secret
        body: Raw request body
        signature: Provided signature
        security_enabled: Whether to enforce security
        
    Returns:
        True if signature is valid or security is disabled
    """
    validator = WebhookSecurityValidator(secret, security_enabled)
    return validator.verify_signature(body, signature)
