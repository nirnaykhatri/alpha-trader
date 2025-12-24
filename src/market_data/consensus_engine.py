"""
Market Data Consensus Engine

Centralizes market data fetching with provider fallback and consensus logic.
Improves reliability by scoring providers and selecting the most trustworthy data.
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from abc import ABC, abstractmethod

from src.market_data.circuit_breaker import ProviderCircuitBreaker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketDataScoringConfig:
    """Configuration for market data freshness and reliability scoring.
    
    Centralizes all threshold values for consensus scoring.
    """
    # Freshness thresholds (seconds)
    fresh_threshold: float = 5.0
    acceptable_threshold: float = 30.0
    stale_threshold: float = 60.0
    
    # Reliability thresholds
    high_confidence_threshold: float = 0.9
    high_age_threshold: float = 2.0
    medium_confidence_threshold: float = 0.75
    medium_age_threshold: float = 5.0
    stale_confidence_threshold: float = 0.5
    stale_age_threshold: float = 15.0
    
    # Outlier detection (IQR-based)
    outlier_iqr_multiplier: float = 1.5  # Standard IQR outlier detection
    min_data_points_for_outlier_detection: int = 3
    
    @classmethod
    def from_config(cls, config: dict) -> 'MarketDataScoringConfig':
        """Load from config dict with defaults."""
        md_config = config.get('market_data', {}).get('scoring', {})
        return cls(
            fresh_threshold=md_config.get('fresh_threshold', 5.0),
            acceptable_threshold=md_config.get('acceptable_threshold', 30.0),
            stale_threshold=md_config.get('stale_threshold', 60.0),
            high_confidence_threshold=md_config.get('high_confidence_threshold', 0.9),
            high_age_threshold=md_config.get('high_age_threshold', 2.0),
            medium_confidence_threshold=md_config.get('medium_confidence_threshold', 0.75),
            medium_age_threshold=md_config.get('medium_age_threshold', 5.0),
            stale_confidence_threshold=md_config.get('stale_confidence_threshold', 0.5),
            stale_age_threshold=md_config.get('stale_age_threshold', 15.0),
            outlier_iqr_multiplier=md_config.get('outlier_iqr_multiplier', 1.5),
            min_data_points_for_outlier_detection=md_config.get('min_data_points_for_outlier_detection', 3)
        )


class DataFreshness(Enum):
    """Data freshness classification."""
    FRESH = "fresh"          # < 5 seconds old
    ACCEPTABLE = "acceptable"  # 5-30 seconds old
    STALE = "stale"          # 30-60 seconds old
    EXPIRED = "expired"      # > 60 seconds old


class DataReliability(Enum):
    """Data reliability classification."""
    HIGH = "HIGH"            # confidence >= 0.9, age < 2s
    MEDIUM = "MEDIUM"        # confidence >= 0.75, age < 5s
    STALE = "STALE"          # confidence >= 0.5, age < 15s
    UNUSABLE = "UNUSABLE"    # confidence < 0.5 or age >= 15s


@dataclass
class MarketDataPoint:
    """
    A single market data point from a provider.
    
    Includes metadata for scoring and consensus determination.
    """
    provider: str
    symbol: str
    price: float
    timestamp: datetime
    volume: Optional[int] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    
    @property
    def age_seconds(self) -> float:
        """Calculate data age in seconds."""
        return (datetime.utcnow() - self.timestamp).total_seconds()
    
    def get_freshness(self, config: Optional[MarketDataScoringConfig] = None) -> DataFreshness:
        """Classify data freshness using configurable thresholds.
        
        Args:
            config: Optional scoring config (uses defaults if None)
        """
        cfg = config or MarketDataScoringConfig()
        age = self.age_seconds
        
        if age < cfg.fresh_threshold:
            return DataFreshness.FRESH
        elif age < cfg.acceptable_threshold:
            return DataFreshness.ACCEPTABLE
        elif age < cfg.stale_threshold:
            return DataFreshness.STALE
        else:
            return DataFreshness.EXPIRED
    
    @property
    def freshness(self) -> DataFreshness:
        """Classify data freshness with default thresholds (backward compatibility)."""
        return self.get_freshness()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            'provider': self.provider,
            'symbol': self.symbol,
            'price': self.price,
            'timestamp': self.timestamp.isoformat(),
            'age_seconds': self.age_seconds,
            'freshness': self.freshness.value,
            'spread': self.spread
        }


@dataclass
class ProviderScore:
    """
    Scoring metrics for a market data provider.
    
    Higher scores indicate more reliable data.
    """
    provider: str
    freshness_score: float = 0.0    # 0-1 based on data age
    spread_score: float = 0.0       # 0-1 based on bid-ask spread
    reliability_score: float = 0.0  # 0-1 based on success rate
    total_score: float = 0.0
    
    def calculate_total(
        self,
        freshness_weight: float = 0.4,
        spread_weight: float = 0.3,
        reliability_weight: float = 0.3
    ) -> float:
        """Calculate weighted total score."""
        self.total_score = (
            self.freshness_score * freshness_weight +
            self.spread_score * spread_weight +
            self.reliability_score * reliability_weight
        )
        return self.total_score


@dataclass
class ConsensusResult:
    """
    Result of consensus calculation across providers.
    
    Includes selected price, metadata, and reliability classification.
    """
    symbol: str
    price: float
    source: str  # "consensus" or provider name
    confidence: float  # 0-1 confidence in result
    reliability: DataReliability  # Classified reliability level
    providers_used: List[str]
    data_points: List[MarketDataPoint] = field(default_factory=list)
    reason: str = ""
    age_seconds: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            'symbol': self.symbol,
            'price': self.price,
            'source': self.source,
            'confidence': self.confidence,
            'reliability': self.reliability.value,
            'age_seconds': self.age_seconds,
            'providers_used': self.providers_used,
            'num_data_points': len(self.data_points),
            'reason': self.reason
        }
    
    @property
    def is_usable(self) -> bool:
        """Check if data is usable for trading decisions."""
        return self.reliability != DataReliability.UNUSABLE
    
    @property
    def is_high_quality(self) -> bool:
        """Check if data is high quality."""
        return self.reliability == DataReliability.HIGH


class IConsensusMarketDataProvider(ABC):
    """
    Interface for market data providers used by the consensus engine.
    
    Note: This is distinct from IMarketDataProvider in src.interfaces which returns
    simple float prices. This interface returns rich MarketDataPoint objects with
    metadata for consensus calculations.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass
    
    @abstractmethod
    async def get_current_price(self, symbol: str) -> Optional[MarketDataPoint]:
        """
        Fetch current market price with metadata.
        
        Returns:
            MarketDataPoint or None if fetch failed
        """
        pass


