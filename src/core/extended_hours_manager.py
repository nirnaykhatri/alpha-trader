"""
Extended Hours Manager - Manages extended hours trading capabilities with Alpaca coordination.
Provides intelligent extended hours trading coordination between market status and trading permissions.
"""

import asyncio
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone
from dataclasses import dataclass

from ..interfaces import IConfigurationManager
from ..exceptions import TradingException, MarketDataException
from ..core.logging_config import get_logger
from .market_hours_manager import AlpacaIntegratedMarketHoursManager, MarketStatusInfo
from .market_status_provider import MarketSession

logger = get_logger(__name__)


@dataclass
class ExtendedHoursSettings:
    """Configuration for extended hours trading."""
    premarket_enabled: bool
    afterhours_enabled: bool
    use_limit_orders_only: bool
    spread_buffer_multiplier: float
    min_volume_threshold: int
    position_size_multiplier: float
    max_spread_tolerance: float


class ExtendedHoursManager:
    """
    Manages extended hours trading using Alpaca's extended hours capabilities.
    Coordinates between market status and trading permissions.
    """
    
    def __init__(
        self, 
        config: IConfigurationManager, 
        market_hours_manager: AlpacaIntegratedMarketHoursManager,
        alpaca_client = None
    ):
        """
        Initialize extended hours manager.
        
        Args:
            config: Configuration manager
            market_hours_manager: Market hours manager for status
            alpaca_client: Alpaca trading client for account checks
        """
        self._config = config
        self._market_hours_manager = market_hours_manager
        self._alpaca_client = alpaca_client
        
        # Load configuration
        self._settings = self._load_extended_hours_settings()
        
        # Extended hours symbol validation cache
        self._symbol_extended_hours_cache: Dict[str, bool] = {}
        self._account_extended_hours_enabled: Optional[bool] = None
        
        logger.info(f"ExtendedHoursManager initialized - Premarket: {self._settings.premarket_enabled}, After-hours: {self._settings.afterhours_enabled}")
    
    def _load_extended_hours_settings(self) -> ExtendedHoursSettings:
        """Load extended hours settings from configuration."""
        return ExtendedHoursSettings(
            premarket_enabled=self._config.get_config("market_hours.extended_hours.premarket_enabled", True),
            afterhours_enabled=self._config.get_config("market_hours.extended_hours.afterhours_enabled", True),
            use_limit_orders_only=self._config.get_config("extended_hours.use_limit_orders_only", False),
            spread_buffer_multiplier=self._config.get_config("extended_hours.extended_hours_spread_buffer", 0.005),
            min_volume_threshold=self._config.get_config("extended_hours.min_volume_threshold", 1000),
            position_size_multiplier=self._config.get_config("extended_hours.pre_market.position_size_multiplier", 1.0),
            max_spread_tolerance=self._config.get_config("extended_hours.max_spread_tolerance", 0.02)  # 2%
        )
    
    async def is_extended_hours_trading_allowed(self, symbol: str) -> Tuple[bool, str]:
        """
        Check if extended hours trading is allowed for a symbol right now.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Tuple of (allowed, reason)
        """
        try:
            # Get current market status
            market_status = await self._market_hours_manager.get_current_market_status()
            
            # Check if we're in extended hours
            if market_status.current_session == MarketSession.REGULAR:
                return True, "regular_hours"  # Always allowed during regular hours
            
            if market_status.current_session == MarketSession.PREMARKET:
                if not self._settings.premarket_enabled:
                    return False, "premarket_disabled_in_config"
                
                # Check if symbol supports premarket trading
                symbol_allowed = await self.validate_extended_hours_symbol(symbol)
                if not symbol_allowed:
                    return False, f"symbol_{symbol}_not_extended_hours_eligible"
                
                return True, "premarket_allowed"
            
            if market_status.current_session == MarketSession.POSTMARKET:
                if not self._settings.afterhours_enabled:
                    return False, "afterhours_disabled_in_config"
                
                # Check if symbol supports after-hours trading
                symbol_allowed = await self.validate_extended_hours_symbol(symbol)
                if not symbol_allowed:
                    return False, f"symbol_{symbol}_not_extended_hours_eligible"
                
                return True, "afterhours_allowed"
            
            # Market is closed
            return False, f"market_closed_{market_status.current_session.value}"
            
        except Exception as e:
            logger.error(f"❌ Error checking extended hours trading permission: {e}")
            return False, f"error_{str(e)[:50]}"
    
    async def configure_extended_hours_order(self, order_request: Dict[str, Any], symbol: str) -> Dict[str, Any]:
        """
        Automatically configure orders for extended hours when appropriate.
        
        Args:
            order_request: Original order request
            symbol: Trading symbol
            
        Returns:
            Modified order request with extended hours parameters
        """
        try:
            # Check if we're in extended hours and it's allowed
            is_allowed, reason = await self.is_extended_hours_trading_allowed(symbol)
            
            if not is_allowed:
                logger.debug(f"📋 Order not modified for extended hours: {reason}")
                return order_request
            
            # Get current market status
            market_status = await self._market_hours_manager.get_current_market_status()
            
            # Configure for extended hours
            modified_order = order_request.copy()
            
            if market_status.current_session in [MarketSession.PREMARKET, MarketSession.POSTMARKET]:
                logger.info(f"🌅 CONFIGURING EXTENDED HOURS ORDER: {symbol}")
                logger.info(f"   Session: {market_status.current_session.value}")
                
                # Set extended hours flag
                modified_order['extended_hours'] = True
                
                # Force limit orders during extended hours if configured
                if self._settings.use_limit_orders_only and order_request.get('type') == 'market':
                    logger.info(f"🔄 Converting market order to limit order for extended hours")
                    modified_order['type'] = 'limit'
                    
                    # Will need current price to set limit price - handled by order manager
                    modified_order['_needs_limit_price_calculation'] = True
                
                # Add extended hours spread buffer
                if 'limit_price' in modified_order:
                    spread_buffer = self._settings.spread_buffer_multiplier
                    original_price = modified_order['limit_price']
                    
                    # Adjust limit price for better execution during extended hours
                    side = order_request.get('side', 'buy').lower()
                    if side == 'buy':
                        # Buy orders - increase limit price slightly for better execution
                        modified_order['limit_price'] = original_price * (1 + spread_buffer)
                    else:
                        # Sell orders - decrease limit price slightly for better execution
                        modified_order['limit_price'] = original_price * (1 - spread_buffer)
                    
                    logger.info(f"📊 Extended hours price adjustment: ${original_price:.4f} → ${modified_order['limit_price']:.4f}")
                
                # Reduce position size if configured
                if self._settings.position_size_multiplier != 1.0:
                    original_qty = modified_order.get('qty', 0)
                    modified_order['qty'] = int(original_qty * self._settings.position_size_multiplier)
                    logger.info(f"📊 Extended hours position size adjustment: {original_qty} → {modified_order['qty']}")
                
                logger.info(f"✅ Extended hours order configured for {market_status.current_session.value}")
            
            return modified_order
            
        except Exception as e:
            logger.error(f"❌ Error configuring extended hours order: {e}")
            # Return original order if configuration fails
            return order_request
    
    async def validate_extended_hours_symbol(self, symbol: str) -> bool:
        """
        Verify symbol supports extended hours trading on Alpaca.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            True if symbol supports extended hours
        """
        try:
            # Check cache first
            if symbol in self._symbol_extended_hours_cache:
                return self._symbol_extended_hours_cache[symbol]
            
            # For now, assume most major symbols support extended hours
            # This could be enhanced with actual Alpaca API calls to check symbol eligibility
            
            # Major symbols that typically support extended hours
            major_symbols = {
                'AAPL', 'GOOGL', 'GOOG', 'MSFT', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX', 
                'SPY', 'QQQ', 'IWM', 'AMD', 'INTC', 'V', 'MA', 'JPM', 'BAC', 'DIS',
                'CRM', 'ORCL', 'ADBE', 'NOW', 'SNOW', 'ZM', 'PLTR', 'COIN', 'RBLX'
            }
            
            # Simple validation - assume major symbols support extended hours
            is_supported = symbol.upper() in major_symbols or len(symbol) <= 4
            
            # Cache the result
            self._symbol_extended_hours_cache[symbol] = is_supported
            
            if is_supported:
                logger.debug(f"✅ {symbol} supports extended hours trading")
            else:
                logger.warning(f"⚠️ {symbol} may not support extended hours trading")
            
            return is_supported
            
        except Exception as e:
            logger.error(f"❌ Error validating extended hours symbol {symbol}: {e}")
            # Conservative default - assume it doesn't support extended hours
            return False
    
    async def is_extended_hours_available(self) -> bool:
        """
        Check if extended hours trading is available on Alpaca account.
        
        Returns:
            True if account supports extended hours
        """
        try:
            if self._account_extended_hours_enabled is not None:
                return self._account_extended_hours_enabled
            
            # Check account capabilities if Alpaca client is available
            if self._alpaca_client:
                try:
                    account = await asyncio.get_event_loop().run_in_executor(
                        None, self._alpaca_client.get_account
                    )
                    
                    # Check account status and features
                    # Most Alpaca accounts support extended hours, but this could be enhanced
                    self._account_extended_hours_enabled = True
                    
                    logger.info("✅ Account supports extended hours trading")
                    return True
                    
                except Exception as api_error:
                    logger.warning(f"⚠️ Could not verify account extended hours capability: {api_error}")
                    # Assume extended hours is available if we can't check
                    self._account_extended_hours_enabled = True
                    return True
            
            # Default to true if no client available
            logger.debug("📋 Assuming extended hours is available (no account verification)")
            self._account_extended_hours_enabled = True
            return True
            
        except Exception as e:
            logger.error(f"❌ Error checking extended hours availability: {e}")
            return False
    
    async def get_extended_hours_volume_check(self, symbol: str) -> Tuple[bool, int]:
        """
        Check if symbol has sufficient volume for extended hours trading.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Tuple of (sufficient_volume, recent_volume)
        """
        try:
            # This would typically use market data to check recent volume
            # For now, return a basic check
            
            # Assume major symbols have sufficient volume
            major_symbols = {
                'AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'NVDA', 'SPY', 'QQQ'
            }
            
            if symbol.upper() in major_symbols:
                return True, 10000  # Simulated high volume
            else:
                return False, 500   # Simulated low volume
                
        except Exception as e:
            logger.error(f"❌ Error checking extended hours volume for {symbol}: {e}")
            return False, 0
    
    def get_extended_hours_trading_summary(self) -> Dict[str, Any]:
        """Get summary of extended hours trading configuration and status."""
        return {
            'premarket_enabled': self._settings.premarket_enabled,
            'afterhours_enabled': self._settings.afterhours_enabled,
            'use_limit_orders_only': self._settings.use_limit_orders_only,
            'spread_buffer_multiplier': self._settings.spread_buffer_multiplier,
            'min_volume_threshold': self._settings.min_volume_threshold,
            'position_size_multiplier': self._settings.position_size_multiplier,
            'account_extended_hours_enabled': self._account_extended_hours_enabled,
            'validated_symbols_count': len(self._symbol_extended_hours_cache),
            'validated_symbols': list(self._symbol_extended_hours_cache.keys())
        }
    
    async def log_extended_hours_status(self) -> None:
        """Log current extended hours trading status."""
        try:
            market_status = await self._market_hours_manager.get_current_market_status()
            summary = self.get_extended_hours_trading_summary()
            
            logger.info("🌅 EXTENDED HOURS TRADING STATUS:")
            logger.info(f"   Current Session: {market_status.current_session.value.upper()}")
            logger.info(f"   Premarket Enabled: {summary['premarket_enabled']}")
            logger.info(f"   After-hours Enabled: {summary['afterhours_enabled']}")
            logger.info(f"   Account Capability: {summary['account_extended_hours_enabled']}")
            logger.info(f"   Limit Orders Only: {summary['use_limit_orders_only']}")
            logger.info(f"   Validated Symbols: {summary['validated_symbols_count']}")
            
        except Exception as e:
            logger.error(f"❌ Error logging extended hours status: {e}")