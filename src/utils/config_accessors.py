"""
Configuration Accessor Mixin.

Provides typed property accessors for commonly accessed configuration values.
Classes can inherit from this mixin to get type-safe config access.

Author: Trading Bot Team
Version: 2.0.0
"""

from typing import Optional, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from src.core.configuration import ConfigManager


# =============================================================================
# Configuration Data Classes
# =============================================================================

@dataclass
class RiskConfig:
    """Risk management configuration."""
    max_position_size: float = 10000.0
    max_daily_loss: float = 500.0
    max_open_positions: int = 5
    max_drawdown_percent: float = 5.0
    risk_per_trade: float = 0.02
    stop_loss_percent: float = 5.0


@dataclass
class TradingConfig:
    """Trading execution configuration."""
    default_quantity: int = 100
    order_type: str = "limit"
    limit_order_offset: float = 0.001
    market_order_slippage: float = 0.002
    order_timeout_minutes: int = 5
    aggressive_order_timeout_minutes: int = 5
    max_price_adjustment_percent: float = 0.5
    max_daily_trades: int = 50


@dataclass
class MonitoringConfig:
    """Monitoring configuration."""
    order_monitoring_interval: int = 5
    position_monitoring_interval: int = 10
    health_check_interval: int = 30


@dataclass
class PerformanceConfig:
    """Performance tuning configuration."""
    max_concurrent_orders: int = 5
    max_concurrent_price_fetches: int = 10
    cache_ttl_seconds: int = 300


# =============================================================================
# Configuration Accessor Mixin
# =============================================================================

class ConfigAccessorMixin:
    """
    Mixin providing typed access to configuration values.
    
    Classes that use this mixin must have a `config` or `_config` attribute
    that implements `get_config(key, default)`.
    
    Usage:
        class TradingBot(ConfigAccessorMixin):
            def __init__(self, config: ConfigManager):
                self._config = config
            
            def execute_trade(self):
                # Use typed accessor
                if self.risk_config.max_position_size < order_size:
                    raise ValueError("Order too large")
    
    Benefits:
        - Type-safe access to configuration values
        - IDE auto-completion for config properties
        - Centralized defaults
        - Easier testing (mock the property, not raw config calls)
    """
    
    @property
    def _config_manager(self) -> "ConfigManager":
        """Get the configuration manager."""
        if hasattr(self, 'config'):
            return getattr(self, 'config')
        if hasattr(self, '_config'):
            return getattr(self, '_config')
        raise AttributeError(
            "ConfigAccessorMixin requires a 'config' or '_config' attribute"
        )
    
    # =========================================================================
    # Risk Configuration
    # =========================================================================
    
    @property
    def risk_config(self) -> RiskConfig:
        """Get risk configuration with typed access."""
        cfg = self._config_manager
        return RiskConfig(
            max_position_size=float(cfg.get_config("risk.max_position_size", 10000.0)),
            max_daily_loss=float(cfg.get_config("risk.max_daily_loss", 500.0)),
            max_open_positions=int(cfg.get_config("risk.max_open_positions", 5)),
            max_drawdown_percent=float(cfg.get_config("risk.max_drawdown_percent", 5.0)),
            risk_per_trade=float(cfg.get_config("trading.risk_per_trade", 0.02)),
            stop_loss_percent=float(cfg.get_config("risk.stop_loss_percent", 5.0)),
        )
    
    # =========================================================================
    # Trading Configuration
    # =========================================================================
    
    @property
    def trading_config(self) -> TradingConfig:
        """Get trading configuration with typed access."""
        cfg = self._config_manager
        return TradingConfig(
            default_quantity=int(cfg.get_config("trading.default_quantity", 100)),
            order_type=str(cfg.get_config("trading.order_type", "limit")),
            limit_order_offset=float(cfg.get_config("trading.limit_order_offset", 0.001)),
            market_order_slippage=float(cfg.get_config("trading.market_order_slippage", 0.002)),
            order_timeout_minutes=int(cfg.get_config("trading.order_timeout_minutes", 5)),
            aggressive_order_timeout_minutes=int(cfg.get_config("trading.aggressive_order_timeout_minutes", 5)),
            max_price_adjustment_percent=float(cfg.get_config("trading.max_price_adjustment_percent", 0.5)),
            max_daily_trades=int(cfg.get_config("trading.max_daily_trades", 50)),
        )
    
    # =========================================================================
    # Monitoring Configuration
    # =========================================================================
    
    @property
    def monitoring_config(self) -> MonitoringConfig:
        """Get monitoring configuration with typed access."""
        cfg = self._config_manager
        return MonitoringConfig(
            order_monitoring_interval=int(cfg.get_config("monitoring.order_monitoring_interval", 5)),
            position_monitoring_interval=int(cfg.get_config("monitoring.position_monitoring_interval", 10)),
            health_check_interval=int(cfg.get_config("monitoring.health_check_interval", 30)),
        )
    
    # =========================================================================
    # Performance Configuration
    # =========================================================================
    
    @property
    def performance_config(self) -> PerformanceConfig:
        """Get performance tuning configuration with typed access."""
        cfg = self._config_manager
        return PerformanceConfig(
            max_concurrent_orders=int(cfg.get_config("performance.max_concurrent_orders", 5)),
            max_concurrent_price_fetches=int(cfg.get_config("performance.max_concurrent_price_fetches", 10)),
            cache_ttl_seconds=int(cfg.get_config("performance.cache_ttl_seconds", 300)),
        )
    
    # =========================================================================
    # Individual Typed Accessors
    # =========================================================================
    
    @property
    def log_level(self) -> str:
        """Get logging level."""
        return str(self._config_manager.get_config("logging.level", "INFO"))
    
    @property
    def is_paper_trading(self) -> bool:
        """Check if paper trading mode is enabled."""
        return bool(self._config_manager.get_config("alpaca.paper_trading", True))
    
    @property
    def webhook_host(self) -> str:
        """Get webhook host."""
        return str(self._config_manager.get_config("api.webhook.host", "0.0.0.0"))
    
    @property
    def webhook_port(self) -> int:
        """Get webhook port."""
        return int(self._config_manager.get_config("api.webhook.port", 8080))
    
    @property
    def default_broker(self) -> str:
        """Get default broker."""
        return str(self._config_manager.get_config("broker.default", "alpaca"))


