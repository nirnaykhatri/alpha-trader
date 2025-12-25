"""
Core exceptions for the trading bot system.
Provides specific exception types for different error scenarios.

.. deprecated:: 2.0.0
    This module is deprecated. Use :class:`src.domain.errors.DomainError`
    for new code. The DomainError class provides:
    
    - Machine-readable error codes (ErrorCode enum)
    - Structured context for debugging
    - Automatic Prometheus metrics emission
    - Exception chaining support
    
    Migration example::
    
        # Old (deprecated):
        raise OrderExecutionException("Order failed")
        
        # New (recommended):
        from src.domain.errors import DomainError, ErrorCode
        raise DomainError(
            code=ErrorCode.ORDER_PLACEMENT_FAILED,
            detail="Order failed",
            context={'symbol': 'AAPL'}
        )
    
    This module will be removed in version 3.0.0.
"""

import warnings


def _emit_deprecation_warning(class_name: str) -> None:
    """Emit deprecation warning for legacy exception usage."""
    warnings.warn(
        f"{class_name} is deprecated. Use src.domain.errors.DomainError instead. "
        "See src.exceptions module docstring for migration guide.",
        DeprecationWarning,
        stacklevel=4  # Show caller's caller's location
    )


class TradingBotException(Exception):
    """
    Base exception for all trading bot errors.
    
    .. deprecated:: 2.0.0
        Use :class:`src.domain.errors.DomainError` instead.
    """
    
    def __init__(self, message: str, error_code: str = None):
        _emit_deprecation_warning(self.__class__.__name__)
        super().__init__(message)
        self.error_code = error_code
        self.message = message


class SignalProcessingException(TradingBotException):
    """
    Exception raised during signal processing.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.SIGNAL_INVALID, ...)`` instead.
    """
    pass


class OrderExecutionException(TradingBotException):
    """
    Exception raised during order execution.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.ORDER_PLACEMENT_FAILED, ...)`` instead.
    """
    pass


class MarketDataException(TradingBotException):
    """
    Exception raised when market data is unavailable or invalid.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.MARKET_DATA_UNAVAILABLE, ...)`` instead.
    """
    pass


class RiskManagementException(TradingBotException):
    """
    Exception raised when risk limits are exceeded.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.RISK_LIMIT_EXCEEDED, ...)`` instead.
    """
    pass


class ConfigurationException(TradingBotException):
    """
    Exception raised for configuration-related errors.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.CONFIG_INVALID, ...)`` instead.
    """
    pass


class APIException(TradingBotException):
    """
    Exception raised for external API errors.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.EXTERNAL_API_ERROR, ...)`` instead.
    """
    
    def __init__(self, message: str, status_code: int = None, 
                 response_data: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class ValidationException(TradingBotException):
    """
    Exception raised for validation errors.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.VALIDATION_FAILED, ...)`` instead.
    """
    pass


class InsufficientFundsException(TradingBotException):
    """
    Exception raised when there are insufficient funds for a trade.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.ORDER_INSUFFICIENT_FUNDS, ...)`` instead.
    """
    pass


class PositionNotFoundException(TradingBotException):
    """
    Exception raised when a position is not found.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.POSITION_NOT_FOUND, ...)`` instead.
    """
    pass


class OrderException(TradingBotException):
    """
    Exception raised for order-related errors.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.ORDER_PLACEMENT_FAILED, ...)`` instead.
    """
    pass


class TradingException(TradingBotException):
    """
    Exception raised for general trading errors.
    
    .. deprecated:: 2.0.0
        Use appropriate ``DomainError`` with specific ``ErrorCode`` instead.
    """
    pass


class RiskException(TradingBotException):
    """
    Exception raised for risk management errors.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.RISK_LIMIT_EXCEEDED, ...)`` instead.
    """
    pass


class RiskLimitException(TradingBotException):
    """
    Exception raised when risk limits are exceeded.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.RISK_LIMIT_EXCEEDED, ...)`` instead.
    """
    pass


class SignalException(TradingBotException):
    """
    Exception raised for signal processing errors.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.SIGNAL_INVALID, ...)`` instead.
    """
    pass


class ConnectionException(TradingBotException):
    """
    Exception raised for connection errors.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.EXTERNAL_API_ERROR, ...)`` instead.
    """
    pass


class BrokerException(TradingBotException):
    """
    Base exception for all broker-related errors.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.ORDER_BROKER_REJECTED, ...)`` instead.
    """
    pass


class BrokerConnectionException(BrokerException):
    """
    Exception raised when connection to broker fails.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.EXTERNAL_API_ERROR, ...)`` instead.
    """
    pass


class BrokerOrderException(BrokerException, OrderExecutionException):
    """
    Exception raised when a broker rejects an order or fails to process it.
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.ORDER_BROKER_REJECTED, ...)`` instead.
    """
    pass


class BrokerPermissionException(BrokerException):
    """
    Exception raised when broker denies permission (e.g. insufficient funds, short selling restricted).
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.ORDER_INSUFFICIENT_FUNDS, ...)`` instead.
    """
    pass


class BrokerAPIException(BrokerException, APIException):
    """
    Exception raised when broker API returns an error (e.g. rate limit, server error).
    
    .. deprecated:: 2.0.0
        Use ``DomainError(code=ErrorCode.EXTERNAL_API_ERROR, ...)`` instead.
    """
    pass
