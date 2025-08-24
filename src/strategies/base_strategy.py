"""
Base Strategy Abstract Class
Provides common functionality and enforces consistent interface for all trading strategies.
Follows SOLID principles and provides template method pattern.
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

from ..interfaces import IConfigurationManager, IMarketDataProvider
from ..core.logging_config import get_logger
from ..exceptions import TradingBotException, ConfigurationException


logger = get_logger(__name__)


class StrategyState(Enum):
    """Strategy execution states."""
    INITIALIZED = "initialized"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class StrategyMetrics:
    """Strategy performance metrics."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    average_trade_duration: float = 0.0
    last_updated: datetime = None
    
    def __post_init__(self):
        if self.last_updated is None:
            self.last_updated = datetime.utcnow()
    
    def update_win_rate(self):
        """Update win rate based on current trade counts."""
        if self.total_trades > 0:
            self.win_rate = self.winning_trades / self.total_trades
        else:
            self.win_rate = 0.0


class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    Implements common functionality and enforces consistent interface.
    """
    
    def __init__(self, config: IConfigurationManager, market_data: IMarketDataProvider):
        """
        Initialize base strategy.
        
        Args:
            config: Configuration manager instance
            market_data: Market data provider instance
        """
        self._config = config
        self._market_data = market_data
        self._state = StrategyState.INITIALIZED
        self._metrics = StrategyMetrics()
        self._logger = get_logger(self.__class__.__name__)
        
        # Protected attributes that subclasses can access
        self._validation_enabled = True
        self._performance_tracking = True
        
        # Load base configuration
        self._load_base_config()
        
        self._logger.info(f"{self.__class__.__name__} initialized")
    
    @property
    def state(self) -> StrategyState:
        """Get current strategy state."""
        return self._state
    
    @property
    def metrics(self) -> StrategyMetrics:
        """Get strategy performance metrics."""
        return self._metrics
    
    def _load_base_config(self) -> None:
        """Load base configuration common to all strategies."""
        try:
            self._validation_enabled = self._config.get_config("strategies.validation_enabled", True)
            self._performance_tracking = self._config.get_config("strategies.performance_tracking", True)
            
            # Log level for strategy-specific logging
            strategy_log_level = self._config.get_config("strategies.log_level", "INFO")
            
        except Exception as e:
            self._logger.warning(f"Failed to load base configuration: {e}")
            raise ConfigurationException(f"Base strategy configuration error: {e}")
    
    def _validate_inputs(self, **kwargs) -> None:
        """
        Enhanced input validation with comprehensive edge case handling.
        
        Handles edge cases that can occur during bot restarts, market gaps,
        or data inconsistencies.
        
        Raises:
            ValueError: If validation fails
            ValidationException: For complex validation errors
        """
        if not self._validation_enabled:
            return
        
        # Common validations with enhanced error messages
        for key, value in kwargs.items():
            if value is None:
                raise ValueError(f"Required parameter '{key}' cannot be None")
            
            # Enhanced price validation with edge case detection
            if key.endswith('_price'):
                if not isinstance(value, (int, float)):
                    raise ValueError(f"Price parameter '{key}' must be numeric, got: {type(value).__name__}")
                
                if value <= 0:
                    raise ValueError(f"Price parameter '{key}' must be positive, got: {value}")
                
                # Check for extreme values that might indicate data errors
                if value > 1000000:  # $1M per share - very unusual
                    self._logger.warning(f"⚠️ Extremely high price detected for {key}: ${value:,.2f}")
                elif value < 0.001:  # Less than 0.1 cent - very unusual
                    self._logger.warning(f"⚠️ Very low price detected for {key}: ${value:.6f}")
            
            # Enhanced symbol validation
            if key == 'symbol':
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"Symbol must be non-empty string, got: {value}")
                
                # Clean and validate symbol format
                cleaned_symbol = value.strip().upper()
                if not cleaned_symbol.replace('.', '').replace('-', '').replace('_', '').isalnum():
                    raise ValueError(f"Invalid symbol format: {value}")
                
                # Check for unreasonably long symbols (potential corruption)
                if len(cleaned_symbol) > 15:
                    self._logger.warning(f"⚠️ Unusually long symbol: {cleaned_symbol}")
            
            # Quantity validation
            if key in ['quantity', 'shares', 'size']:
                if not isinstance(value, (int, float)):
                    raise ValueError(f"Quantity parameter '{key}' must be numeric, got: {type(value).__name__}")
                
                if value <= 0:
                    raise ValueError(f"Quantity parameter '{key}' must be positive, got: {value}")
            
            # Percentage validation
            if key.endswith('_percent') or key.endswith('_percentage'):
                if not isinstance(value, (int, float)):
                    raise ValueError(f"Percentage parameter '{key}' must be numeric, got: {type(value).__name__}")
                
                if not (0 <= value <= 100):
                    self._logger.warning(f"⚠️ Unusual percentage value for {key}: {value}%")

    def _handle_strategy_error(self, error: Exception, context: str) -> Dict[str, Any]:
        """
        Centralized error handling for strategy execution.
        
        Provides recovery mechanisms and consistent error reporting.
        
        Args:
            error: The exception that occurred
            context: Context description of where the error occurred
            
        Returns:
            Error response dictionary with recovery suggestions
        """
        error_type = type(error).__name__
        error_message = str(error)
        
        # Log the error with context
        self._logger.error(f"Strategy error in {context}: {error_type} - {error_message}")
        
        # Change state to error if it's a critical failure
        if isinstance(error, (ConnectionError, TimeoutError)):
            self._change_state(StrategyState.ERROR, f"Connection/timeout error in {context}")
        elif isinstance(error, ValueError):
            self._change_state(StrategyState.ERROR, f"Validation error in {context}")
        else:
            self._logger.warning(f"Non-critical error in {context}, continuing execution")
        
        # Build error response with recovery suggestions
        error_response = {
            'success': False,
            'error_type': error_type,
            'error_message': error_message,
            'context': context,
            'timestamp': datetime.utcnow(),
            'strategy_state': self._state.value
        }
        
        # Add recovery suggestions based on error type
        if isinstance(error, ConnectionError):
            error_response['recovery_suggestions'] = [
                "Check network connectivity",
                "Verify API endpoints are accessible",
                "Consider implementing retry logic"
            ]
        elif isinstance(error, TimeoutError):
            error_response['recovery_suggestions'] = [
                "Increase timeout values",
                "Check system performance",
                "Verify data provider response times"
            ]
        elif isinstance(error, ValueError):
            error_response['recovery_suggestions'] = [
                "Validate input parameters",
                "Check data format and types",
                "Review configuration settings"
            ]
        else:
            error_response['recovery_suggestions'] = [
                "Review strategy logs for details",
                "Check system resources",
                "Consider restarting the strategy"
            ]
        
        return error_response

    def _safe_execute(self, operation_name: str, operation_func, *args, **kwargs) -> Any:
        """
        Safely execute a strategy operation with error handling and recovery.
        
        Args:
            operation_name: Description of the operation being performed
            operation_func: Function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Operation result or None if failed
        """
        try:
            self._logger.debug(f"Executing {operation_name}")
            result = operation_func(*args, **kwargs)
            self._logger.debug(f"✅ {operation_name} completed successfully")
            return result
            
        except Exception as e:
            error_response = self._handle_strategy_error(e, operation_name)
            self._logger.error(f"❌ {operation_name} failed: {error_response['error_message']}")
            
            # Decide whether to re-raise or return None based on error type
            if isinstance(e, (ValueError, TypeError)):
                # Re-raise validation errors as they indicate programming issues
                raise
            else:
                # Return None for runtime errors to allow graceful degradation
                return None

    async def _safe_async_execute(self, operation_name: str, operation_func, *args, **kwargs) -> Any:
        """
        Safely execute an async strategy operation with error handling and recovery.
        
        Args:
            operation_name: Description of the operation being performed
            operation_func: Async function to execute
            *args: Positional arguments for the function
            **kwargs: Keyword arguments for the function
            
        Returns:
            Operation result or None if failed
        """
        try:
            self._logger.debug(f"Executing async {operation_name}")
            result = await operation_func(*args, **kwargs)
            self._logger.debug(f"✅ Async {operation_name} completed successfully")
            return result
            
        except asyncio.TimeoutError:
            error_response = self._handle_strategy_error(
                TimeoutError(f"Operation {operation_name} timed out"), operation_name
            )
            self._logger.error(f"⏰ {operation_name} timed out")
            return None
            
        except Exception as e:
            error_response = self._handle_strategy_error(e, operation_name)
            self._logger.error(f"❌ Async {operation_name} failed: {error_response['error_message']}")
            
            # Decide whether to re-raise or return None based on error type
            if isinstance(e, (ValueError, TypeError)):
                # Re-raise validation errors as they indicate programming issues
                raise
            else:
                # Return None for runtime errors to allow graceful degradation
                return None
    
    def _update_metrics(self, trade_result: Dict[str, Any]) -> None:
        """
        Update strategy performance metrics.
        
        Args:
            trade_result: Dictionary containing trade outcome data
        """
        if not self._performance_tracking:
            return
        
        try:
            self._metrics.total_trades += 1
            
            pnl = trade_result.get('pnl', 0.0)
            self._metrics.total_pnl += pnl
            
            if pnl > 0:
                self._metrics.winning_trades += 1
            elif pnl < 0:
                self._metrics.losing_trades += 1
            
            # Update win rate
            self._metrics.update_win_rate()
            
            # Update timestamp
            self._metrics.last_updated = datetime.utcnow()
            
            self._logger.debug(f"Metrics updated: PnL={pnl:.2f}, Win Rate={self._metrics.win_rate:.2%}")
            
        except Exception as e:
            self._logger.warning(f"Failed to update metrics: {e}")
    
    def _change_state(self, new_state: StrategyState, reason: str = "") -> None:
        """
        Change strategy state with logging.
        
        Args:
            new_state: New state to transition to
            reason: Optional reason for state change
        """
        if self._state != new_state:
            old_state = self._state
            self._state = new_state
            self._logger.info(f"State changed: {old_state.value} -> {new_state.value}" + 
                            (f" (Reason: {reason})" if reason else ""))
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize strategy. Must be implemented by subclasses.
        
        Returns:
            True if initialization successful
        """
        pass
    
    @abstractmethod
    async def execute(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute strategy logic. Must be implemented by subclasses.
        
        Args:
            data: Input data for strategy execution
            
        Returns:
            Strategy execution results
        """
        pass
    
    @abstractmethod
    async def cleanup(self) -> None:
        """
        Cleanup strategy resources. Must be implemented by subclasses.
        """
        pass
    
    def get_config_value(self, key: str, default: Any = None) -> Any:
        """
        Safe method to get configuration values with fallback.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        try:
            return self._config.get_config(key, default)
        except Exception as e:
            self._logger.warning(f"Failed to get config '{key}': {e}")
            return default
