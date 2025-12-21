"""
Command history tracker for transaction management.
Maintains history of executed commands and supports rollback.
"""

from typing import Dict, List, Optional
from collections import deque
from datetime import datetime

from src.commands.base_command import TradingCommand, CommandStatus
from src.core.logging_config import get_logger


logger = get_logger(__name__)


class CommandHistory:
    """
    Maintains history of executed commands.
    Supports rollback and transaction management.
    """
    
    def __init__(self, max_history: int = 1000):
        """
        Initialize command history.
        
        Args:
            max_history: Maximum number of commands to retain in history
        """
        self.max_history = max_history
        self._commands: deque[TradingCommand] = deque(maxlen=max_history)
        self._commands_by_id: Dict[str, TradingCommand] = {}
        
        logger.info(f"Command history initialized (max: {max_history})")
    
    def add_command(self, command: TradingCommand) -> None:
        """
        Add command to history.
        
        Args:
            command: Command to add
        """
        self._commands.append(command)
        self._commands_by_id[command.command_id] = command
        
        # Clean up old references if deque exceeded max size
        if len(self._commands_by_id) > self.max_history:
            # Remove oldest command IDs that are no longer in deque
            current_ids = {cmd.command_id for cmd in self._commands}
            old_ids = set(self._commands_by_id.keys()) - current_ids
            for old_id in old_ids:
                del self._commands_by_id[old_id]
        
        logger.debug(f"Added command {command.command_id} to history")
    
    def get_command(self, command_id: str) -> Optional[TradingCommand]:
        """
        Get command by ID.
        
        Args:
            command_id: Command ID to retrieve
            
        Returns:
            Command if found, None otherwise
        """
        return self._commands_by_id.get(command_id)
    
    def get_recent_commands(self, count: int = 10) -> List[TradingCommand]:
        """
        Get most recent commands.
        
        Args:
            count: Number of commands to retrieve
            
        Returns:
            List of recent commands
        """
        return list(self._commands)[-count:]
    
    def get_commands_by_status(self, status: CommandStatus) -> List[TradingCommand]:
        """
        Get all commands with specified status.
        
        Args:
            status: Command status to filter by
            
        Returns:
            List of commands with matching status
        """
        return [cmd for cmd in self._commands if cmd.status == status]
    
    def get_rollbackable_commands(self) -> List[TradingCommand]:
        """
        Get all commands that can be rolled back.
        
        Returns:
            List of rollbackable commands
        """
        return [cmd for cmd in self._commands if cmd.can_undo()]
    
    async def rollback_command(self, command_id: str) -> bool:
        """
        Rollback a specific command.
        
        Args:
            command_id: ID of command to rollback
            
        Returns:
            True if rollback successful, False otherwise
        """
        command = self.get_command(command_id)
        
        if not command:
            logger.warning(f"Command {command_id} not found in history")
            return False
        
        if not command.can_undo():
            logger.warning(f"Command {command_id} cannot be undone")
            return False
        
        logger.info(f"Rolling back command {command_id}")
        success = await command.undo()
        
        if success:
            logger.info(f"Successfully rolled back command {command_id}")
        else:
            logger.error(f"Failed to rollback command {command_id}")
        
        return success
    
    async def rollback_last_n_commands(self, count: int) -> Dict[str, bool]:
        """
        Rollback last N commands.
        
        Args:
            count: Number of commands to rollback
            
        Returns:
            Dictionary mapping command IDs to rollback success status
        """
        recent_commands = self.get_recent_commands(count)
        results = {}
        
        # Rollback in reverse order (most recent first)
        for command in reversed(recent_commands):
            if command.can_undo():
                logger.info(f"Rolling back command {command.command_id}")
                success = await command.undo()
                results[command.command_id] = success
            else:
                logger.debug(f"Skipping non-rollbackable command {command.command_id}")
                results[command.command_id] = False
        
        return results
    
    def get_statistics(self) -> Dict[str, any]:
        """
        Get command history statistics.
        
        Returns:
            Dictionary with statistics
        """
        total = len(self._commands)
        
        if total == 0:
            return {
                "total_commands": 0,
                "by_status": {},
                "rollbackable": 0
            }
        
        by_status = {}
        for status in CommandStatus:
            count = len(self.get_commands_by_status(status))
            if count > 0:
                by_status[status.value] = count
        
        rollbackable = len(self.get_rollbackable_commands())
        
        return {
            "total_commands": total,
            "by_status": by_status,
            "rollbackable": rollbackable,
            "oldest_command": self._commands[0].created_at.isoformat() if total > 0 else None,
            "newest_command": self._commands[-1].created_at.isoformat() if total > 0 else None
        }
    
    def clear_history(self) -> None:
        """Clear all command history."""
        logger.warning("Clearing entire command history")
        self._commands.clear()
        self._commands_by_id.clear()