class MarketDataConsensusEngine:
    """
    Consensus engine for market data with provider fallback.
    
    Centralizes all market data fetching logic, replacing ad-hoc fallback patterns.
    
    Example:
        engine = MarketDataConsensusEngine(providers=[alpaca_provider, polygon_provider])
        result = await engine.get_consensus_price('AAPL')
        
        if result.confidence > 0.7:
            # High confidence price
            execute_order(price=result.price)
        else:
            # Low confidence, may want to skip trade
            logger.warning(f"Low confidence price: {result.confidence:.2%}")
    """
    
    def __init__(
        self,
        providers: List[IConsensusMarketDataProvider],
        spread_threshold: float = 0.01,  # 1% max spread
        staleness_threshold: float = 60.0,  # 60 seconds max age
        circuit_breaker_enabled: bool = True,
        failure_threshold: int = 5,
        reset_timeout: int = 60,
        scoring_config: Optional[MarketDataScoringConfig] = None
    ):
        """
        Initialize consensus engine.
        
        Args:
            providers: List of market data providers
            spread_threshold: Maximum acceptable bid-ask spread (fraction)
            staleness_threshold: Maximum acceptable data age (seconds)
            circuit_breaker_enabled: Whether to enable circuit breaker
            failure_threshold: Consecutive failures before opening circuit
            reset_timeout: Seconds before attempting circuit reset
            scoring_config: Market data scoring configuration (optional, uses defaults if None)
        """
        self.providers = providers
        self.spread_threshold = spread_threshold
        self.staleness_threshold = staleness_threshold
        self.scoring_config = scoring_config or MarketDataScoringConfig()
        
        # Provider reliability tracking
        self.provider_stats: Dict[str, Dict[str, int]] = {
            provider.name: {'successes': 0, 'failures': 0}
            for provider in providers
        }
        
        # Circuit breaker for provider resilience
        self.circuit_breaker_enabled = circuit_breaker_enabled
        if circuit_breaker_enabled:
            self.circuit_breaker = ProviderCircuitBreaker(
                failure_threshold=failure_threshold,
                reset_timeout=reset_timeout
            )
            logger.info("Circuit breaker enabled for provider fault tolerance")
        else:
            self.circuit_breaker = None
        
        logger.info(
            f"MarketDataConsensusEngine initialized with {len(providers)} providers: "
            f"{[p.name for p in providers]}"
        )
    
    async def get_consensus_price(
        self,
        symbol: str,
        timeout: float = 5.0
    ) -> Optional[ConsensusResult]:
        """
        Get consensus price across all providers.
        
        Args:
            symbol: Symbol to fetch price for
            timeout: Maximum time to wait for provider responses
            
        Returns:
            ConsensusResult with best price estimate
        """
        # Filter out disabled providers (circuit breaker)
        active_providers = [
            provider for provider in self.providers
            if not self._is_provider_disabled(provider.name)
        ]
        
        if not active_providers:
            logger.error(
                f"All providers disabled for {symbol} - "
                f"circuit breakers open, no data available"
            )
            return None
        
        # PARALLEL FETCH: Query active providers concurrently
        tasks = [
            self._fetch_with_tracking(provider, symbol)
            for provider in active_providers
        ]
        
        try:
            # Wait for all providers with timeout
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=timeout
            )
            
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching price for {symbol} after {timeout}s")
            results = []
        
        # Filter successful results
        data_points: List[MarketDataPoint] = [
            r for r in results
            if isinstance(r, MarketDataPoint)
        ]
        
        if not data_points:
            logger.error(f"No providers returned data for {symbol}")
            return None
        
        logger.info(
            f"Fetched {len(data_points)}/{len(active_providers)} prices for {symbol}"
        )
        
        # Score providers
        scored_points = self._score_data_points(data_points)
        
        # Filter outliers (Issue #5 - IQR-based outlier detection)
        scored_points = self._filter_outliers(scored_points)
        
        # Calculate consensus
        consensus = self._calculate_consensus(symbol, scored_points)
        
        logger.info(
            f"Consensus for {symbol}: ${consensus.price:.2f} "
            f"(confidence: {consensus.confidence:.1%}, reliability: {consensus.reliability.value}, "
            f"source: {consensus.source})"
        )
        
        # Warn if low reliability
        if consensus.reliability == DataReliability.UNUSABLE:
            logger.error(
                f"UNUSABLE data for {symbol}: confidence={consensus.confidence:.1%}, "
                f"age={consensus.age_seconds:.1f}s - SKIP TRADING"
            )
        elif consensus.reliability == DataReliability.STALE:
            logger.warning(
                f"STALE data for {symbol}: age={consensus.age_seconds:.1f}s - use with caution"
            )
        
        return consensus
    
    async def _fetch_with_tracking(
        self,
        provider: IConsensusMarketDataProvider,
        symbol: str
    ) -> Optional[MarketDataPoint]:
        """
        Fetch from provider with success/failure tracking and circuit breaker.
        
        Updates provider reliability statistics and circuit breaker state.
        """
        try:
            data_point = await provider.get_current_price(symbol)
            
            if data_point:
                self.provider_stats[provider.name]['successes'] += 1
                
                # Record success in circuit breaker
                if self.circuit_breaker:
                    self.circuit_breaker.record_success(provider.name)
                
                logger.debug(
                    f"✅ {provider.name}: ${data_point.price:.2f} "
                    f"(age: {data_point.age_seconds:.1f}s)"
                )
                return data_point
            else:
                self.provider_stats[provider.name]['failures'] += 1
                
                # Record failure in circuit breaker
                if self.circuit_breaker:
                    self.circuit_breaker.record_failure(provider.name)
                
                logger.debug(f"❌ {provider.name}: No data")
                return None
                
        except Exception as e:
            self.provider_stats[provider.name]['failures'] += 1
            
            # Record failure in circuit breaker
            if self.circuit_breaker:
                self.circuit_breaker.record_failure(provider.name)
            
            logger.warning(f"❌ {provider.name} failed: {e}")
            return None
    
    def _is_provider_disabled(self, provider_name: str) -> bool:
        """Check if provider is disabled by circuit breaker."""
        if not self.circuit_breaker:
            return False
        
        return self.circuit_breaker.is_disabled(provider_name)
    
    def _score_data_points(
        self,
        data_points: List[MarketDataPoint]
    ) -> List[Tuple[MarketDataPoint, ProviderScore]]:
        """
        Score each data point based on freshness, spread, and reliability.
        
        Returns:
            List of (data_point, score) tuples sorted by total_score descending
        """
        scored = []
        
        for point in data_points:
            score = ProviderScore(provider=point.provider)
            
            # Freshness score (0-1)
            age = point.age_seconds
            if age < 5:
                score.freshness_score = 1.0
            elif age < 30:
                score.freshness_score = 0.8
            elif age < 60:
                score.freshness_score = 0.5
            else:
                score.freshness_score = 0.2
            
            # Spread score (0-1)
            if point.spread is not None:
                if point.spread < 0.001:  # 0.1%
                    score.spread_score = 1.0
                elif point.spread < 0.005:  # 0.5%
                    score.spread_score = 0.8
                elif point.spread < self.spread_threshold:
                    score.spread_score = 0.6
                else:
                    score.spread_score = 0.3
            else:
                score.spread_score = 0.5  # Neutral if spread unknown
            
            # Reliability score (0-1)
            stats = self.provider_stats[point.provider]
            total = stats['successes'] + stats['failures']
            if total > 0:
                score.reliability_score = stats['successes'] / total
            else:
                score.reliability_score = 0.5  # Neutral for new providers
            
            # Calculate total weighted score
            score.calculate_total()
            
            scored.append((point, score))
        
        # Sort by total score descending
        scored.sort(key=lambda x: x[1].total_score, reverse=True)
        
        return scored
    
    def _classify_reliability(self, confidence: float, age_seconds: float) -> DataReliability:
        """
        Classify data reliability based on confidence and age.
        
        Args:
            confidence: Confidence score (0-1)
            age_seconds: Data age in seconds
            
        Returns:
            DataReliability classification
        """
        cfg = self.scoring_config
        
        if confidence >= cfg.high_confidence_threshold and age_seconds < cfg.high_age_threshold:
            return DataReliability.HIGH
        elif confidence >= cfg.medium_confidence_threshold and age_seconds < cfg.medium_age_threshold:
            return DataReliability.MEDIUM
        elif confidence >= cfg.stale_confidence_threshold and age_seconds < cfg.stale_age_threshold:
            return DataReliability.STALE
        else:
            return DataReliability.UNUSABLE
    
    def _filter_outliers(
        self,
        scored_points: List[Tuple[MarketDataPoint, ProviderScore]]
    ) -> List[Tuple[MarketDataPoint, ProviderScore]]:
        """
        Filter out price outliers using IQR-based detection.
        
        Protects against erroneous provider data by removing statistical outliers
        before consensus calculation.
        
        Args:
            scored_points: List of (data point, score) tuples
            
        Returns:
            Filtered list with outliers removed
        """
        if len(scored_points) < self.scoring_config.min_data_points_for_outlier_detection:
            # Too few points for meaningful outlier detection
            return scored_points
        
        prices = [point.price for point, _ in scored_points]
        prices_sorted = sorted(prices)
        n = len(prices_sorted)
        
        # Calculate quartiles
        q1_idx = n // 4
        q3_idx = (3 * n) // 4
        q1 = prices_sorted[q1_idx]
        q3 = prices_sorted[q3_idx]
        
        # Calculate IQR and bounds
        iqr = q3 - q1
        multiplier = self.scoring_config.outlier_iqr_multiplier
        lower_bound = q1 - (multiplier * iqr)
        upper_bound = q3 + (multiplier * iqr)
        
        # Filter outliers
        filtered = [
            (point, score)
            for point, score in scored_points
            if lower_bound <= point.price <= upper_bound
        ]
        
        # Log if outliers detected
        if len(filtered) < len(scored_points):
            removed_count = len(scored_points) - len(filtered)
            outlier_prices = [
                point.price
                for point, _ in scored_points
                if point.price < lower_bound or point.price > upper_bound
            ]
            logger.warning(
                f"Removed {removed_count} price outliers: {outlier_prices} "
                f"(IQR bounds: ${lower_bound:.2f} - ${upper_bound:.2f})"
            )
        
        return filtered if filtered else scored_points  # Fail-safe: return original if all filtered
    
    def _calculate_consensus(
        self,
        symbol: str,
        scored_points: List[Tuple[MarketDataPoint, ProviderScore]]
    ) -> ConsensusResult:
        """
        Calculate consensus price from scored data points.
        
        Uses the highest-scored provider if all agree, otherwise uses weighted average.
        """
        if not scored_points:
            raise ValueError("No scored data points to calculate consensus")
        
        prices = [point.price for point, _ in scored_points]
        
        # Check for agreement (prices within 0.5%)
        price_range = max(prices) - min(prices)
        mid_price = (max(prices) + min(prices)) / 2
        
        if mid_price > 0:
            price_variance = price_range / mid_price
        else:
            price_variance = 0
        
        if price_variance < 0.005:  # 0.5% variance
            # High agreement - use highest scored provider
            best_point, best_score = scored_points[0]
            
            # Calculate reliability
            age_seconds = best_point.age_seconds
            confidence = 0.95
            reliability = self._classify_reliability(confidence, age_seconds)
            
            return ConsensusResult(
                symbol=symbol,
                price=best_point.price,
                source=best_point.provider,
                confidence=confidence,
                reliability=reliability,
                providers_used=[p.provider for p, _ in scored_points],
                data_points=[p for p, _ in scored_points],
                reason=f"High agreement ({len(scored_points)} providers within 0.5%)",
                age_seconds=age_seconds
            )
        
        else:
            # Disagreement - use weighted average
            total_weight = sum(score.total_score for _, score in scored_points)
            
            if total_weight > 0:
                weighted_price = sum(
                    point.price * score.total_score
                    for point, score in scored_points
                ) / total_weight
            else:
                # Fallback to simple average
                weighted_price = sum(prices) / len(prices)
            
            # Lower confidence due to disagreement
            confidence = max(0.5, 1.0 - price_variance)
            
            # Calculate average age
            avg_age = sum(p.age_seconds for p, _ in scored_points) / len(scored_points)
            
            # Calculate reliability
            reliability = self._classify_reliability(confidence, avg_age)
            
            return ConsensusResult(
                symbol=symbol,
                price=weighted_price,
                source="consensus",
                confidence=confidence,
                reliability=reliability,
                providers_used=[p.provider for p, _ in scored_points],
                data_points=[p for p, _ in scored_points],
                reason=f"Weighted average ({len(scored_points)} providers, {price_variance:.1%} variance)",
                age_seconds=avg_age
            )
    
    def get_provider_statistics(self) -> Dict[str, Dict[str, Any]]:
        """
        Get reliability statistics for all providers.
        
        Returns:
            Dict mapping provider name to statistics (includes circuit breaker state)
        """
        stats = {}
        
        for provider_name, counts in self.provider_stats.items():
            total = counts['successes'] + counts['failures']
            success_rate = counts['successes'] / total if total > 0 else 0
            
            provider_stats = {
                'successes': counts['successes'],
                'failures': counts['failures'],
                'total_requests': total,
                'success_rate': success_rate
            }
            
            # Add circuit breaker state if enabled
            if self.circuit_breaker:
                circuit_stats = self.circuit_breaker.get_statistics(provider_name)
                provider_stats['circuit_breaker'] = circuit_stats
            
            stats[provider_name] = provider_stats
        
        return stats
    
    def reset_statistics(self) -> None:
        """Reset provider statistics to zero."""
        for stats in self.provider_stats.values():
            stats['successes'] = 0
            stats['failures'] = 0
        
        logger.info("Provider statistics reset")
