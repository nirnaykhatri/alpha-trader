"""
Position Monitor Service - Monitors positions and triggers profit-taking.

This service encapsulates all position monitoring logic, following Single
Responsibility Principle by separating monitoring from the main orchestrator.

SOLID Compliance:
- SRP: Single responsibility for position monitoring
- OCP: Extensible for new monitoring strategies
- LSP: N/A (no inheritance hierarchy)
- ISP: Focused interface for monitoring operations only
- DIP: Depends on abstractions (interfaces)

Thread Safety: Async-safe (uses async operations throughout)

Author: Trading Bot Team
Date: 2025
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable, TYPE_CHECKING
from datetime import datetime

from src import Position
from src.interfaces import IPositionManager, IConfigurationManager, ITrailingProfitManager
from src.utils import BoundedFetcher


# Use TYPE_CHECKING to avoid circular import
# BrokerSubsystem imports from src/trading which imports PositionMonitor
if TYPE_CHECKING:
    from src.broker.subsystem import BrokerSubsystem

logger = logging.getLogger(__name__)


class PositionMonitor:
    """
    Service for monitoring positions and detecting profit-taking opportunities.
    
    This service handles:
    - Periodic position monitoring loops
    - Parallel price fetching with bounded concurrency
    - Profit-taking condition detection
    - Position status logging
    - Market data updates
    
    Responsibilities:
    - Position monitoring lifecycle
    - Price fetching coordination
    - Status reporting
    
    NOT responsible for:
    - Executing profit-taking (that's handled by callback)
    - Order management (that's OrderManager)
    - Position persistence (that's PositionManager)
    
    Example Usage:
        ```python
        monitor = PositionMonitor(
            config=config,
            position_manager=position_manager,
            broker_subsystem=broker_subsystem,
            trailing_manager=trailing_manager,
            price_fetcher=price_fetcher
        )
        
        # Start monitoring loop
        await monitor.start_monitoring(
            shutdown_event=shutdown_event,
            on_profit_opportunity=handle_profit_taking,
            on_fill_detected=handle_order_fill,
            on_status_log=log_trading_status
        )
        ```
    """
    
    def __init__(
        self,
        config: IConfigurationManager,
        position_manager: IPositionManager,
        broker_subsystem: "BrokerSubsystem",
        trailing_manager: ITrailingProfitManager,
        price_fetcher: BoundedFetcher,
        advanced_strategy: Optional[Any] = None
    ):
        """
        Initialize PositionMonitor.
        
        Args:
            config: Configuration manager
            position_manager: Position manager for retrieving positions
            broker_subsystem: Broker subsystem for market data
            trailing_manager: Trailing profit manager for profit conditions
            price_fetcher: Bounded fetcher for parallel price requests
            advanced_strategy: Optional advanced strategy for DCA monitoring
        """
        self.config = config
        self.position_manager = position_manager
        self.broker_subsystem = broker_subsystem
        self.trailing_manager = trailing_manager
        self.price_fetcher = price_fetcher
        self.advanced_strategy = advanced_strategy
        
        # Error tracking for profit-taking cooldown
        self.last_error_time: Dict[str, float] = {}
        self.error_cooldown = 60  # seconds
        
        logger.debug("PositionMonitor initialized")
    
    async def start_monitoring(
        self,
        shutdown_event: asyncio.Event,
        on_profit_opportunity: Callable[[Position, float], Any],
        on_fill_detected: Optional[Callable[[Any], Any]] = None,
        on_status_log: Optional[Callable[[], Any]] = None,
        check_fills_callback: Optional[Callable[[], Any]] = None
    ) -> None:
        """
        Start the position monitoring loop.
        
        Args:
            shutdown_event: Event to signal monitoring shutdown
            on_profit_opportunity: Callback for profit-taking opportunities (position, price)
            on_fill_detected: Optional callback when order fill detected
            on_status_log: Optional callback for periodic status logging
            check_fills_callback: Optional callback to check for order fills
            
        Example:
            ```python
            async def handle_profit(position, price):
                await execute_profit_taking(position, price)
            
            await monitor.start_monitoring(
                shutdown_event=bot.shutdown_event,
                on_profit_opportunity=handle_profit
            )
            ```
        """
        try:
            sync_counter = 0
            status_log_counter = 0
            
            monitoring_interval = self.config.get_config("monitoring.position_monitoring_interval", 10)
            sync_interval_seconds = self.config.get_config("monitoring.alpaca_sync_interval", 60)
            status_log_interval_seconds = self.config.get_config("monitoring.status_log_interval", 300)
            
            sync_interval_cycles = max(1, sync_interval_seconds // monitoring_interval)
            status_log_cycles = max(1, status_log_interval_seconds // monitoring_interval)
            
            logger.info(f"📊 Position monitoring started (interval: {monitoring_interval}s)")
            
            while not shutdown_event.is_set():
                try:
                    # Check for order fills if callback provided
                    if check_fills_callback:
                        try:
                            newly_filled_orders = await check_fills_callback()
                            if newly_filled_orders and on_fill_detected:
                                for filled_order in newly_filled_orders:
                                    logger.info(f"🔄 Processing newly filled order: {filled_order.order_id}")
                                    await on_fill_detected(filled_order)
                        except Exception as fill_check_error:
                            logger.error(f"❌ Error checking order fills: {fill_check_error}")
                    
                    # Periodically log detailed trading status
                    if status_log_counter % status_log_cycles == 0 and on_status_log:
                        await on_status_log()
                    
                    sync_counter += 1
                    status_log_counter += 1
                    
                    # Monitor positions
                    await self._monitor_positions_cycle(
                        on_profit_opportunity=on_profit_opportunity
                    )
                    
                    # Wait for next cycle or shutdown
                    try:
                        await asyncio.wait_for(shutdown_event.wait(), timeout=monitoring_interval)
                        break  # Shutdown signal received
                    except asyncio.TimeoutError:
                        continue  # Continue monitoring
                        
                except Exception as e:
                    logger.error(f"Error in position monitoring cycle: {str(e)}")
                    try:
                        await asyncio.wait_for(shutdown_event.wait(), timeout=30)
                        break  # Shutdown signal received
                    except asyncio.TimeoutError:
                        continue  # Continue monitoring
                        
        except asyncio.CancelledError:
            logger.debug("Position monitor task cancelled")
            raise
        finally:
            logger.info("📊 Position monitoring stopped")
    
    async def _monitor_positions_cycle(
        self,
        on_profit_opportunity: Callable[[Position, float], Any]
    ) -> None:
        """
        Execute one cycle of position monitoring.
        
        Args:
            on_profit_opportunity: Callback for profit-taking opportunities
        """
        positions = await self.position_manager.get_all_positions()
        
        # Use bounded concurrency for price fetching
        symbols = [p.symbol for p in positions if p.quantity != 0]
        if not symbols:
            return
        
        price_dict = await self.price_fetcher.fetch_all(
            symbols,
            self.broker_subsystem.market_data.get_current_price
        )
        
        for position in positions:
            if position.quantity == 0:
                continue
            
            # Get current price from fetched dict
            current_price = price_dict.get(position.symbol)
            if current_price is None:
                logger.warning(f"Failed to fetch price for {position.symbol}, skipping monitoring")
                continue
            
            # Update advanced strategy positions and check for DCA opportunities
            if self.advanced_strategy:
                await self.advanced_strategy.update_position_monitoring(
                    position.symbol,
                    current_price
                )
            
            # Check trailing profit conditions
            if await self.trailing_manager.should_take_profit(position, current_price):
                # Check if we're in error cooldown for this symbol
                import time
                current_time = time.time()
                symbol_key = f"profit_taking_{position.symbol}"
                
                if symbol_key in self.last_error_time:
                    if current_time - self.last_error_time[symbol_key] < self.error_cooldown:
                        # Skip profit taking during cooldown
                        continue
                
                try:
                    await on_profit_opportunity(position, current_price)
                    # Reset error time on success
                    if symbol_key in self.last_error_time:
                        del self.last_error_time[symbol_key]
                except Exception as e:
                    # Set error cooldown time
                    self.last_error_time[symbol_key] = current_time
                    logger.error(
                        f"❌ PROFIT TAKING ERROR: {position.symbol} - "
                        f"Entering {self.error_cooldown}s cooldown"
                    )
                    logger.error(f"   Error: {e}")
    
    async def update_market_data(
        self,
        shutdown_event: asyncio.Event
    ) -> None:
        """
        Periodically update market data for all positions.
        
        Args:
            shutdown_event: Event to signal shutdown
            
        Note:
            This is a separate monitoring loop for market data refresh.
            Runs independently from main position monitoring.
        """
        try:
            logger.info("📈 Market data update loop started")
            
            while not shutdown_event.is_set():
                try:
                    # Update prices for all active positions
                    positions = await self.position_manager.get_all_positions()
                    
                    for position in positions:
                        if position.quantity != 0:
                            current_price = await self.broker_subsystem.market_data.get_current_price(
                                position.symbol
                            )
                            # Update position with current price
                            position.current_price = current_price
                            
                            # Calculate unrealized P&L
                            if position.quantity > 0:
                                position.unrealized_pnl = (
                                    (current_price - position.avg_price) * position.quantity
                                )
                            else:
                                position.unrealized_pnl = (
                                    (position.avg_price - current_price) * abs(position.quantity)
                                )
                    
                    # Update at configurable interval or until shutdown
                    refresh_interval = self.config.get_config(
                        "monitoring.market_data_refresh_interval",
                        60
                    )
                    try:
                        await asyncio.wait_for(shutdown_event.wait(), timeout=refresh_interval)
                        break  # Shutdown signal received
                    except asyncio.TimeoutError:
                        continue  # Continue monitoring
                        
                except Exception as e:
                    logger.error(f"Error updating market data: {str(e)}")
                    try:
                        await asyncio.wait_for(shutdown_event.wait(), timeout=60)
                        break  # Shutdown signal received
                    except asyncio.TimeoutError:
                        continue  # Continue monitoring
                        
        except asyncio.CancelledError:
            logger.debug("Market data update task cancelled")
            raise
        finally:
            logger.info("📈 Market data update loop stopped")
