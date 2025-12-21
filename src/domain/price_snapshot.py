"""
Price Snapshot Value Object

Standardizes market data representation across all providers.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class PriceSnapshot:
    """
    Immutable price snapshot from a market data provider.
    
    Standardizes price representation and provides computed properties
    for spread analysis and reliability assessment.
    
    Attributes:
        symbol: Trading symbol
        bid: Bid price
        ask: Ask price
        timestamp: Data timestamp
        volume: Trading volume (optional)
        reliability_score: Provider reliability score 0-1 (optional)
        provider: Provider name (optional)
    """
    
    symbol: str
    bid: float
    ask: float
    timestamp: datetime
    volume: Optional[int] = None
    reliability_score: Optional[float] = None
    provider: Optional[str] = None
    
    @property
    def midpoint(self) -> float:
        """Calculate midpoint price."""
        return (self.bid + self.ask) / 2.0
    
    @property
    def spread(self) -> float:
        """Calculate bid-ask spread."""
        return self.ask - self.bid
    
    @property
    def spread_percent(self) -> float:
        """Calculate spread as percentage of midpoint."""
        mid = self.midpoint
        if mid > 0:
            return (self.spread / mid) * 100.0
        return 0.0
    
    @property
    def age_seconds(self) -> float:
        """Calculate data age in seconds."""
        return (datetime.utcnow() - self.timestamp).total_seconds()
    
    @property
    def is_fresh(self) -> bool:
        """Check if data is fresh (< 5 seconds old)."""
        return self.age_seconds < 5.0
    
    @property
    def is_stale(self) -> bool:
        """Check if data is stale (> 60 seconds old)."""
        return self.age_seconds > 60.0
    
    def __post_init__(self):
        """Validate price snapshot."""
        if self.bid <= 0:
            raise ValueError(f"Invalid bid price: {self.bid}")
        
        if self.ask <= 0:
            raise ValueError(f"Invalid ask price: {self.ask}")
        
        if self.ask < self.bid:
            raise ValueError(f"Ask {self.ask} < bid {self.bid}")
        
        if self.reliability_score is not None:
            if not 0 <= self.reliability_score <= 1:
                raise ValueError(f"Reliability score must be 0-1: {self.reliability_score}")
