"""
Centralized interval parsing utilities for TradingView webhook signals.

This module consolidates all interval/timeframe parsing logic to avoid duplication
across signal processing components. Provides standardized extraction and normalization
of interval strings from various webhook formats.

Architectural Rationale (ARCH-01):
- Single source of truth for interval parsing logic
- Reusable across all signal handlers
- Consistent normalization rules
- Easier to test and maintain
"""

import re
from typing import Optional
from src.core.logging_config import get_logger

logger = get_logger(__name__)


# Interval normalization mapping (canonical format: Xm, Xh, Xd, Xw)
INTERVAL_MAP = {
    # Minute intervals
    "1": "1m", "1m": "1m", "1min": "1m",
    "5": "5m", "5m": "5m", "5min": "5m",
    "15": "15m", "15m": "15m", "15min": "15m",
    "30": "30m", "30m": "30m", "30min": "30m",
    
    # Hourly intervals
    "60": "1h", "1h": "1h", "1hour": "1h", "h1": "1h",
    "240": "4h", "4h": "4h", "4hour": "4h", "h4": "4h",
    
    # Daily intervals
    "1440": "1d", "1d": "1d", "1day": "1d", "d1": "1d", "daily": "1d",
    
    # Weekly intervals
    "10080": "1w", "1w": "1w", "1week": "1w", "w1": "1w", "weekly": "1w"
}

# Regex patterns for interval extraction from text
INTERVAL_PATTERNS = [
    r'\b(\d+)([mhd])\b',  # 1h, 4h, 1d, etc.
    r'\b(\d+)\s?(minute|min|hour|day)s?\b',  # 1 hour, 5 minutes, etc.
    r'\btf[:\s]*(\d+[mhd]?)\b',  # tf: 1h, tf 4h, etc.
    r'\binterval[:\s]*(\d+[mhd]?)\b',  # interval: 1h, etc.
]


def normalize(interval: str) -> str:
    """
    Normalize interval to standard format (Xm, Xh, Xd, Xw).
    
    Supports multiple input formats:
    - Numeric minutes (e.g., "60" → "1h", "1440" → "1d")
    - TradingView format (e.g., "1h", "4H", "1D")
    - Alternative formats (e.g., "1hour", "h1", "daily")
    
    Args:
        interval: Raw interval string from webhook or config
        
    Returns:
        Normalized interval string in canonical format
        
    Examples:
        >>> normalize("60")
        "1h"
        >>> normalize("1H")
        "1h"
        >>> normalize("daily")
        "1d"
        >>> normalize("240")
        "4h"
    """
    interval = str(interval).strip().lower()
    
    # Handle numeric minutes (TradingView often sends numeric values)
    if interval.isdigit():
        minutes = int(interval)
        if minutes < 60:
            return f"{minutes}m"
        elif minutes < 1440:
            hours = minutes // 60
            return f"{hours}h"
        elif minutes < 10080:
            days = minutes // 1440
            return f"{days}d"
        else:
            weeks = minutes // 10080
            return f"{weeks}w"
    
    # Apply mapping for known formats
    return INTERVAL_MAP.get(interval, interval)


def extract_from_text(text: str) -> Optional[str]:
    """
    Extract interval from text using pattern matching.
    
    Useful for parsing interval from alert names, messages, or custom fields
    where interval may be embedded in natural language.
    
    Args:
        text: Text to search for interval patterns (alert name, message, etc.)
        
    Returns:
        Extracted and normalized interval string, or None if not found
        
    Examples:
        >>> extract_from_text("AAPL 1h bullish signal")
        "1h"
        >>> extract_from_text("tf: 4h long entry")
        "4h"
        >>> extract_from_text("daily trend change")
        "1d"
    """
    text = text.lower()
    
    for pattern in INTERVAL_PATTERNS:
        match = re.search(pattern, text)
        if match:
            # Extract matched interval
            if len(match.groups()) == 2:
                # Format: number + unit (e.g., "1h")
                num, unit = match.groups()
                
                # Normalize unit
                unit_map = {
                    "m": "m", "min": "m", "minute": "m",
                    "h": "h", "hour": "h",
                    "d": "d", "day": "d"
                }
                normalized_unit = unit_map.get(unit, unit)
                interval = f"{num}{normalized_unit}"
            else:
                # Direct interval string
                interval = match.group(1)
            
            # Apply normalization
            return normalize(interval)
    
    return None


def extract_from_webhook_data(
    signal_data: dict,
    default_interval: Optional[str] = None
) -> Optional[str]:
    """
    Extract interval from TradingView webhook data with fallback chain.
    
    Tries multiple strategies to find interval in order of priority:
    1. Direct "interval" field (TradingView {{interval}} placeholder)
    2. Alternative "timeframe" or "tf" fields (custom webhooks)
    3. Embedded in "message" or "alert_name" text
    4. Provided default interval (config fallback)
    
    Args:
        signal_data: Raw signal data dictionary from webhook
        default_interval: Default interval to use if not found (optional)
        
    Returns:
        Normalized interval string, or None if not found and no default
        
    Examples:
        >>> extract_from_webhook_data({"interval": "1h", "symbol": "AAPL"})
        "1h"
        >>> extract_from_webhook_data({"timeframe": "240", "symbol": "MSFT"})
        "4h"
        >>> extract_from_webhook_data({"alert_name": "TSLA 1d breakout"})
        "1d"
        >>> extract_from_webhook_data({"symbol": "SPY"}, default_interval="1h")
        "1h"
    """
    try:
        # Strategy 1: Direct interval field (primary TradingView field)
        interval = signal_data.get("interval")
        if interval:
            return normalize(interval)
        
        # Strategy 2: Alternative field names for backwards compatibility
        timeframe = signal_data.get("timeframe") or signal_data.get("tf")
        if timeframe:
            return normalize(timeframe)
        
        # Strategy 3: Extract from message or alert name
        message = signal_data.get("message", "")
        alert_name = signal_data.get("alert_name", "")
        
        interval_from_text = extract_from_text(message + " " + alert_name)
        if interval_from_text:
            return interval_from_text
        
        # Strategy 4: Use default interval if provided
        if default_interval:
            logger.debug(f"No interval found in signal data, using default: {default_interval}")
            return normalize(default_interval)
        
        return None
        
    except Exception as e:
        logger.warning(f"Error extracting interval from webhook data: {str(e)}")
        return default_interval if default_interval else None
