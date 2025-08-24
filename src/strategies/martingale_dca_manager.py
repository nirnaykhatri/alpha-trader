"""
Martingale DCA Manager
Implements configurable martingale Dollar Cost Averaging strategy with per-symbol risk management.
Replaces technical analysis-based DCA with user-controllable position sizing and risk limits.
"""

import asyncio
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN

from ..interfaces import IConfigurationManager, IMarketDataProvider, IRiskManager
from ..core.logging_config import get_logger
from .. import OrderType, OrderSide
from ..exceptions import TradingBotException, ConfigurationException


logger = get_logger(__name__)


class OrderSizeType(Enum):
    """Order size calculation methods."""
    DOLLARS = "dollars"
    PORTFOLIO_PERCENT = "portfolio_percent"


class DCAAmountType(Enum):
    """DCA amount calculation methods."""
    MULTIPLIER = "multiplier"
    FIXED_DOLLARS = "fixed_dollars"
    FIXED_PERCENT = "fixed_percent"


@dataclass
class MartingaleConfig:
    """Per-symbol martingale configuration."""
    symbol: str
    base_order_size_type: OrderSizeType
    base_order_size: float
    dca_order_size_type: DCAAmountType
    dca_amount_multiplier: float
    dca_step_percent: float
    step_multiplier: float
    max_dca_orders: int
    take_profit_percent: float
    trailing_deviation_percent: float
    max_position_value: float
    enabled: bool = True
    
    def __post_init__(self):
        """Validate configuration parameters."""
        self._validate_config()
    
    def _validate_config(self):
        """Validate configuration parameters are within safe ranges."""
        if self.base_order_size <= 0:
            raise ConfigurationException(f"base_order_size must be positive, got {self.base_order_size}")
        
        if self.base_order_size_type == OrderSizeType.PORTFOLIO_PERCENT and self.base_order_size > 50:
            raise ConfigurationException(f"base_order_size percentage too high: {self.base_order_size}%")
        
        if self.dca_amount_multiplier < 1.0:
            raise ConfigurationException(f"dca_amount_multiplier must be >= 1.0, got {self.dca_amount_multiplier}")
        
        if self.dca_amount_multiplier > 10.0:
            logger.warning(f"High DCA multiplier {self.dca_amount_multiplier} for {self.symbol} - high risk!")
        
        if not 0.1 <= self.dca_step_percent <= 50:
            raise ConfigurationException(f"dca_step_percent must be 0.1-50%, got {self.dca_step_percent}")
        
        if not 1.0 <= self.step_multiplier <= 5.0:
            raise ConfigurationException(f"step_multiplier must be 1.0-5.0, got {self.step_multiplier}")
        
        if not 1 <= self.max_dca_orders <= 20:
            raise ConfigurationException(f"max_dca_orders must be 1-20, got {self.max_dca_orders}")
        
        if not 0.5 <= self.take_profit_percent <= 100:
            raise ConfigurationException(f"take_profit_percent must be 0.5-100%, got {self.take_profit_percent}")
        
        if not 0.1 <= self.trailing_deviation_percent <= 10:
            raise ConfigurationException(f"trailing_deviation_percent must be 0.1-10%, got {self.trailing_deviation_percent}")
        
        if self.max_position_value <= self.base_order_size:
            raise ConfigurationException(f"max_position_value ({self.max_position_value}) must be larger than base_order_size ({self.base_order_size})")


@dataclass
class MartingalePositionState:
    """State tracking for martingale DCA positions."""
    symbol: str
    entry_price: float
    current_average_price: float
    total_quantity: float
    total_value_invested: float
    dca_count: int = 0
    dca_order_history: List[Dict[str, Any]] = field(default_factory=list)
    next_dca_step_percent: float = 0.0
    next_dca_order_size: float = 0.0
    peak_profit_price: Optional[float] = None
    trailing_stop_price: Optional[float] = None
    is_trailing_active: bool = False
    last_dca_trigger_price: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    
    def update_timestamp(self):
        """Update the last modified timestamp."""
        self.updated_at = datetime.utcnow()


