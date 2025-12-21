"""
Confidence Factor Interface

Abstract base class for pluggable confidence scoring factors.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from src.domain import DecisionContext


@dataclass(frozen=True)
class ConfidenceScore:
    """
    Individual confidence factor score.
    
    Attributes:
        score: Confidence score (0.0 to 1.0)
        weight: Weight of this factor in final calculation
        reason: Human-readable explanation
        factor_name: Name of the factor
        metadata: Additional diagnostic information
    """
    score: float
    weight: float
    reason: str
    factor_name: str
    metadata: dict
    
    @property
    def weighted_score(self) -> float:
        """Calculate weighted contribution to final score."""
        return self.score * self.weight
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/serialization."""
        return {
            'factor': self.factor_name,
            'score': self.score,
            'weight': self.weight,
            'weighted_score': self.weighted_score,
            'reason': self.reason,
            'metadata': self.metadata
        }


class IConfidenceFactor(ABC):
    """
    Abstract base class for confidence scoring factors.
    
    Each factor evaluates one aspect of the decision context
    and returns a normalized confidence score.
    """
    
    def __init__(self, weight: float = 1.0):
        """
        Initialize confidence factor.
        
        Args:
            weight: Relative weight of this factor (default 1.0)
        """
        if weight < 0:
            raise ValueError(f"Weight must be non-negative, got {weight}")
        self.weight = weight
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this factor."""
        pass
    
    @abstractmethod
    async def evaluate(self, context: DecisionContext) -> ConfidenceScore:
        """
        Evaluate confidence for the given decision context.
        
        Args:
            context: Immutable decision context
            
        Returns:
            ConfidenceScore with normalized score (0.0-1.0)
            
        Raises:
            ValueError: If insufficient data in context
        """
        pass
    
    def _create_score(
        self, 
        score: float, 
        reason: str, 
        metadata: Optional[dict] = None
    ) -> ConfidenceScore:
        """
        Helper to create ConfidenceScore instance.
        
        Args:
            score: Raw score (will be clamped to 0.0-1.0)
            reason: Explanation of the score
            metadata: Additional diagnostic information
            
        Returns:
            ConfidenceScore instance
        """
        clamped_score = max(0.0, min(1.0, score))
        
        return ConfidenceScore(
            score=clamped_score,
            weight=self.weight,
            reason=reason,
            factor_name=self.name,
            metadata=metadata or {}
        )
