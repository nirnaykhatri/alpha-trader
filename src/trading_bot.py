"""
Trading Bot Integration Layer

This module brings together all components to create a complete trading system.
The TradingBotOrchestrator serves as a thin facade delegating to specialized components:
- ComponentInitializer: Handles component creation and initialization
- ShutdownCoordinator: Manages graceful shutdown sequence
- SignalProcessor: Routes and processes trading signals
- ExecutionPolicyService: Profit-taking and order adjustment policy decisions
- ReconciliationService: Broker/database state synchronization
- TradingSummaryService: Performance reporting and summaries

Key Improvements (v1.2.0):
- Extracted policy logic to dedicated services (ExecutionPolicyService, etc.)
- Orchestrator now focuses purely on lifecycle + wiring (composition root)
- Policy decisions delegated to services, execution remains in orchestrator
- Integration with TaskRegistry for proper task lifecycle management
- All background tasks are tracked and can be properly cancelled on shutdown
- Ordered shutdown by task category (signal handlers first, infrastructure last)

This refactoring follows the Single Responsibility Principle (SRP).
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
from src.core.task_registry import get_task_registry, TaskCategory
from src.signals import TradingViewSignalListener
from src.trading import OrderManager
from src.broker.subsystem import BrokerSubsystem
from src.broker.interfaces import BrokerType
from src.strategies import DCAStrategy, TrailingManager
from src.risk import RiskManager
from src.position import PositionManager
from src.database import CosmosDBManager

# Utility imports
from src.utils import run_blocking, BoundedFetcher

# Data models
from src import TradingSignal, Order, Position, OrderType, OrderSide, OrderStatus, SignalType
from src.interfaces import IAsyncContextManager
from src.exceptions import TradingBotException, ConfigurationException, OrderExecutionException
from src.trading import OrderManager, ExitPlanner, TradeService, PositionMonitor
from src.services.fill_processor import FillProcessor

# Policy services (extracted from orchestrator for SRP compliance)
from src.services.execution_policy_service import (
    ExecutionPolicyService,
    create_execution_policy_service,
)
from src.services.reconciliation_service import (
    ReconciliationService,
    create_reconciliation_service,
)
from src.services.trading_summary_service import (
    TradingSummaryService,
    create_trading_summary_service,
)

# Extracted components (SRP refactoring)
from src.bot_engine.component_initializer import ComponentInitializer, InitializedComponents
from src.bot_engine.shutdown_coordinator import ShutdownCoordinator
from src.bot_engine.signal_processor import SignalProcessor


logger = get_logger(__name__)


class TradingBotOrchestrator(IAsyncContextManager):
    """
    Main orchestrator class that coordinates all trading bot components.
    
    This is a pure composition root (thin facade) that delegates to specialized components:
    - ComponentInitializer: Creates and initializes all subsystems
    - ShutdownCoordinator: Handles graceful shutdown sequence
    - SignalProcessor: Routes trading signals to handlers
    - ExecutionPolicyService: Policy decisions for profit-taking and order management
    - ReconciliationService: Broker/database state synchronization
    - TradingSummaryService: Performance reporting and summaries
    
    Orchestrator responsibilities (ONLY lifecycle + wiring):
    - Component initialization and dependency injection
    - Starting/stopping background tasks
    - Signal routing to appropriate handlers
    - Shutdown coordination
    
    Policy decisions are delegated to services:
    - Whether to execute profit-taking → ExecutionPolicyService
    - Whether to adjust orders → ExecutionPolicyService
    - State reconciliation → ReconciliationService
    - Performance reporting → TradingSummaryService
    
    This design follows the Single Responsibility Principle (SRP).
    """
    
    def __init__(self, config_file: str = None):
        """
        Initialize the trading bot orchestrator.
        
        Args:
            config_file: DEPRECATED - No longer used. Configuration is loaded from
                        Azure Key Vault, Azure App Configuration, or environment
                        variables (Azure-first strategy). Kept for backward compatibility.
        """
        if config_file is not None:
            import warnings
            warnings.warn(
                "config_file parameter is deprecated. Configuration is now loaded from "
                "Azure Key Vault, Azure App Configuration, or environment variables "
                "(Azure-first strategy). See docs/AZURE_DEPLOYMENT.md for setup.",
                DeprecationWarning,
                stacklevel=2
            )
        
        # Extracted components (SRP)
        self._component_initializer: Optional[ComponentInitializer] = None
        self._shutdown_coordinator: ShutdownCoordinator = ShutdownCoordinator()
        self._signal_processor: Optional[SignalProcessor] = None
        
        # Policy services (extracted for SRP compliance)
        self._execution_policy: Optional[ExecutionPolicyService] = None
        self._reconciliation_service: Optional[ReconciliationService] = None
        self._summary_service: Optional[TradingSummaryService] = None
        
        self.config: Optional[ConfigurationManager] = None
        self._is_running = False  # Use private var, expose via property
        
        # Track background tasks for proper cleanup
        self.background_tasks: List[asyncio.Task] = []
        
        # Subsystems
        self.broker_subsystem: Optional[BrokerSubsystem] = None
        
        # Component instances
        self.signal_listener: Optional[TradingViewSignalListener] = None
        self.order_manager: Optional[OrderManager] = None
        self.position_manager: Optional[PositionManager] = None
        self.risk_manager: Optional[RiskManager] = None
        self.trailing_manager: Optional[TrailingManager] = None
        self.dca_strategy: Optional[DCAStrategy] = None
        self.database: Optional[CosmosDBManager] = None
        
        # Bounded concurrency utilities
        self._price_fetcher: Optional[BoundedFetcher] = None
        self._exit_planner: Optional[ExitPlanner] = None
        self._trade_service: Optional[TradeService] = None
        self._position_monitor: Optional[PositionMonitor] = None
        self._fill_processor: Optional[FillProcessor] = None
        
        # State tracking
        self.active_positions: Dict[str, Position] = {}
        
        # Rate limiting for error handling
        self.last_error_time: Dict[str, float] = {}  # Track last error time per symbol
        self.error_cooldown = 60  # 60 seconds cooldown between repeated errors
        
        logger.info("TradingBotOrchestrator initialized")
    
    @property
    def shutdown_event(self) -> asyncio.Event:
        """Get the shutdown event from ShutdownCoordinator."""
        return self._shutdown_coordinator.shutdown_event
    
    @property
    def is_running(self) -> bool:
        """Check if the bot is currently running."""
        return self._is_running
    
    @is_running.setter
    def is_running(self, value: bool) -> None:
        """Set the running state."""
        self._is_running = value
    
    @property
    def processed_signals(self) -> Dict[str, TradingSignal]:
        """Get processed signals from SignalProcessor."""
        if self._signal_processor:
            return self._signal_processor.processed_signals
        return {}
    
    async def start(self) -> None:
        """
        Start the trading bot system.
        This is the main entry point for users.
        """
        try:
            logger.info("Starting Trading Bot System...")
            
            # Setup signal handlers FIRST (before any components start)
            self._setup_signal_handlers()
            
            # Initialize all components using ComponentInitializer
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
        """Stop the trading bot system gracefully using ShutdownCoordinator."""
        if not self.is_running:
            logger.debug("Trading bot is already stopped")
            return
        
        self.is_running = False
        
        # Update shutdown coordinator with current component references
        self._shutdown_coordinator.update_components(
            signal_listener=self.signal_listener,
            broker_subsystem=self.broker_subsystem,
            database=self.database,
            order_manager=self.order_manager,
            background_tasks=self.background_tasks
        )
        
        # Delegate shutdown to coordinator
        await self._shutdown_coordinator.shutdown()
    
    async def _initialize_components(self) -> None:
        """Initialize all trading bot components using ComponentInitializer."""
        logger.info("Initializing components...")
        
        # Use ComponentInitializer for component creation
        self._component_initializer = ComponentInitializer()
        
        # Initialize all components
        components = await self._component_initializer.initialize_all(
            signal_callback=self._handle_trading_signal,
            bot_instance=self
        )
        
        # Assign component references for compatibility
        self.config = components.config
        self.database = components.database
        self.broker_subsystem = components.broker_subsystem
        self.position_manager = components.position_manager
        self.risk_manager = components.risk_manager
        self.order_manager = components.order_manager
        self.trailing_manager = components.trailing_manager
        self.dca_strategy = components.dca_strategy
        self.signal_listener = components.signal_listener
        self._price_fetcher = components.price_fetcher
        self._exit_planner = components.exit_planner
        self._trade_service = components.trade_service
        self._position_monitor = components.position_monitor
        self._fill_processor = components.fill_processor
        
        # Initialize SignalProcessor for signal handling
        self._signal_processor = SignalProcessor(
            risk_manager=self.risk_manager,
            position_manager=self.position_manager,
            order_manager=self.order_manager,
            exit_planner=self._exit_planner,
            dca_strategy=self.dca_strategy
        )
        
        # Initialize policy services (v1.2.0 - god module refactoring)
        # These services encapsulate policy decisions, keeping the orchestrator
        # focused purely on lifecycle management and component wiring.
        self._execution_policy = create_execution_policy_service(
            config=self.config,
            exit_planner=self._exit_planner
        )
        
        self._reconciliation_service = create_reconciliation_service(
            position_manager=self.position_manager,
            broker_provider=self.broker_subsystem,
            trade_service=self._trade_service
        )
        
        self._summary_service = create_trading_summary_service(
            position_manager=self.position_manager,
            market_data=self._price_fetcher,
            database=self.database
        )
        
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
        
        # Get the task registry for structured task management
        task_registry = get_task_registry()
        
        # Get webhook configuration
        webhook_host = self.config.get_config("api.webhook.host", "0.0.0.0")
        webhook_port = self.config.get_config("api.webhook.port", 8080)
        
        # Display Azure deployment info
        azure_endpoint = os.getenv("AZURE_CONTAINER_APP_URL", "")
        if azure_endpoint:
            print("\n" + "="*60)
            print("☁️  AZURE CONTAINER APPS DEPLOYMENT")
            print("="*60)
            print(f"🌐 Public URL: {azure_endpoint}")
            print(f"🎯 Webhook URL: {azure_endpoint}/webhook")
            print()
            print("📋 COPY THIS TO TRADINGVIEW:")
            print(f"   {azure_endpoint}/webhook")
            print("="*60)
            logger.info(f"Running on Azure Container Apps: {azure_endpoint}")
        else:
            print("\n" + "="*60)
            print("🏠 LOCAL DEVELOPMENT MODE")
            print("="*60)
            print(f"🔗 Local URL: http://{webhook_host}:{webhook_port}")
            print(f"📚 API Docs: http://{webhook_host}:{webhook_port}/docs")
            print()
            print("💡 For production, deploy to Azure Container Apps")
            print("   See: docs/AZURE_DEPLOYMENT.md")
            print("="*60)
        
        # Start signal listener (category: SIGNAL_HANDLERS - stops first on shutdown)
        signal_task = await task_registry.create_task(
            self.signal_listener.start(),
            name="signal_listener",
            category=TaskCategory.SIGNAL_HANDLERS,
            owner=self,
            critical=True  # Signal listener failure is critical
        )
        self.background_tasks.append(signal_task)
        
        # Start Broker Subsystem (handles market data, TT session, etc.)
        await self.broker_subsystem.start()
        
        # Start position monitoring via PositionMonitor service (category: MONITORING)
        position_task = await task_registry.create_task(
            self._position_monitor.start_monitoring(
                shutdown_event=self.shutdown_event,
                on_profit_opportunity=self._execute_profit_taking,
                on_fill_detected=self._handle_order_fill,
                on_status_log=self.log_position_status,
                check_fills_callback=self.order_manager.check_and_update_fills
            ),
            name="position_monitor",
            category=TaskCategory.MONITORING,
            owner=self
        )
        self.background_tasks.append(position_task)
        
        # Start order monitoring (category: MONITORING)
        order_task = await task_registry.create_task(
            self._monitor_orders(),
            name="order_monitor",
            category=TaskCategory.MONITORING,
            owner=self
        )
        self.background_tasks.append(order_task)
        
        # Start market data updates via PositionMonitor service (category: STREAMING)
        market_task = await task_registry.create_task(
            self._position_monitor.update_market_data(shutdown_event=self.shutdown_event),
            name="market_data_updater",
            category=TaskCategory.STREAMING,
            owner=self
        )
        self.background_tasks.append(market_task)
        
        logger.info("All components started")
    
    async def _handle_trading_signal(self, signal: TradingSignal) -> None:
        """
        Handle incoming trading signals from TradingView.
        Delegates to SignalProcessor for actual processing.
        """
        if self._signal_processor:
            await self._signal_processor.process_signal(signal)
        else:
            logger.warning(f"SignalProcessor not initialized - signal {signal.signal_id} not processed")
    
    async def _handle_buy_signal(self, signal: TradingSignal) -> None:
        """Handle buy signals - delegates to SignalProcessor."""
        if self._signal_processor:
            await self._signal_processor._handle_buy_signal(signal)
    
    async def _handle_sell_signal(self, signal: TradingSignal) -> None:
        """Handle sell signals - delegates to SignalProcessor."""
        if self._signal_processor:
            await self._signal_processor._handle_sell_signal(signal)
    
    async def _handle_close_signal(self, signal: TradingSignal) -> None:
        """Handle close signals - delegates to SignalProcessor."""
        if self._signal_processor:
            await self._signal_processor._handle_close_signal(signal)
    
    async def _monitor_unfilled_orders_aggressively(self) -> None:
        """
        Monitor unfilled orders and aggressively adjust prices for better fill rates.
        
        This method delegates policy decisions to ExecutionPolicyService,
        keeping the orchestrator focused on execution flow rather than
        policy logic (timeout thresholds, price gap rules, etc.).
        """
        try:
            # Get all open orders
            open_orders = await self.order_manager.get_open_orders()
            
            if not open_orders:
                return
            
            logger.debug(f"🔍 Monitoring {len(open_orders)} open orders for aggressive management")
            
            for order in open_orders:
                try:
                    # Skip market orders (they should fill immediately)
                    if order.order_type != OrderType.LIMIT:
                        continue
                    
                    # Get current market price for comparison
                    current_market_price = await self.broker_subsystem.market_data.get_current_price(order.symbol)
                    
                    # Delegate policy decision to ExecutionPolicyService
                    decision = await self._execution_policy.evaluate_order_adjustment(
                        order=order,
                        current_market_price=current_market_price
                    )
                    
                    # Log order status
                    if decision.order_age_minutes is not None:
                        logger.info(f"📋 UNFILLED ORDER: {order.symbol} {order.side.value} {order.quantity} @ ${order.price:.4f}")
                        logger.info(f"   Age: {decision.order_age_minutes:.1f} minutes")
                        logger.info(f"   Current Market: ${current_market_price:.4f}")
                        logger.info(f"   Price Gap: ${decision.price_gap:.4f} ({decision.price_gap_percent:.2f}%)")
                    
                    # Act on the policy decision
                    if not decision.should_adjust:
                        if decision.skip_reason:
                            logger.debug(f"Order {order.order_id}: {decision.skip_reason}")
                        else:
                            logger.debug(f"Order {order.order_id} within normal parameters, monitoring...")
                        continue
                    
                    logger.info(f"🚀 AGGRESSIVE ORDER MANAGEMENT: {order.symbol}")
                    logger.info(f"   Reason: {decision.adjustment_reason}")
                    logger.info(f"   Action: Adjusting price toward market for better fill")
                    
                    # Execute the adjustment using the order manager
                    new_order_id = await self.order_manager.adjust_order_price_aggressively(
                        order.order_id, 
                        current_market_price, 
                        max_adjustment_percent=decision.max_adjustment_percent
                    )
                    
                    if new_order_id:
                        logger.info(f"✅ Order aggressively adjusted: {order.order_id} → {new_order_id}")
                    else:
                        logger.debug(f"No adjustment needed/possible for order {order.order_id}")
                        
                except Exception as order_error:
                    logger.error(f"❌ Error monitoring order {order.order_id}: {order_error}")
                    continue
                    
        except Exception as e:
            logger.error(f"❌ Error in aggressive order monitoring: {str(e)}")
    
    async def _execute_profit_taking(self, position: Position, current_price: float) -> None:
        """
        Execute profit taking for a position.
        
        This method delegates policy decisions to ExecutionPolicyService and
        reconciliation to ReconciliationService, keeping the orchestrator focused
        on execution flow rather than policy logic.
        
        Args:
            position: The position to potentially exit.
            current_price: Current market price for the symbol.
        """
        try:
            logger.info(f"💰 POSITION EXIT: {position.symbol}")
            logger.info(f"   Position: {position.quantity:.2f} @ ${position.avg_price:.2f}")
            logger.info(f"   Current Price: ${current_price:.2f}")
            
            # Get pending orders for policy evaluation
            open_orders = await self.order_manager.get_open_orders()
            
            # Verify position with broker via reconciliation service
            verification = await self._reconciliation_service.verify_position_with_broker(
                position=position,
                broker_provider=self.broker_subsystem.primary_account_provider
            )
            
            if not verification.is_valid:
                if verification.broker_quantity == 0:
                    # Position closed externally - delegate to reconciliation
                    await self._handle_externally_closed_position(position)
                else:
                    logger.error(f"❌ Position verification failed: {verification.error_message}")
                return
            
            # Delegate policy decision to ExecutionPolicyService
            decision = await self._execution_policy.evaluate_profit_taking(
                position=position,
                current_price=current_price,
                broker_provider=self.broker_subsystem.primary_account_provider,
                open_orders=open_orders
            )
            
            # Act on the policy decision
            if not decision.should_execute:
                logger.info(f"⚠️ Profit taking skipped: {decision.skip_reason}")
                return
            
            # Log profit/loss determination from policy
            action_type = "PROFIT TAKING" if decision.is_profit else "STOP LOSS"
            logger.info(f"   Profit: {decision.profit_percentage:.2f}%")
            logger.info(f"🎯 {action_type} TRIGGERED: {position.symbol}")
            logger.info(f"✅ Position verified - DB: {position.quantity}, Broker: {decision.broker_quantity}")
            
            # Use ExitPlanner to build exit order (planning, not policy)
            exit_plan = await self._exit_planner.plan_exit(
                position,
                reason=action_type.lower().replace(" ", "_"),
                quantity_override=decision.exit_quantity,
                current_price=current_price
            )
            
            # Submit the exit order
            order = exit_plan.to_order()
            order_id = await self.order_manager.place_order(order)
            
            # Log with appropriate action type
            action_emoji = "💰" if decision.is_profit else "🛑"
            action_name = "PROFIT ORDER" if decision.is_profit else "STOP LOSS ORDER"
            logger.info(f"{action_emoji} {action_name}: {position.symbol} {order.side.value} {decision.exit_quantity} shares (Order ID: {order_id})")
            
            # Reset trailing state
            self.trailing_manager.reset_trailing_state(position.symbol)
            
        except Exception as e:
            error_msg = str(e)
            if "insufficient qty available" in error_msg.lower():
                logger.error(f"❌ INSUFFICIENT QUANTITY: {position.symbol} - Cannot place order due to pending orders or insufficient shares")
                logger.error(f"   Suggestion: Check for pending orders and cancel if necessary")
            else:
                logger.error(f"❌ Error executing profit taking: {error_msg}")
    
    async def _handle_externally_closed_position(self, position: Position) -> None:
        """
        Handle position that was closed externally (outside the bot).
        
        Delegates to ReconciliationService for consistent handling of
        external position changes across the system.
        
        Args:
            position: The position that was detected as closed externally.
        """
        logger.info(f"📋 POSITION ALREADY CLOSED: {position.symbol}")
        logger.info(f"   Database shows: {position.quantity} @ ${position.avg_price:.2f}")
        logger.info(f"   Broker shows: 0 (position was closed externally)")
        
        # Delegate to reconciliation service for consistent handling
        result = await self._reconciliation_service.reconcile_position(
            position=position,
            broker_provider=self.broker_subsystem.primary_account_provider,
            broker_quantity=0  # Already verified as zero
        )
        
        if result.action_taken:
            logger.info(f"✅ Reconciliation completed: {result.action_taken}")
        if result.error_message:
            logger.error(f"❌ Reconciliation error: {result.error_message}")
    
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
        """
        Handle order fill events with enhanced fill price validation.
        
        Delegates to FillProcessor service for actual processing.
        This method is kept thin to maintain orchestrator focus on coordination.
        """
        await self._fill_processor.process_fill(order)
    
    async def _handle_order_cancel(self, order: Order) -> None:
        """Handle order cancellation events."""
        logger.info(f"🚫 Order canceled: {order.order_id} ({order.symbol})")
        
        # CRITICAL: Clean up DCA tracking for cancelled orders
        if self.order_manager.is_dca_order(order.order_id):
            logger.info(f"🧹 CLEANING UP CANCELLED DCA ORDER: {order.symbol}")
            
            # Remove from strategy position's active orders
            if self.dca_strategy and order.symbol in self.dca_strategy.positions:
                strategy_position = self.dca_strategy.positions[order.symbol]
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
        
        Delegates to TradingSummaryService for summary generation, keeping
        the orchestrator focused on lifecycle management.
        
        Returns:
            Dictionary with current positions, open trades, recent trades, and performance.
        """
        try:
            # Delegate to TradingSummaryService for summary generation
            summary = await self._summary_service.get_trading_summary()
            return summary.to_dict()
            
        except Exception as e:
            logger.error(f"Error generating trading summary: {str(e)}")
            return {'error': str(e)}
    
    async def log_position_status(self) -> None:
        """
        Log detailed position status for debugging and monitoring.
        
        Delegates to TradingSummaryService for consistent formatting
        and reporting across the system.
        """
        try:
            await self._summary_service.log_position_status()
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
        # Validate configuration using ConfigurationManager
        from src.core import ConfigurationManager
        import os
        config = ConfigurationManager()
        # Basic validation: check if essential configs are available
        cosmos_endpoint = os.environ.get("COSMOS_ENDPOINT", "")
        if cosmos_endpoint or config.get_alpaca_config().is_configured:
            print(f"✅ Configuration for '{args.env}' environment is valid!")
            print(f"  - Cosmos DB configured: {'Yes' if cosmos_endpoint else 'No'}")
            print(f"  - Alpaca configured: {'Yes' if config.get_alpaca_config().is_configured else 'No'}")
            print(f"  - Azure deployment: {'Yes' if config.is_azure_deployment() else 'No'}")
        else:
            print(f"❌ Configuration validation failed - COSMOS_ENDPOINT and broker not configured")
            sys.exit(1)
    else:
        # Run the bot
        asyncio.run(run_trading_bot())
