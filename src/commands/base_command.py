"""
Base command abstraction for the Command Pattern.
All trading commands inherit from TradingCommand.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
import uuid

from src.core.logging_config import get_logger


logger = get_logger(__name__)


class CommandStatus(Enum):
    """Status of command execution."""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class CommandResult:
    """Result of command execution."""
    success: bool
    command_id: str
    status: CommandStatus
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    executed_at: datetime = field(default_factory=datetime.utcnow)
    rollback_data: Optional[Dict[str, Any]] = None  # Data needed for undo
    
    def __post_init__(self):
        """Ensure executed_at is set."""
        if self.executed_at is None:
            self.executed_at = datetime.utcnow()


class TradingCommand(ABC):
    """
    Abstract base class for all trading commands.
    Implements Command Pattern with execute/undo capabilities.
    """
    
    def __init__(self, command_id: Optional[str] = None):
        """
        Initialize command with unique ID.
        
        Args:
            command_id: Optional command ID (auto-generated if not provided)
        """
        self.command_id = command_id or str(uuid.uuid4())
        self.status = CommandStatus.PENDING
        self.created_at = datetime.utcnow()
        self.executed_at: Optional[datetime] = None
        self.result: Optional[CommandResult] = None
        
        logger.debug(f"Created command {self.__class__.__name__} with ID {self.command_id}")
    
    @abstractmethod
    async def execute(self) -> CommandResult:
        """
        Execute the command.
        
        Returns:
            CommandResult with execution status and data
        """
        pass
    
    @abstractmethod
    async def undo(self) -> bool:
        """
        Undo the command (rollback).
        
        Returns:
            True if rollback successful, False otherwise
        """
        pass
    
    async def _execute_with_state_tracking(self) -> CommandResult:
        """
        Execute command with automatic state tracking.
        
        Returns:
            CommandResult from execution
        """
        try:
            self.status = CommandStatus.EXECUTING
            logger.info(f"Executing command {self.command_id} ({self.__class__.__name__})")
            
            result = await self.execute()
            
            self.executed_at = datetime.utcnow()
            self.result = result
            self.status = CommandStatus.COMPLETED if result.success else CommandStatus.FAILED
            
            if result.success:
                logger.info(f"Command {self.command_id} completed successfully")
            else:
                logger.error(f"Command {self.command_id} failed: {result.error}")
            
            return result
            
        except Exception as e:
            self.status = CommandStatus.FAILED
            error_msg = f"Command execution failed: {str(e)}"
            logger.error(f"Command {self.command_id} error: {error_msg}", exc_info=True)
            
            return CommandResult(
                success=False,
                command_id=self.command_id,
                status=CommandStatus.FAILED,
                error=error_msg
            )
    
    async def execute_with_tracking(self) -> CommandResult:
        """
        Public method to execute command with tracking.
        
        Returns:
            CommandResult from execution
        """
        return await self._execute_with_state_tracking()
    
    def can_undo(self) -> bool:
        """
        Check if command can be undone.
        
        Returns:
            True if command can be undone
        """
        return (
            self.status == CommandStatus.COMPLETED and
            self.result is not None and
            self.result.success and
            self.result.rollback_data is not None
        )
    
    def get_metadata(self) -> Dict[str, Any]:
        """
        Get command metadata.
        
        Returns:
            Dictionary with command metadata
        """
        return {
            "command_id": self.command_id,
            "command_type": self.__class__.__name__,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "can_undo": self.can_undo()
        }
