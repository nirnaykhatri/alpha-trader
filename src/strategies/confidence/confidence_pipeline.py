"""
Confidence Pipeline

Aggregates multiple confidence factors using chain-of-responsibility pattern.
Includes optional drift analysis for adaptive weight adjustment.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from time import perf_counter

from src.domain import DecisionContext
from src.strategies.confidence.confidence_factor import IConfidenceFactor, ConfidenceScore
from src.utils.metrics import confidence_factor_latency_seconds

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    """
    Aggregated confidence pipeline result.
    
    Attributes:
        final_score: Weighted average of all factor scores (0.0-1.0)
        factor_scores: Individual scores from each factor
        total_weight: Sum of all factor weights
        evaluation_time_ms: Total evaluation time in milliseconds
        passed_threshold: Whether score exceeds configured threshold
        reasons: Aggregated reasons from all factors
        drift_metrics: Optional drift analysis metrics per factor
    """
    final_score: float
    factor_scores: tuple[ConfidenceScore, ...]
    total_weight: float
    evaluation_time_ms: float
    passed_threshold: bool
    reasons: tuple[str, ...]
    drift_metrics: Optional[Dict] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for logging/serialization."""
        result = {
            'final_score': self.final_score,
            'passed_threshold': self.passed_threshold,
            'evaluation_time_ms': self.evaluation_time_ms,
            'total_weight': self.total_weight,
            'factor_scores': [score.to_dict() for score in self.factor_scores],
            'reasons': list(self.reasons)
        }
        if self.drift_metrics:
            result['drift_metrics'] = self.drift_metrics
        return result


