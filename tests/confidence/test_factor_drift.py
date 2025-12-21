"""
Tests for ConfidenceDriftAnalyzer

Validates drift detection logic and weight dampening.
"""

import pytest
from src.strategies.confidence.drift_analyzer import (
    ConfidenceDriftAnalyzer,
    FactorDriftMetrics
)


class TestConfidenceDriftAnalyzer:
    """Test suite for ConfidenceDriftAnalyzer."""
    
    def test_initialization(self):
        """Test analyzer initializes with correct defaults."""
        analyzer = ConfidenceDriftAnalyzer()
        
        assert analyzer.window_size == 50
        assert analyzer.z_threshold == 2.0
        assert analyzer.min_samples == 20
        assert analyzer.max_dampening == 0.30
    
    def test_custom_initialization(self):
        """Test analyzer initializes with custom parameters."""
        analyzer = ConfidenceDriftAnalyzer(
            window_size=100,
            z_threshold=2.5,
            min_samples=30,
            max_dampening=0.25
        )
        
        assert analyzer.window_size == 100
        assert analyzer.z_threshold == 2.5
        assert analyzer.min_samples == 30
        assert analyzer.max_dampening == 0.25
    
    def test_no_drift_with_stable_values(self):
        """Test that stable values do not trigger drift detection."""
        analyzer = ConfidenceDriftAnalyzer(z_threshold=2.0, min_samples=20)
        
        # Create stable historical scores (mean ~0.7, low variance)
        historical_scores = {
            'TechnicalFactor': [0.68, 0.71, 0.69, 0.72, 0.70] * 10,  # 50 samples
            'VolumeFactor': [0.60, 0.62, 0.61, 0.63, 0.61] * 10
        }
        
        drift_metrics = analyzer.compute(historical_scores)
        
        assert 'TechnicalFactor' in drift_metrics
        assert 'VolumeFactor' in drift_metrics
        
        # Neither factor should detect drift
        assert drift_metrics['TechnicalFactor'].drift_detected is False
        assert drift_metrics['VolumeFactor'].drift_detected is False
        
        # Z-scores should be low
        assert drift_metrics['TechnicalFactor'].z_score < 2.0
        assert drift_metrics['VolumeFactor'].z_score < 2.0
    
    def test_detects_drift_on_mean_shift(self):
        """Test detection of drift when mean shifts significantly."""
        analyzer = ConfidenceDriftAnalyzer(z_threshold=2.0, min_samples=20)
        
        # Create historical scores with stable mean around 0.70
        historical_scores = {
            'TechnicalFactor': [0.70 + (i % 3 - 1) * 0.02 for i in range(50)]
        }
        
        # Current score significantly below historical mean
        current_scores = {'TechnicalFactor': 0.45}
        
        drift_metrics = analyzer.compute(historical_scores, current_scores)
        
        assert 'TechnicalFactor' in drift_metrics
        
        # Should detect drift
        assert drift_metrics['TechnicalFactor'].drift_detected is True
        assert drift_metrics['TechnicalFactor'].z_score > 2.0
    
    def test_weight_dampening_applied(self):
        """Test that weight dampening is applied correctly when drift detected."""
        analyzer = ConfidenceDriftAnalyzer(
            z_threshold=2.0,
            max_dampening=0.30,
            min_samples=20
        )
        
        # Create drift scenario
        drift_metrics = {
            'TechnicalFactor': FactorDriftMetrics(
                factor='TechnicalFactor',
                mean=0.7,
                variance=0.01,
                deviation=-0.4,
                z_score=3.0,  # Exceeds threshold
                drift_detected=True,
                sample_count=50
            ),
            'VolumeFactor': FactorDriftMetrics(
                factor='VolumeFactor',
                mean=0.6,
                variance=0.01,
                deviation=0.05,
                z_score=0.5,  # Does not exceed threshold
                drift_detected=False,
                sample_count=50
            )
        }
        
        original_weights = {
            'TechnicalFactor': 0.4,
            'VolumeFactor': 0.6
        }
        
        adjusted_weights = analyzer.adjust_weights(original_weights, drift_metrics)
        
        # TechnicalFactor should be dampened
        # Dampening = min(0.30, (3.0 - 2.0) * 0.05) = min(0.30, 0.05) = 0.05
        # Adjusted = 0.4 * (1 - 0.05) = 0.38 (before normalization)
        assert adjusted_weights['TechnicalFactor'] < original_weights['TechnicalFactor']
        
        # VolumeFactor should be unchanged (before normalization)
        # After normalization, both will sum to 1.0
        assert sum(adjusted_weights.values()) == pytest.approx(1.0, rel=1e-6)
    
    def test_max_dampening_limit(self):
        """Test that dampening does not exceed max_dampening."""
        analyzer = ConfidenceDriftAnalyzer(
            z_threshold=2.0,
            max_dampening=0.30,
            min_samples=20
        )
        
        # Create extreme drift scenario with multiple factors
        drift_metrics = {
            'TechnicalFactor': FactorDriftMetrics(
                factor='TechnicalFactor',
                mean=0.7,
                variance=0.01,
                deviation=-0.5,
                z_score=10.0,  # Extreme z-score
                drift_detected=True,
                sample_count=50
            ),
            'VolumeFactor': FactorDriftMetrics(
                factor='VolumeFactor',
                mean=0.6,
                variance=0.01,
                deviation=0.05,
                z_score=0.5,  # No drift
                drift_detected=False,
                sample_count=50
            )
        }
        
        original_weights = {'TechnicalFactor': 0.6, 'VolumeFactor': 0.4}
        adjusted_weights = analyzer.adjust_weights(original_weights, drift_metrics)
        
        # Dampening = min(0.30, (10.0 - 2.0) * 0.05) = min(0.30, 0.40) = 0.30
        # TechnicalFactor: 0.6 * (1 - 0.30) = 0.42
        # VolumeFactor: 0.4 (no change)
        # Normalized: TechnicalFactor = 0.42/(0.42+0.4) = 0.512, VolumeFactor = 0.488
        assert adjusted_weights['TechnicalFactor'] < original_weights['TechnicalFactor']
        assert adjusted_weights['VolumeFactor'] > original_weights['VolumeFactor']
        assert abs(sum(adjusted_weights.values()) - 1.0) < 0.01  # Normalized
    
    def test_insufficient_samples_skipped(self):
        """Test that factors with insufficient samples are skipped."""
        analyzer = ConfidenceDriftAnalyzer(min_samples=20)
        
        # Only 10 samples (below minimum)
        historical_scores = {
            'TechnicalFactor': [0.7] * 10
        }
        
        drift_metrics = analyzer.compute(historical_scores)
        
        # Should not compute drift for insufficient samples
        assert 'TechnicalFactor' not in drift_metrics or len(drift_metrics) == 0
    
    def test_get_drift_summary(self):
        """Test drift summary generation."""
        analyzer = ConfidenceDriftAnalyzer()
        
        drift_metrics = {
            'TechnicalFactor': FactorDriftMetrics(
                factor='TechnicalFactor',
                mean=0.7,
                variance=0.01,
                deviation=-0.3,
                z_score=2.5,
                drift_detected=True,
                sample_count=50
            ),
            'VolumeFactor': FactorDriftMetrics(
                factor='VolumeFactor',
                mean=0.6,
                variance=0.01,
                deviation=0.1,
                z_score=1.0,
                drift_detected=False,
                sample_count=50
            )
        }
        
        summary = analyzer.get_drift_summary(drift_metrics)
        
        assert summary['total_factors'] == 2
        assert summary['drifted_factors'] == 1
        assert summary['drift_rate'] == 0.5
        assert 'TechnicalFactor' in summary['factors']
        assert 'VolumeFactor' in summary['factors']
        assert summary['factors']['TechnicalFactor']['drift_detected'] is True
        assert summary['factors']['VolumeFactor']['drift_detected'] is False
