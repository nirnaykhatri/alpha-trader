"""
Decision Context Value Object

Immutable context object for passing decision-making data to strategy components.
Reduces coupling and prevents accidental state expansion in strategy logic.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class PositionDirection(Enum):
    """Direction of a trading position."""
    LONG = "long"
    SHORT = "short"


@dataclass(frozen=True)
class DecisionContext:
    """
    Immutable context for trading decision making.
    
    Encapsulates all necessary information for strategy decisions,
    preventing direct coupling to position and market data objects.
    
    Attributes:
        symbol: Trading symbol (e.g., 'AAPL')
        timeframe: Signal timeframe (e.g., '15min', '1h')
        current_price: Current market price
        support_levels: Calculated technical support levels
        resistance_levels: Calculated technical resistance levels
        volatility: Current volatility (ATR or similar)
        volume: Recent volume metrics
        avg_entry_price: Average entry price for existing position
        position_direction: Long or short position
        position_size: Current position size (shares/contracts)
        dca_attempts: Number of DCA attempts made
        last_dca_price: Price of last DCA execution
        unrealized_pnl: Current unrealized P&L
        unrealized_pnl_percent: Current unrealized P&L percentage
        position_lifecycle_id: Unique identifier for position lifecycle
        timestamp: Context creation timestamp
    """
    
    # Symbol identification
    symbol: str
    timeframe: str
    
    # Market data
    current_price: float
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)
    volatility: float = 0.0
    volume: float = 0.0
    
    # Position data
    avg_entry_price: float = 0.0
    position_direction: Optional[PositionDirection] = None
    position_size: int = 0
    dca_attempts: int = 0
    last_dca_price: Optional[float] = None
    unrealized_pnl: float = 0.0
    unrealized_pnl_percent: float = 0.0
    position_lifecycle_id: Optional[str] = None
    
    # Metadata
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def has_position(self) -> bool:
        """Check if context represents an active position."""
        return self.position_size > 0
    
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.position_direction == PositionDirection.LONG
    
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.position_direction == PositionDirection.SHORT
    
    def at_support_level(self, tolerance: float = 0.01) -> Optional[float]:
        """
        Check if current price is at a support level.
        
        Args:
            tolerance: Price tolerance as percentage (default 1%)
            
        Returns:
            Support level if price is within tolerance, None otherwise
        """
        for level in self.support_levels:
            if abs(self.current_price - level) / level <= tolerance:
                return level
        return None
    
    def at_resistance_level(self, tolerance: float = 0.01) -> Optional[float]:
        """
        Check if current price is at a resistance level.
        
        Args:
            tolerance: Price tolerance as percentage (default 1%)
            
        Returns:
            Resistance level if price is within tolerance, None otherwise
        """
        for level in self.resistance_levels:
            if abs(self.current_price - level) / level <= tolerance:
                return level
        return None
    
    def price_improvement_for_dca(self, new_price: float) -> bool:
        """
        Check if new DCA price would improve position average.
        
        Args:
            new_price: Proposed DCA entry price
            
        Returns:
            True if DCA would improve average, False otherwise
        """
        if not self.last_dca_price:
            return True  # First DCA always allowed
            
        if self.is_long():
            # Long: New DCA must be LOWER than last
            return new_price < self.last_dca_price
        elif self.is_short():
            # Short: New DCA must be HIGHER than last
            return new_price > self.last_dca_price
        
        return False