class MartingaleDCAManager:
    """
    Manages martingale DCA strategy with configurable per-symbol parameters.
    Provides precise position sizing control and comprehensive risk management.
    """
    
    def __init__(self, config: IConfigurationManager, market_data: IMarketDataProvider, 
                 risk_manager: IRiskManager):
        """
        Initialize the Martingale DCA Manager.
        
        Args:
            config: Configuration manager instance
            market_data: Market data provider
            risk_manager: Risk management interface
        """
        self.config = config
        self.market_data = market_data
        self.risk_manager = risk_manager
        
        # Symbol-specific configurations
        self._symbol_configs: Dict[str, MartingaleConfig] = {}
        
        # Active position states
        self._position_states: Dict[str, MartingalePositionState] = {}
        
        # Default configuration fallbacks
        self._load_default_config()
        
        # Load symbol-specific configurations
        self._load_symbol_configs()
        
        logger.info("MartingaleDCAManager initialized with configurations for {} symbols", 
                   len(self._symbol_configs))
    
    def _load_default_config(self):
        """Load default configuration values."""
        self._default_config = {
            'base_order_size_type': 'dollars',
            'base_order_size': 1000.0,
            'dca_order_size_type': 'multiplier',
            'dca_amount_multiplier': 2.0,
            'dca_step_percent': 1.5,
            'step_multiplier': 1.2,
            'max_dca_orders': 5,
            'take_profit_percent': 3.0,
            'trailing_deviation_percent': 0.8,
            'max_position_value': 10000.0,
            'enabled': True
        }
    
    def _load_symbol_configs(self):
        """Load per-symbol martingale configurations from config file."""
        try:
            symbol_settings = self.config.get_config('symbol_settings', {})
            
            for symbol, settings in symbol_settings.items():
                try:
                    # Merge with defaults
                    merged_config = {**self._default_config, **settings}
                    
                    # Convert string enums to proper types
                    base_size_type = OrderSizeType(merged_config['base_order_size_type'])
                    dca_amount_type = DCAAmountType(merged_config['dca_order_size_type'])
                    
                    martingale_config = MartingaleConfig(
                        symbol=symbol,
                        base_order_size_type=base_size_type,
                        base_order_size=float(merged_config['base_order_size']),
                        dca_order_size_type=dca_amount_type,
                        dca_amount_multiplier=float(merged_config['dca_amount_multiplier']),
                        dca_step_percent=float(merged_config['dca_step_percent']),
                        step_multiplier=float(merged_config['step_multiplier']),
                        max_dca_orders=int(merged_config['max_dca_orders']),
                        take_profit_percent=float(merged_config['take_profit_percent']),
                        trailing_deviation_percent=float(merged_config['trailing_deviation_percent']),
                        max_position_value=float(merged_config['max_position_value']),
                        enabled=bool(merged_config.get('enabled', True))
                    )
                    
                    self._symbol_configs[symbol] = martingale_config
                    logger.info(f"Loaded martingale config for {symbol}: "
                               f"base=${martingale_config.base_order_size}, "
                               f"multiplier={martingale_config.dca_amount_multiplier}x, "
                               f"max_dca={martingale_config.max_dca_orders}")
                    
                except Exception as e:
                    logger.error(f"Failed to load config for symbol {symbol}: {e}")
                    
        except Exception as e:
            logger.warning(f"Failed to load symbol configurations: {e}")
    
    def get_symbol_config(self, symbol: str) -> MartingaleConfig:
        """
        Get martingale configuration for a symbol.
        Returns default config if symbol-specific config not found.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            MartingaleConfig for the symbol
        """
        if symbol in self._symbol_configs:
            return self._symbol_configs[symbol]
        
        # Create default config for symbol
        logger.info(f"Creating default martingale config for {symbol}")
        
        default_config = MartingaleConfig(
            symbol=symbol,
            base_order_size_type=OrderSizeType.DOLLARS,
            base_order_size=self._default_config['base_order_size'],
            dca_order_size_type=DCAAmountType.MULTIPLIER,
            dca_amount_multiplier=self._default_config['dca_amount_multiplier'],
            dca_step_percent=self._default_config['dca_step_percent'],
            step_multiplier=self._default_config['step_multiplier'],
            max_dca_orders=self._default_config['max_dca_orders'],
            take_profit_percent=self._default_config['take_profit_percent'],
            trailing_deviation_percent=self._default_config['trailing_deviation_percent'],
            max_position_value=self._default_config['max_position_value'],
            enabled=self._default_config['enabled']
        )
        
        self._symbol_configs[symbol] = default_config
        return default_config
    
    async def calculate_base_order_size(self, symbol: str, current_price: float) -> float:
        """
        Calculate the base order size for initial position entry.
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            
        Returns:
            Order size in dollars
        """
        config = self.get_symbol_config(symbol)
        
        if config.base_order_size_type == OrderSizeType.DOLLARS:
            order_value = config.base_order_size
        elif config.base_order_size_type == OrderSizeType.PORTFOLIO_PERCENT:
            portfolio_value = await self.risk_manager.get_portfolio_value()
            order_value = portfolio_value * (config.base_order_size / 100.0)
        else:
            raise TradingBotException(f"Unknown base order size type: {config.base_order_size_type}")
        
        # Apply risk management limits
        max_allowed = await self.risk_manager.get_max_order_value(symbol)
        if max_allowed and order_value > max_allowed:
            logger.warning(f"Base order size ${order_value:,.2f} exceeds max allowed ${max_allowed:,.2f} for {symbol}")
            order_value = max_allowed
        
        logger.info(f"Calculated base order size for {symbol}: ${order_value:,.2f}")
        return order_value
    
    async def calculate_dca_order_size(self, symbol: str, dca_number: int, 
                                     base_order_value: float) -> float:
        """
        Calculate the DCA order size based on martingale progression.
        
        Args:
            symbol: Trading symbol
            dca_number: DCA order number (1, 2, 3, etc.)
            base_order_value: Base order value in dollars
            
        Returns:
            DCA order size in dollars
        """
        config = self.get_symbol_config(symbol)
        
        if config.dca_order_size_type == DCAAmountType.MULTIPLIER:
            # Martingale progression: base * (multiplier ^ dca_number)
            dca_order_value = base_order_value * (config.dca_amount_multiplier ** dca_number)
        
        elif config.dca_order_size_type == DCAAmountType.FIXED_DOLLARS:
            dca_order_value = config.dca_amount_multiplier  # Use as fixed dollar amount
        
        elif config.dca_order_size_type == DCAAmountType.FIXED_PERCENT:
            portfolio_value = await self.risk_manager.get_portfolio_value()
            dca_order_value = portfolio_value * (config.dca_amount_multiplier / 100.0)
        
        else:
            raise TradingBotException(f"Unknown DCA amount type: {config.dca_order_size_type}")
        
        # Apply safety limits
        if dca_order_value > config.max_position_value:
            logger.warning(f"DCA order ${dca_order_value:,.2f} would exceed max position value "
                          f"${config.max_position_value:,.2f} for {symbol}")
            dca_order_value = min(dca_order_value, config.max_position_value / 2)
        
        logger.info(f"Calculated DCA {dca_number} order size for {symbol}: ${dca_order_value:,.2f} "
                   f"(progression: {config.dca_amount_multiplier}^{dca_number})")
        
        return dca_order_value
    
    def calculate_next_dca_step_percent(self, symbol: str, current_dca_count: int) -> float:
        """
        Calculate the percentage step for the next DCA trigger.
        Implements progressive step increases: 1.5%, 1.8%, 2.16%, etc.
        
        Args:
            symbol: Trading symbol
            current_dca_count: Current number of DCA orders executed
            
        Returns:
            Next DCA step percentage
        """
        config = self.get_symbol_config(symbol)
        
        # Calculate progressive step: initial * (step_multiplier ^ dca_count)
        next_step = config.dca_step_percent * (config.step_multiplier ** current_dca_count)
        
        # Cap at reasonable maximum
        max_step = config.dca_step_percent * 10  # 10x initial step as maximum
        next_step = min(next_step, max_step)
        
        logger.debug(f"Next DCA step for {symbol} (DCA #{current_dca_count + 1}): {next_step:.2f}%")
        return next_step
    
    def initialize_position(self, symbol: str, entry_price: float, quantity: float, 
                           order_value: float) -> MartingalePositionState:
        """
        Initialize a new martingale position state.
        
        Args:
            symbol: Trading symbol
            entry_price: Entry price per share
            quantity: Number of shares
            order_value: Total order value in dollars
            
        Returns:
            Initialized position state
        """
        config = self.get_symbol_config(symbol)
        
        position_state = MartingalePositionState(
            symbol=symbol,
            entry_price=entry_price,
            current_average_price=entry_price,
            total_quantity=quantity,
            total_value_invested=order_value,
            dca_count=0,
            next_dca_step_percent=self.calculate_next_dca_step_percent(symbol, 0),
            next_dca_order_size=0.0  # Will be calculated when needed
        )
        
        # Add initial order to history
        position_state.dca_order_history.append({
            'order_number': 0,  # Entry order
            'price': entry_price,
            'quantity': quantity,
            'value': order_value,
            'timestamp': datetime.utcnow(),
            'average_price_after': entry_price
        })
        
        self._position_states[symbol] = position_state
        
        logger.info(f"Initialized martingale position for {symbol}: "
                   f"entry=${entry_price:.2f}, qty={quantity:.2f}, value=${order_value:,.2f}")
        
        return position_state
    
    def should_trigger_dca(self, symbol: str, current_price: float, 
                          is_long_position: bool = True) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if DCA should be triggered based on martingale step thresholds.
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            is_long_position: True for long positions, False for short
            
        Returns:
            Tuple of (should_trigger, trigger_info_dict)
        """
        if symbol not in self._position_states:
            return False, {'reason': 'No position state found'}
        
        position_state = self._position_states[symbol]
        config = self.get_symbol_config(symbol)
        
        # Check if we've reached maximum DCA orders
        if position_state.dca_count >= config.max_dca_orders:
            return False, {
                'reason': 'Maximum DCA orders reached',
                'dca_count': position_state.dca_count,
                'max_dca_orders': config.max_dca_orders
            }
        
        # Check position value limits - both current and if DCA would be executed
        if position_state.total_value_invested >= config.max_position_value:
            return False, {
                'reason': 'Maximum position value reached',
                'current_value': position_state.total_value_invested,
                'max_value': config.max_position_value
            }
        
        # Check if next DCA order would exceed position value limit
        next_dca_value = self._calculate_dca_order_value_sync(symbol, current_price)
        if position_state.total_value_invested + next_dca_value > config.max_position_value:
            return False, {
                'reason': 'Next DCA order would exceed maximum position value',
                'current_value': position_state.total_value_invested,
                'next_dca_value': next_dca_value,
                'total_after_dca': position_state.total_value_invested + next_dca_value,
                'max_value': config.max_position_value
            }
        
        # Calculate price movement from average price
        price_change_percent = abs(current_price - position_state.current_average_price) / position_state.current_average_price * 100
        
        # For long positions: DCA when price drops
        # For short positions: DCA when price rises
        if is_long_position:
            price_moved_unfavorably = current_price < position_state.current_average_price
        else:
            price_moved_unfavorably = current_price > position_state.current_average_price
        
        should_trigger = (
            price_moved_unfavorably and 
            price_change_percent >= position_state.next_dca_step_percent
        )
        
        trigger_info = {
            'current_price': current_price,
            'average_price': position_state.current_average_price,
            'price_change_percent': price_change_percent,
            'required_step_percent': position_state.next_dca_step_percent,
            'dca_count': position_state.dca_count,
            'max_dca_orders': config.max_dca_orders,
            'is_long_position': is_long_position,
            'price_moved_unfavorably': price_moved_unfavorably,
            'reason': 'DCA trigger conditions met' if should_trigger else 'DCA conditions not met'
        }
        
        if should_trigger:
            logger.info(f"DCA triggered for {symbol}: price moved {price_change_percent:.2f}% "
                       f"(required: {position_state.next_dca_step_percent:.2f}%), "
                       f"DCA #{position_state.dca_count + 1}")
        
        return should_trigger, trigger_info
    
    def _calculate_dca_order_value_sync(self, symbol: str, current_price: float) -> float:
        """
        Calculate DCA order value synchronously (without risk manager calls).
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            
        Returns:
            DCA order value in dollars
        """
        position_state = self._position_states.get(symbol)
        if not position_state:
            return 0.0
            
        config = self.get_symbol_config(symbol)
        
        # Calculate base DCA amount based on configuration
        if config.dca_order_size_type == DCAAmountType.MULTIPLIER:
            # Use multiplier based on base order size
            dca_order_value = config.base_order_size * config.dca_amount_multiplier
        else:
            # Use fixed dollar amount
            dca_order_value = config.dca_amount_multiplier
        
        # Apply progressive scaling if enabled
        if config.step_multiplier > 1.0:
            scale_factor = config.step_multiplier ** position_state.dca_count
            dca_order_value *= scale_factor
        
        return dca_order_value
    
    async def calculate_dca_order_details(self, symbol: str, current_price: float) -> Dict[str, Any]:
        """
        Calculate complete DCA order details including size and expected outcomes.
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            
        Returns:
            Dictionary with DCA order details
        """
        if symbol not in self._position_states:
            raise TradingBotException(f"No position state found for {symbol}")
        
        position_state = self._position_states[symbol]
        config = self.get_symbol_config(symbol)
        
        next_dca_number = position_state.dca_count + 1
        base_order_value = config.base_order_size
        
        # Calculate DCA order size
        dca_order_value = await self.calculate_dca_order_size(symbol, next_dca_number, base_order_value)
        
        # Calculate shares to buy/sell
        dca_quantity = dca_order_value / current_price
        
        # Calculate new average price and total position
        new_total_quantity = position_state.total_quantity + dca_quantity
        new_total_value = position_state.total_value_invested + dca_order_value
        new_average_price = new_total_value / new_total_quantity
        
        # Calculate next DCA step after this one
        next_step_percent = self.calculate_next_dca_step_percent(symbol, next_dca_number)
        
        # Safety checks
        position_value_after = new_total_value
        exceeds_max_value = position_value_after > config.max_position_value
        exceeds_max_orders = next_dca_number > config.max_dca_orders
        
        return {
            'dca_number': next_dca_number,
            'order_value': dca_order_value,
            'quantity': dca_quantity,
            'price': current_price,
            'new_average_price': new_average_price,
            'new_total_quantity': new_total_quantity,
            'new_total_value': new_total_value,
            'next_step_percent': next_step_percent,
            'exceeds_max_value': exceeds_max_value,
            'exceeds_max_orders': exceeds_max_orders,
            'is_safe_to_execute': not (exceeds_max_value or exceeds_max_orders),
            'config': {
                'max_position_value': config.max_position_value,
                'max_dca_orders': config.max_dca_orders,
                'dca_multiplier': config.dca_amount_multiplier
            }
        }
    
    def update_position_after_dca(self, symbol: str, dca_price: float, dca_quantity: float, 
                                 dca_value: float) -> MartingalePositionState:
        """
        Update position state after DCA order execution.
        
        Args:
            symbol: Trading symbol
            dca_price: Price of DCA order execution
            dca_quantity: Quantity of shares in DCA order
            dca_value: Total value of DCA order
            
        Returns:
            Updated position state
        """
        if symbol not in self._position_states:
            raise TradingBotException(f"No position state found for {symbol}")
        
        position_state = self._position_states[symbol]
        
        # Update position metrics
        position_state.total_quantity += dca_quantity
        position_state.total_value_invested += dca_value
        position_state.current_average_price = position_state.total_value_invested / position_state.total_quantity
        position_state.dca_count += 1
        
        # Calculate next DCA step percentage
        position_state.next_dca_step_percent = self.calculate_next_dca_step_percent(symbol, position_state.dca_count)
        
        # Add to order history
        position_state.dca_order_history.append({
            'order_number': position_state.dca_count,
            'price': dca_price,
            'quantity': dca_quantity,
            'value': dca_value,
            'timestamp': datetime.utcnow(),
            'average_price_after': position_state.current_average_price
        })
        
        # Update timestamp
        position_state.update_timestamp()
        
        logger.info(f"Updated {symbol} position after DCA #{position_state.dca_count}: "
                   f"new_avg=${position_state.current_average_price:.2f}, "
                   f"total_qty={position_state.total_quantity:.2f}, "
                   f"total_value=${position_state.total_value_invested:,.2f}")
        
        return position_state
    
    def should_take_profit(self, symbol: str, current_price: float, 
                          is_long_position: bool = True) -> Tuple[bool, Dict[str, Any]]:
        """
        Check if position should take profit based on configured thresholds.
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            is_long_position: True for long positions, False for short
            
        Returns:
            Tuple of (should_take_profit, profit_info_dict)
        """
        if symbol not in self._position_states:
            return False, {'reason': 'No position state found'}
        
        position_state = self._position_states[symbol]
        config = self.get_symbol_config(symbol)
        
        # Calculate current profit percentage
        if is_long_position:
            profit_percent = (current_price - position_state.current_average_price) / position_state.current_average_price * 100
        else:
            profit_percent = (position_state.current_average_price - current_price) / position_state.current_average_price * 100
        
        should_take = profit_percent >= config.take_profit_percent
        
        profit_info = {
            'current_price': current_price,
            'average_price': position_state.current_average_price,
            'profit_percent': profit_percent,
            'take_profit_threshold': config.take_profit_percent,
            'profit_amount': (current_price - position_state.current_average_price) * position_state.total_quantity if is_long_position else (position_state.current_average_price - current_price) * position_state.total_quantity,
            'is_long_position': is_long_position,
            'reason': 'Take profit triggered' if should_take else 'Profit target not reached'
        }
        
        if should_take:
            logger.info(f"Take profit triggered for {symbol}: {profit_percent:.2f}% profit "
                       f"(target: {config.take_profit_percent:.2f}%)")
        
        return should_take, profit_info
    
    def update_trailing_stop(self, symbol: str, current_price: float, 
                           is_long_position: bool = True) -> Tuple[bool, Dict[str, Any]]:
        """
        Update trailing stop logic and check if stop should trigger.
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            is_long_position: True for long positions, False for short
            
        Returns:
            Tuple of (should_stop, trailing_info_dict)
        """
        if symbol not in self._position_states:
            return False, {'reason': 'No position state found'}
        
        position_state = self._position_states[symbol]
        config = self.get_symbol_config(symbol)
        
        # Calculate current profit percentage
        if is_long_position:
            profit_percent = (current_price - position_state.current_average_price) / position_state.current_average_price * 100
        else:
            profit_percent = (position_state.current_average_price - current_price) / position_state.current_average_price * 100
        
        # Initialize trailing if profitable and not already trailing
        if profit_percent > 0 and not position_state.is_trailing_active:
            position_state.is_trailing_active = True
            position_state.peak_profit_price = current_price
            
            if is_long_position:
                position_state.trailing_stop_price = current_price * (1 - config.trailing_deviation_percent / 100)
            else:
                position_state.trailing_stop_price = current_price * (1 + config.trailing_deviation_percent / 100)
            
            logger.info(f"Activated trailing stop for {symbol}: peak=${current_price:.2f}, "
                       f"stop=${position_state.trailing_stop_price:.2f}")
        
        # Update trailing if in profit
        elif position_state.is_trailing_active and profit_percent > 0:
            # Update peak price if we have a new high/low
            if is_long_position and current_price > position_state.peak_profit_price:
                position_state.peak_profit_price = current_price
                position_state.trailing_stop_price = current_price * (1 - config.trailing_deviation_percent / 100)
                
            elif not is_long_position and current_price < position_state.peak_profit_price:
                position_state.peak_profit_price = current_price
                position_state.trailing_stop_price = current_price * (1 + config.trailing_deviation_percent / 100)
        
        # Check if trailing stop should trigger
        should_stop = False
        if position_state.is_trailing_active and position_state.trailing_stop_price:
            if is_long_position:
                should_stop = current_price <= position_state.trailing_stop_price
            else:
                should_stop = current_price >= position_state.trailing_stop_price
        
        trailing_info = {
            'current_price': current_price,
            'average_price': position_state.current_average_price,
            'profit_percent': profit_percent,
            'is_trailing_active': position_state.is_trailing_active,
            'peak_profit_price': position_state.peak_profit_price,
            'trailing_stop_price': position_state.trailing_stop_price,
            'trailing_deviation_percent': config.trailing_deviation_percent,
            'is_long_position': is_long_position,
            'should_stop': should_stop,
            'reason': 'Trailing stop triggered' if should_stop else 'Trailing stop active' if position_state.is_trailing_active else 'No trailing stop'
        }
        
        if should_stop:
            logger.info(f"Trailing stop triggered for {symbol}: price=${current_price:.2f}, "
                       f"stop=${position_state.trailing_stop_price:.2f}")
        
        return should_stop, trailing_info
    
    def get_position_state(self, symbol: str) -> Optional[MartingalePositionState]:
        """Get current position state for a symbol."""
        return self._position_states.get(symbol)
    
    def remove_position(self, symbol: str) -> bool:
        """Remove position state when position is closed."""
        if symbol in self._position_states:
            del self._position_states[symbol]
            logger.info(f"Removed position state for {symbol}")
            return True
        return False
    
    def get_position_summary(self, symbol: str) -> Dict[str, Any]:
        """Get comprehensive position summary."""
        if symbol not in self._position_states:
            return {'error': 'No position found'}
        
        position_state = self._position_states[symbol]
        config = self.get_symbol_config(symbol)
        
        return {
            'symbol': symbol,
            'entry_price': position_state.entry_price,
            'current_average_price': position_state.current_average_price,
            'total_quantity': position_state.total_quantity,
            'total_value_invested': position_state.total_value_invested,
            'dca_count': position_state.dca_count,
            'max_dca_orders': config.max_dca_orders,
            'next_dca_step_percent': position_state.next_dca_step_percent,
            'max_position_value': config.max_position_value,
            'take_profit_percent': config.take_profit_percent,
            'trailing_deviation_percent': config.trailing_deviation_percent,
            'is_trailing_active': position_state.is_trailing_active,
            'peak_profit_price': position_state.peak_profit_price,
            'trailing_stop_price': position_state.trailing_stop_price,
            'dca_order_history': position_state.dca_order_history,
            'created_at': position_state.created_at,
            'updated_at': position_state.updated_at
        }
    
    def get_all_positions_summary(self) -> Dict[str, Dict[str, Any]]:
        """Get summary of all active positions."""
        return {symbol: self.get_position_summary(symbol) 
                for symbol in self._position_states.keys()}
    
    async def validate_dca_safety_limits(self, symbol: str, proposed_dca_value: float) -> Dict[str, Any]:
        """
        Validate that proposed DCA order meets all safety limits.
        
        Args:
            symbol: Trading symbol
            proposed_dca_value: Proposed DCA order value in dollars
            
        Returns:
            Validation result dictionary
        """
        config = self.get_symbol_config(symbol)
        position_state = self._position_states.get(symbol)
        
        if not position_state:
            return {
                'is_valid': False,
                'reason': 'No position state found',
                'violations': ['no_position_state']
            }
        
        violations = []
        
        # Check DCA count limit
        if position_state.dca_count >= config.max_dca_orders:
            violations.append('max_dca_orders_exceeded')
        
        # Check position value limit
        new_total_value = position_state.total_value_invested + proposed_dca_value
        if new_total_value > config.max_position_value:
            violations.append('max_position_value_exceeded')
        
        # Check portfolio risk limits
        portfolio_value = await self.risk_manager.get_portfolio_value()
        position_portfolio_percent = (new_total_value / portfolio_value) * 100
        max_portfolio_percent = self.config.get_config('trading.max_portfolio_risk', 20) * 100
        
        if position_portfolio_percent > max_portfolio_percent:
            violations.append('portfolio_risk_exceeded')
        
        # Check account balance
        available_cash = await self.risk_manager.get_available_cash()
        if proposed_dca_value > available_cash:
            violations.append('insufficient_funds')
        
        is_valid = len(violations) == 0
        
        return {
            'is_valid': is_valid,
            'violations': violations,
            'current_dca_count': position_state.dca_count,
            'max_dca_orders': config.max_dca_orders,
            'current_position_value': position_state.total_value_invested,
            'new_position_value': new_total_value,
            'max_position_value': config.max_position_value,
            'proposed_dca_value': proposed_dca_value,
            'position_portfolio_percent': position_portfolio_percent,
            'max_portfolio_percent': max_portfolio_percent,
            'available_cash': available_cash,
            'reason': 'All safety checks passed' if is_valid else f'Violations: {", ".join(violations)}'
        }