class ConfidencePipeline:
    """
    Chain-of-responsibility confidence scorer.
    
    Evaluates multiple confidence factors and aggregates results
    using weighted averaging.
    
    Example:
        >>> pipeline = ConfidencePipeline([
        ...     TechnicalLevelConfidenceFactor(weight=2.0),
        ...     VolumeConfidenceFactor(weight=1.0),
        ...     VolatilityConfidenceFactor(weight=1.5)
        ... ], min_threshold=0.7)
        >>> result = await pipeline.evaluate(decision_context)
        >>> if result.passed_threshold:
        ...     # Execute DCA
    """
    
    def __init__(
        self, 
        factors: List[IConfidenceFactor],
        min_threshold: float = 0.7,
        drift_analyzer=None,
        closed_position_repository=None
    ):
        """
        Initialize confidence pipeline.
        
        Args:
            factors: List of confidence factors to evaluate
            min_threshold: Minimum score required to pass (0.0-1.0)
            drift_analyzer: Optional ConfidenceDriftAnalyzer for adaptive weighting
            closed_position_repository: Optional repository for historical data
            
        Raises:
            ValueError: If no factors provided or invalid threshold
        """
        if not factors:
            raise ValueError("At least one confidence factor required")
        
        if not 0.0 <= min_threshold <= 1.0:
            raise ValueError(f"Threshold must be 0.0-1.0, got {min_threshold}")
        
        self.factors = factors
        self.min_threshold = min_threshold
        self.drift_analyzer = drift_analyzer
        self.closed_position_repository = closed_position_repository
        self.total_weight = sum(factor.weight for factor in factors)
        
        # Factor weights (can be adjusted by drift analyzer)
        self._weights = {factor.name: factor.weight for factor in factors}
        
        logger.info(
            f"ConfidencePipeline initialized with {len(factors)} factors, "
            f"total weight: {self.total_weight}, threshold: {min_threshold}, "
            f"drift_enabled: {drift_analyzer is not None}"
        )
    
    async def evaluate(self, context: DecisionContext) -> PipelineResult:
        """
        Evaluate all confidence factors and aggregate results.
        
        Args:
            context: Immutable decision context
            
        Returns:
            PipelineResult with aggregated confidence score
        """
        start_time = perf_counter()
        
        # Evaluate all factors
        scores: List[ConfidenceScore] = []
        reasons: List[str] = []
        
        for factor in self.factors:
            try:
                # Measure factor evaluation latency
                factor_start = perf_counter()
                score = await factor.evaluate(context)
                factor_latency = perf_counter() - factor_start
                
                # Record latency metric
                confidence_factor_latency_seconds.labels(factor_name=factor.name).observe(factor_latency)
                
                scores.append(score)
                reasons.append(f"{factor.name}: {score.reason}")
                
                logger.debug(
                    f"Factor '{factor.name}' scored {score.score:.3f} "
                    f"(weighted: {score.weighted_score:.3f}, latency: {factor_latency*1000:.2f}ms)"
                )
                
            except Exception as e:
                logger.error(
                    f"Factor '{factor.name}' evaluation failed: {e}",
                    exc_info=True
                )
                # Continue with other factors
        
        # Apply drift analysis if available
        # NOTE: Drift analysis requires historical confidence scores to be persisted
        # TODO: Implement confidence score persistence in EnhancedPositionRecord
        drift_summary = None
        adjusted_weights = None
        
        if self.drift_analyzer and self.closed_position_repository:
            try:
                # This is a placeholder for future drift implementation
                # Currently, confidence scores are not persisted with positions
                logger.debug(
                    "Drift analysis available but confidence score persistence not yet implemented",
                    extra={"component": "ConfidencePipeline"}
                )
                # When implemented:
                # historical_scores = await self._load_historical_factor_scores()
                # drift_metrics = self.drift_analyzer.compute(historical_scores)
                # adjusted_weights = self.drift_analyzer.adjust_weights(self._weights, drift_metrics)
                # drift_summary = self.drift_analyzer.get_drift_summary(drift_metrics)
            except Exception as e:
                logger.error(f"Drift analysis failed: {e}", exc_info=True)
        
        # Calculate weighted average (use adjusted weights if available)
        if not scores:
            logger.warning("No confidence scores available, returning 0.0")
            final_score = 0.0
        else:
            # Use adjusted weights if drift analysis ran
            if adjusted_weights:
                weighted_sum = sum(
                    score.score * adjusted_weights.get(score.factor_name, score.weight)
                    for score in scores
                )
                active_weight = sum(adjusted_weights.values())
            else:
                weighted_sum = sum(score.weighted_score for score in scores)
                active_weight = sum(score.weight for score in scores)
            
            final_score = weighted_sum / active_weight if active_weight > 0 else 0.0
        
        evaluation_time = (perf_counter() - start_time) * 1000  # ms
        passed = final_score >= self.min_threshold
        
        result = PipelineResult(
            final_score=final_score,
            factor_scores=tuple(scores),
            total_weight=self.total_weight,
            evaluation_time_ms=evaluation_time,
            passed_threshold=passed,
            reasons=tuple(reasons),
            drift_metrics=drift_summary
        )
        
        logger.info(
            f"Confidence evaluation complete: {final_score:.3f} "
            f"(threshold: {self.min_threshold}, passed: {passed}, "
            f"time: {evaluation_time:.2f}ms, drift_applied: {drift_summary is not None})"
        )
        
        return result
    
    def add_factor(self, factor: IConfidenceFactor) -> None:
        """
        Add a new confidence factor to the pipeline.
        
        Args:
            factor: Confidence factor to add
        """
        self.factors.append(factor)
        self.total_weight = sum(f.weight for f in self.factors)
        
        logger.info(
            f"Added factor '{factor.name}' (weight: {factor.weight}), "
            f"new total weight: {self.total_weight}"
        )
    
    def remove_factor(self, factor_name: str) -> bool:
        """
        Remove a confidence factor by name.
        
        Args:
            factor_name: Name of factor to remove
            
        Returns:
            True if factor was removed, False if not found
        """
        initial_count = len(self.factors)
        self.factors = [f for f in self.factors if f.name != factor_name]
        
        if len(self.factors) < initial_count:
            self.total_weight = sum(f.weight for f in self.factors)
            logger.info(f"Removed factor '{factor_name}', new total weight: {self.total_weight}")
            return True
        
        return False
