"""
Application-wide constants to eliminate magic numbers and strings.

This module centralizes all constant values used throughout the trading bot
to improve code readability, maintainability, and prevent errors from typos.
"""

from typing import Final


class APIConstants:
    """Constants related to API calls and network operations."""
    
    # Timeout values (in seconds)
    DEFAULT_TIMEOUT: Final[float] = 5.0
    EXTENDED_TIMEOUT: Final[float] = 10.0
    WEBHOOK_PROCESSING_TIMEOUT: Final[float] = 5.0
    ORDER_PLACEMENT_TIMEOUT: Final[float] = 30.0
    
    # Retry configuration
    MAX_RETRY_ATTEMPTS: Final[int] = 3
    RETRY_BACKOFF_BASE: Final[float] = 2.0  # Exponential backoff base
    RETRY_BACKOFF_MAX: Final[float] = 60.0  # Max wait time between retries
    
    # Rate limiting
    ERROR_COOLDOWN_SECONDS: Final[int] = 60
    API_RATE_LIMIT_DELAY: Final[float] = 0.1
    
    # Connection pooling
    CONNECTION_POOL_SIZE: Final[int] = 20
    CONNECTION_POOL_MAX_OVERFLOW: Final[int] = 40


class HTTPStatus:
    """HTTP status codes used throughout the application."""
    
    # Success codes
    OK: Final[int] = 200
    CREATED: Final[int] = 201
    ACCEPTED: Final[int] = 202
    NO_CONTENT: Final[int] = 204
    
    # Client error codes
    BAD_REQUEST: Final[int] = 400
    UNAUTHORIZED: Final[int] = 401
    FORBIDDEN: Final[int] = 403
    NOT_FOUND: Final[int] = 404
    METHOD_NOT_ALLOWED: Final[int] = 405
    CONFLICT: Final[int] = 409
    UNPROCESSABLE_ENTITY: Final[int] = 422
    TOO_MANY_REQUESTS: Final[int] = 429
    
    # Server error codes
    INTERNAL_ERROR: Final[int] = 500
    BAD_GATEWAY: Final[int] = 502
    SERVICE_UNAVAILABLE: Final[int] = 503
    GATEWAY_TIMEOUT: Final[int] = 504


class TradingConstants:
    """Constants related to trading operations."""
    
    # Position sizing
    MIN_ORDER_VALUE: Final[float] = 1.0  # Minimum order value in dollars
    DEFAULT_POSITION_SIZE_PCT: Final[float] = 0.02  # 2% of account
    
    # DCA configuration
    DEFAULT_DCA_MULTIPLIER: Final[float] = 1.5
    MAX_DCA_ATTEMPTS: Final[int] = 5
    MIN_DCA_SPACING_PCT: Final[float] = 0.01  # 1% minimum price movement
    
    # DCA Price Safety Factors
    # These factors ensure DCA orders are placed at favorable prices:
    # - For LONG positions: buy BELOW current price (averaging down)
    # - For SHORT positions: sell ABOVE current price (averaging up)
    DCA_PRICE_OFFSET_NORMAL: Final[float] = 0.998   # 0.2% offset from current/technical level
    DCA_PRICE_OFFSET_SAFETY: Final[float] = 0.995   # 0.5% fallback if normal offset fails
    DCA_PRICE_OFFSET_SHORT_NORMAL: Final[float] = 1.002  # 0.2% above for shorts
    DCA_PRICE_OFFSET_SHORT_SAFETY: Final[float] = 1.005  # 0.5% above fallback for shorts
    
    # Risk management
    MAX_POSITION_SIZE_PCT: Final[float] = 0.10  # 10% max per position
    MAX_TOTAL_EXPOSURE_PCT: Final[float] = 0.90  # 90% max total exposure
    
    # Order types
    ORDER_TYPE_MARKET: Final[str] = "market"
    ORDER_TYPE_LIMIT: Final[str] = "limit"
    ORDER_TYPE_STOP: Final[str] = "stop"
    ORDER_TYPE_STOP_LIMIT: Final[str] = "stop_limit"


class DatabaseConstants:
    """Constants related to database operations."""
    
    # Connection pool settings
    POOL_SIZE: Final[int] = 20
    POOL_MAX_OVERFLOW: Final[int] = 40
    POOL_TIMEOUT: Final[int] = 30
    POOL_RECYCLE: Final[int] = 3600  # Recycle connections after 1 hour
    
    # Query limits
    DEFAULT_QUERY_LIMIT: Final[int] = 100
    MAX_QUERY_LIMIT: Final[int] = 1000
    
    # Batch sizes
    BULK_INSERT_BATCH_SIZE: Final[int] = 500


class TimeConstants:
    """Time-related constants."""
    
    # Market hours (Eastern Time)
    MARKET_OPEN_HOUR: Final[int] = 9
    MARKET_OPEN_MINUTE: Final[int] = 30
    MARKET_CLOSE_HOUR: Final[int] = 16
    MARKET_CLOSE_MINUTE: Final[int] = 0
    
    # Pre/post market
    PRE_MARKET_OPEN_HOUR: Final[int] = 4
    POST_MARKET_CLOSE_HOUR: Final[int] = 20
    
    # Cache TTL (in seconds)
    CACHE_TTL_SHORT: Final[int] = 60  # 1 minute
    CACHE_TTL_MEDIUM: Final[int] = 300  # 5 minutes
    CACHE_TTL_LONG: Final[int] = 3600  # 1 hour
    
    # Timeframes
    TIMEFRAME_1MIN: Final[str] = "1Min"
    TIMEFRAME_5MIN: Final[str] = "5Min"
    TIMEFRAME_15MIN: Final[str] = "15Min"
    TIMEFRAME_1HOUR: Final[str] = "1Hour"
    TIMEFRAME_4HOUR: Final[str] = "4Hour"
    TIMEFRAME_1DAY: Final[str] = "1Day"


