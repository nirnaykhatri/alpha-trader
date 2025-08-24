"""
Risk management implementation.
Handles position sizing, risk limits, and trade validation.
"""

from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from ..interfaces import IRiskManager, IConfigurationManager, IPositionManager, IAccountProvider
from ..exceptions import RiskManagementException
from ..core.logging_config import get_logger
from .. import TradingSignal, Order, Position


logger = get_logger(__name__)


class RiskManager(IRiskManager):
    """
    Comprehensive risk management system.
    Manages position sizing, exposure limits, and risk validation.
    """
    
    def __init__(self, config: IConfigurationManager, position_manager: IPositionManager, 
                 account_provider: Optional[IAccountProvider] = None):
        """
        Initialize risk manager.
        
        Args:
            config: Configuration manager instance
            position_manager: Position manager instance
            account_provider: Account provider for real-time balance (optional)
        """
        self._config = config
        self._position_manager = position_manager
        self._account_provider = account_provider
        
        # Risk parameters
        self._risk_per_trade = config.get_config("trading.risk_per_trade", 0.02)
        self._max_portfolio_risk = config.get_config("trading.max_portfolio_risk", 0.10)
        self._max_position_size = config.get_config("trading.max_position_size", 1000)
        self._max_daily_trades = config.get_config("trading.max_daily_trades", 50)
        
        # Tracking
        self._daily_trades: Dict[str, int] = {}  # symbol -> trade count
        self._last_reset_date = datetime.utcnow().date()
        
        logger.info("RiskManager initialized")
    
    async def validate_order(self, order: Order) -> bool:
        """
        Validate order against risk parameters.
        
        Args:
            order: Order to validate
            
        Returns:
            True if order passes risk validation
        """
        try:
            logger.debug(f"Validating order: {order.symbol} {order.side} {order.quantity}")
            
            # Reset daily counters if needed
            self._reset_daily_counters_if_needed()
            
            # Check daily trade limit
            if not self._check_daily_trade_limit(order.symbol):
                logger.warning(f"Daily trade limit exceeded for {order.symbol}")
                return False
            
            # Check position size limits
            if not await self._check_position_size_limit(order):
                logger.warning(f"Position size limit exceeded for {order.symbol}")
                return False
            
            # Check portfolio exposure
            if not await self._check_portfolio_exposure(order):
                logger.warning(f"Portfolio exposure limit exceeded")
                return False
            
            # Check symbol-specific limits
            if not self._check_symbol_limits(order):
                logger.warning(f"Symbol-specific limits exceeded for {order.symbol}")
                return False
            
            # Check buying power
            if order.side == "buy" and not await self._check_buying_power(order.symbol, order.quantity, order.price):
                logger.warning(f"Insufficient buying power for {order.symbol}")
                return False
            
            logger.debug(f"Order validation passed: {order.symbol}")
            return True
            
        except Exception as e:
            logger.error(f"Error validating order: {str(e)}")
            return False
    
    async def validate_signal(self, signal: TradingSignal) -> bool:
        """
        Validate trading signal against risk parameters.
        
        Args:
            signal: Trading signal to validate
            
        Returns:
            True if signal passes risk validation
        """
        try:
            logger.debug(f"Validating signal: {signal.symbol} {signal.signal_type.value}")
            
            # Check if symbol is allowed (with configurable whitelist)
            whitelist_enabled = self._config.get_config("symbols.whitelist_enabled", True)
            if whitelist_enabled:
                allowed_symbols = self._config.get_config("symbols.default_symbols", [])
                if allowed_symbols and signal.symbol not in allowed_symbols:
                    logger.warning(f"Symbol {signal.symbol} not in allowed whitelist (whitelist_enabled=true)")
                    return False
            else:
                logger.debug(f"Symbol whitelist disabled - allowing {signal.symbol} from signal")
            
            # Check signal price reasonableness
            if signal.price <= 0:
                logger.warning(f"Invalid signal price: {signal.price}")
                return False
            
            # Check for duplicate signals (within time window)
            if self._is_duplicate_signal(signal):
                logger.warning(f"Duplicate signal detected: {signal.signal_id}")
                return False
            
            logger.debug(f"Signal validation passed: {signal.symbol}")
            return True
            
        except Exception as e:
            logger.error(f"Error validating signal: {str(e)}")
            return False
    
    async def calculate_position_size(self, symbol: str, signal: TradingSignal, 
                                     averaging_attempt: int = 0) -> float:
        """
        Calculate appropriate position size based on configured sizing method.
        
        Args:
            symbol: Trading symbol
            signal: Trading signal with price information
            averaging_attempt: Position averaging attempt number (0 = initial, 1+ = averaging)
            
        Returns:
            Position size in shares (0 if insufficient funds)
        """
        try:
            # Get position sizing configuration
            sizing_method = self._config.get_config("trading.position_sizing.method", "percentage")
            current_price = signal.price
            
            # Calculate position size based on method
            if sizing_method == "fixed":
                quantity = await self._calculate_fixed_position_size(symbol, signal)
            elif sizing_method == "percentage":
                quantity = await self._calculate_percentage_position_size(symbol, current_price, averaging_attempt)
            elif sizing_method == "risk_based":
                quantity = await self._calculate_risk_based_position_size(symbol, current_price)
            else:
                logger.warning(f"Unknown position sizing method: {sizing_method}, falling back to percentage")
                quantity = await self._calculate_percentage_position_size(symbol, current_price, averaging_attempt)
            
            # Final validation - ensure it's a whole number and positive
            quantity = max(0, int(quantity))
            
            if quantity == 0:
                logger.warning(f"Position size calculated as 0 for {symbol} - trade will be skipped")
            
            return float(quantity)
                
        except Exception as e:
            logger.error(f"Error calculating position size for {symbol}: {str(e)}")
            return 0.0  # Return 0 on error to prevent trades
    
    async def _calculate_fixed_position_size(self, symbol: str, signal: TradingSignal) -> float:
        """Calculate position size using fixed quantity method."""
        default_qty = self._config.get_config("trading.position_sizing.default_quantity", 100)
        max_qty = self._config.get_config("trading.position_sizing.max_quantity", 10000)
        min_qty = self._config.get_config("trading.position_sizing.min_quantity", 1)
        
        # Use signal quantity if provided, otherwise use default
        quantity = signal.quantity if signal.quantity else default_qty
        
        # Ensure it's a whole number (round down)
        quantity = int(quantity)
        
        # Apply limits
        quantity = max(min_qty, min(quantity, max_qty))
        
        # Validate we can afford this quantity (basic check)
        if signal.price > 0:
            cost = quantity * signal.price
            logger.info(f"Fixed position size for {symbol}: {quantity} shares @ ${signal.price:.2f} = ${cost:.2f}")
        else:
            logger.debug(f"Fixed position size for {symbol}: {quantity} shares (price not available)")
        
        return float(quantity)
    
    async def _calculate_percentage_position_size(self, symbol: str, current_price: float, 
                                                averaging_attempt: int = 0) -> float:
        """
        Calculate position size based on portfolio percentage using martingale approach.
        
        Args:
            symbol: Trading symbol
            current_price: Current stock price
            averaging_attempt: 0 = initial position, 1+ = averaging attempts
        """
        try:
            # Get configuration - use different percentage for initial vs averaging
            if averaging_attempt == 0:
                # Initial position - use conservative percentage
                portfolio_percentage = self._config.get_config("trading.position_sizing.initial_portfolio_percentage", 0.01)
                logger.debug(f"Initial position sizing for {symbol}: {portfolio_percentage*100:.1f}% of buying power")
            else:
                # Averaging position - use martingale approach
                initial_percentage = self._config.get_config("trading.position_sizing.initial_portfolio_percentage", 0.01)
                multiplier = self._config.get_config("trading.position_sizing.averaging.multiplier", 2.0)
                
                # Calculate martingale size: initial * (multiplier ^ averaging_attempt)
                portfolio_percentage = initial_percentage * (multiplier ** averaging_attempt)
                
                logger.debug(f"Averaging position #{averaging_attempt} for {symbol}: "
                           f"{portfolio_percentage*100:.1f}% of buying power "
                           f"(initial {initial_percentage*100:.1f}% × {multiplier}^{averaging_attempt})")
            
            max_qty = self._config.get_config("trading.position_sizing.max_quantity", 10000)
            min_qty = self._config.get_config("trading.position_sizing.min_quantity", 1)
            
            # Check maximum total position exposure
            max_total_percentage = self._config.get_config("trading.position_sizing.max_total_position_percentage", 0.15)
            
            # Get available buying power
            if self._account_provider:
                buying_power = await self._account_provider.get_buying_power()
                account_value = await self._account_provider.get_account_value()
                logger.debug(f"Using buying power: ${buying_power:,.2f} (account value: ${account_value:,.2f})")
                # Use percentage of buying power for sizing
                available_funds = buying_power * portfolio_percentage
            else:
                # Fallback: use percentage of fallback account value
                account_value = await self._get_account_value()
                available_funds = account_value * portfolio_percentage * 2.0  # Assume 2:1 buying power
                logger.debug(f"No account provider - using {portfolio_percentage*100:.1f}% of estimated buying power: ${available_funds:,.2f}")
            
            # Calculate quantity based on current price
            if current_price <= 0:
                logger.warning(f"Invalid price {current_price} for {symbol}, cannot calculate position size")
                return 0.0
            
            # Calculate raw quantity
            raw_quantity = available_funds / current_price
            
            # Round down to whole shares (no fractional shares)
            quantity = int(raw_quantity)
            
            # Check if we can afford at least 1 share
            if quantity < min_qty:
                min_cost = min_qty * current_price
                logger.warning(f"Insufficient buying power for {symbol} (attempt #{averaging_attempt}): "
                             f"need ${min_cost:.2f} for {min_qty} share(s), "
                             f"but only have ${available_funds:.2f} available "
                             f"({portfolio_percentage*100:.1f}% of buying power)")
                return 0.0  # Cannot place trade
            
            # Apply maximum limits
            quantity = min(quantity, max_qty)
            
            # Log the calculation details
            actual_cost = quantity * current_price
            if self._account_provider:
                logger.info(f"{'Martingale' if averaging_attempt > 0 else 'Initial'} position sizing for {symbol} "
                           f"(attempt #{averaging_attempt}): {quantity} shares @ ${current_price:.2f} = ${actual_cost:.2f} "
                           f"(using ${actual_cost:.2f} of ${available_funds:.2f} available, "
                           f"{portfolio_percentage*100:.1f}% of buying power)")
            else:
                account_value = await self._get_account_value()
                logger.info(f"{'Martingale' if averaging_attempt > 0 else 'Initial'} position sizing for {symbol} "
                           f"(attempt #{averaging_attempt}): {quantity} shares @ ${current_price:.2f} = ${actual_cost:.2f} "
                           f"({actual_cost/account_value*100:.2f}% of portfolio)")
            
            return float(quantity)
            
        except Exception as e:
            logger.error(f"Error calculating percentage position size for {symbol}: {str(e)}")
            return 0.0
    
    async def _calculate_risk_based_position_size(self, symbol: str, current_price: float) -> float:
        """Calculate position size based on risk percentage."""
        try:
            # Get configuration
            risk_per_trade = self._config.get_config("trading.position_sizing.risk_per_trade", 0.02)
            max_qty = self._config.get_config("trading.position_sizing.max_quantity", 10000)
            min_qty = self._config.get_config("trading.position_sizing.min_quantity", 1)
            
            # Get symbol-specific risk settings
            symbol_settings = self._config.get_config(f"symbols.symbol_settings.{symbol}", {})
            risk_per_trade = symbol_settings.get("risk_per_trade", risk_per_trade)
            
            # Get account value
            account_value = await self._get_account_value()
            risk_amount = account_value * risk_per_trade
            
            # Calculate position size based on risk amount
            if current_price <= 0:
                logger.warning(f"Invalid price {current_price} for {symbol}, cannot calculate position size")
                return 0.0
            
            # For risk-based sizing, we use the full risk amount for position sizing
            # In a more sophisticated implementation, this would consider stop loss distance
            raw_quantity = risk_amount / current_price
            
            # Round down to whole shares (no fractional shares)
            quantity = int(raw_quantity)
            
            # Check if we can afford at least 1 share
            if quantity < min_qty:
                min_cost = min_qty * current_price
                logger.warning(f"Insufficient risk budget for {symbol}: need ${min_cost:.2f} for {min_qty} share(s), "
                             f"but risk budget is only ${risk_amount:.2f} "
                             f"({risk_per_trade*100:.1f}% of ${account_value:,.2f})")
                return 0.0  # Cannot place trade
            
            # Apply maximum limits
            quantity = min(quantity, max_qty)
            
            # Log the calculation details
            actual_cost = quantity * current_price
            logger.info(f"Risk-based position sizing for {symbol}: {quantity} shares @ ${current_price:.2f} = ${actual_cost:.2f} "
                       f"(risk: ${actual_cost:.2f} of ${risk_amount:.2f} budget)")
            
            return float(quantity)
            
        except Exception as e:
            logger.error(f"Error calculating risk-based position size for {symbol}: {str(e)}")
            return 0.0
    
    async def get_max_exposure(self, symbol: str) -> float:
        """
        Get maximum allowed exposure for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Maximum exposure amount
        """
        try:
            symbol_settings = self._config.get_config(f"symbols.symbol_settings.{symbol}", {})
            max_position = symbol_settings.get("max_position_size", self._max_position_size)
            
            # Get current price to calculate dollar exposure
            # For now, return position size - could be enhanced with price data
            return float(max_position)
            
        except Exception as e:
            logger.error(f"Error getting max exposure for {symbol}: {str(e)}")
            return float(self._max_position_size)
    
    def _reset_daily_counters_if_needed(self) -> None:
        """Reset daily trade counters if it's a new day."""
        current_date = datetime.utcnow().date()
        if current_date != self._last_reset_date:
            self._daily_trades.clear()
            self._last_reset_date = current_date
            logger.info("Daily trade counters reset")
    
    def _check_daily_trade_limit(self, symbol: str) -> bool:
        """Check if daily trade limit is exceeded."""
        current_trades = self._daily_trades.get(symbol, 0)
        if current_trades >= self._max_daily_trades:
            return False
        
        # Increment counter (optimistic - will be decremented if trade fails)
        self._daily_trades[symbol] = current_trades + 1
        return True
    
    async def _check_position_size_limit(self, order: Order) -> bool:
        """Check position size limits."""
        symbol_settings = self._config.get_config(f"symbols.symbol_settings.{order.symbol}", {})
        max_position = symbol_settings.get("max_position_size", self._max_position_size)
        
        # Get current position
        existing_position = await self._position_manager.get_position(order.symbol)
        current_quantity = existing_position.quantity if existing_position else 0
        
        # Calculate new position size
        if order.side == "buy":
            new_quantity = current_quantity + order.quantity
        else:
            new_quantity = current_quantity - order.quantity
        
        return abs(new_quantity) <= max_position
    
    async def _check_portfolio_exposure(self, order: Order) -> bool:
        """Check overall portfolio exposure limits."""
        try:
            # Get all positions
            positions = await self._position_manager.get_all_positions()
            
            # Calculate current exposure
            total_exposure = sum(abs(pos.quantity * pos.avg_price) for pos in positions)
            
            # Calculate additional exposure from this order
            order_exposure = order.quantity * (order.price or 0)
            
            # Get account value
            account_value = await self._get_account_value()
            
            # Check if total exposure would exceed limit
            total_exposure_ratio = (total_exposure + order_exposure) / account_value
            
            return total_exposure_ratio <= self._max_portfolio_risk
            
        except Exception as e:
            logger.error(f"Error checking portfolio exposure: {str(e)}")
            return True  # Allow trade if we can't calculate exposure
    
    def _check_symbol_limits(self, order: Order) -> bool:
        """Check symbol-specific trading limits."""
        # Add any symbol-specific checks here
        # For example, check if symbol is temporarily blocked
        blocked_symbols = self._config.get_config("symbols.blocked_symbols", [])
        return order.symbol not in blocked_symbols
    
    def _is_duplicate_signal(self, signal: TradingSignal) -> bool:
        """Check if signal is a duplicate within time window."""
        # This would typically check against a cache of recent signals
        # For now, always return False (no duplicate detection)
        return False
    
    async def _get_account_value(self) -> float:
        """Get current account value from Alpaca API - fail safely if unavailable."""
        try:
            # PRODUCTION SAFETY: Always require real account data from Alpaca
            if not self._account_provider:
                error_msg = "No account provider available - cannot get real account balance"
                logger.error(error_msg)
                raise RiskManagementException(error_msg)
            
            # Check if fail-safe mode is enabled
            fail_safe = self._config.get_config("trading.account.fail_safe_on_api_error", True)
            
            try:
                account_value = await self._account_provider.get_account_value()
                logger.debug(f"Real account value from Alpaca: ${account_value:,.2f}")
                return account_value
                
            except Exception as api_error:
                if fail_safe:
                    error_msg = f"Alpaca API failed and fail-safe mode enabled: {str(api_error)}"
                    logger.error(error_msg)
                    raise RiskManagementException(error_msg)
                else:
                    # This should only be used in development/testing
                    logger.critical(f"Alpaca API failed but fail-safe disabled: {str(api_error)}")
                    raise api_error
            
        except RiskManagementException:
            # Re-raise risk management exceptions
            raise
        except Exception as e:
            error_msg = f"Critical error getting account value: {str(e)}"
            logger.error(error_msg)
            raise RiskManagementException(error_msg)
    
    def get_risk_metrics(self) -> Dict[str, Any]:
        """Get current risk metrics."""
        return {
            "risk_per_trade": self._risk_per_trade,
            "max_portfolio_risk": self._max_portfolio_risk,
            "max_position_size": self._max_position_size,
            "max_daily_trades": self._max_daily_trades,
            "daily_trades": dict(self._daily_trades),
            "last_reset_date": self._last_reset_date.isoformat()
        }
    
    async def _check_buying_power(self, symbol: str, quantity: float, price: float) -> bool:
        """Check if we have sufficient buying power for the trade."""
        try:
            if not self._account_provider:
                # If no account provider, we already calculated based on available funds
                logger.debug("No account provider - assuming sufficient buying power (already calculated)")
                return True
            
            buying_power = await self._account_provider.get_buying_power()
            required_funds = quantity * price
            
            if required_funds > buying_power:
                logger.warning(f"Insufficient buying power for {symbol}: need ${required_funds:,.2f}, "
                             f"available: ${buying_power:,.2f}")
                return False
            
            logger.debug(f"Buying power check passed for {symbol}: ${required_funds:,.2f} of ${buying_power:,.2f}")
            return True
            
        except Exception as e:
            logger.error(f"Error checking buying power: {str(e)}")
            # On error, allow the trade (our position sizing should have already handled this)
            return True
