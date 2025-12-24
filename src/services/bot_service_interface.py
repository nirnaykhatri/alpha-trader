"""
Bot Service Interface.

Defines the interface for bot management operations.
Implementations can be in-memory (for testing) or backed by
a database and actual trading execution.

Author: Trading Bot Team
Version: 1.0.0
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from decimal import Decimal

from src.domain.bot_models import (
    Bot,
    BotConfiguration,
    BotState,
    BotAction,
    BotHistoryEntry,
    BotOrder,
    BotPerformance,
)


class IBotService(ABC):
    """
    Interface for bot management operations.
    
    Provides methods for:
    - CRUD operations on bots
    - Bot lifecycle management (start, stop, pause)
    - Bot actions (manual averaging, position close)
    - History retrieval and management
    
    Thread Safety:
        Implementations must be thread-safe as methods may be
        called from multiple async contexts.
    
    Example:
        >>> class BotService(IBotService):
        ...     async def create_bot(self, user_id, config):
        ...         # Implementation
        ...         pass
    """
    
    # =========================================================================
    # Bot CRUD Operations
    # =========================================================================
    
    @abstractmethod
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
            PermissionError: If user cannot create bots
        """
        pass
    
    @abstractmethod
    async def get_bot(self, bot_id: str, user_id: str) -> Optional[Bot]:
        """
        Get a bot by ID.
        
        Args:
            bot_id: Unique bot identifier
            user_id: ID of requesting user (for authorization)
            
        Returns:
            Bot if found and accessible, None otherwise
        """
        pass
    
    @abstractmethod
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
            state_filter: Filter by bot states (e.g., [RUNNING, PAUSED])
            symbol_filter: Filter by symbol (partial match)
            exchange_filter: Filter by exchange
            include_performance: Whether to include performance metrics
            
        Returns:
            List of Bot instances matching filters
        """
        pass
    
    @abstractmethod
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
            configuration: New configuration (optional, only if not running)
            
        Returns:
            Updated Bot if successful, None if not found
            
        Raises:
            ValueError: If bot is in invalid state for modification
        """
        pass
    
    @abstractmethod
    async def delete_bot(self, bot_id: str, user_id: str) -> bool:
        """
        Delete a bot.
        
        Can only delete bots that are not running. Creates a history
        entry before deletion if the bot was ever started.
        
        Args:
            bot_id: Bot to delete
            user_id: ID of requesting user
            
        Returns:
            True if deleted, False if not found
            
        Raises:
            ValueError: If bot is currently running
        """
        pass
    
    # =========================================================================
    # Bot Lifecycle Actions
    # =========================================================================
    
    @abstractmethod
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
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    async def resume_bot(self, bot_id: str, user_id: str) -> Bot:
        """
        Resume a paused bot.
        
        Args:
            bot_id: Bot to resume
            user_id: ID of requesting user
            
        Returns:
            Updated Bot with state=RUNNING
        """
        pass
    
    # =========================================================================
    # Bot Trading Actions
    # =========================================================================
    
    @abstractmethod
    async def manual_average(
        self,
        bot_id: str,
        user_id: str,
        amount: Optional[Decimal] = None
    ) -> Bot:
        """
        Trigger manual position averaging (DCA).
        
        Immediately places an averaging order at current price,
        regardless of configured price deviation.
        
        Args:
            bot_id: Bot to average
            user_id: ID of requesting user
            amount: Optional override for order size
            
        Returns:
            Updated Bot after order placement
            
        Raises:
            ValueError: If bot not running or at max layers
        """
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
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
        pass
    
    # =========================================================================
    # Bot Orders and Performance
    # =========================================================================
    
    @abstractmethod
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
        pass
    
    @abstractmethod
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
        pass
    
    # =========================================================================
    # Bot History
    # =========================================================================
    
    @abstractmethod
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
            include_deleted: Include soft-deleted entries
            limit: Maximum entries to return
            offset: Pagination offset
            
        Returns:
            List of BotHistoryEntry instances
        """
        pass
    
    @abstractmethod
    async def delete_history_entry(
        self,
        history_id: str,
        user_id: str,
        hard_delete: bool = False
    ) -> bool:
        """
        Delete a history entry.
        
        Args:
            history_id: History entry to delete
            user_id: ID of requesting user
            hard_delete: If True, permanently delete; if False, soft delete
            
        Returns:
            True if deleted, False if not found
        """
        pass
    
    @abstractmethod
    async def get_history_stats(
        self,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Get aggregate statistics from bot history.
        
        Args:
            user_id: ID of the user
            
        Returns:
            Dictionary with aggregate stats (total profit, win rate, etc.)
        """
        pass
