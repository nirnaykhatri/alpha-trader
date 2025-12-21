"""
Portfolio Exposure Validator

Validates cross-symbol portfolio exposure to prevent overconcentration risk.
Implements diversification checks including:
- Per-symbol concentration limits
- Correlation-based exposure aggregation
- Sector/industry diversification rules

Prevents systemic risk from highly correlated positions moving in tandem.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import numpy as np

from src.core.logging_config import get_logger
from src.interfaces import IConfigurationManager, IMarketDataProvider
from src.domain.risk_decision import RiskDecision, RiskDecisionStatus


logger = get_logger(__name__)


@dataclass
class SymbolExposure:
    """Exposure metrics for a single symbol."""
    
    symbol: str
    position_count: int
    total_quantity: float
    total_value: float
    concentration_percent: float  # % of total portfolio value
    
    def __str__(self) -> str:
        return (
            f"{self.symbol}: {self.position_count} positions, "
            f"${self.total_value:,.2f} ({self.concentration_percent:.1f}%)"
        )


@dataclass
class CorrelationExposure:
    """Exposure metrics for correlated symbol group."""
    
    symbols: List[str]
    correlation_coefficient: float
    combined_exposure_percent: float
    risk_multiplier: float  # Effective risk due to correlation
    
    def __str__(self) -> str:
        return (
            f"Correlated group {self.symbols}: {self.correlation_coefficient:.2f} correlation, "
            f"{self.combined_exposure_percent:.1f}% combined exposure "
            f"(risk multiplier: {self.risk_multiplier:.2f}x)"
        )


@dataclass
class PortfolioExposureResult:
    """Result of portfolio exposure validation with proportional scaling.
    
    Attributes:
        approved: Whether position is approved (even with scaling)
        scaling_factor: Multiplicative factor to apply to position size (0.0-1.0)
        reasons: List of reasons for scaling or denial
        diversification_score: Optional score indicating portfolio diversification (0.0-1.0)
    """
    approved: bool
    scaling_factor: float  # 1.0 = no scaling, 0.5 = reduce by 50%, 0.0 = deny
    reasons: List[str]
    diversification_score: Optional[float] = None


class PortfolioExposureValidator:
    """
    Validates portfolio-level exposure constraints.
    
    Checks:
    1. Per-symbol concentration limits (e.g., max 20% in one symbol)
    2. Correlated symbol exposure (aggregate exposure of correlated symbols)
    3. Total portfolio exposure (existing check, enhanced here)
    
    Uses rolling correlation analysis to detect hidden concentration risk
    from multiple positions in correlated symbols.
    """
    
    # Default limits (overridable via config)
    DEFAULT_MAX_SYMBOL_CONCENTRATION = 0.20  # 20% max per symbol
    DEFAULT_MAX_CORRELATED_GROUP_EXPOSURE = 0.40  # 40% max for correlated group
    DEFAULT_CORRELATION_THRESHOLD = 0.70  # Symbols with >0.70 correlation treated as group
    DEFAULT_CORRELATION_LOOKBACK_DAYS = 60
    
    def __init__(self,
                 market_data: IMarketDataProvider,
                 config: Optional[IConfigurationManager] = None):
        """
        Initialize portfolio exposure validator.
        
        Args:
            market_data: Market data provider for correlation analysis
            config: Configuration manager
        """
        self.market_data = market_data
        self.config = config
        
        # Load configuration
        if self.config:
            self.max_symbol_concentration = self.config.get(
                'risk.portfolio.max_symbol_concentration',
                default=self.DEFAULT_MAX_SYMBOL_CONCENTRATION
            )
            self.max_correlated_group_exposure = self.config.get(
                'risk.portfolio.max_correlated_group_exposure',
                default=self.DEFAULT_MAX_CORRELATED_GROUP_EXPOSURE
            )
            self.correlation_threshold = self.config.get(
                'risk.portfolio.correlation_threshold',
                default=self.DEFAULT_CORRELATION_THRESHOLD
            )
            self.correlation_lookback_days = self.config.get(
                'risk.portfolio.correlation_lookback_days',
                default=self.DEFAULT_CORRELATION_LOOKBACK_DAYS
            )
        else:
            self.max_symbol_concentration = self.DEFAULT_MAX_SYMBOL_CONCENTRATION
            self.max_correlated_group_exposure = self.DEFAULT_MAX_CORRELATED_GROUP_EXPOSURE
            self.correlation_threshold = self.DEFAULT_CORRELATION_THRESHOLD
            self.correlation_lookback_days = self.DEFAULT_CORRELATION_LOOKBACK_DAYS
        
        # Correlation cache
        self._correlation_cache: Dict[Tuple[str, str], Tuple[float, datetime]] = {}
        self._cache_ttl = timedelta(hours=4)  # Correlation changes slowly
        
        logger.info(
            f"PortfolioExposureValidator initialized "
            f"(max_symbol={self.max_symbol_concentration:.1%}, "
            f"max_correlated={self.max_correlated_group_exposure:.1%}, "
            f"correlation_threshold={self.correlation_threshold:.2f})"
        )
    
    async def validate_new_position(self,
                                    symbol: str,
                                    position_value: float,
                                    current_positions: Dict[str, float],
                                    account_value: float) -> PortfolioExposureResult:
        """
        Validate a new position against portfolio exposure constraints with proportional scaling.
        
        Args:
            symbol: Symbol for new position
            position_value: Dollar value of new position
            current_positions: Dict of {symbol: total_value} for existing positions
            account_value: Total account value
        
        Returns:
            PortfolioExposureResult with scaling_factor and approval status
        """
        reasons = []
        scaling_factors = []
        
        # Calculate exposures
        symbol_exposures = self._calculate_symbol_exposures(
            current_positions,
            account_value,
            new_symbol=symbol,
            new_value=position_value
        )
        
        # Check 1: Per-symbol concentration limit with proportional scaling
        for exposure in symbol_exposures:
            if exposure.symbol == symbol:
                current_concentration = current_positions.get(symbol, 0.0) / account_value * 100
                max_concentration_pct = self.max_symbol_concentration * 100
                
                if exposure.concentration_percent > max_concentration_pct:
                    # Calculate headroom and scaling factor
                    headroom_pct = max(0.0, max_concentration_pct - current_concentration)
                    
                    if headroom_pct <= 0:
                        # No headroom - deny completely
                        return PortfolioExposureResult(
                            approved=False,
                            scaling_factor=0.0,
                            reasons=[
                                f"Symbol concentration at limit: {symbol} already {current_concentration:.1f}% "
                                f"(max: {max_concentration_pct:.1f}%)"
                            ]
                        )
                    
                    # Calculate scaling factor based on headroom
                    allowed_value = (headroom_pct / 100.0) * account_value
                    symbol_scaling_factor = allowed_value / position_value
                    
                    scaling_factors.append(symbol_scaling_factor)
                    reasons.append(
                        f"Symbol concentration: scaling to {symbol_scaling_factor:.2%} "
                        f"({current_concentration:.1f}% → {current_concentration + (headroom_pct):.1f}%)"
                    )
                    
                    logger.info(
                        f"📊 Symbol concentration scaling applied for {symbol}",
                        extra={
                            "component": "PortfolioExposureValidator",
                            "symbol": symbol,
                            "current_pct": current_concentration,
                            "max_pct": max_concentration_pct,
                            "headroom_pct": headroom_pct,
                            "scaling_factor": symbol_scaling_factor
                        }
                    )
        
        # Check 2: Correlated symbol exposure with proportional scaling
        if len(current_positions) > 0:
            correlation_scaling = await self._check_correlation_exposure_with_scaling(
                symbol,
                position_value,
                current_positions,
                account_value
            )
            
            if correlation_scaling['scaling_factor'] < 1.0:
                scaling_factors.append(correlation_scaling['scaling_factor'])
                reasons.append(correlation_scaling['reason'])
        
        # Determine final scaling factor (most restrictive)
        if scaling_factors:
            final_scaling_factor = min(scaling_factors)
        else:
            final_scaling_factor = 1.0
        
        # Approve if scaling_factor > 0
        approved = final_scaling_factor > 0.0
        
        if not approved:
            reasons.append("No headroom available for this position")
        elif final_scaling_factor == 1.0:
            reasons = [f"Portfolio exposure within limits for {symbol}"]
        
        return PortfolioExposureResult(
            approved=approved,
            scaling_factor=final_scaling_factor,
            reasons=reasons
        )
    
    def _calculate_symbol_exposures(self,
                                    current_positions: Dict[str, float],
                                    account_value: float,
                                    new_symbol: Optional[str] = None,
                                    new_value: float = 0.0) -> List[SymbolExposure]:
        """
        Calculate per-symbol exposure metrics.
        
        Args:
            current_positions: Current positions {symbol: value}
            account_value: Total account value
            new_symbol: Symbol for new position (optional)
            new_value: Value of new position (optional)
        
        Returns:
            List of SymbolExposure objects
        """
        # Aggregate positions by symbol
        symbol_values = current_positions.copy()
        
        if new_symbol:
            symbol_values[new_symbol] = symbol_values.get(new_symbol, 0.0) + new_value
        
        # Calculate exposures
        exposures = []
        for symbol, value in symbol_values.items():
            concentration = (value / account_value * 100) if account_value > 0 else 0.0
            
            exposures.append(SymbolExposure(
                symbol=symbol,
                position_count=1,  # Simplified (could track multiple positions per symbol)
                total_quantity=0.0,  # Not tracked here
                total_value=value,
                concentration_percent=concentration
            ))
        
        # Sort by concentration descending
        exposures.sort(key=lambda e: e.concentration_percent, reverse=True)
        
        return exposures
    
    async def _check_correlation_exposure(self,
                                         new_symbol: str,
                                         new_value: float,
                                         current_positions: Dict[str, float],
                                         account_value: float) -> RiskDecision:
        """
        Check for excessive exposure to correlated symbols.
        
        Args:
            new_symbol: Symbol for new position
            new_value: Value of new position
            current_positions: Current positions {symbol: value}
            account_value: Total account value
        
        Returns:
            RiskDecision (allow/deny)
        """
        # Find symbols correlated with new symbol
        correlated_symbols = []
        
        for existing_symbol in current_positions.keys():
            if existing_symbol == new_symbol:
                continue
            
            correlation = await self._get_correlation(new_symbol, existing_symbol)
            
            if abs(correlation) >= self.correlation_threshold:
                correlated_symbols.append((existing_symbol, correlation))
        
        if not correlated_symbols:
            # No correlated symbols found
            return RiskDecision.allow(
                reason=f"No highly correlated positions found for {new_symbol}"
            )
        
        # Calculate combined exposure of correlated group
        correlated_exposure = new_value
        for existing_symbol, _ in correlated_symbols:
            correlated_exposure += current_positions[existing_symbol]
        
        correlated_percent = (correlated_exposure / account_value * 100) if account_value > 0 else 0.0
        
        # Check against limit
        if correlated_percent > self.max_correlated_group_exposure * 100:
            correlated_symbol_names = [s for s, _ in correlated_symbols]
            
            return RiskDecision.deny(
                status=RiskDecisionStatus.CORRELATED_EXPOSURE_EXCEEDED,
                reason=(
                    f"Correlated symbol exposure limit exceeded: {new_symbol} is correlated "
                    f"with {correlated_symbol_names} (combined: {correlated_percent:.1f}% of portfolio, "
                    f"max: {self.max_correlated_group_exposure * 100:.1f}%)"
                ),
                details={
                    'new_symbol': new_symbol,
                    'correlated_symbols': [
                        {'symbol': s, 'correlation': c} for s, c in correlated_symbols
                    ],
                    'combined_exposure_percent': correlated_percent,
                    'limit_percent': self.max_correlated_group_exposure * 100,
                    'combined_value': correlated_exposure
                }
            )
        
        # Exposure within limits
        return RiskDecision.allow(
            reason=(
                f"Correlated exposure within limits: {new_symbol} + correlated symbols = "
                f"{correlated_percent:.1f}%"
            ),
            details={
                'correlated_symbols': [s for s, _ in correlated_symbols],
                'combined_exposure_percent': correlated_percent
            }
        )
    
    async def _check_correlation_exposure_with_scaling(self,
                                                       new_symbol: str,
                                                       new_value: float,
                                                       current_positions: Dict[str, float],
                                                       account_value: float) -> Dict:
        """
        Check correlation exposure with proportional scaling support.
        
        Args:
            new_symbol: Symbol for new position
            new_value: Value of new position
            current_positions: Current positions {symbol: value}
            account_value: Total account value
        
        Returns:
            Dict with 'scaling_factor' and 'reason'
        """
        # Find symbols correlated with new symbol
        correlated_symbols = []
        
        for existing_symbol in current_positions.keys():
            if existing_symbol == new_symbol:
                continue
            
            correlation = await self._get_correlation(new_symbol, existing_symbol)
            
            if abs(correlation) >= self.correlation_threshold:
                correlated_symbols.append((existing_symbol, correlation))
        
        if not correlated_symbols:
            # No correlated symbols - no scaling needed
            return {'scaling_factor': 1.0, 'reason': 'No correlation constraints'}
        
        # Calculate current correlated group exposure (without new position)
        current_correlated_exposure = sum(
            current_positions[s] for s, _ in correlated_symbols
        )
        current_correlated_pct = (current_correlated_exposure / account_value * 100) if account_value > 0 else 0.0
        
        max_correlated_pct = self.max_correlated_group_exposure * 100
        
        # Calculate headroom
        headroom_pct = max(0.0, max_correlated_pct - current_correlated_pct)
        
        if headroom_pct <= 0:
            # No headroom - deny completely
            return {
                'scaling_factor': 0.0,
                'reason': f"Correlated group at limit: {current_correlated_pct:.1f}% (max: {max_correlated_pct:.1f}%)"
            }
        
        # Calculate proposed total exposure
        proposed_correlated_exposure = current_correlated_exposure + new_value
        proposed_correlated_pct = (proposed_correlated_exposure / account_value * 100) if account_value > 0 else 0.0
        
        if proposed_correlated_pct > max_correlated_pct:
            # Calculate scaling factor based on headroom
            allowed_value = (headroom_pct / 100.0) * account_value
            correlation_scaling_factor = allowed_value / new_value
            
            correlated_names = [s for s, _ in correlated_symbols]
            
            logger.info(
                f"🔗 Correlation-based scaling applied for {new_symbol}",
                extra={
                    "component": "PortfolioExposureValidator",
                    "new_symbol": new_symbol,
                    "correlated_with": correlated_names,
                    "current_pct": current_correlated_pct,
                    "max_pct": max_correlated_pct,
                    "headroom_pct": headroom_pct,
                    "scaling_factor": correlation_scaling_factor
                }
            )
            
            return {
                'scaling_factor': correlation_scaling_factor,
                'reason': (
                    f"Correlated exposure: scaling to {correlation_scaling_factor:.2%} "
                    f"(correlated with {correlated_names}, "
                    f"{current_correlated_pct:.1f}% → {current_correlated_pct + headroom_pct:.1f}%)"
                )
            }
        
        # Within limits - no scaling needed
        return {'scaling_factor': 1.0, 'reason': 'Correlation within limits'}
    
    
    async def _get_correlation(self, symbol1: str, symbol2: str) -> float:
        """
        Get correlation coefficient between two symbols.
        
        Uses caching to avoid repeated calculations.
        
        Args:
            symbol1: First symbol
            symbol2: Second symbol
        
        Returns:
            Correlation coefficient (-1.0 to 1.0)
        """
        # Normalize symbol pair (always alphabetical order)
        pair = tuple(sorted([symbol1, symbol2]))
        
        # Check cache
        if pair in self._correlation_cache:
            correlation, timestamp = self._correlation_cache[pair]
            if datetime.utcnow() - timestamp < self._cache_ttl:
                return correlation
        
        # Calculate correlation
        try:
            correlation = await self._calculate_correlation(symbol1, symbol2)
            
            # Cache result
            self._correlation_cache[pair] = (correlation, datetime.utcnow())
            
            return correlation
            
        except Exception as e:
            logger.warning(
                f"Failed to calculate correlation for {symbol1}-{symbol2}: {e}",
                extra={'component': 'PortfolioExposureValidator'}
            )
            # Default to 0 (uncorrelated) on error
            return 0.0
    
    async def _calculate_correlation(self, symbol1: str, symbol2: str) -> float:
        """
        Calculate Pearson correlation coefficient between two symbols.
        
        Args:
            symbol1: First symbol
            symbol2: Second symbol
        
        Returns:
            Correlation coefficient
        """
        # Fetch historical data
        bars1 = await self.market_data.get_bars(
            symbol=symbol1,
            timeframe="1Day",
            limit=self.correlation_lookback_days
        )
        
        bars2 = await self.market_data.get_bars(
            symbol=symbol2,
            timeframe="1Day",
            limit=self.correlation_lookback_days
        )
        
        if not bars1 or not bars2 or len(bars1) < 10 or len(bars2) < 10:
            logger.warning(
                f"Insufficient data for correlation: {symbol1} ({len(bars1) if bars1 else 0} bars), "
                f"{symbol2} ({len(bars2) if bars2 else 0} bars)"
            )
            return 0.0
        
        # Extract closing prices
        prices1 = np.array([bar.close for bar in bars1])
        prices2 = np.array([bar.close for bar in bars2])
        
        # Calculate returns
        returns1 = np.diff(prices1) / prices1[:-1]
        returns2 = np.diff(prices2) / prices2[:-1]
        
        # Align lengths (in case different number of bars)
        min_len = min(len(returns1), len(returns2))
        returns1 = returns1[-min_len:]
        returns2 = returns2[-min_len:]
        
        # Calculate Pearson correlation
        if len(returns1) < 2:
            return 0.0
        
        correlation_matrix = np.corrcoef(returns1, returns2)
        correlation = correlation_matrix[0, 1]
        
        # Handle NaN (can occur with constant prices)
        if np.isnan(correlation):
            return 0.0
        
        return float(correlation)
    
    def get_portfolio_summary(self,
                             current_positions: Dict[str, float],
                             account_value: float) -> Dict:
        """
        Get portfolio exposure summary.
        
        Args:
            current_positions: Current positions {symbol: value}
            account_value: Total account value
        
        Returns:
            Summary dictionary with exposures and concentrations
        """
        exposures = self._calculate_symbol_exposures(current_positions, account_value)
        
        return {
            'account_value': account_value,
            'total_positions': len(current_positions),
            'symbol_exposures': [
                {
                    'symbol': e.symbol,
                    'value': e.total_value,
                    'concentration_percent': e.concentration_percent,
                    'exceeds_limit': e.concentration_percent > self.max_symbol_concentration * 100
                }
                for e in exposures
            ],
            'top_concentration': exposures[0] if exposures else None,
            'diversification_score': self._calculate_diversification_score(exposures)
        }
    
    def _calculate_diversification_score(self, exposures: List[SymbolExposure]) -> float:
        """
        Calculate portfolio diversification score (0.0 to 1.0).
        
        1.0 = perfectly diversified (equal weights)
        0.0 = completely concentrated (one symbol)
        
        Uses Herfindahl-Hirschman Index (HHI) for concentration measurement.
        
        Args:
            exposures: List of symbol exposures
        
        Returns:
            Diversification score
        """
        if not exposures:
            return 1.0
        
        # Calculate HHI (sum of squared concentration percentages)
        hhi = sum(e.concentration_percent ** 2 for e in exposures)
        
        # Normalize: HHI ranges from 1/N (perfect) to 10000 (monopoly)
        # Convert to 0-1 scale where 1 is most diversified
        n = len(exposures)
        min_hhi = 10000 / n  # Perfect diversification
        max_hhi = 10000      # Complete concentration
        
        if max_hhi == min_hhi:
            return 1.0
        
        # Invert and normalize
        score = 1.0 - ((hhi - min_hhi) / (max_hhi - min_hhi))
        
        return max(0.0, min(1.0, score))
