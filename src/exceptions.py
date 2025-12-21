"""
Core exceptions for the trading bot system.
Provides specific exception types for different error scenarios.
"""


class TradingBotException(Exception):
    """Base exception for all trading bot errors."""
    
    def __init__(self, message: str, error_code: str = None):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


class SignalProcessingException(TradingBotException):
    """Exception raised during signal processing."""
    pass


class OrderExecutionException(TradingBotException):
    """Exception raised during order execution."""
    pass


class MarketDataException(TradingBotException):
    """Exception raised when market data is unavailable or invalid."""
    pass


class RiskManagementException(TradingBotException):
    """Exception raised when risk limits are exceeded."""
    pass


class ConfigurationException(TradingBotException):
    """Exception raised for configuration-related errors."""
    pass


class APIException(TradingBotException):
    """Exception raised for external API errors."""
    
    def __init__(self, message: str, status_code: int = None, 
                 response_data: dict = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class ValidationException(TradingBotException):
    """Exception raised for validation errors."""
    pass


class InsufficientFundsException(TradingBotException):
    """Exception raised when there are insufficient funds for a trade."""
    pass


class PositionNotFoundException(TradingBotException):
    """Exception raised when a position is not found."""
    pass


class OrderException(TradingBotException):
    """Exception raised for order-related errors."""
    pass


class TradingException(TradingBotException):
    """Exception raised for general trading errors."""
    pass


class RiskException(TradingBotException):
    """Exception raised for risk management errors."""
    pass


class RiskLimitException(TradingBotException):
    """Exception raised when risk limits are exceeded."""
    pass


class SignalException(TradingBotException):
    """Exception raised for signal processing errors."""
    pass


class ConnectionException(TradingBotException):
    """Exception raised for connection errors."""
    pass


class BrokerException(TradingBotException):
    """Base exception for all broker-related errors."""
    pass


class BrokerConnectionException(BrokerException):
    """Exception raised when connection to broker fails."""
    pass


class BrokerOrderException(BrokerException, OrderExecutionException):
    """Exception raised when a broker rejects an order or fails to process it."""
    pass


class BrokerPermissionException(BrokerException):
    """Exception raised when broker denies permission (e.g. insufficient funds, short selling restricted)."""
    pass


class BrokerAPIException(BrokerException, APIException):
    """Exception raised when broker API returns an error (e.g. rate limit, server error)."""
    pass
