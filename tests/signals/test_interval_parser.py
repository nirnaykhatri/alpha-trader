"""
Tests for centralized interval parsing utilities.

Test Coverage:
- Normalization of various interval formats
- Extraction from text patterns
- Webhook data extraction with fallback chain
- Edge cases and error handling
"""

import pytest
from src.signals.interval_parser import (
    normalize,
    extract_from_text,
    extract_from_webhook_data,
    INTERVAL_MAP
)


class TestNormalize:
    """Test interval normalization."""
    
    def test_normalize_numeric_minutes(self):
        """Numeric minutes should convert to standard format."""
        assert normalize("1") == "1m"
        assert normalize("5") == "5m"
        assert normalize("15") == "15m"
        assert normalize("30") == "30m"
    
    def test_normalize_numeric_hours(self):
        """Numeric hours should convert from minutes."""
        assert normalize("60") == "1h"
        assert normalize("240") == "4h"
    
    def test_normalize_numeric_days(self):
        """Numeric days should convert from minutes."""
        assert normalize("1440") == "1d"
        assert normalize("10080") == "1w"
    
    def test_normalize_standard_format(self):
        """Standard format should remain unchanged."""
        assert normalize("1h") == "1h"
        assert normalize("4h") == "4h"
        assert normalize("1d") == "1d"
    
    def test_normalize_case_insensitive(self):
        """Normalization should be case-insensitive."""
        assert normalize("1H") == "1h"
        assert normalize("4H") == "4h"
        assert normalize("1D") == "1d"
    
    def test_normalize_alternative_formats(self):
        """Alternative formats should normalize correctly."""
        assert normalize("1hour") == "1h"
        assert normalize("h1") == "1h"
        assert normalize("h4") == "4h"
        assert normalize("daily") == "1d"
        assert normalize("weekly") == "1w"
    
    def test_normalize_with_whitespace(self):
        """Whitespace should be stripped."""
        assert normalize(" 1h ") == "1h"
        assert normalize("  4h  ") == "4h"
    
    def test_normalize_unknown_format(self):
        """Unknown formats should pass through."""
        assert normalize("unknown") == "unknown"


class TestExtractFromText:
    """Test interval extraction from text."""
    
    def test_extract_standard_interval(self):
        """Standard intervals in text should be extracted."""
        assert extract_from_text("AAPL 1h bullish") == "1h"
        assert extract_from_text("MSFT 4h breakout") == "4h"
        assert extract_from_text("SPY 1d trend") == "1d"
    
    def test_extract_with_tf_prefix(self):
        """Intervals with 'tf:' prefix should be extracted."""
        assert extract_from_text("tf: 1h long entry") == "1h"
        assert extract_from_text("tf 4h signal") == "4h"
        assert extract_from_text("tf:1d") == "1d"
    
    def test_extract_with_interval_prefix(self):
        """Intervals with 'interval:' prefix should be extracted."""
        assert extract_from_text("interval: 1h") == "1h"
        assert extract_from_text("interval 4h") == "4h"
    
    def test_extract_word_format(self):
        """Word-based intervals should be extracted."""
        assert extract_from_text("1 hour chart") == "1h"
        assert extract_from_text("5 minutes signal") == "5m"
        assert extract_from_text("1 day trend") == "1d"
    
    def test_extract_not_found(self):
        """No interval in text should return None."""
        assert extract_from_text("no interval here") is None
        assert extract_from_text("AAPL long signal") is None
    
    def test_extract_case_insensitive(self):
        """Extraction should be case-insensitive."""
        assert extract_from_text("AAPL 1H BULLISH") == "1h"
        assert extract_from_text("TF: 4H") == "4h"


