"""
Logging configuration for the trading bot system.
"""

import logging
import sys
import os
import json
from typing import Optional
from pathlib import Path
from datetime import datetime


def configure_windows_console():
    """Configure Windows console for better Unicode support."""
    if sys.platform == "win32":
        try:
            # Set console code page to UTF-8
            os.system("chcp 65001 > nul")
            # Try to set environment variable for UTF-8
            os.environ["PYTHONIOENCODING"] = "utf-8"
        except Exception:
            pass


class UnicodeStreamHandler(logging.StreamHandler):
    """Stream handler that safely handles Unicode characters on Windows."""
    
    def emit(self, record):
        try:
            super().emit(record)
        except UnicodeEncodeError:
            # If Unicode encoding fails, replace problematic characters
            try:
                msg = self.format(record)
                safe_msg = msg.encode('ascii', 'replace').decode('ascii')
                self.stream.write(safe_msg + self.terminator)
                self.flush()
            except Exception:
                # Last resort: just print the error info
                self.stream.write(f"[ENCODING ERROR] {record.levelname}: <message with unicode characters>\n")
                self.flush()


class SafeJSONFormatter(logging.Formatter):
    """JSON formatter that safely handles Unicode characters."""
    
    def format(self, record):
        try:
            # Create timestamp
            timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
            
            # Get safe message
            try:
                message = str(record.getMessage())
            except Exception:
                message = "<error formatting message>"
            
            # Create JSON object
            log_data = {
                "timestamp": timestamp,
                "level": record.levelname,
                "logger": record.name,
                "message": message,
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno
            }
            
            return json.dumps(log_data, ensure_ascii=False)
        
        except Exception:
            # Fallback: create simple safe JSON
            timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
            safe_message = str(record.getMessage()).encode('ascii', 'replace').decode('ascii')
            
            return json.dumps({
                "timestamp": timestamp,
                "level": record.levelname,
                "logger": record.name,
                "message": safe_message,
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno
            }, ensure_ascii=True)


def setup_logging(
    level: str = "INFO",
    format_type: str = "json",
    log_file: Optional[str] = None
) -> None:
    """
    Setup logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_type: Format type ('json' or 'text')
        log_file: Optional log file path
    """
    # Configure Windows console for better Unicode support
    configure_windows_console()
    
    # Convert string level to logging level
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create formatter
    if format_type.lower() == "json":
        formatter = SafeJSONFormatter()
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler with Unicode support
    console_handler = UnicodeStreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_path, encoding='utf-8')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Setup specific loggers
    setup_specific_loggers(numeric_level)


def setup_specific_loggers(level: int) -> None:
    """Setup specific loggers for different modules."""
    loggers = [
        "trading_bot",
        "trading_bot.core",
        "trading_bot.signals",
        "trading_bot.trading",
        "trading_bot.strategies",
        "alpaca",
        "uvicorn",
        "fastapi"
    ]
    
    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(level)
        logger.propagate = True


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)

# Configure Windows console for better Unicode support
configure_windows_console()
