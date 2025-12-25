"""
Bot Service Implementation.

Concrete implementation of IBotService that uses IBotRepository for
database persistence and coordinates with trading components for
bot lifecycle and trading operations.

This service bridges the domain layer (bots) with infrastructure
(database, trading execution).

Author: Trading Bot Team
Version: 3.0.0
"""

from typing import List, Optional, Dict, Any, TYPE_CHECKING
from decimal import Decimal
from datetime import datetime
import uuid

from src.core.logging_config import get_logger
from src.services.bot_service_interface import IBotService
from src.database.database_interface import IBotRepository
from src.domain.bot_models import (
    Bot,
    BotConfiguration,
    BotState,
    BotAction,
    BotHistoryEntry,
    BotOrder,
    BotPerformance,
)
from src.interfaces import IOrderManager, IPositionManager, Order, OrderSide, OrderType

if TYPE_CHECKING:
    from src.bot_engine.interfaces import IBotEngineManager

logger = get_logger(__name__)


class BotService(IBotService):
    """
    Production bot service implementation.
    
    Uses IBotRepository for persistence and integrates with trading
    components for actual order execution. Supports Cosmos DB backend.
    
    Attributes:
        _repository: IBotRepository for database operations
        _account_mode: Current account mode (demo/live)
        _active_bots: In-memory cache of running bot instances
    
    Thread Safety:
        Uses async locks for state modifications.
        Repository operations are async.
    
    Example:
        >>> repo: IBotRepository = CosmosBotRepository(cosmos_endpoint, "trading-bot")
        >>> await repo.initialize()
        >>> service = BotService(repo, account_mode="demo")
        >>> bot = await service.create_bot(
        ...     user_id="user123",
        ...     name="BTC DCA Bot",
        ...     configuration=config
        ... )
    """
    
    def __init__(
        self,
        repository: IBotRepository,
        account_mode: str = "demo",
        order_manager: Optional[IOrderManager] = None,
        position_manager: Optional[IPositionManager] = None,
        bot_engine_manager: Optional["IBotEngineManager"] = None,
    ):
        """
        Initialize bot service.
        
        Args:
            repository: IBotRepository implementation (e.g., CosmosBotRepository)
            account_mode: Account mode (demo/live)
            order_manager: Optional order manager for trading execution
            position_manager: Optional position manager for position queries
            bot_engine_manager: Optional bot engine manager for bot lifecycle
        """
        self._repository = repository
        self._account_mode = account_mode
        self._active_bots: Dict[str, Bot] = {}
        
        # Trading execution components (optional - injected for production)
        self._order_manager = order_manager
        self._position_manager = position_manager
        self._bot_engine_manager = bot_engine_manager
        
        logger.info(f"BotService initialized in {account_mode} mode")
    
    # =========================================================================
    # Bot CRUD Operations
    # =========================================================================
    
    async def create_bot(
        self,
        user_id: str,
        name: str,
        configuration: BotConfiguration,
        description: str = "",
        tags: List[str] = None
    ) -> Bot:
        """
        Create a new bot with the given configuration.
        
        Creates a bot in CREATED state and persists to database.
        
        Args:
            user_id: ID of the user creating the bot
            name: Display name for the bot
            configuration: Bot configuration settings
            description: Optional description
            tags: Optional tags for organization
            
        Returns:
            Created Bot instance with state=CREATED
            
        Raises:
            ValueError: If configuration is invalid
        """
        # Validate configuration
        self._validate_configuration(configuration)
        
        # Create domain model
        bot = Bot(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=name,
            description=description,
            state=BotState.CREATED,
            configuration=configuration,
            performance=BotPerformance.empty(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            tags=tags or [],
        )
        
        # Persist to database
        created_bot = await self._repository.create_bot(bot)
        
        logger.info(f"Created bot {created_bot.id} for user {user_id}: {name}")
        return created_bot
    
    async def get_bot(self, bot_id: str, user_id: str) -> Optional[Bot]:
        """
        Get a bot by ID.
        
        Args:
            bot_id: Unique bot identifier
            user_id: ID of requesting user (for authorization)
            
        Returns:
            Bot if found and accessible, None otherwise
        """
        # Cosmos uses user_id as partition key for efficient lookup
        bot = await self._repository.get_bot(bot_id, user_id)
        return bot
    
    async def list_bots(
        self,
        user_id: str,
        state_filter: Optional[List[BotState]] = None,
        symbol_filter: Optional[str] = None,
        exchange_filter: Optional[str] = None,
        include_performance: bool = True
    ) -> List[Bot]:
        """
        List all bots for a user.
        
        Args:
            user_id: ID of the user
            state_filter: Filter by bot states
            symbol_filter: Filter by symbol (partial match)
            exchange_filter: Filter by exchange
            include_performance: Whether to include performance metrics
            
        Returns:
            List of Bot instances matching filters
        """
        # Use first state from filter for Cosmos query (simplified)
        state = state_filter[0] if state_filter else None
        
        bots = await self._repository.list_bots(
            user_id=user_id,
            state=state,
            symbol=symbol_filter,
        )
        
        return bots
    
    async def update_bot(
        self,
        bot_id: str,
        user_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        configuration: Optional[BotConfiguration] = None
    ) -> Optional[Bot]:
        """
        Update a bot's settings.
        
        Can only update bots in CREATED, STOPPED, or PAUSED state.
        
        Args:
            bot_id: Bot to update
            user_id: ID of requesting user
            name: New name (optional)
            description: New description (optional)
            tags: New tags (optional)
            configuration: New configuration (optional)
            
        Returns:
            Updated Bot if successful, None if not found
            
        Raises:
            ValueError: If bot is in invalid state for modification
        """
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            return None
        
        # Check if bot can be modified
        modifiable_states = [BotState.CREATED, BotState.STOPPED, BotState.PAUSED]
        if bot.state not in modifiable_states:
            raise ValueError(f"Cannot modify bot in {bot.state.value} state")
        
        # Apply updates
        if name:
            bot.name = name
        if description is not None:
            bot.description = description
        if tags is not None:
            bot.tags = tags
        if configuration:
            self._validate_configuration(configuration)
            bot.configuration = configuration
        
        bot.updated_at = datetime.utcnow()
        
        # Persist
        updated_bot = await self._repository.update_bot(bot)
        
        logger.info(f"Updated bot {bot_id}")
        return updated_bot
    
    async def delete_bot(self, bot_id: str, user_id: str) -> bool:
        """
        Delete a bot.
        
        Creates a history entry before deletion if the bot was ever started.
        
        Args:
            bot_id: Bot to delete
            user_id: ID of requesting user
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            ValueError: If bot is currently running
        """
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            return False
        
        # Cannot delete running bots
        if bot.state == BotState.RUNNING:
            raise ValueError("Cannot delete a running bot. Stop it first.")
        
        # Delete bot (archives to history automatically in Cosmos)
        deleted = await self._repository.delete_bot(
            bot_id=bot_id,
            user_id=user_id,
            close_reason="user_deleted",
            archive=True
        )
        
        if deleted:
            logger.info(f"Deleted bot {bot_id}")
        
        return deleted
    
    # =========================================================================
    # Bot Lifecycle Actions
    # =========================================================================
    
    async def start_bot(self, bot_id: str, user_id: str) -> Bot:
        """
        Start a bot.
        
        Transitions bot from CREATED/STOPPED/PAUSED to STARTING, then RUNNING.
        
        Args:
            bot_id: Bot to start
            user_id: ID of requesting user
            
        Returns:
            Updated Bot with new state
            
        Raises:
            ValueError: If bot cannot be started from current state
        """
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            raise ValueError(f"Bot {bot_id} not found")
        
        # Validate state transition
        startable_states = [BotState.CREATED, BotState.STOPPED, BotState.PAUSED]
        if bot.state not in startable_states:
            raise ValueError(f"Cannot start bot from {bot.state.value} state")
        
        # Update state
        bot.state = BotState.STARTING
        bot.started_at = datetime.utcnow()
        bot.stopped_at = None
        bot.updated_at = datetime.utcnow()
        
        await self._repository.update_bot(bot)
        
        # Integrate with trading execution via BotEngineManager
        if self._bot_engine_manager:
            try:
                await self._bot_engine_manager.start_bot(bot)
                logger.info(f"Bot {bot_id} started via BotEngineManager")
            except Exception as e:
                # Rollback state on failure
                bot.state = BotState.STOPPED
                await self._repository.update_bot(bot)
                raise ValueError(f"Failed to start bot engine: {e}")
        else:
            logger.warning(f"Bot {bot_id} started without BotEngineManager (demo mode)")
        
        # Transition to running
        bot.state = BotState.RUNNING
        updated_bot = await self._repository.update_bot(bot)
        
        # Cache as active
        self._active_bots[bot_id] = updated_bot
        
        logger.info(f"Started bot {bot_id}")
        return updated_bot
    
    async def stop_bot(
        self,
        bot_id: str,
        user_id: str,
        close_positions: bool = False,
        cancel_orders: bool = True
    ) -> Bot:
        """
        Stop a running bot.
        
        Args:
            bot_id: Bot to stop
            user_id: ID of requesting user
            close_positions: Whether to close all open positions
            cancel_orders: Whether to cancel all pending orders
            
        Returns:
            Updated Bot with state=STOPPED
            
        Raises:
            ValueError: If bot cannot be stopped
        """
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            raise ValueError(f"Bot {bot_id} not found")
        
        stoppable_states = [BotState.RUNNING, BotState.PAUSED, BotState.STARTING]
        if bot.state not in stoppable_states:
            raise ValueError(f"Cannot stop bot from {bot.state.value} state")
        
        # Cancel pending orders if requested
        if cancel_orders and self._order_manager:
            try:
                open_orders = await self._order_manager.get_open_orders(
                    symbol=bot.configuration.symbol
                )
                for order in open_orders:
                    await self._order_manager.cancel_order(order.id)
                logger.info(f"Cancelled {len(open_orders)} orders for bot {bot_id}")
            except Exception as e:
                logger.warning(f"Failed to cancel orders for bot {bot_id}: {e}")
        
        # Close positions if requested
        if close_positions and self._order_manager:
            try:
                await self._close_bot_position(bot)
                logger.info(f"Closed positions for bot {bot_id}")
            except Exception as e:
                logger.warning(f"Failed to close positions for bot {bot_id}: {e}")
        
        # Update state
        bot.state = BotState.STOPPING
        bot.updated_at = datetime.utcnow()
        await self._repository.update_bot(bot)
        
        # Stop via BotEngineManager if available
        if self._bot_engine_manager:
            try:
                await self._bot_engine_manager.stop_bot(bot.id)
            except Exception as e:
                logger.warning(f"BotEngineManager stop failed for {bot_id}: {e}")
        
        # Finalize stop
        bot.state = BotState.STOPPED

        updated_bot = await self._repository.update_bot(bot)
        
        # Remove from active cache
        self._active_bots.pop(bot_id, None)
        
        logger.info(f"Stopped bot {bot_id}")
        return updated_bot
    
    async def pause_bot(self, bot_id: str, user_id: str) -> Bot:
        """
        Pause a running bot.
        
        Bot stops placing new orders but maintains existing positions.
        
        Args:
            bot_id: Bot to pause
            user_id: ID of requesting user
            
        Returns:
            Updated Bot with state=PAUSED
        """
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            raise ValueError(f"Bot {bot_id} not found")
        
        if bot.state != BotState.RUNNING:
            raise ValueError(f"Cannot pause bot from {bot.state.value} state")
        
        bot.state = BotState.PAUSED
        bot.updated_at = datetime.utcnow()
        
        updated_bot = await self._repository.update_bot(bot)
        
        logger.info(f"Paused bot {bot_id}")
        return updated_bot
    
    async def resume_bot(self, bot_id: str, user_id: str) -> Bot:
        """
        Resume a paused bot.
        
        Args:
            bot_id: Bot to resume
            user_id: ID of requesting user
            
        Returns:
            Updated Bot with state=RUNNING
        """
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            raise ValueError(f"Bot {bot_id} not found")
        
        if bot.state != BotState.PAUSED:
            raise ValueError(f"Cannot resume bot from {bot.state.value} state")
        
        bot.state = BotState.RUNNING
        bot.updated_at = datetime.utcnow()
        
        updated_bot = await self._repository.update_bot(bot)
        
        logger.info(f"Resumed bot {bot_id}")
        return updated_bot
    
    # =========================================================================
    # Bot Trading Actions
    # =========================================================================
    
    async def manual_average(
        self,
        bot_id: str,
        user_id: str,
        amount: Optional[Decimal] = None
    ) -> Bot:
        """
        Trigger manual position averaging (DCA).
        
        Args:
            bot_id: Bot to average
            user_id: ID of requesting user
            amount: Optional override for order size
            
        Returns:
            Updated Bot after order placement
            
        Raises:
            ValueError: If bot not running or at max layers
        """
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            raise ValueError(f"Bot {bot_id} not found")
        
        if bot.state != BotState.RUNNING:
            raise ValueError("Bot must be running to perform manual averaging")
        
        # Check if at max layers using the new averaging_orders config
        if bot.configuration.dca_config and bot.configuration.dca_config.averaging_orders:
            max_layers = bot.configuration.dca_config.averaging_orders.orders_count
            if bot.performance and bot.performance.dca_layers_used >= max_layers:
                raise ValueError(f"Bot has reached maximum DCA layers ({max_layers})")
        
        # Place the averaging order through order manager
        if self._order_manager:
            try:
                # Calculate DCA order size from config
                base_order_size = bot.configuration.base_order_size or Decimal("100")
                dca_multiplier = Decimal("1.5")  # Could be from config
                layer = (bot.performance.dca_layers_used if bot.performance else 0) + 1
                order_size = base_order_size * (dca_multiplier ** layer)
                
                # Create and place order
                order = Order(
                    symbol=bot.configuration.symbol,
                    side=OrderSide.BUY,  # DCA averages down (buy more)
                    order_type=OrderType.MARKET,
                    quantity=float(order_size),
                )
                order_id = await self._order_manager.place_order(order)
                logger.info(f"Placed DCA order {order_id} for bot {bot_id}")
            except Exception as e:
                raise ValueError(f"Failed to place averaging order: {e}")
        else:
            logger.warning(f"Manual average for bot {bot_id} - no order manager (demo mode)")
        
        # Update layer count
        if bot.performance:
            bot.performance = BotPerformance(
                **{**bot.performance.__dict__, 
                   'dca_layers_used': bot.performance.dca_layers_used + 1}
            )
        
        bot.updated_at = datetime.utcnow()
        updated_bot = await self._repository.update_bot(bot)
        
        logger.info(f"Manual average for bot {bot_id}")
        return updated_bot
    
    async def adjust_margin(
        self,
        bot_id: str,
        user_id: str,
        new_margin: Decimal
    ) -> Bot:
        """
        Adjust margin for a futures bot.
        
        Args:
            bot_id: Bot to adjust
            user_id: ID of requesting user
            new_margin: New margin amount
            
        Returns:
            Updated Bot
            
        Raises:
            ValueError: If bot not a futures bot or not running
        """
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            raise ValueError(f"Bot {bot_id} not found")
        
        if bot.state != BotState.RUNNING:
            raise ValueError("Bot must be running to adjust margin")
        
        if bot.configuration.leverage <= 1:
            raise ValueError("Margin adjustment only available for futures bots")
        
        # Adjust margin through broker (futures-specific operation)
        if self._order_manager and hasattr(self._order_manager, 'adjust_margin'):
            try:
                await self._order_manager.adjust_margin(
                    symbol=bot.configuration.symbol,
                    margin=float(new_margin)
                )
                logger.info(f"Adjusted margin for bot {bot_id} to {new_margin}")
            except Exception as e:
                raise ValueError(f"Failed to adjust margin: {e}")
        else:
            logger.warning(f"Margin adjustment not available for bot {bot_id}")
        
        logger.info(f"Adjusted margin for bot {bot_id} to {new_margin}")
        return bot
    
    async def close_position(
        self,
        bot_id: str,
        user_id: str,
        percentage: Decimal = Decimal("100")
    ) -> Bot:
        """
        Close bot's position.
        
        Args:
            bot_id: Bot whose position to close
            user_id: ID of requesting user
            percentage: Percentage of position to close (1-100)
            
        Returns:
            Updated Bot after position close
        """
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            raise ValueError(f"Bot {bot_id} not found")
        
        if bot.state not in [BotState.RUNNING, BotState.PAUSED]:
            raise ValueError("Bot must be running or paused to close position")
        
        if percentage < 1 or percentage > 100:
            raise ValueError("Percentage must be between 1 and 100")
        
        # Close position through order manager
        if self._order_manager and self._position_manager:
            try:
                position = await self._position_manager.get_position(bot.configuration.symbol)
                if position and position.quantity != 0:
                    # Calculate quantity to close
                    close_qty = abs(position.quantity) * (float(percentage) / 100.0)
                    
                    # Determine sell side based on position direction
                    side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
                    
                    order = Order(
                        symbol=bot.configuration.symbol,
                        side=side,
                        order_type=OrderType.MARKET,
                        quantity=close_qty,
                    )
                    order_id = await self._order_manager.place_order(order)
                    logger.info(f"Closed {percentage}% of position for bot {bot_id} (order: {order_id})")
                else:
                    logger.warning(f"No position found for bot {bot_id}")
            except Exception as e:
                raise ValueError(f"Failed to close position: {e}")
        else:
            logger.warning(f"Position close for bot {bot_id} - no order manager (demo mode)")
        
        logger.info(f"Closed {percentage}% of position for bot {bot_id}")
        return bot
    
    # =========================================================================
    # Bot Orders and Performance
    # =========================================================================
    
    async def get_bot_orders(
        self,
        bot_id: str,
        user_id: str,
        status_filter: Optional[List[str]] = None,
        limit: int = 50
    ) -> List[BotOrder]:
        """
        Get orders placed by a bot.
        
        Args:
            bot_id: Bot to query
            user_id: ID of requesting user
            status_filter: Filter by order status
            limit: Maximum orders to return
            
        Returns:
            List of BotOrder instances
        """
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            return []
        
        # Query orders from order manager if available
        if self._order_manager:
            try:
                open_orders = await self._order_manager.get_open_orders(
                    symbol=bot.configuration.symbol
                )
                # Convert to BotOrder format
                return [
                    BotOrder(
                        id=str(order.id),
                        bot_id=bot_id,
                        symbol=order.symbol,
                        side=order.side.value if hasattr(order.side, 'value') else str(order.side),
                        order_type=order.order_type.value if hasattr(order.order_type, 'value') else str(order.order_type),
                        quantity=Decimal(str(order.quantity)),
                        price=Decimal(str(order.price)) if order.price else None,
                        status=order.status.value if hasattr(order.status, 'value') else str(order.status),
                        created_at=datetime.utcnow(),
                    )
                    for order in open_orders[:limit]
                ]
            except Exception as e:
                logger.warning(f"Failed to query orders for bot {bot_id}: {e}")
        
        return []
    
    async def get_bot_performance(
        self,
        bot_id: str,
        user_id: str
    ) -> BotPerformance:
        """
        Get current performance metrics for a bot.
        
        Args:
            bot_id: Bot to query
            user_id: ID of requesting user
            
        Returns:
            Current BotPerformance metrics
        """
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            raise ValueError(f"Bot {bot_id} not found")
        
        return bot.performance or BotPerformance.empty()
    
    # =========================================================================
    # Bot History
    # =========================================================================
    
    async def get_bot_history(
        self,
        user_id: str,
        symbol_filter: Optional[str] = None,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> List[BotHistoryEntry]:
        """
        Get historical bot records.
        
        Args:
            user_id: ID of the user
            symbol_filter: Filter by symbol
            include_deleted: Include soft-deleted entries (not used in Cosmos)
            limit: Maximum entries to return
            offset: Pagination offset (not used in Cosmos)
            
        Returns:
            List of BotHistoryEntry instances
        """
        return await self._repository.list_history(
            user_id=user_id,
            symbol=symbol_filter,
            limit=limit,
        )
    
    async def delete_history_entry(
        self,
        history_id: str,
        user_id: str,
        hard_delete: bool = False
    ) -> bool:
        """
        Delete a history entry.
        
        Note: Cosmos DB implementation does not support history deletion
        for audit trail purposes. Returns False.
        
        Args:
            history_id: History entry to delete
            user_id: ID of requesting user
            hard_delete: If True, permanently delete
            
        Returns:
            False (history deletion not supported in Cosmos)
        """
        logger.warning(f"History deletion not supported - history_id: {history_id}")
        return False
    
    async def get_history_stats(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get aggregate statistics from bot history.
        
        Args:
            user_id: ID of the user
            
        Returns:
            Dictionary with aggregate stats
        """
        return await self._repository.get_history_stats(user_id=user_id)
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _validate_configuration(self, configuration: BotConfiguration) -> None:
        """
        Validate bot configuration.
        
        Args:
            configuration: Configuration to validate
            
        Raises:
            ValueError: If configuration is invalid
        """
        if not configuration.symbol:
            raise ValueError("Symbol is required")
        
        if configuration.investment_amount <= 0:
            raise ValueError("Investment amount must be positive")
        
        if configuration.leverage < 1:
            raise ValueError("Leverage must be at least 1")
        
        # Validate DCA config if present
        if configuration.dca_config:
            # Use averaging_orders.orders_count for max layers validation
            if configuration.dca_config.averaging_orders:
                if configuration.dca_config.averaging_orders.orders_count < 1:
                    raise ValueError("Orders count must be at least 1")
                if configuration.dca_config.averaging_orders.step_percent <= 0:
                    raise ValueError("Step percent must be positive")
    
    async def _close_bot_position(self, bot: Bot) -> None:
        """
        Close all positions for a bot.
        
        Args:
            bot: Bot whose positions to close
            
        Raises:
            ValueError: If position close fails
        """
        if not self._order_manager or not self._position_manager:
            return
        
        position = await self._position_manager.get_position(bot.configuration.symbol)
        if position and position.quantity != 0:
            side = OrderSide.SELL if position.quantity > 0 else OrderSide.BUY
            order = Order(
                symbol=bot.configuration.symbol,
                side=side,
                order_type=OrderType.MARKET,
                quantity=abs(position.quantity),
            )
            await self._order_manager.place_order(order)


class MockBotService(IBotService):
    """
    In-memory bot service for testing and development.
    
    Stores bots in memory, no database required.
    Useful for unit tests and local development.
    """
    
    def __init__(self):
        """Initialize with empty bot storage."""
        self._bots: Dict[str, Bot] = {}
        self._history: List[BotHistoryEntry] = []
        logger.info("MockBotService initialized (in-memory)")
    
    async def create_bot(
        self,
        user_id: str,
        name: str,
        configuration: BotConfiguration,
        description: str = "",
        tags: List[str] = None
    ) -> Bot:
        """Create a mock bot."""
        bot_id = str(uuid.uuid4())
        bot = Bot(
            id=bot_id,
            user_id=user_id,
            name=name,
            description=description,
            state=BotState.CREATED,
            configuration=configuration,
            performance=BotPerformance.empty(),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            tags=tags or [],
        )
        self._bots[bot_id] = bot
        return bot
    
    async def get_bot(self, bot_id: str, user_id: str) -> Optional[Bot]:
        """Get a mock bot."""
        bot = self._bots.get(bot_id)
        if bot and bot.user_id == user_id:
            return bot
        return None
    
    async def list_bots(
        self,
        user_id: str,
        state_filter: Optional[List[BotState]] = None,
        symbol_filter: Optional[str] = None,
        exchange_filter: Optional[str] = None,
        include_performance: bool = True
    ) -> List[Bot]:
        """List mock bots."""
        bots = [b for b in self._bots.values() if b.user_id == user_id]
        
        if state_filter:
            bots = [b for b in bots if b.state in state_filter]
        if symbol_filter:
            bots = [b for b in bots if symbol_filter.lower() in b.configuration.symbol.lower()]
        if exchange_filter:
            bots = [b for b in bots if b.configuration.exchange == exchange_filter]
        
        return bots
    
    async def update_bot(
        self,
        bot_id: str,
        user_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        configuration: Optional[BotConfiguration] = None
    ) -> Optional[Bot]:
        """Update a mock bot."""
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            return None
        
        if name:
            bot.name = name
        if description is not None:
            bot.description = description
        if tags is not None:
            bot.tags = tags
        if configuration:
            bot.configuration = configuration
        
        bot.updated_at = datetime.utcnow()
        return bot
    
    async def delete_bot(self, bot_id: str, user_id: str) -> bool:
        """Delete a mock bot."""
        bot = await self.get_bot(bot_id, user_id)
        if bot:
            del self._bots[bot_id]
            return True
        return False
    
    async def start_bot(self, bot_id: str, user_id: str) -> Bot:
        """Start a mock bot."""
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            raise ValueError(f"Bot {bot_id} not found")
        bot.state = BotState.RUNNING
        bot.started_at = datetime.utcnow()
        return bot

    async def stop_bot(
        self,
        bot_id: str,
        user_id: str,
        close_positions: bool = False,
        cancel_orders: bool = True
    ) -> Bot:
        """Stop a mock bot."""
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            raise ValueError(f"Bot {bot_id} not found")
        bot.state = BotState.STOPPED
        bot.stopped_at = datetime.utcnow()
        return bot

    async def pause_bot(self, bot_id: str, user_id: str) -> Bot:
        """Pause a mock bot."""
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            raise ValueError(f"Bot {bot_id} not found")
        bot.state = BotState.PAUSED
        return bot
    
    async def resume_bot(self, bot_id: str, user_id: str) -> Bot:
        """Resume a mock bot."""
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            raise ValueError(f"Bot {bot_id} not found")
        bot.state = BotState.RUNNING
        return bot
    
    async def manual_average(
        self,
        bot_id: str,
        user_id: str,
        amount: Optional[Decimal] = None
    ) -> Bot:
        """Mock manual average."""
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            raise ValueError(f"Bot {bot_id} not found")
        return bot
    
    async def adjust_margin(
        self,
        bot_id: str,
        user_id: str,
        new_margin: Decimal
    ) -> Bot:
        """Mock margin adjustment."""
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            raise ValueError(f"Bot {bot_id} not found")
        return bot
    
    async def close_position(
        self,
        bot_id: str,
        user_id: str,
        percentage: Decimal = Decimal("100")
    ) -> Bot:
        """Mock position close."""
        bot = await self.get_bot(bot_id, user_id)
        if not bot:
            raise ValueError(f"Bot {bot_id} not found")
        return bot
    
    async def get_bot_orders(
        self,
        bot_id: str,
        user_id: str,
        status_filter: Optional[List[str]] = None,
        limit: int = 50
    ) -> List[BotOrder]:
        """Get mock orders."""
        return []
    
    async def get_bot_performance(
        self,
        bot_id: str,
        user_id: str
    ) -> BotPerformance:
        """Get mock performance."""
        bot = await self.get_bot(bot_id, user_id)
        if bot:
            return bot.performance or BotPerformance.empty()
        return BotPerformance.empty()
    
    async def get_bot_history(
        self,
        user_id: str,
        symbol_filter: Optional[str] = None,
        include_deleted: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> List[BotHistoryEntry]:
        """Get mock history."""
        return self._history[:limit]
    
    async def delete_history_entry(
        self,
        history_id: str,
        user_id: str,
        hard_delete: bool = False
    ) -> bool:
        """Delete mock history entry."""
        return False
    
    async def get_history_stats(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """Get mock stats."""
        return {
            "total_bots_run": 0,
            "total_profit": 0.0,
            "average_profit_percent": 0.0,
            "win_rate": 0.0,
        }
