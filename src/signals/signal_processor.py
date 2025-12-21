"""
Signal processing module for TradingView webhook signals.
Handles signal validation, parsing, and transformation.
"""

import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

from src.interfaces import IConfigurationManager, IMarketDataProvider
from src.exceptions import SignalProcessingException, ValidationException
from src.core.logging_config import get_logger
from src import TradingSignal, SignalType
from src.signals import interval_parser
from src.signals.webhook_security import WebhookSecurityValidator


logger = get_logger(__name__)


class SignalProcessor:
    """
    Processes and validates TradingView signals.
    Provides signal parsing, validation, and transformation logic.
    """
    
    def __init__(
        self,
        config: IConfigurationManager,
        market_data: Optional[IMarketDataProvider] = None
    ):
        """
        Initialize signal processor.
        
        Args:
            config: Configuration manager instance
            market_data: Market data provider for price fetching
        """
        self._config = config
        self._market_data = market_data
        
        # Initialize webhook security validator
        security_enabled = config.get_config("api.webhook.security_enabled", True)
        secret = config.get_config("api.webhook.secret", "")
        self._security_validator = WebhookSecurityValidator(secret, security_enabled)
        
        logger.info("Signal processor initialized")
    
    async def process_signal(self, signal_data: Dict[str, Any]) -> TradingSignal:
        """
        Process incoming signal data and convert to TradingSignal.
        
        Args:
            signal_data: Raw signal data from webhook
            
        Returns:
            Processed TradingSignal object
            
        Raises:
            SignalProcessingException: If signal processing fails
        """
        try:
            logger.debug(f"Processing signal data: {signal_data}")
            
            # Validate required fields
            self.validate_signal_data(signal_data)
            
            # Extract signal information
            symbol = signal_data.get("ticker", signal_data.get("symbol", "")).upper()
            action = signal_data.get("signal", signal_data.get("action", "")).lower()
            
            # Get actual current market price
            if "price" in signal_data:
                price = float(signal_data["price"])
                price_source = "signal"
            else:
                # Fetch current market price if not provided in signal
                if self._market_data:
                    try:
                        price = await self._market_data.get_current_price(symbol)
                        price_source = "market_data"
                        logger.info(f"Fetched current price for {symbol}: ${price:.2f}")
                    except Exception as e:
                        logger.error(f"Failed to fetch current price for {symbol}: {e}")
                        raise SignalProcessingException(f"Unable to determine price for {symbol}: {e}")
                else:
                    logger.error(f"No market data provider available to fetch price for {symbol}")
                    raise SignalProcessingException(f"No market data provider available for pricing {symbol}")
            
            # Validate that we have a valid price
            if price <= 0:
                raise SignalProcessingException(f"Invalid price for {symbol}: ${price:.2f}")
            
            quantity = signal_data.get("quantity")
            
            # Extract interval from TradingView webhook (if available)
            default_interval = self._config.get_config("strategies.averaging_down.timeframe", "1h")
            interval = interval_parser.extract_from_webhook_data(signal_data, default_interval=default_interval)
            
            # Convert action to signal type
            signal_type = self.convert_action_to_signal_type(action)
            
            # Enhance metadata with extracted information
            enhanced_metadata = signal_data.copy()
            if interval:
                enhanced_metadata["interval"] = interval
                logger.debug(f"Extracted interval '{interval}' from signal for {symbol}")
            
            # Create TradingSignal object
            signal = TradingSignal(
                signal_id=None,  # Will be auto-generated
                symbol=symbol,
                signal_type=signal_type,
                price=price,
                quantity=float(quantity) if quantity else None,
                timestamp=datetime.utcnow(),
                metadata=enhanced_metadata
            )
            
            logger.info(
                f"Signal processed: {signal.symbol} {signal.signal_type.value} @ ${signal.price:.2f} ({price_source})"
                f"{f' (interval: {interval})' if interval else ''}"
            )
            return signal
            
        except Exception as e:
            logger.error(f"Failed to process signal: {str(e)}")
            raise SignalProcessingException(f"Failed to process signal: {str(e)}")
    
    def validate_signal_data(self, signal_data: Dict[str, Any]) -> None:
        """
        Validate signal data structure and content.
        
        Args:
            signal_data: Signal data to validate
            
        Raises:
            ValidationException: If validation fails
        """
        # At least one of ticker/symbol is required
        if "ticker" not in signal_data and "symbol" not in signal_data:
            raise ValidationException("Missing required field: ticker or symbol")
        
        # At least one of signal/action is required
        if "signal" not in signal_data and "action" not in signal_data:
            raise ValidationException("Missing required field: signal or action")
        
        # Validate ticker/symbol (accept either)
        symbol = signal_data.get("ticker") or signal_data.get("symbol", "")
        if not symbol or not isinstance(symbol, str):
            raise ValidationException("Ticker/symbol must be a non-empty string")
        
        # Validate signal/action (accept either)
        action = signal_data.get("signal") or signal_data.get("action", "")
        valid_actions = ["buy", "sell", "close", "long", "short"]
        if action.lower() not in valid_actions:
            raise ValidationException(f"Invalid signal: {action}")
        
        # Validate price if present (optional - used only for logging/auditing)
        if "price" in signal_data:
            try:
                price = float(signal_data.get("price", 0))
                if price <= 0:
                    raise ValidationException("Price must be positive")
            except (ValueError, TypeError):
                raise ValidationException("Price must be a valid number")
        
        # Validate quantity if provided
        quantity = signal_data.get("quantity")
        if quantity is not None:
            try:
                qty = float(quantity)
                if qty <= 0:
                    raise ValidationException("Quantity must be positive")
            except (ValueError, TypeError):
                raise ValidationException("Quantity must be a valid number")
    
    def convert_action_to_signal_type(self, action: str) -> SignalType:
        """
        Convert action string to SignalType enum.
        
        Args:
            action: Action string from signal
            
        Returns:
            Corresponding SignalType
        """
        action_mapping = {
            "buy": SignalType.BUY,
            "long": SignalType.BUY,
            "sell": SignalType.SELL,
            "short": SignalType.SELL,
            "close": SignalType.CLOSE,
            "exit": SignalType.CLOSE
        }
        
        return action_mapping.get(action.lower(), SignalType.BUY)
    
    def verify_secret(self, provided_secret: str) -> bool:
        """
        Verify webhook secret for URL path or body authentication.
        
        Delegates to centralized WebhookSecurityValidator for consistent
        security validation across all webhook endpoints.
        
        Args:
            provided_secret: Secret provided in URL path or request body
            
        Returns:
            True if secret is valid or security is disabled
        """
        return self._security_validator.verify_secret(provided_secret)
    
    def verify_signature(self, body: bytes, signature: str) -> bool:
        """
        Verify HMAC signature.
        
        Delegates to centralized WebhookSecurityValidator for consistent
        security validation across all webhook endpoints.
        
        Args:
            body: Raw request body
            signature: Signature from X-Signature header
            
        Returns:
            True if signature is valid, False otherwise
        """
        return self._security_validator.verify_signature(body, signature)
