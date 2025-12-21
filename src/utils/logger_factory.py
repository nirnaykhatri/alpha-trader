"""
Logger Factory

Centralized logger initialization to eliminate duplication across 15+ files.
Provides consistent logger configuration with structured logging support.
"""

import logging
from typing import Optional, Dict
from src.core.logging_config import get_logger as _get_core_logger


class LoggerFactory:
    """
    Factory for creating and managing loggers across the application.
    
    Implements singleton pattern for each logger name to ensure
    consistent configuration and avoid duplicate logger instances.
    
    Example:
        >>> from src.utils.logger_factory import LoggerFactory
        >>> logger = LoggerFactory.get_logger(__name__)
        >>> logger.info("Module initialized")
    """
    
    _loggers: Dict[str, logging.Logger] = {}
    
    @classmethod
    def get_logger(
        cls,
        name: str,
        level: Optional[int] = None,
        component: Optional[str] = None
    ) -> logging.Logger:
        """
        Get or create a logger with the specified name.
        
        Args:
            name: Logger name (typically __name__)
            level: Optional logging level (defaults to config setting)
            component: Optional component name for structured logging
            
        Returns:
            Configured logger instance
            
        Example:
            >>> logger = LoggerFactory.get_logger(__name__)
            >>> logger.info("Processing started", extra={'order_id': '123'})
            
            >>> # With custom level
            >>> debug_logger = LoggerFactory.get_logger(__name__, level=logging.DEBUG)
            
            >>> # With component tag
            >>> strategy_logger = LoggerFactory.get_logger(
            ...     __name__, 
            ...     component='AdvancedStrategy'
            ... )
        """
        # Check if logger already exists
        if name in cls._loggers:
            logger = cls._loggers[name]
            
            # Update level if specified
            if level is not None and logger.level != level:
                logger.setLevel(level)
                
            return logger
        
        # Create new logger using core logging config
        logger = _get_core_logger(name)
        
        # Set custom level if specified
        if level is not None:
            logger.setLevel(level)
        
        # Add component filter if specified
        if component:
            logger = logging.LoggerAdapter(logger, {'component': component})
        
        # Cache the logger
        cls._loggers[name] = logger
        
        return logger
    
    @classmethod
    def set_level(cls, name: str, level: int) -> None:
        """
        Set logging level for a specific logger.
        
        Args:
            name: Logger name
            level: Logging level (e.g., logging.DEBUG, logging.INFO)
            
        Example:
            >>> LoggerFactory.set_level('src.strategies.advanced_strategy', logging.DEBUG)
        """
        if name in cls._loggers:
            cls._loggers[name].setLevel(level)
    
    @classmethod
    def set_all_levels(cls, level: int) -> None:
        """
        Set logging level for all managed loggers.
        
        Args:
            level: Logging level to apply to all loggers
            
        Example:
            >>> LoggerFactory.set_all_levels(logging.WARNING)
        """
        for logger in cls._loggers.values():
            logger.setLevel(level)
    
    @classmethod
    def get_all_loggers(cls) -> Dict[str, logging.Logger]:
        """
        Get all managed loggers.
        
        Returns:
            Dictionary mapping logger names to logger instances
            
        Example:
            >>> all_loggers = LoggerFactory.get_all_loggers()
            >>> for name, logger in all_loggers.items():
            ...     print(f"{name}: {logger.level}")
        """
        return cls._loggers.copy()
    
    @classmethod
    def reset(cls) -> None:
        """
        Reset factory state (useful for testing).
        
        Clears all cached loggers.
        """
        cls._loggers.clear()


# Convenience function for backward compatibility
def get_logger(name: str, **kwargs) -> logging.Logger:
    """
    Convenience function for getting a logger.
    
    Args:
        name: Logger name (typically __name__)
        **kwargs: Additional arguments passed to LoggerFactory.get_logger()
        
    Returns:
        Configured logger instance
        
    Example:
        >>> from src.utils.logger_factory import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Processing started")
    """
    return LoggerFactory.get_logger(name, **kwargs)