class LoggingConstants:
    """Logging-related constants."""
    
    # Log levels
    LEVEL_DEBUG: Final[str] = "DEBUG"
    LEVEL_INFO: Final[str] = "INFO"
    LEVEL_WARNING: Final[str] = "WARNING"
    LEVEL_ERROR: Final[str] = "ERROR"
    LEVEL_CRITICAL: Final[str] = "CRITICAL"
    
    # Log formats
    DEFAULT_FORMAT: Final[str] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    DETAILED_FORMAT: Final[str] = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
    
    # Log file rotation
    MAX_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MB
    BACKUP_COUNT: Final[int] = 5


class SecurityConstants:
    """Security-related constants."""
    
    # Allowed hosts for localhost-only endpoints
    LOCALHOST_IPS: Final[tuple] = ("127.0.0.1", "localhost", "::1")
    
    # Token/Secret lengths
    MIN_SECRET_LENGTH: Final[int] = 32
    MIN_API_KEY_LENGTH: Final[int] = 20
    
    # Rate limiting
    MAX_REQUESTS_PER_MINUTE: Final[int] = 60
    MAX_REQUESTS_PER_HOUR: Final[int] = 1000


class SignalConstants:
    """Constants for trading signals."""
    
    # Signal types
    SIGNAL_LONG: Final[str] = "long"
    SIGNAL_SHORT: Final[str] = "short"
    SIGNAL_EXIT_LONG: Final[str] = "exit_long"
    SIGNAL_EXIT_SHORT: Final[str] = "exit_short"
    SIGNAL_CLOSE: Final[str] = "close"
    
    # Valid signals set
    VALID_SIGNALS: Final[set] = {
        SIGNAL_LONG,
        SIGNAL_SHORT,
        SIGNAL_EXIT_LONG,
        SIGNAL_EXIT_SHORT,
        SIGNAL_CLOSE
    }
    
    # Signal validation
    MIN_PRICE: Final[float] = 0.01
    MAX_PRICE: Final[float] = 1000000.0


class ErrorMessages:
    """Standardized error messages."""
    
    # API errors
    API_CONNECTION_ERROR: Final[str] = "Failed to connect to API"
    API_TIMEOUT_ERROR: Final[str] = "API request timed out"
    API_RATE_LIMIT_ERROR: Final[str] = "API rate limit exceeded"
    
    # Trading errors
    INSUFFICIENT_FUNDS: Final[str] = "Insufficient funds for order"
    INVALID_SYMBOL: Final[str] = "Invalid trading symbol"
    MARKET_CLOSED: Final[str] = "Market is closed"
    ORDER_REJECTED: Final[str] = "Order rejected by broker"
    
    # Configuration errors
    MISSING_CONFIG: Final[str] = "Required configuration missing"
    INVALID_CONFIG: Final[str] = "Invalid configuration value"
    
    # Security errors
    UNAUTHORIZED_ACCESS: Final[str] = "Unauthorized access attempt"
    FORBIDDEN_ACCESS: Final[str] = "Only accessible from localhost"
    INVALID_WEBHOOK_SECRET: Final[str] = "Invalid webhook secret"


class SuccessMessages:
    """Standardized success messages."""
    
    ORDER_PLACED: Final[str] = "Order placed successfully"
    ORDER_FILLED: Final[str] = "Order filled successfully"
    POSITION_OPENED: Final[str] = "Position opened"
    POSITION_CLOSED: Final[str] = "Position closed"
    DCA_EXECUTED: Final[str] = "DCA order executed"


class NgrokConstants:
    """Constants for ngrok tunnel management."""
    
    # API configuration
    API_PORT: Final[int] = 4040
    API_HOST: Final[str] = "localhost"
    API_TUNNELS_ENDPOINT: Final[str] = "/api/tunnels"
    
    # Timeout values (in seconds)
    API_TIMEOUT: Final[int] = 5
    EXTENDED_API_TIMEOUT: Final[int] = 10
    PROCESS_WAIT_TIMEOUT: Final[int] = 5
    
    # Retry configuration
    MAX_STARTUP_ATTEMPTS: Final[int] = 60
    MAX_URL_RETRIES: Final[int] = 3
    INITIAL_STARTUP_DELAY: Final[float] = 2.0


class TunnelConstants:
    """Constants for tunnel services (cloudflared, localtunnel)."""
    
    # Startup delays (in seconds)
    CLOUDFLARE_STARTUP_DELAY: Final[float] = 3.0
    LOCALTUNNEL_STARTUP_DELAY: Final[float] = 2.0
    POLL_INTERVAL: Final[float] = 1.0
    
    # Timeout values
    CLOUDFLARE_MAX_WAIT_SECONDS: Final[int] = 30
    LOCALTUNNEL_MAX_WAIT_SECONDS: Final[int] = 20
