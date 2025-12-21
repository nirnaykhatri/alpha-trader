"""
Trading Bot Integration Layer
This module brings together all components to create a complete trading system.
"""

import asyncio
import os
import signal
import sys
from typing import Dict, Any, Optional, List
from datetime import datetime
from contextlib import asynccontextmanager

# Core imports
from src.core import ConfigurationManager, setup_logging, get_logger
from src.signals import TradingViewSignalListener
from src.trading import OrderManager
from src.broker.subsystem import BrokerSubsystem
from src.broker.interfaces import BrokerType
from src.strategies import ConfigurableTrailingProfitManager
from src.strategies.advanced_strategy import AdvancedTradingStrategy
from src.risk import RiskManager
from src.position import PositionManager
from src.database import DatabaseManager

# Utility imports
from src.utils import NgrokManager, run_blocking, BoundedFetcher

# Data models
from src import TradingSignal, Order, Position, OrderType, OrderSide, OrderStatus, SignalType
from src.interfaces import IAsyncContextManager
from src.exceptions import TradingBotException, ConfigurationException, OrderExecutionException
from src.trading import OrderManager, ExitPlanner, TradeService, PositionMonitor


logger = get_logger(__name__)


class TradingBotOrchestrator(IAsyncContextManager):
    """
    Main orchestrator class that coordinates all trading bot components.
    This is the central hub that users interact with to run the trading bot.
    """
    
    def __init__(self, config_file: str = None):
        """
        Initialize the trading bot orchestrator.
        
        Args:
            config_file: DEPRECATED - No longer used. Configuration is loaded from
                        config/ directory using TOML files. Kept for backward compatibility.
        """
        if config_file is not None:
            import warnings
            warnings.warn(
                "config_file parameter is deprecated. Configuration is now loaded from "
                "config/ directory using TOML files. Set TRADING_BOT_ENV environment "
                "variable to switch between 'demo' and 'live' environments.",
                DeprecationWarning,
                stacklevel=2
            )
        
        self.config: Optional[ConfigurationManager] = None
        self.is_running = False
        self.shutdown_event = asyncio.Event()
        
        # Track background tasks for proper cleanup
        self.background_tasks: List[asyncio.Task] = []
        
        # Subsystems
        self.broker_subsystem: Optional[BrokerSubsystem] = None
        
        # Component instances
        self.signal_listener: Optional[TradingViewSignalListener] = None
        self.order_manager: Optional[OrderManager] = None
        self.position_manager: Optional[PositionManager] = None
        self.risk_manager: Optional[RiskManager] = None
        self.trailing_manager: Optional[ConfigurableTrailingProfitManager] = None
        self.advanced_strategy: Optional[AdvancedTradingStrategy] = None
        self.database: Optional[DatabaseManager] = None
        
        # Bounded concurrency utilities
        self._price_fetcher: Optional[BoundedFetcher] = None
        self._exit_planner: Optional[ExitPlanner] = None
        self._trade_service: Optional[TradeService] = None
        self._position_monitor: Optional[PositionMonitor] = None
        
        # Ngrok manager for local development
        self.ngrok_manager: Optional[NgrokManager] = None
        
        # State tracking
        self.active_positions: Dict[str, Position] = {}
        self.processed_signals: Dict[str, TradingSignal] = {}
        
        # Rate limiting for error handling
        self.last_error_time: Dict[str, float] = {}  # Track last error time per symbol
        self.error_cooldown = 60  # 60 seconds cooldown between repeated errors
        
        logger.info("TradingBotOrchestrator initialized")
    
    async def start(self) -> None:
        """
        Start the trading bot system.
        This is the main entry point for users.
        """
        try:
            logger.info("Starting Trading Bot System...")
            
            # Setup signal handlers FIRST (before any components start)
            self._setup_signal_handlers()
            
            # Initialize all components
            await self._initialize_components()
            
            # Validate configuration
            await self._validate_configuration()
            
            # Start components
            await self._start_components()
            
            self.is_running = True
            logger.info("Trading Bot System started successfully!")
            
            # Main event loop
            await self._run_main_loop()
            
        except Exception as e:
            logger.error(f"Failed to start trading bot: {str(e)}")
            await self.stop()
            raise
    
    async def stop(self) -> None:
        """Stop the trading bot system gracefully."""
        if not self.is_running:
            logger.debug("Trading bot is already stopped")
            return
        
        logger.info("Shutting down Trading Bot System...")
        self.is_running = False
        
        try:
            # Force stop the signal listener first
            if self.signal_listener:
                logger.info("Stopping signal listener...")
                if self.signal_listener._server:
                    self.signal_listener._server.should_exit = True
                    if hasattr(self.signal_listener._server, 'force_exit'):
                        self.signal_listener._server.force_exit = True
                await self.signal_listener.stop()
            
            # Stop Broker Subsystem
            if self.broker_subsystem:
                await self.broker_subsystem.stop()

            # Cancel all background tasks
            logger.info("Cancelling background tasks...")
            for task in self.background_tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for tasks to cancel (with timeout)
            if self.background_tasks:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*self.background_tasks, return_exceptions=True),
                        timeout=3.0
                    )
                    logger.info("All background tasks stopped")
                except asyncio.TimeoutError:
                    logger.warning("Some background tasks did not cancel within timeout")
            
            # Stop ngrok tunnel
            if self.ngrok_manager:
                logger.info("Stopping ngrok tunnel...")
                self.ngrok_manager.stop_tunnel()
            
            # Cancel all open orders
            logger.info("Canceling open orders...")
            await self._cancel_all_orders()
            
            # Close database connections
            if self.database:
                logger.info("Closing database connections...")
                await self.database.close()
            
            # Signal shutdown completion
            if not self.shutdown_event.is_set():
                self.shutdown_event.set()
            
            logger.info("Trading Bot System stopped successfully")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {str(e)}")
            # Even if there's an error, mark as shutdown
            if not self.shutdown_event.is_set():
                self.shutdown_event.set()
    
    async def _initialize_components(self) -> None:
        """Initialize all trading bot components."""
        logger.info("Initializing components...")
        
        # Load configuration (singleton - no file path needed)
        self.config = ConfigurationManager()
        
        # Setup logging
        setup_logging(
            level=self.config.get_config("logging.level", "INFO"),
            format_type=self.config.get_config("logging.format", "json"),
            log_file=self.config.get_config("logging.file")
        )
        
        # Initialize database
        self.database = DatabaseManager(self.config)
        await self.database.initialize()
        
        # Initialize Broker Subsystem
        self.broker_subsystem = BrokerSubsystem(self.config)
        await self.broker_subsystem.initialize()
        
        # Initialize position manager with broker router for multi-broker sync
        self.position_manager = PositionManager(self.config, self.database, self.broker_subsystem.router)
        
        # Initialize risk manager with account provider
        self.risk_manager = RiskManager(self.config, self.position_manager, self.broker_subsystem.primary_account_provider)
        
        # Initialize order manager with broker router
        self.order_manager = OrderManager(self.config, self.broker_subsystem.router)
        
        # Initialize strategy components
        self.trailing_manager = ConfigurableTrailingProfitManager(self.config)
        
        # Initialize advanced strategy (main strategy handler)
        self.advanced_strategy = AdvancedTradingStrategy(
            self.config, 
            self.order_manager, 
            self.broker_subsystem.market_data,
            self.risk_manager,
            self.position_manager  # Add position manager for database persistence
        )
        
        # Initialize signal listener with market data provider for accurate pricing
        self.signal_listener = TradingViewSignalListener(
            self.config, 
            self._handle_trading_signal,
            self.broker_subsystem.market_data,  # Pass market data provider for current price fetching
            bot_instance=self  # Pass bot instance for status endpoints
        )
        
        # Initialize bounded concurrency utilities
        max_concurrent_price_fetches = self.config.get_config("performance.max_concurrent_orders", 5)
        self._price_fetcher = BoundedFetcher(max_concurrency=max_concurrent_price_fetches)
        
        # Initialize exit planner service
        self._exit_planner = ExitPlanner(self.config, self.broker_subsystem.market_data)
        
        # Initialize trade service for trade lifecycle management
        self._trade_service = TradeService(self.database, self.order_manager)
        
        # Initialize position monitor service
        self._position_monitor = PositionMonitor(
            config=self.config,
            position_manager=self.position_manager,
            broker_subsystem=self.broker_subsystem,
            trailing_manager=self.trailing_manager,
            price_fetcher=self._price_fetcher,
            advanced_strategy=self.advanced_strategy
        )
        
        # Initialize ngrok manager for local development
        # Check for environment variable override
        no_ngrok_env = os.getenv("TRADING_BOT_NO_NGROK", "").lower() in ("1", "true", "yes")
        ngrok_enabled = self.config.get_config("ngrok.enabled", False) and not no_ngrok_env
        
        if ngrok_enabled:
            self.ngrok_manager = NgrokManager(self.config)
        
        logger.info("All components initialized successfully")
    
    async def _validate_configuration(self) -> None:
        """Validate configuration and check API connections."""
        logger.info("Validating configuration...")
        
        # Validate required configuration
        self.config.validate_required_config()
        
        # Test API connections via subsystem
        await self.broker_subsystem.validate_connections()
        
        logger.info("Configuration validation completed")
    
    async def _start_components(self) -> None:
        """Start all components that need to run continuously."""
        logger.info("Starting components...")
        
        # Check for external ngrok first, then start internal if needed
        webhook_port = self.config.get_config("api.webhook.port", 8080)
        external_ngrok = self._check_external_ngrok()
        
        if external_ngrok['running']:
            print("\n" + "="*60)
            print("🔍 DETECTED EXTERNAL NGROK TUNNEL")
            print("="*60)
            if external_ngrok['tunnel_url']:
                print(f"🌐 Public URL: {external_ngrok['tunnel_url']}")
                print(f"🎯 Webhook URL: {external_ngrok['webhook_url']}")
                print(f"📊 Monitor traffic: {external_ngrok['monitor_url']}")
                print()
                print("✅ Using external ngrok tunnel (better for shutdown!)")
                print("📋 COPY THIS TO TRADINGVIEW:")
                print(f"   {external_ngrok['webhook_url']}")
                print("="*60)
                logger.info(f"Using external ngrok tunnel: {external_ngrok['tunnel_url']}")
            else:
                print("⚠️  External ngrok detected but no suitable tunnel found")
                print("="*60)
        elif self.ngrok_manager:
            print("\n" + "="*60)
            print("🚇 STARTING INTERNAL NGROK TUNNEL")
            print("="*60)
            
            tunnel_url = await self.ngrok_manager.start_tunnel(webhook_port)
            if tunnel_url:
                logger.info(f"Internal ngrok tunnel established: {tunnel_url}")
                # The ngrok manager already displays the tunnel info, so no need to duplicate
            else:
                logger.warning("Failed to start internal ngrok tunnel - continuing without it")
                print("⚠️  WARNING: No ngrok tunnel available.")
                print("   Your bot will run locally only.")
                print("   TradingView webhooks will not reach your bot.")
                print("   To fix this:")
                print("   1. Check ngrok auth token in config/.secrets.toml")
                print("   2. Ensure your firewall allows outbound connections")
                print("   3. Try running: start_ngrok_standalone.bat")
                print("   4. Or restart the bot")
                print("="*60)
        else:
            print("\n" + "="*60)
            print("ℹ️  NO NGROK CONFIGURED")
            print("="*60)
            print("⚠️  No ngrok tunnel available.")
            print("   Your bot will run locally only.")
            print("   TradingView webhooks will not reach your bot.")
            print("   To enable ngrok:")
            print("   1. Set 'enabled = true' in config/settings.toml [default.ngrok]")
            print("   2. Add your ngrok auth token to config/.secrets.toml")
            print("   3. Or run: start_ngrok_standalone.bat")
            print("="*60)
        
        # Start signal listener
        signal_task = asyncio.create_task(self.signal_listener.start())
        self.background_tasks.append(signal_task)
        
        # Start Broker Subsystem (handles market data, TT session, etc.)
        await self.broker_subsystem.start()
        
        # Start background monitoring tasks (only if ngrok is enabled)
        if self.ngrok_manager:
            ngrok_task = asyncio.create_task(self._monitor_ngrok_tunnel())
            self.background_tasks.append(ngrok_task)
        
        # Start position monitoring via PositionMonitor service
        position_task = asyncio.create_task(
            self._position_monitor.start_monitoring(
                shutdown_event=self.shutdown_event,
                on_profit_opportunity=self._execute_profit_taking,
                on_fill_detected=self._handle_order_fill,
                on_status_log=self.log_position_status,
                check_fills_callback=self.order_manager.check_and_update_fills
            )
        )
        self.background_tasks.append(position_task)
        
        # Start order monitoring
        order_task = asyncio.create_task(self._monitor_orders())
        self.background_tasks.append(order_task)
        
        # Start market data updates via PositionMonitor service
        market_task = asyncio.create_task(
            self._position_monitor.update_market_data(shutdown_event=self.shutdown_event)
        )
        self.background_tasks.append(market_task)
        
        logger.info("All components started")
    
    async def _handle_trading_signal(self, signal: TradingSignal) -> None:
        """
        Handle incoming trading signals from TradingView.
        This is the main signal processing pipeline using the advanced strategy.
        """
        try:
            logger.info(f"Processing signal: {signal.symbol} {signal.signal_type.value} @ {signal.price}")
            
            # Store signal for tracking
            self.processed_signals[signal.signal_id] = signal
            
            # Risk validation
            if not await self.risk_manager.validate_signal(signal):
                logger.warning(f"Signal rejected by risk manager: {signal.signal_id}")
                return
            
            # Use advanced strategy to handle the signal
            await self.advanced_strategy.process_signal(signal)
            
            logger.info(f"Signal processed successfully: {signal.signal_id}")
            
        except Exception as e:
            logger.error(f"Error processing signal {signal.signal_id}: {str(e)}")
    
    async def _handle_buy_signal(self, signal: TradingSignal) -> None:
        """Handle buy signals - DCA is now handled by AdvancedTradingStrategy."""
        try:
            symbol = signal.symbol
            
            # Check if we already have a position
            existing_position = await self.position_manager.get_position(symbol)
            
            if existing_position and existing_position.quantity > 0:
                # We already have a long position - DCA is handled by AdvancedTradingStrategy
                # The martingale DCA logic monitors positions and places DCA orders automatically
                logger.info(f"Position exists for {symbol} - DCA handled by AdvancedTradingStrategy")
                return
            
            # Calculate position size
            position_size = await self.risk_manager.calculate_position_size(symbol, signal)
            
            # Create buy order
            order = Order(
                order_id=None,
                symbol=symbol,
                quantity=position_size,
                order_type=OrderType.MARKET if signal.price == 0 else OrderType.LIMIT,
                side=OrderSide.BUY,
                price=signal.price if signal.price > 0 else None
            )
            
            # Place order
            order_id = await self.order_manager.place_order(order)
            logger.info(f"Buy order placed: {order_id}")
            
        except Exception as e:
            logger.error(f"Error handling buy signal: {str(e)}")
    
    async def _handle_sell_signal(self, signal: TradingSignal) -> None:
        """Handle sell signals."""
        try:
            symbol = signal.symbol
            
            # Check if we have a position to sell
            position = await self.position_manager.get_position(symbol)
            
            if not position or position.quantity <= 0:
                logger.warning(f"No position to sell for {symbol}")
                return
            
            # Calculate quantity to sell
            sell_quantity = signal.quantity or position.quantity
            
            # Create sell order
            order = Order(
                order_id=None,
                symbol=symbol,
                quantity=sell_quantity,
                order_type=OrderType.MARKET if signal.price == 0 else OrderType.LIMIT,
                side=OrderSide.SELL,
                price=signal.price if signal.price > 0 else None
            )
            
            # Place order
            order_id = await self.order_manager.place_order(order)
            logger.info(f"Sell order placed: {order_id}")
            
        except Exception as e:
            logger.error(f"Error handling sell signal: {str(e)}")
    
    async def _handle_close_signal(self, signal: TradingSignal) -> None:
        """Handle close signals - close all positions for the symbol."""
        try:
            symbol = signal.symbol
            position = await self.position_manager.get_position(symbol)
            
            if not position:
                logger.warning(f"No position to close for {symbol}")
                return
            
            # Use ExitPlanner to build exit order
            exit_plan = await self._exit_planner.plan_exit(
                position,
                reason="signal_close"
            )
            
            # Submit the exit order
            order = exit_plan.to_order()
            order_id = await self.order_manager.place_order(order)
            logger.info(f"Close order placed: {order_id}")
            
        except Exception as e:
            logger.error(f"Error handling close signal: {str(e)}")
    
    async def _monitor_unfilled_orders_aggressively(self) -> None:
        """
        Monitor unfilled orders and aggressively adjust prices for better fill rates.
        Implements intelligent order management with price improvements.
        """
        try:
            # Get all open orders
            open_orders = await self.order_manager.get_open_orders()
            
            if not open_orders:
                return
            
            logger.debug(f"🔍 Monitoring {len(open_orders)} open orders for aggressive management")
            
            # Configure aggressive timeouts
            aggressive_timeout_minutes = self.config.get_config("trading.aggressive_order_timeout_minutes", 5)  # 5 minutes default
            price_adjustment_percent = self.config.get_config("trading.max_price_adjustment_percent", 0.3)  # 0.3% default
            
            for order in open_orders:
                try:
                    # Skip market orders (they should fill immediately)
                    if order.order_type != OrderType.LIMIT:
                        continue
                    
                    # Check order age
                    order_age_minutes = None
                    if order.created_at:
                        from datetime import datetime
                        age_delta = datetime.utcnow() - order.created_at.replace(tzinfo=None)
                        order_age_minutes = age_delta.total_seconds() / 60.0
                    
                    # Skip very new orders (give them a chance to fill naturally)
                    if order_age_minutes is None or order_age_minutes < 2:
                        continue
                    
                    # Get current market price for comparison
                    current_market_price = await self.broker_subsystem.market_data.get_current_price(order.symbol)
                    
                    # Log unfilled order status
                    logger.info(f"📋 UNFILLED ORDER: {order.symbol} {order.side.value} {order.quantity} @ ${order.price:.4f}")
                    logger.info(f"   Age: {order_age_minutes:.1f} minutes")
                    logger.info(f"   Current Market: ${current_market_price:.4f}")
                    price_diff = abs(order.price - current_market_price)
                    price_diff_percent = (price_diff / current_market_price) * 100
                    logger.info(f"   Price Gap: ${price_diff:.4f} ({price_diff_percent:.2f}%)")
                    
                    # Decide if aggressive action is needed
                    should_adjust = False
                    adjustment_reason = ""
                    
                    if order_age_minutes >= aggressive_timeout_minutes:
                        should_adjust = True
                        adjustment_reason = f"timeout_{order_age_minutes:.1f}min"
                    elif price_diff_percent > 1.0:  # If price is more than 1% away from market
                        should_adjust = True
                        adjustment_reason = f"price_gap_{price_diff_percent:.1f}%"
                    
                    if should_adjust:
                        logger.info(f"🚀 AGGRESSIVE ORDER MANAGEMENT: {order.symbol}")
                        logger.info(f"   Reason: {adjustment_reason}")
                        logger.info(f"   Action: Adjusting price toward market for better fill")
                        
                        # Attempt aggressive price adjustment
                        new_order_id = await self.order_manager.adjust_order_price_aggressively(
                            order.order_id, 
                            current_market_price, 
                            max_adjustment_percent=price_adjustment_percent
                        )
                        
                        if new_order_id:
                            logger.info(f"✅ Order aggressively adjusted: {order.order_id} → {new_order_id}")
                        else:
                            logger.debug(f"No adjustment needed/possible for order {order.order_id}")
                    else:
                        logger.debug(f"Order {order.order_id} within normal parameters, monitoring...")
                        
                except Exception as order_error:
                    logger.error(f"❌ Error monitoring order {order.order_id}: {order_error}")
                    continue
                    
        except Exception as e:
            logger.error(f"❌ Error in aggressive order monitoring: {str(e)}")
    
    async def _execute_profit_taking(self, position: Position, current_price: float) -> None:
        """Execute profit taking for a position."""
        try:
            logger.info(f"💰 POSITION EXIT: {position.symbol}")
            logger.info(f"   Position: {position.quantity:.2f} @ ${position.avg_price:.2f}")
            logger.info(f"   Current Price: ${current_price:.2f}")
            
            # Calculate profit percentage
            if position.quantity > 0:  # Long position
                profit_pct = (current_price - position.avg_price) / position.avg_price * 100
            else:  # Short position
                profit_pct = (position.avg_price - current_price) / position.avg_price * 100
            
            logger.info(f"   Profit: {profit_pct:.2f}%")
            
            # Determine if this is profit-taking or stop-loss
            is_profit = profit_pct >= 0  # Include breakeven as profit-taking
            action_type = "PROFIT TAKING" if is_profit else "STOP LOSS"
            
            logger.info(f"🎯 {action_type} TRIGGERED: {position.symbol}")
            
            # Verify actual position with broker before proceeding
            actual_position_qty = await self.broker_subsystem.primary_account_provider.get_actual_position(position.symbol)
            if actual_position_qty is None:
                logger.error(f"❌ Could not verify actual position for {position.symbol}, skipping profit taking")
                return
            
            # Handle position already closed externally
            if actual_position_qty == 0:
                await self._handle_externally_closed_position(position)
                return
            
            # Check if database and broker positions match direction (sign)
            if not self._validate_position_direction(position, actual_position_qty):
                return
            
            logger.info(f"✅ Position verified - DB: {position.quantity}, Broker: {actual_position_qty}")
            
            # Get pending orders and calculate available quantity
            open_orders = await self.order_manager.get_open_orders()
            pending_qty = self._calculate_pending_quantity(position, open_orders)
            
            # Validate exit quantity using ExitPlanner
            available_qty, is_valid = self._exit_planner.validate_exit_quantity(
                requested_qty=abs(position.quantity),
                position_qty=position.quantity,
                pending_qty=pending_qty
            )
            
            if not is_valid or available_qty <= 0:
                logger.warning(f"⚠️  NO AVAILABLE QUANTITY: {position.symbol} - pending orders cover position")
                return
            
            # Final safety check: don't exit more than we actually own in broker
            max_available = abs(actual_position_qty)
            if available_qty > max_available:
                logger.warning(f"⚠️ QUANTITY ADJUSTMENT: Reducing from {available_qty} to {max_available}")
                available_qty = max_available
            
            if available_qty <= 0:
                logger.warning(f"⚠️ NO QUANTITY TO CLOSE: {position.symbol}")
                return
            
            # Use ExitPlanner to build exit order
            exit_plan = await self._exit_planner.plan_exit(
                position,
                reason=action_type.lower().replace(" ", "_"),
                quantity_override=available_qty,
                current_price=current_price  # Reuse fetched price
            )
            
            # Submit the exit order
            order = exit_plan.to_order()
            order_id = await self.order_manager.place_order(order)
            
            # Log with appropriate action type
            action_emoji = "💰" if is_profit else "🛑"
            action_name = "PROFIT ORDER" if is_profit else "STOP LOSS ORDER"
            logger.info(f"{action_emoji} {action_name}: {position.symbol} {order.side.value} {available_qty} shares (Order ID: {order_id})")
            
            # Reset trailing state
            self.trailing_manager.reset_trailing_state(position.symbol)
            
        except Exception as e:
            error_msg = str(e)
            if "insufficient qty available" in error_msg.lower():
                logger.error(f"❌ INSUFFICIENT QUANTITY: {position.symbol} - Cannot place order due to pending orders or insufficient shares")
                logger.error(f"   Suggestion: Check for pending orders and cancel if necessary")
                # Don't retry immediately - let the monitoring cycle handle it
            else:
                logger.error(f"❌ Error executing profit taking: {error_msg}")
    
    async def _handle_externally_closed_position(self, position: Position) -> None:
        """Handle position that was closed externally (outside the bot)."""
        logger.info(f"📋 POSITION ALREADY CLOSED: {position.symbol}")
        logger.info(f"   Database shows: {position.quantity} @ ${position.avg_price:.2f}")
        logger.info(f"   Broker shows: 0 (position was closed externally)")
        
        # Use TradeService to handle trade completion
        await self._trade_service.handle_externally_closed_position(
            symbol=position.symbol,
            position_quantity=position.quantity
        )
        
        # Close the position in our database
        try:
            await self.position_manager.close_position(position.symbol)
            logger.info(f"✅ POSITION CLOSED IN DATABASE: {position.symbol}")
        except Exception as close_error:
            logger.error(f"❌ Failed to close position in database: {close_error}")
    
    def _validate_position_direction(self, position: Position, actual_position_qty: float) -> bool:
        """Validate that database and broker position directions match."""
        db_sign = 1 if position.quantity > 0 else -1
        broker_sign = 1 if actual_position_qty > 0 else -1
        
        if db_sign != broker_sign:
            logger.error(f"❌ POSITION DIRECTION MISMATCH for {position.symbol}:")
            logger.error(f"   Database: {position.quantity} ({'LONG' if position.quantity > 0 else 'SHORT'})")
            logger.error(f"   Broker: {actual_position_qty} ({'LONG' if actual_position_qty > 0 else 'SHORT'})")
            logger.error(f"   Cannot safely place profit-taking order - manual intervention required")
            return False
        return True
    
    def _calculate_pending_quantity(self, position: Position, open_orders: List[Order]) -> float:
        """Calculate pending quantity for a position from open orders."""
        pending_sell_qty = 0
        pending_buy_qty = 0
        
        for order in open_orders:
            if order.symbol == position.symbol:
                if order.side == OrderSide.SELL:
                    pending_sell_qty += order.quantity
                elif order.side == OrderSide.BUY:
                    pending_buy_qty += order.quantity
        
        # Return pending quantity in the exit direction
        if position.quantity > 0:  # Long position exits via sell
            return pending_sell_qty
        else:  # Short position exits via buy
            return pending_buy_qty
    
    async def _monitor_orders(self) -> None:
        """Monitor open orders for fills and timeouts."""
        try:
            while self.is_running and not self.shutdown_event.is_set():
                try:
                    open_orders = await self.order_manager.get_open_orders()
                    
                    for order in open_orders:
                        # Check for fills - this will refresh order status and fill info
                        current_status = await self.order_manager.get_order_status(order.order_id)
                        
                        if current_status == OrderStatus.FILLED:
                            # Get the refreshed order object with fill information
                            filled_order = await self._get_refreshed_order(order.order_id)
                            if filled_order:
                                await self._handle_order_fill(filled_order)
                            else:
                                logger.warning(f"Could not get refreshed order data for {order.order_id}")
                                await self._handle_order_fill(order)  # Fallback to original order
                        elif current_status == OrderStatus.CANCELED:
                            await self._handle_order_cancel(order)
                    
                    # Check at configurable interval or until shutdown
                    order_interval = self.config.get_config("monitoring.order_monitoring_interval", 5)
                    try:
                        await asyncio.wait_for(self.shutdown_event.wait(), timeout=order_interval)
                        break  # Shutdown signal received
                    except asyncio.TimeoutError:
                        continue  # Continue monitoring
                        
                except Exception as e:
                    logger.error(f"Error monitoring orders: {str(e)}")
                    try:
                        await asyncio.wait_for(self.shutdown_event.wait(), timeout=30)
                        break  # Shutdown signal received
                    except asyncio.TimeoutError:
                        continue  # Continue monitoring
        except asyncio.CancelledError:
            logger.debug("Order monitor task cancelled")
            raise
    
    async def _handle_order_fill(self, order: Order) -> None:
        """Handle order fill events with enhanced fill price validation."""
        try:
            logger.info(f"🔄 Processing order fill: {order.order_id}")
            
            # CRITICAL: Always get the actual fill price from broker
            actual_fill_price = await self.order_manager.get_actual_fill_price(order.order_id)
            
            if actual_fill_price is not None:
                # Update order with actual fill price
                original_price = order.price
                order.filled_price = actual_fill_price
                order.filled_at = datetime.utcnow()
                
                logger.info(f"✅ ACTUAL FILL PRICE CAPTURED: {order.symbol} {order.side.value} "
                           f"@ ${actual_fill_price:.4f}")
                
                if original_price and abs(actual_fill_price - original_price) > 0.01:
                    price_diff = actual_fill_price - original_price
                    logger.info(f"📊 PRICE SLIPPAGE: Order: ${original_price:.4f}, "
                               f"Fill: ${actual_fill_price:.4f}, "
                               f"Difference: ${price_diff:+.4f}")
            else:
                logger.error(f"❌ CRITICAL: Cannot get actual fill price for {order.order_id}!")
                
                # Force refresh one more time
                logger.info("🔄 Forcing order refresh to capture fill price...")
                await self.order_manager._refresh_order_status(order.order_id)
                
                # Try to get the fill price again
                updated_order = await self.order_manager.get_order_by_id(order.order_id)
                if updated_order and updated_order.filled_price:
                    order.filled_price = updated_order.filled_price
                    order.filled_at = updated_order.filled_at
                    logger.info(f"✅ Fill price recovered: ${order.filled_price:.4f}")
                else:
                    # Last resort: use order price with warning
                    logger.warning(f"⚠️ Using order price ${order.price:.4f} as fallback for fill price")
                    order.filled_price = order.price
                    order.filled_at = datetime.utcnow()
            
            # Validate we have a fill price
            fill_price = order.filled_price
            if fill_price is None:
                raise OrderExecutionException(f"Cannot process fill without fill price for order {order.order_id}")
            
            logger.info(f"📈 PROCESSING FILL: {order.symbol} {order.side.value} "
                       f"{order.quantity} @ ${fill_price:.4f}")
            
            # Update position with actual fill price (this is critical for trailing stops)
            quantity_change = order.quantity if order.side == OrderSide.BUY else -order.quantity
            await self.position_manager.update_position(
                order.symbol, 
                quantity_change, 
                fill_price  # Use actual fill price for position calculations
            )
            
            # CRITICAL: Update strategy position with actual fill price
            if self.advanced_strategy and order.symbol in self.advanced_strategy.positions:
                strategy_position = self.advanced_strategy.positions[order.symbol]
                
                # Check if this is a DCA order that needs fill price update
                is_dca_order = self.order_manager.is_dca_order(order.order_id)
                
                # Recalculate average price with actual fill price
                if strategy_position.quantity != 0:
                    old_total_cost = strategy_position.quantity * strategy_position.average_price
                    old_avg_price = strategy_position.average_price
                    
                    # Add this order's contribution with actual fill price
                    new_total_cost = old_total_cost + (quantity_change * fill_price)
                    new_total_quantity = strategy_position.quantity + quantity_change
                    
                    if new_total_quantity != 0:
                        strategy_position.average_price = abs(new_total_cost / new_total_quantity)
                        strategy_position.quantity = new_total_quantity
                        
                        logger.info(f"🔄 STRATEGY POSITION UPDATED: {order.symbol}")
                        logger.info(f"   Old avg: ${old_avg_price:.4f}, New avg: ${strategy_position.average_price:.4f}")
                        logger.info(f"   Quantity: {strategy_position.quantity}")
                
                # CRITICAL FIX: Update DCA tracking with ACTUAL FILL PRICE instead of order price
                if is_dca_order:
                    # CRITICAL: Increment DCA attempt counter only on successful fill (not placement)
                    strategy_position.averaging_attempts += 1
                    logger.info(f"🔢 DCA ATTEMPT COMPLETED: {order.symbol} attempt #{strategy_position.averaging_attempts}")
                    
                    # Get the actual order price that was originally tracked
                    original_order_price = order.price
                    
                    # Update DCA tracking to use FILL price instead of ORDER price
                    if strategy_position.last_dca_price == original_order_price:
                        logger.info(f"🔧 FIXING DCA PRICE TRACKING: {order.symbol}")
                        logger.info(f"   Replacing ORDER price ${original_order_price:.4f} with FILL price ${fill_price:.4f}")
                        
                        # Update the last DCA price to the actual fill price
                        strategy_position.last_dca_price = fill_price
                        
                        # Update the DCA price history as well
                        if strategy_position.dca_order_prices and strategy_position.dca_order_prices[-1] == original_order_price:
                            strategy_position.dca_order_prices[-1] = fill_price
                            logger.info(f"   Updated DCA history: {[f'${p:.2f}' for p in strategy_position.dca_order_prices]}")
                        
                        # Save the corrected DCA metadata to database
                        try:
                            await self.advanced_strategy._save_position_dca_metadata(
                                symbol=order.symbol,
                                attempts=strategy_position.averaging_attempts,
                                prices=strategy_position.dca_order_prices,
                                last_price=strategy_position.last_dca_price
                            )
                            logger.info(f"✅ DCA metadata updated with actual fill price: ${fill_price:.4f}")
                        except Exception as dca_save_error:
                            logger.error(f"❌ Failed to save corrected DCA metadata: {dca_save_error}")
                    
                    logger.info(f"🎯 DCA ORDER FILL PROCESSED: {order.symbol}")
                    logger.info(f"   Order Price: ${original_order_price:.4f}")
                    logger.info(f"   Fill Price: ${fill_price:.4f}")
                    logger.info(f"   Price Diff: ${fill_price - original_order_price:+.4f}")
                    logger.info(f"   DCA Level: {strategy_position.averaging_attempts}")
                    logger.info(f"   Next DCA will use: ${fill_price:.4f} as reference price")
            
            # Log position update for transparency
            logger.info(f"📊 Position updated: {order.symbol} {quantity_change:+.2f} @ ${fill_price:.4f}")
            
            # Create trade records for better tracking
            await self._handle_trade_tracking(order)
            
            # Save order to database
            await self.database.save_order(order)
            
        except Exception as e:
            logger.error(f"Error handling order fill: {str(e)}")
    
    async def _handle_trade_tracking(self, order: Order) -> None:
        """Handle trade tracking when orders are filled."""
        try:
            # Convert OrderSide enum to string for comparison
            side_str = order.side.value if hasattr(order.side, 'value') else str(order.side)
            
            if side_str.lower() == "buy":
                # Entry order - create new trade record
                await self.database.create_trade_entry(
                    symbol=order.symbol,
                    entry_order=order,
                    strategy_used="signal_based"  # You can enhance this based on actual strategy
                )
                logger.info(f"Trade entry recorded: {order.symbol} LONG {order.filled_quantity} @ ${order.filled_price:.4f}")
                
            else:
                # Exit order - complete existing trade
                # Find the corresponding open trade
                open_trades = await self.database.get_open_trades(order.symbol)
                
                if open_trades:
                    # Complete the most recent open trade
                    latest_trade = open_trades[-1]  # Get the last opened trade
                    trade_summary = await self.database.complete_trade(
                        trade_id=latest_trade['trade_id'],
                        exit_order=order,
                        exit_reason="profit_taking"  # You can determine this based on context
                    )
                    
                    logger.info(f"Trade completed: {order.symbol} - "
                               f"P&L: ${trade_summary['realized_pnl']:.2f} "
                               f"({trade_summary['profit_percentage']:.2f}%)")
                else:
                    logger.warning(f"Exit order {order.order_id} filled but no open trade found for {order.symbol}")
                    
        except Exception as e:
            logger.error(f"Error in trade tracking: {str(e)}")
    
    async def _handle_order_cancel(self, order: Order) -> None:
        """Handle order cancellation events."""
        logger.info(f"🚫 Order canceled: {order.order_id} ({order.symbol})")
        
        # CRITICAL: Clean up DCA tracking for cancelled orders
        if self.order_manager.is_dca_order(order.order_id):
            logger.info(f"🧹 CLEANING UP CANCELLED DCA ORDER: {order.symbol}")
            
            # Remove from strategy position's active orders
            if self.advanced_strategy and order.symbol in self.advanced_strategy.positions:
                strategy_position = self.advanced_strategy.positions[order.symbol]
                if order.order_id in strategy_position.active_orders:
                    strategy_position.active_orders.remove(order.order_id)
                    logger.info(f"   Removed {order.order_id} from active orders list")
                
                # Don't increment averaging_attempts for cancelled orders
                logger.info(f"   DCA attempts remain at: {strategy_position.averaging_attempts}")
                logger.info(f"   Next DCA order will be attempt #{strategy_position.averaging_attempts + 1}")
            
            # Clean up order manager's DCA tracking
            if self.order_manager.clear_dca_metadata(order.order_id):
                logger.info(f"   Cleaned up DCA metadata for {order.order_id}")
        
        await self.database.save_order(order)
    
    async def _get_refreshed_order(self, order_id: str) -> Optional[Order]:
        """Get the most up-to-date order information including fill data."""
        try:
            # Check if order is in active orders (updated by refresh)
            order = self.order_manager.get_active_order(order_id)
            if order:
                return order
            
            # Check order history (moved there after fill)
            order = self.order_manager.get_historical_order(order_id)
            if order:
                return order
            
            logger.warning(f"Order {order_id} not found in active orders or history")
            return None
            
        except Exception as e:
            logger.error(f"Error getting refreshed order {order_id}: {str(e)}")
            return None
    
    async def get_trading_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive trading summary with accurate P&L tracking.
        
        Returns:
            Dictionary with current positions, open trades, recent trades, and performance
        """
        try:
            # Get current positions
            positions = await self.position_manager.get_all_positions()
            
            # Get open trades
            open_trades = await self.database.get_open_trades()
            
            # Get recent completed trades
            completed_trades = await self.database.get_completed_trades(limit=20)
            
            # Calculate performance metrics
            total_realized_pnl = sum(trade['realized_pnl'] for trade in completed_trades if trade['realized_pnl'])
            winning_trades = [t for t in completed_trades if t['realized_pnl'] and t['realized_pnl'] > 0]
            losing_trades = [t for t in completed_trades if t['realized_pnl'] and t['realized_pnl'] < 0]
            
            win_rate = (len(winning_trades) / len(completed_trades) * 100) if completed_trades else 0
            avg_win = sum(t['realized_pnl'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss = sum(t['realized_pnl'] for t in losing_trades) / len(losing_trades) if losing_trades else 0
            
            summary = {
                'timestamp': datetime.utcnow().isoformat(),
                'current_positions': [],
                'open_trades': open_trades,
                'recent_trades': completed_trades,
                'performance': {
                    'total_realized_pnl': total_realized_pnl,
                    'total_trades': len(completed_trades),
                    'winning_trades': len(winning_trades),
                    'losing_trades': len(losing_trades),
                    'win_rate_percent': win_rate,
                    'average_win': avg_win,
                    'average_loss': avg_loss,
                    'profit_factor': abs(avg_win / avg_loss) if avg_loss != 0 else 0
                }
            }
            
            # Add current position details
            for position in positions:
                if position.quantity != 0:
                    current_price = await self.broker_subsystem.market_data.get_current_price(position.symbol)
                    unrealized_pnl = (current_price - position.avg_price) * position.quantity
                    unrealized_pct = ((current_price - position.avg_price) / position.avg_price) * 100
                    
                    # Get position tracking info
                    tracking = await self.database.get_position_tracking(position.symbol)
                    
                    position_info = {
                        'symbol': position.symbol,
                        'quantity': position.quantity,
                        'avg_price': position.avg_price,
                        'current_price': current_price,
                        'unrealized_pnl': unrealized_pnl,
                        'unrealized_percent': unrealized_pct,
                        'is_trailing': tracking['is_trailing'] if tracking else False,
                        'trailing_activation_price': tracking['trailing_activation_price'] if tracking else None,
                        'trailing_stop_price': tracking['trailing_stop_price'] if tracking else None
                    }
                    
                    summary['current_positions'].append(position_info)
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating trading summary: {str(e)}")
            return {'error': str(e)}
    
    async def log_position_status(self) -> None:
        """Log detailed position status for debugging and monitoring."""
        try:
            summary = await self.get_trading_summary()
            
            logger.info("📊 TRADING SUMMARY:")
            logger.info(f"   Total P&L: ${summary['performance']['total_realized_pnl']:.2f}")
            logger.info(f"   Win Rate: {summary['performance']['win_rate_percent']:.1f}%")
            logger.info(f"   Open Positions: {len(summary['current_positions'])}")
            logger.info(f"   Open Trades: {len(summary['open_trades'])}")
            
            for pos in summary['current_positions']:
                trailing_info = ""
                if pos['is_trailing']:
                    trailing_info = f" [TRAILING from ${pos['trailing_activation_price']:.2f}, stop @ ${pos['trailing_stop_price']:.2f}]"
                
                logger.info(f"   • {pos['symbol']}: {pos['quantity']} @ ${pos['avg_price']:.2f} "
                           f"(Current: ${pos['current_price']:.2f}, "
                           f"P&L: ${pos['unrealized_pnl']:.2f} / {pos['unrealized_percent']:.2f}%){trailing_info}")
            
        except Exception as e:
            logger.error(f"Error logging position status: {str(e)}")
    
    async def _cancel_all_orders(self) -> None:
        """Cancel all open orders during shutdown."""
        try:
            open_orders = await self.order_manager.get_open_orders()
            
            for order in open_orders:
                await self.order_manager.cancel_order(order.order_id)
                
            logger.info(f"Canceled {len(open_orders)} open orders")
            
        except Exception as e:
            logger.error(f"Error canceling orders: {str(e)}")
    
    async def _run_main_loop(self) -> None:
        """Main event loop - wait for shutdown signal."""
        try:
            logger.info("Main event loop started, waiting for shutdown signal...")
            await self.shutdown_event.wait()
            logger.info("Shutdown signal received, stopping bot...")
            await self.stop()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, stopping bot...")
            await self.stop()
        except Exception as e:
            logger.error(f"Error in main loop: {str(e)}")
            await self.stop()
    
    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        # Simple signal handlers that just set the shutdown event
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating shutdown...")
            if not self.shutdown_event.is_set():
                self.shutdown_event.set()
        
        try:
            signal.signal(signal.SIGINT, signal_handler)
            if hasattr(signal, 'SIGTERM'):
                signal.signal(signal.SIGTERM, signal_handler)
        except Exception as e:
            # This is not critical - we can rely on KeyboardInterrupt in the main loop
            logger.debug(f"Could not set signal handlers: {e}")
    
    async def _monitor_ngrok_tunnel(self) -> None:
        """Monitor ngrok tunnel health and display status periodically."""
        if not self.ngrok_manager:
            return
        
        try:
            # Initial delay to let the bot settle
            await asyncio.sleep(30)
            
            while self.is_running and not self.shutdown_event.is_set():
                try:
                    if self.ngrok_manager.is_tunnel_active():
                        tunnel_url = self.ngrok_manager.get_tunnel_url()
                        if tunnel_url:
                            logger.info(f"🌐 ngrok tunnel active: {tunnel_url}")
                        else:
                            logger.warning("🔍 ngrok process running but no tunnel URL available")
                    else:
                        logger.warning("⚠️  ngrok tunnel is not active - webhooks will not work")
                        print("\n" + "="*60)
                        print("⚠️  NGROK TUNNEL DOWN")
                        print("="*60)
                        print("   Your ngrok tunnel has stopped working.")
                        print("   TradingView webhooks will not reach your bot.")
                        print("   The bot will continue running but won't receive signals.")
                        print("   Consider restarting the bot to restore the tunnel.")
                        print("="*60)
                    
                    # Check every 5 minutes or until shutdown
                    try:
                        await asyncio.wait_for(self.shutdown_event.wait(), timeout=300)
                        break  # Shutdown signal received
                    except asyncio.TimeoutError:
                        continue  # Continue monitoring
                        
                except Exception as e:
                    logger.error(f"Error monitoring ngrok tunnel: {e}")
                    try:
                        await asyncio.wait_for(self.shutdown_event.wait(), timeout=60)
                        break  # Shutdown signal received
                    except asyncio.TimeoutError:
                        continue  # Continue monitoring
        except asyncio.CancelledError:
            logger.debug("ngrok monitor task cancelled")
            raise
    
    def _check_external_ngrok(self) -> Dict[str, Any]:
        """
        Check if ngrok is running externally and return tunnel information.
        
        Returns:
            Dict with keys: 'running', 'tunnel_url', 'webhook_url', 'monitor_url', 'error'
        """
        import json
        import urllib.request
        
        result = {
            'running': False,
            'tunnel_url': None,
            'webhook_url': None,
            'monitor_url': 'http://localhost:4040',
            'error': None
        }
        
        try:
            # Try to connect to ngrok API
            api_endpoints = [
                "http://localhost:4040/api/tunnels",
                "http://127.0.0.1:4040/api/tunnels"
            ]
            
            data = None
            for api_url in api_endpoints:
                try:
                    with urllib.request.urlopen(api_url, timeout=3) as response:
                        data = json.loads(response.read().decode())
                        break
                except Exception:
                    continue
            
            if not data:
                return result
            
            result['running'] = True
            tunnels = data.get("tunnels", [])
            
            # Find the best tunnel (prefer HTTPS)
            best_tunnel = None
            for tunnel in tunnels:
                if tunnel.get("proto") == "https":
                    best_tunnel = tunnel
                    break
            
            # Fallback to HTTP tunnel
            if not best_tunnel:
                for tunnel in tunnels:
                    if tunnel.get("proto") == "http":
                        best_tunnel = tunnel
                        break
            
            if best_tunnel:
                tunnel_url = best_tunnel.get("public_url")
                if tunnel_url:
                    # Ensure HTTPS for TradingView compatibility
                    if tunnel_url.startswith("http://"):
                        tunnel_url = tunnel_url.replace("http://", "https://")
                    
                    result['tunnel_url'] = tunnel_url
                    result['webhook_url'] = f"{tunnel_url}/webhook"
            
            return result
            
        except Exception as e:
            result['error'] = f"Error checking ngrok: {str(e)}"
            return result

    # Public API methods for users
    async def get_status(self) -> Dict[str, Any]:
        """Get current bot status."""
        positions = await self.position_manager.get_all_positions()
        open_orders = await self.order_manager.get_open_orders()
        
        return {
            "is_running": self.is_running,
            "positions": len([p for p in positions if p.quantity != 0]),
            "open_orders": len(open_orders),
            "total_unrealized_pnl": sum(p.unrealized_pnl for p in positions),
            "signal_listener_running": self.signal_listener.is_running if self.signal_listener else False,
            "processed_signals": len(self.processed_signals)
        }
    
    async def get_positions(self) -> List[Position]:
        """Get all current positions."""
        return await self.position_manager.get_all_positions()
    
    async def get_open_orders(self) -> List[Order]:
        """Get all open orders."""
        return await self.order_manager.get_open_orders()
    
    async def manual_close_position(self, symbol: str) -> bool:
        """Manually close a position."""
        try:
            position = await self.position_manager.get_position(symbol)
            if not position or position.quantity == 0:
                return False
            
            # Use ExitPlanner to build exit order
            exit_plan = await self._exit_planner.plan_exit(
                position,
                reason="manual_close"
            )
            
            # Submit the exit order
            order = exit_plan.to_order()
            await self.order_manager.place_order(order)
            return True
            
        except Exception as e:
            logger.error(f"Error manually closing position: {str(e)}")
            return False


# Context manager for easy usage
@asynccontextmanager
async def trading_bot_context(config_file: str = None):
    """
    Context manager for easy trading bot usage.
    
    Args:
        config_file: DEPRECATED - No longer used. Configuration is loaded from
                    config/ directory. Set TRADING_BOT_ENV for environment selection.
    """
    bot = TradingBotOrchestrator(config_file)
    try:
        yield bot
    finally:
        if bot.is_running:
            await bot.stop()


# Main entry point for users
async def run_trading_bot(config_file: str = None) -> None:
    """
    Main entry point to run the trading bot.
    
    Args:
        config_file: DEPRECATED - No longer used. Configuration is loaded from
                    config/ directory. Set TRADING_BOT_ENV for environment selection.
    """
    bot = TradingBotOrchestrator(config_file)
    await bot.start()


# Command line interface
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Trading Bot")
    parser.add_argument("--env", choices=["demo", "live"], default="demo",
                       help="Trading environment (demo or live)")
    parser.add_argument("--validate", action="store_true", help="Validate configuration only")
    
    args = parser.parse_args()
    
    # Set environment before loading config
    if args.env:
        os.environ["TRADING_BOT_ENV"] = args.env
    
    if args.validate:
        # Validate configuration using centralized startup validation
        from src.config.settings import validate_and_exit_on_error
        config = validate_and_exit_on_error()
        print(f"✅ Configuration for '{args.env}' environment is valid!")
    else:
        # Run the bot
        asyncio.run(run_trading_bot())
