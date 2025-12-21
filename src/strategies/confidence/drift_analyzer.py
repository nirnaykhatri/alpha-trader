"""
Confidence Drift Analyzer

Detects statistically significant drift in confidence factor performance
using z-score analysis against historical baselines. Adapts factor weights
to dampen underperforming factors.

Key Metrics:
- Z-score threshold: 2.0 (statistically significant drift)
- Dampening: Up to 30% weight reduction
- Minimum samples: 20 positions required for adaptation

Usage:
    analyzer = ConfidenceDriftAnalyzer(window_size=50, z_threshold=2.0)
    
    # Compute drift metrics
    drift_metrics = analyzer.compute(historical_scores)
    
    # Adjust weights based on drift
    adjusted_weights = analyzer.adjust_weights(original_weights, drift_metrics)
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional
from statistics import mean, stdev

from src.core.logging_config import get_logger


logger = get_logger(__name__)


@dataclass(frozen=True)
class FactorDriftMetrics:
    """Drift analysis metrics for a confidence factor.
    
    Attributes:
        factor: Factor name (e.g., 'TechnicalFactor')
        mean: Historical mean score
        variance: Historical variance
        deviation: Current deviation from mean
        z_score: Standardized z-score (deviation / std_dev)
        drift_detected: Whether drift exceeds threshold
        sample_count: Number of samples in baseline
    """
    factor: str
    mean: float
    variance: float
    deviation: float
    z_score: float
    drift_detected: bool
    sample_count: int


class ConfidenceDriftAnalyzer:
    """Analyzes confidence factor performance drift and adapts weights.
    
    Detects when factors consistently underperform historical baselines
    using z-score analysis. Applies dampening to weights when drift is detected.
    
    Attributes:
        window_size: Number of historical positions to analyze
        z_threshold: Z-score threshold for drift detection (default: 2.0)
        min_samples: Minimum samples required for analysis (default: 20)
        max_dampening: Maximum weight reduction (default: 0.30 = 30%)
    """
    
    def __init__(
        self,
        window_size: int = 50,
        z_threshold: float = 2.0,
        min_samples: int = 20,
        max_dampening: float = 0.30
    ):
        """Initialize confidence drift analyzer.
        
        Args:
            window_size: Number of positions in rolling window
            z_threshold: Z-score threshold for drift detection
            min_samples: Minimum samples required for analysis
            max_dampening: Maximum weight reduction fraction (0.30 = 30%)
        """
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.min_samples = min_samples
        self.max_dampening = max_dampening
        
        logger.info(
            f"ConfidenceDriftAnalyzer initialized",
            extra={
                "component": "ConfidenceDriftAnalyzer",
                "window_size": window_size,
                "z_threshold": z_threshold,
                "min_samples": min_samples,
                "max_dampening": max_dampening
            }
        )
    
    def compute(
        self,
        historical_scores: Dict[str, List[float]],
        current_scores: Optional[Dict[str, float]] = None
    ) -> Dict[str, FactorDriftMetrics]:
        """Compute drift metrics for each confidence factor.
        
        Args:
            historical_scores: Dict mapping factor name to list of historical scores
            current_scores: Optional dict of current factor scores to compare
        
        Returns:
            Dict mapping factor name to FactorDriftMetrics
        """
        drift_metrics = {}
        
        for factor, scores in historical_scores.items():
            # Skip if insufficient samples
            if len(scores) < self.min_samples:
                logger.debug(
                    f"Insufficient samples for {factor}: {len(scores)} < {self.min_samples}",
                    extra={"component": "ConfidenceDriftAnalyzer", "factor": factor}
                )
                continue
            
            try:
                # Calculate baseline statistics
                factor_mean = mean(scores)
                factor_stdev = stdev(scores) if len(scores) > 1 else 0.0
                
                # Calculate current deviation
                if current_scores and factor in current_scores:
                    current_value = current_scores[factor]
                    deviation = current_value - factor_mean
                else:
                    # Use latest score as current if not provided
                    deviation = scores[-1] - factor_mean
                
                # Calculate z-score
                if factor_stdev > 0:
                    z_score = abs(deviation) / factor_stdev
                else:
                    z_score = 0.0
                
                # Detect drift
                drift_detected = z_score > self.z_threshold
                
                metrics = FactorDriftMetrics(
                    factor=factor,
                    mean=factor_mean,
                    variance=factor_stdev ** 2,
                    deviation=deviation,
                    z_score=z_score,
                    drift_detected=drift_detected,
                    sample_count=len(scores)
                )
                
                drift_metrics[factor] = metrics
                
                if drift_detected:
                    logger.warning(
                        f"🔍 Drift detected for {factor}",
                        extra={
                            "component": "ConfidenceDriftAnalyzer",
                            "factor": factor,
                            "z_score": z_score,
                            "threshold": self.z_threshold,
                            "mean": factor_mean,
                            "deviation": deviation
                        }
                    )
                
            except Exception as e:
                logger.error(
                    f"Error computing drift for {factor}: {e}",
                    extra={
                        "component": "ConfidenceDriftAnalyzer",
                        "factor": factor,
                        "error": str(e)
                    },
                    exc_info=True
                )
                continue
        
        return drift_metrics
    
    def adjust_weights(
        self,
        original_weights: Dict[str, float],
        drift_metrics: Dict[str, FactorDriftMetrics]
    ) -> Dict[str, float]:
        """Adjust factor weights based on drift metrics.
        
        Applies dampening to weights for factors with detected drift:
        adjusted_weight = original * (1.0 - min(max_dampening, (z - threshold) * 0.05))
        
        Args:
            original_weights: Dict mapping factor name to original weight
            drift_metrics: Dict mapping factor name to FactorDriftMetrics
        
        Returns:
            Dict mapping factor name to adjusted weight
        """
        adjusted_weights = original_weights.copy()
        
        for factor, metrics in drift_metrics.items():
            if factor not in adjusted_weights:
                continue
            
            if metrics.drift_detected:
                # Calculate dampening amount
                # Formula: min(max_dampening, (z_score - threshold) * 0.05)
                excess_z = metrics.z_score - self.z_threshold
                dampening = min(self.max_dampening, excess_z * 0.05)
                
                # Apply dampening
                original_weight = original_weights[factor]
                adjusted_weight = original_weight * (1.0 - dampening)
                adjusted_weights[factor] = adjusted_weight
                
                logger.info(
                    f"⚖️ Weight adjusted for {factor}",
                    extra={
                        "component": "ConfidenceDriftAnalyzer",
                        "factor": factor,
                        "original_weight": original_weight,
                        "adjusted_weight": adjusted_weight,
                        "dampening": dampening,
                        "z_score": metrics.z_score
                    }
                )
        
        # Normalize weights to sum to 1.0
        total_weight = sum(adjusted_weights.values())
        if total_weight > 0:
            adjusted_weights = {
                factor: weight / total_weight
                for factor, weight in adjusted_weights.items()
            }
        
        logger.debug(
            f"Weights adjusted",
            extra={
                "component": "ConfidenceDriftAnalyzer",
                "original_sum": sum(original_weights.values()),
                "adjusted_sum": sum(adjusted_weights.values()),
                "adjustments": {
                    f: f"{original_weights.get(f, 0):.3f} → {w:.3f}"
                    for f, w in adjusted_weights.items()
                    if abs(original_weights.get(f, 0) - w) > 0.001
                }
            }
        )
        
        return adjusted_weights
    
    def get_drift_summary(
        self,
        drift_metrics: Dict[str, FactorDriftMetrics]
    ) -> Dict[str, any]:
        """Generate summary of drift analysis for logging/monitoring.
        
        Args:
            drift_metrics: Dict of FactorDriftMetrics
        
        Returns:
            Summary dict with drift statistics
        """
        total_factors = len(drift_metrics)
        drifted_factors = sum(1 for m in drift_metrics.values() if m.drift_detected)
        
        summary = {
            "total_factors": total_factors,
            "drifted_factors": drifted_factors,
            "drift_rate": drifted_factors / total_factors if total_factors > 0 else 0.0,
            "factors": {
                factor: {
                    "z_score": metrics.z_score,
                    "drift_detected": metrics.drift_detected,
                    "sample_count": metrics.sample_count
                }
                for factor, metrics in drift_metrics.items()
            }
        }
        
        return summary
