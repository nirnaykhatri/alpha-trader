"""
Enhanced DCA Strategy Implementation
Pure support/resistance based DCA using original signal timeframe
"""

from typing import Dict, Optional
from datetime import datetime
from ..interfaces import IConfigurationManager, IOrderManager, IMarketDataProvider
from ..core.logging_config import get_logger
from .. import TradingSignal, Order, OrderType, OrderSide
from .support_calculator import TechnicalSupportCalculator

logger = get_logger(__name__)

class EnhancedDCAStrategy:
    """
    Enhanced DCA strategy that uses pure support/resistance levels
    based on the original signal's timeframe and technical analysis.
    """
    
    def __init__(self, config: IConfigurationManager, order_manager: IOrderManager, 
                 market_data: IMarketDataProvider, support_calculator: TechnicalSupportCalculator):
        self.config = config
        self.order_manager = order_manager
        self.market_data = market_data
        self.support_calculator = support_calculator
        
        # Track original signal data for each position
        self.position_signal_data: Dict[str, dict] = {}
        
    async def process_signal_with_timeframe_tracking(self, signal: TradingSignal):
        """Process signal and store timeframe data for future DCA decisions."""
        symbol = signal.symbol
        
        # Store original signal data including timeframe
        self.position_signal_data[symbol] = {
            'timeframe': signal.metadata.get('timeframe', '15m'),
            'entry_price': signal.price,
            'signal_type': signal.signal_type,
            'entry_time': datetime.utcnow(),
            'webhook_source': signal.metadata.get('source', 'tradingview')
        }
        
        logger.info(f"📊 SIGNAL TRACKING: {symbol} timeframe: {self.position_signal_data[symbol]['timeframe']}")
        
    async def check_dca_opportunity(self, symbol: str, current_price: float, position_quantity: float, avg_price: float) -> bool:
        """
        Check DCA opportunity using PURE support/resistance analysis
        NO loss threshold - only technical levels matter
        """
        if symbol not in self.position_signal_data:
            logger.warning(f"No signal data found for {symbol}, cannot calculate DCA")
            return False
            
        signal_data = self.position_signal_data[symbol]
        timeframe = signal_data['timeframe']
        is_long_position = position_quantity > 0
        
        logger.info(f"🎯 DCA CHECK: {symbol} using {timeframe} timeframe from original signal")
        
        if is_long_position:
            return await self._check_support_based_dca(symbol, current_price, avg_price, timeframe)
        else:
            return await self._check_resistance_based_dca(symbol, current_price, avg_price, timeframe)
    
    async def _check_support_based_dca(self, symbol: str, current_price: float, avg_price: float, timeframe: str) -> dict:
        """
        Check for DCA opportunity based on support levels
        Returns dict with decision and reasoning
        """
        try:
            # Calculate support levels using original signal timeframe
            support_data = await self.support_calculator.calculate_support_levels(symbol, timeframe)
            
            if not support_data or not support_data.levels:
                logger.warning(f"⚠️ NO SUPPORT DATA: {symbol} ({timeframe}) - Cannot calculate DCA without technical levels")
                return {
                    'should_dca': False,
                    'reason': 'no_support_data',
                    'message': f'No support levels found for {timeframe} timeframe'
                }
            
            # Find the strongest support level below current price
            valid_supports = [level for level in support_data.levels if level.price < current_price]
            
            if not valid_supports:
                logger.info(f"📈 NO SUPPORT BREACH: {symbol} current ${current_price:.2f} above all support levels")
                return {
                    'should_dca': False,
                    'reason': 'above_support',
                    'message': f'Price ${current_price:.2f} still above support levels'
                }
            
            # Get the nearest strong support level
            nearest_support = max(valid_supports, key=lambda x: x.price)
            support_price = nearest_support.price
            support_confidence = nearest_support.confidence
            
            # Check if we're AT or BELOW the support level
            support_buffer = self.config.get_config('strategies.dca.support_buffer_percent', 0.005)  # 0.5% buffer
            support_trigger_price = support_price * (1 + support_buffer)
            
            if current_price <= support_trigger_price:
                logger.info(f"🎯 SUPPORT BREACH DCA: {symbol}")
                logger.info(f"   Current: ${current_price:.2f}")
                logger.info(f"   Support: ${support_price:.2f} (confidence: {support_confidence:.1%})")
                logger.info(f"   Trigger: ${support_trigger_price:.2f}")
                logger.info(f"   Timeframe: {timeframe}")
                
                return {
                    'should_dca': True,
                    'reason': 'support_breach',
                    'support_level': support_price,
                    'confidence': support_confidence,
                    'trigger_price': support_trigger_price,
                    'timeframe': timeframe,
                    'message': f'Price breached support at ${support_price:.2f}'
                }
            else:
                logger.debug(f"🔍 WATCHING SUPPORT: {symbol} ${current_price:.2f} > ${support_trigger_price:.2f}")
                return {
                    'should_dca': False,
                    'reason': 'watching_support',
                    'next_support': support_price,
                    'distance_to_support': ((current_price - support_trigger_price) / current_price) * 100,
                    'message': f'Watching support at ${support_price:.2f} ({((current_price - support_trigger_price) / current_price) * 100:.1f}% away)'
                }
                
        except Exception as e:
            logger.error(f"Error checking support-based DCA for {symbol}: {e}")
            return {
                'should_dca': False,
                'reason': 'error',
                'message': f'Error calculating support: {str(e)}'
            }
    
    async def _check_resistance_based_dca(self, symbol: str, current_price: float, avg_price: float, timeframe: str) -> dict:
        """
        Check for DCA opportunity based on resistance levels (for short positions)
        """
        try:
            # Calculate resistance levels using original signal timeframe  
            resistance_data = await self.support_calculator.calculate_resistance_levels(symbol, timeframe)
            
            if not resistance_data or not resistance_data.levels:
                logger.warning(f"⚠️ NO RESISTANCE DATA: {symbol} ({timeframe}) - Cannot calculate DCA without technical levels")
                return {
                    'should_dca': False,
                    'reason': 'no_resistance_data',
                    'message': f'No resistance levels found for {timeframe} timeframe'
                }
            
            # Find the strongest resistance level above current price
            valid_resistances = [level for level in resistance_data.levels if level.price > current_price]
            
            if not valid_resistances:
                logger.info(f"📉 NO RESISTANCE BREACH: {symbol} current ${current_price:.2f} below all resistance levels")
                return {
                    'should_dca': False,
                    'reason': 'below_resistance',
                    'message': f'Price ${current_price:.2f} still below resistance levels'
                }
            
            # Get the nearest strong resistance level
            nearest_resistance = min(valid_resistances, key=lambda x: x.price)
            resistance_price = nearest_resistance.price
            resistance_confidence = nearest_resistance.confidence
            
            # Check if we're AT or ABOVE the resistance level
            resistance_buffer = self.config.get_config('strategies.dca.resistance_buffer_percent', 0.005)  # 0.5% buffer
            resistance_trigger_price = resistance_price * (1 - resistance_buffer)
            
            if current_price >= resistance_trigger_price:
                logger.info(f"🎯 RESISTANCE BREACH DCA: {symbol}")
                logger.info(f"   Current: ${current_price:.2f}")
                logger.info(f"   Resistance: ${resistance_price:.2f} (confidence: {resistance_confidence:.1%})")
                logger.info(f"   Trigger: ${resistance_trigger_price:.2f}")
                logger.info(f"   Timeframe: {timeframe}")
                
                return {
                    'should_dca': True,
                    'reason': 'resistance_breach',
                    'resistance_level': resistance_price,
                    'confidence': resistance_confidence,
                    'trigger_price': resistance_trigger_price,
                    'timeframe': timeframe,
                    'message': f'Price breached resistance at ${resistance_price:.2f}'
                }
            else:
                logger.debug(f"🔍 WATCHING RESISTANCE: {symbol} ${current_price:.2f} < ${resistance_trigger_price:.2f}")
                return {
                    'should_dca': False,
                    'reason': 'watching_resistance',
                    'next_resistance': resistance_price,
                    'distance_to_resistance': ((resistance_trigger_price - current_price) / current_price) * 100,
                    'message': f'Watching resistance at ${resistance_price:.2f} ({((resistance_trigger_price - current_price) / current_price) * 100:.1f}% away)'
                }
                
        except Exception as e:
            logger.error(f"Error checking resistance-based DCA for {symbol}: {e}")
            return {
                'should_dca': False,
                'reason': 'error',
                'message': f'Error calculating resistance: {str(e)}'
            }

    async def execute_technical_dca(self, symbol: str, dca_analysis: dict, position_data: dict) -> Optional[str]:
        """
        Execute DCA order based on technical analysis results
        """
        if not dca_analysis.get('should_dca', False):
            return None
            
        try:
            is_long_position = position_data['quantity'] > 0
            current_price = position_data['current_price']
            
            # Calculate DCA position size
            base_quantity = abs(position_data['quantity'])
            multiplier = self.config.get_config('strategies.dca.position_multiplier', 1.5)
            dca_quantity = base_quantity * multiplier
            
            # Order details
            order_side = OrderSide.BUY if is_long_position else OrderSide.SELL
            order_type = OrderType.LIMIT  # Always use limit orders near support/resistance
            
            # Price calculation based on technical level
            if is_long_position:
                # Buy slightly above support to ensure fill
                support_level = dca_analysis['support_level']
                order_price = support_level * 1.001  # 0.1% above support
            else:
                # Sell slightly below resistance to ensure fill  
                resistance_level = dca_analysis['resistance_level']
                order_price = resistance_level * 0.999  # 0.1% below resistance
                
            order_price = round(order_price, 2)
            
            # Create DCA order
            order = Order(
                order_id=None,
                symbol=symbol,
                side=order_side,
                quantity=dca_quantity,
                order_type=order_type,
                price=order_price
            )
            
            # Use enhanced DCA order placement with automatic tracking
            position_lifecycle_id = position_data.get('position_lifecycle_id', symbol)
            dca_level = position_data.get('dca_count', 0) + 1
            
            strategy_metadata = {
                'dca_reason': dca_analysis['reason'],
                'technical_level': dca_analysis.get('support_level', dca_analysis.get('resistance_level')),
                'confidence': dca_analysis['confidence'],
                'timeframe': dca_analysis['timeframe'],
                'original_position_size': abs(position_data['quantity'])
            }
            
            # Place DCA order with enhanced tracking
            if hasattr(self.order_manager, 'place_dca_order'):
                order_id = await self.order_manager.place_dca_order(
                    order, position_lifecycle_id, dca_level, strategy_metadata
                )
            else:
                # Fallback for compatibility
                order_id = await self.order_manager.place_order(order)
            
            logger.info(f"📈 TECHNICAL DCA ORDER: {symbol}")
            logger.info(f"   Type: {dca_analysis['reason']}")
            logger.info(f"   Level: ${dca_analysis.get('support_level', dca_analysis.get('resistance_level')):.2f}")
            logger.info(f"   Confidence: {dca_analysis['confidence']:.1%}")
            logger.info(f"   Order: {order_side.value} {dca_quantity} @ ${order_price:.2f}")
            logger.info(f"   Order ID: {order_id}")
            logger.info(f"   DCA Level: {dca_level}")
            logger.info(f"   Position Lifecycle: {position_lifecycle_id}")
            
            return order_id
            
        except Exception as e:
            logger.error(f"Error executing technical DCA for {symbol}: {e}")
            return None