# =============================================================================
# Async Configuration Accessor Mixin
# =============================================================================

class AsyncConfigAccessorMixin:
    """
    Async version of ConfigAccessorMixin for Azure-native configuration.
    
    Use this for components that use IAsyncConfigurationManager.
    """
    
    @property
    def _async_config_manager(self):
        """Get the async configuration manager."""
        if hasattr(self, 'config'):
            return getattr(self, 'config')
        if hasattr(self, '_config'):
            return getattr(self, '_config')
        raise AttributeError(
            "AsyncConfigAccessorMixin requires a 'config' or '_config' attribute"
        )
    
    async def get_risk_config(self) -> RiskConfig:
        """Get risk configuration with typed access (async)."""
        cfg = self._async_config_manager
        return RiskConfig(
            max_position_size=float(await cfg.get_config("risk.max_position_size", 10000.0)),
            max_daily_loss=float(await cfg.get_config("risk.max_daily_loss", 500.0)),
            max_open_positions=int(await cfg.get_config("risk.max_open_positions", 5)),
            max_drawdown_percent=float(await cfg.get_config("risk.max_drawdown_percent", 5.0)),
            risk_per_trade=float(await cfg.get_config("trading.risk_per_trade", 0.02)),
            stop_loss_percent=float(await cfg.get_config("risk.stop_loss_percent", 5.0)),
        )
    
    async def get_trading_config(self) -> TradingConfig:
        """Get trading configuration with typed access (async)."""
        cfg = self._async_config_manager
        return TradingConfig(
            default_quantity=int(await cfg.get_config("trading.default_quantity", 100)),
            order_type=str(await cfg.get_config("trading.order_type", "limit")),
            limit_order_offset=float(await cfg.get_config("trading.limit_order_offset", 0.001)),
            market_order_slippage=float(await cfg.get_config("trading.market_order_slippage", 0.002)),
            order_timeout_minutes=int(await cfg.get_config("trading.order_timeout_minutes", 5)),
            aggressive_order_timeout_minutes=int(await cfg.get_config("trading.aggressive_order_timeout_minutes", 5)),
            max_price_adjustment_percent=float(await cfg.get_config("trading.max_price_adjustment_percent", 0.5)),
            max_daily_trades=int(await cfg.get_config("trading.max_daily_trades", 50)),
        )
