"""
Confidence scoring infrastructure for DCA decision making.

Pluggable confidence factor system using chain-of-responsibility pattern.
"""

from src.strategies.confidence.confidence_factor import IConfidenceFactor, ConfidenceScore
from src.strategies.confidence.confidence_pipeline import ConfidencePipeline
from src.strategies.confidence.factors import (
    TechnicalLevelConfidenceFactor,
    VolumeConfidenceFactor,
    VolatilityConfidenceFactor,
    TrendStrengthConfidenceFactor,
)

__all__ = [
    'IConfidenceFactor',
    'ConfidenceScore',
    'ConfidencePipeline',
    'TechnicalLevelConfidenceFactor',
    'VolumeConfidenceFactor',
    'VolatilityConfidenceFactor',
    'TrendStrengthConfidenceFactor',
]
