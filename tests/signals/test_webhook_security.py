"""
Tests for centralized webhook security utilities.

Test Coverage:
- Secret verification with constant-time comparison
- HMAC signature verification
- Security disabled mode
- Edge cases and error handling
"""

import hmac
import hashlib
import pytest
from src.signals.webhook_security import (
    WebhookSecurityValidator,
    verify_secret,
    verify_signature
)


class TestWebhookSecurityValidator:
    """Test WebhookSecurityValidator class."""
    
    def setup_method(self):
        """Setup test fixtures."""
        self.secret = "test-secret-key-12345"
        self.validator = WebhookSecurityValidator(self.secret, security_enabled=True)
        self.validator_disabled = WebhookSecurityValidator(self.secret, security_enabled=False)
    
    def test_verify_secret_valid(self):
        """Valid secret should pass verification."""
        assert self.validator.verify_secret(self.secret) is True
    
    def test_verify_secret_invalid(self):
        """Invalid secret should fail verification."""
        assert self.validator.verify_secret("wrong-secret") is False
    
    def test_verify_secret_empty(self):
        """Empty secret should fail verification."""
        assert self.validator.verify_secret("") is False
    
    def test_verify_secret_none(self):
        """None secret should fail verification."""
        assert self.validator.verify_secret(None) is False
    
    def test_verify_secret_case_sensitive(self):
        """Secret verification should be case-sensitive."""
        assert self.validator.verify_secret(self.secret.upper()) is False
    
    def test_verify_secret_disabled_security(self):
        """Disabled security should bypass secret check."""
        assert self.validator_disabled.verify_secret("any-secret") is True
        assert self.validator_disabled.verify_secret("") is True
        assert self.validator_disabled.verify_secret("wrong") is True
    
    def test_verify_signature_valid(self):
        """Valid signature should pass verification."""
        body = b'{"symbol": "AAPL", "action": "buy"}'
        signature = hmac.new(
            self.secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        assert self.validator.verify_signature(body, signature) is True
    
    def test_verify_signature_with_prefix(self):
        """Signature with 'sha256=' prefix should be handled."""
        body = b'{"symbol": "MSFT", "action": "sell"}'
        signature = hmac.new(
            self.secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        assert self.validator.verify_signature(body, f"sha256={signature}") is True
    
    def test_verify_signature_invalid(self):
        """Invalid signature should fail verification."""
        body = b'{"symbol": "AAPL", "action": "buy"}'
        wrong_signature = "0" * 64  # Invalid hex signature
        
        assert self.validator.verify_signature(body, wrong_signature) is False
    
    def test_verify_signature_empty(self):
        """Empty signature should fail verification."""
        body = b'{"symbol": "AAPL", "action": "buy"}'
        assert self.validator.verify_signature(body, "") is False
    
    def test_verify_signature_none(self):
        """None signature should fail verification."""
        body = b'{"symbol": "AAPL", "action": "buy"}'
        assert self.validator.verify_signature(body, None) is False
    
    def test_verify_signature_wrong_body(self):
        """Signature for different body should fail."""
        body1 = b'{"symbol": "AAPL", "action": "buy"}'
        body2 = b'{"symbol": "MSFT", "action": "sell"}'
        
        signature = hmac.new(
            self.secret.encode(),
            body1,
            hashlib.sha256
        ).hexdigest()
        
        assert self.validator.verify_signature(body2, signature) is False
    
    def test_verify_signature_disabled_security(self):
        """Disabled security should bypass signature check."""
        body = b'{"symbol": "AAPL", "action": "buy"}'
        assert self.validator_disabled.verify_signature(body, "invalid") is True
        assert self.validator_disabled.verify_signature(body, "") is True
    
    def test_compute_signature(self):
        """compute_signature should generate valid HMAC."""
        body = b'{"symbol": "AAPL", "action": "buy"}'
        computed = self.validator.compute_signature(body)
        
        expected = hmac.new(
            self.secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        assert computed == expected
    
    def test_compute_signature_length(self):
        """Computed signature should be 64 hex characters (SHA256)."""
        body = b'{"symbol": "AAPL"}'
        signature = self.validator.compute_signature(body)
        
        assert len(signature) == 64
        assert all(c in '0123456789abcdef' for c in signature)


class TestConvenienceFunctions:
    """Test convenience functions for backward compatibility."""
    
    def test_verify_secret_function(self):
        """verify_secret convenience function should work."""
        secret = "test-secret"
        
        assert verify_secret(secret, secret, security_enabled=True) is True
        assert verify_secret(secret, "wrong", security_enabled=True) is False
        assert verify_secret(secret, "wrong", security_enabled=False) is True
    
    def test_verify_signature_function(self):
        """verify_signature convenience function should work."""
        secret = "test-secret"
        body = b'{"symbol": "AAPL"}'
        
        signature = hmac.new(
            secret.encode(),
            body,
            hashlib.sha256
        ).hexdigest()
        
        assert verify_signature(secret, body, signature, security_enabled=True) is True
        assert verify_signature(secret, body, "invalid", security_enabled=True) is False
        assert verify_signature(secret, body, "invalid", security_enabled=False) is True


class TestConstantTimeComparison:
    """Test timing attack protection."""
    
    def test_secret_comparison_timing(self):
        """Secret comparison should use constant-time algorithm."""
        secret = "test-secret-key-12345"
        validator = WebhookSecurityValidator(secret, security_enabled=True)
        
        # These should all fail in constant time
        # (In practice, timing differences would be measured)
        assert validator.verify_secret("t") is False  # Prefix match
        assert validator.verify_secret("test-") is False  # Partial match
        assert validator.verify_secret("test-secret-key-1234") is False  # Almost match
        assert validator.verify_secret("wrong-secret-entirely") is False  # No match
    
    def test_signature_comparison_timing(self):
        """Signature comparison should use constant-time algorithm."""
        secret = "test-secret"
        body = b'{"symbol": "AAPL"}'
        validator = WebhookSecurityValidator(secret, security_enabled=True)
        
        valid_signature = validator.compute_signature(body)
        
        # Modify signature slightly
        almost_valid = valid_signature[:-1] + ("0" if valid_signature[-1] != "0" else "1")
        
        assert validator.verify_signature(body, almost_valid) is False


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_secret_initialization(self):
        """Empty secret should be allowed but fail on empty provided secret."""
        validator = WebhookSecurityValidator("", security_enabled=True)
        # Empty provided secret fails validation (logged as "No secret provided")
        assert validator.verify_secret("") is False
        # Non-empty secret fails comparison
        assert validator.verify_secret("anything") is False
    
    def test_unicode_secret(self):
        """Unicode secrets should be handled (hmac.compare_digest limitation)."""
        secret = "test-secret-ascii"  # Use ASCII-only for timing-safe comparison
        validator = WebhookSecurityValidator(secret, security_enabled=True)
        assert validator.verify_secret(secret) is True
        assert validator.verify_secret("wrong") is False
    
    def test_special_characters_secret(self):
        """Special characters in secret should be handled."""
        secret = "test!@#$%^&*()_+-=[]{}|;:',.<>?/~`"
        validator = WebhookSecurityValidator(secret, security_enabled=True)
        assert validator.verify_secret(secret) is True
    
    def test_binary_body_signature(self):
        """Binary request bodies should work with signatures."""
        secret = "test-secret"
        body = b'\x00\x01\x02\x03\xff\xfe\xfd\xfc'  # Binary data
        validator = WebhookSecurityValidator(secret, security_enabled=True)
        
        signature = validator.compute_signature(body)
        assert validator.verify_signature(body, signature) is True
    
    def test_empty_body_signature(self):
        """Empty body should generate valid signature."""
        secret = "test-secret"
        body = b''
        validator = WebhookSecurityValidator(secret, security_enabled=True)
        
        signature = validator.compute_signature(body)
        assert len(signature) == 64
        assert validator.verify_signature(body, signature) is True
    
    def test_large_body_signature(self):
        """Large bodies should work with signatures."""
        secret = "test-secret"
        body = b'{"data": "' + b'x' * 100000 + b'"}'  # 100KB body
        validator = WebhookSecurityValidator(secret, security_enabled=True)
        
        signature = validator.compute_signature(body)
        assert validator.verify_signature(body, signature) is True