class TestExtractFromWebhookData:
    """Test interval extraction from webhook data."""
    
    def test_extract_direct_interval_field(self):
        """Direct 'interval' field should be used first."""
        data = {"interval": "1h", "symbol": "AAPL"}
        assert extract_from_webhook_data(data) == "1h"
    
    def test_extract_timeframe_field(self):
        """'timeframe' field should be used as fallback."""
        data = {"timeframe": "4h", "symbol": "MSFT"}
        assert extract_from_webhook_data(data) == "4h"
    
    def test_extract_tf_field(self):
        """'tf' field should be used as fallback."""
        data = {"tf": "1d", "symbol": "SPY"}
        assert extract_from_webhook_data(data) == "1d"
    
    def test_extract_numeric_timeframe(self):
        """Numeric timeframe should be normalized."""
        data = {"timeframe": "240", "symbol": "TSLA"}
        assert extract_from_webhook_data(data) == "4h"
    
    def test_extract_from_message(self):
        """Interval from message should be extracted."""
        data = {"message": "AAPL 1h bullish signal", "symbol": "AAPL"}
        assert extract_from_webhook_data(data) == "1h"
    
    def test_extract_from_alert_name(self):
        """Interval from alert_name should be extracted."""
        data = {"alert_name": "MSFT 4h breakout", "symbol": "MSFT"}
        assert extract_from_webhook_data(data) == "4h"
    
    def test_extract_priority_interval_over_message(self):
        """Direct interval field should take priority over message."""
        data = {
            "interval": "1h",
            "message": "4h signal",  # Should be ignored
            "symbol": "AAPL"
        }
        assert extract_from_webhook_data(data) == "1h"
    
    def test_extract_priority_timeframe_over_message(self):
        """Timeframe field should take priority over message."""
        data = {
            "timeframe": "1h",
            "message": "4h signal",  # Should be ignored
            "symbol": "AAPL"
        }
        assert extract_from_webhook_data(data) == "1h"
    
    def test_extract_with_default(self):
        """Default interval should be used if nothing found."""
        data = {"symbol": "AAPL"}
        assert extract_from_webhook_data(data, default_interval="1h") == "1h"
    
    def test_extract_without_default(self):
        """None should be returned if no interval found and no default."""
        data = {"symbol": "AAPL"}
        assert extract_from_webhook_data(data) is None
    
    def test_extract_normalizes_default(self):
        """Default interval should also be normalized."""
        data = {"symbol": "AAPL"}
        assert extract_from_webhook_data(data, default_interval="60") == "1h"
    
    def test_extract_handles_exception(self):
        """Exceptions should be handled gracefully."""
        data = None  # Invalid data
        assert extract_from_webhook_data(data, default_interval="1h") == "1h"


class TestIntervalMap:
    """Test interval mapping constants."""
    
    def test_interval_map_completeness(self):
        """Interval map should cover common formats."""
        # Minutes
        assert "1m" in INTERVAL_MAP.values()
        assert "5m" in INTERVAL_MAP.values()
        assert "15m" in INTERVAL_MAP.values()
        assert "30m" in INTERVAL_MAP.values()
        
        # Hours
        assert "1h" in INTERVAL_MAP.values()
        assert "4h" in INTERVAL_MAP.values()
        
        # Days
        assert "1d" in INTERVAL_MAP.values()
        
        # Weeks
        assert "1w" in INTERVAL_MAP.values()
    
    def test_interval_map_bidirectional(self):
        """Interval map should support various input formats."""
        # Numeric formats
        assert INTERVAL_MAP["60"] == "1h"
        assert INTERVAL_MAP["240"] == "4h"
        assert INTERVAL_MAP["1440"] == "1d"
        
        # Alternative formats
        assert INTERVAL_MAP["h1"] == "1h"
        assert INTERVAL_MAP["h4"] == "4h"
        assert INTERVAL_MAP["daily"] == "1d"
        assert INTERVAL_MAP["weekly"] == "1w"


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_normalize_empty_string(self):
        """Empty string should pass through."""
        assert normalize("") == ""
    
    def test_extract_empty_text(self):
        """Empty text should return None."""
        assert extract_from_text("") is None
    
    def test_extract_empty_webhook_data(self):
        """Empty webhook data should return default."""
        assert extract_from_webhook_data({}, default_interval="1h") == "1h"
    
    def test_normalize_integer_input(self):
        """Integer input should be converted to string."""
        assert normalize(60) == "1h"
        assert normalize(240) == "4h"
