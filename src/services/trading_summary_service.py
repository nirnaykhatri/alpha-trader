"""
Trading Summary Service

Generates trading performance summaries and reports.
Extracted from TradingBotOrchestrator to follow Single Responsibility Principle.

This service encapsulates:
- Performance metrics calculation (P&L, win rate, profit factor)
- Position summary generation
- Trade history aggregation

SOLID Compliance:
- SRP: Single responsibility for generating trading reports
- OCP: Extensible for new report types
- LSP: N/A (no inheritance hierarchy)
- ISP: Focused interface for reporting only
- DIP: Depends on abstractions not concretions

Thread Safety: Async-safe (read-only operations)

Author: Trading Bot Team
Version: 1.1.0 - Uses canonical interfaces from src.interfaces
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Protocol

from src.interfaces import IPositionManager, IMarketDataProvider
from src.database.pagination import extract_items

logger = logging.getLogger(__name__)


# ============================================================================
# Service-Specific Protocol Definitions (not duplicating canonical interfaces)
# ============================================================================

class IDatabaseManager(Protocol):
    """
    Protocol for database access specific to trading summaries.
    
    Note: This defines only the methods needed by TradingSummaryService.
    The full IDatabaseManager interface is in src/database/database_interface.py.
    """
    
    async def get_open_trades(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get open trades."""
        ...
    
    async def get_completed_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get completed trades."""
        ...
    
    async def get_position_tracking(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get position tracking info."""
        ...


# ============================================================================
# Data Classes for Summaries
# ============================================================================

@dataclass
class PerformanceMetrics:
    """
    Performance metrics for trading activity.
    
    Attributes:
        total_realized_pnl: Total realized profit/loss
        total_trades: Total number of completed trades
        winning_trades: Number of winning trades
        losing_trades: Number of losing trades
        win_rate_percent: Win rate as percentage
        average_win: Average winning trade amount
        average_loss: Average losing trade amount
        profit_factor: Ratio of gross profit to gross loss
    """
    total_realized_pnl: float = 0.0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate_percent: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    profit_factor: float = 0.0


@dataclass
class PositionSummary:
    """
    Summary of a single position.
    
    Attributes:
        symbol: Trading symbol
        quantity: Position quantity
        avg_price: Average entry price
        current_price: Current market price
        unrealized_pnl: Unrealized profit/loss
        unrealized_percent: Unrealized P&L percentage
        is_trailing: Whether trailing stop is active
        trailing_activation_price: Price at which trailing started
        trailing_stop_price: Current trailing stop price
    """
    symbol: str
    quantity: float
    avg_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_percent: float
    is_trailing: bool = False
    trailing_activation_price: Optional[float] = None
    trailing_stop_price: Optional[float] = None


@dataclass
class TradingSummary:
    """
    Complete trading summary.
    
    Attributes:
        timestamp: When summary was generated
        performance: Performance metrics
        current_positions: List of position summaries
        open_trades: Raw open trade data
        recent_trades: Recent completed trades
    """
    timestamp: datetime
    performance: PerformanceMetrics
    current_positions: List[PositionSummary] = field(default_factory=list)
    open_trades: List[Dict[str, Any]] = field(default_factory=list)
    recent_trades: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert summary to dictionary for JSON serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'performance': {
                'total_realized_pnl': self.performance.total_realized_pnl,
                'total_trades': self.performance.total_trades,
                'winning_trades': self.performance.winning_trades,
                'losing_trades': self.performance.losing_trades,
                'win_rate_percent': self.performance.win_rate_percent,
                'average_win': self.performance.average_win,
                'average_loss': self.performance.average_loss,
                'profit_factor': self.performance.profit_factor,
            },
            'current_positions': [
                {
                    'symbol': p.symbol,
                    'quantity': p.quantity,
                    'avg_price': p.avg_price,
                    'current_price': p.current_price,
                    'unrealized_pnl': p.unrealized_pnl,
                    'unrealized_percent': p.unrealized_percent,
                    'is_trailing': p.is_trailing,
                    'trailing_activation_price': p.trailing_activation_price,
                    'trailing_stop_price': p.trailing_stop_price,
                }
                for p in self.current_positions
            ],
            'open_trades': self.open_trades,
            'recent_trades': self.recent_trades,
        }


# ============================================================================
# Trading Summary Service
# ============================================================================

class TradingSummaryService:
    """
    Service for generating trading performance summaries.
    
    This service encapsulates all reporting and summary logic:
    - Performance metric calculations
    - Position summary generation
    - Trade history aggregation
    
    The service is stateless and can be called on-demand.
    
    Usage:
        summary_service = TradingSummaryService(
            position_manager=position_manager,
            market_data=market_data,
            database=database
        )
        
        # Get full trading summary
        summary = await summary_service.get_trading_summary()
        print(f"Win Rate: {summary.performance.win_rate_percent:.1f}%")
        
        # Log position status
        await summary_service.log_position_status()
    """
    
    def __init__(
        self,
        position_manager: IPositionManager,
        market_data: IMarketDataProvider,
        database: IDatabaseManager,
    ):
        """
        Initialize TradingSummaryService.
        
        Args:
            position_manager: Position management service
            market_data: Market data provider
            database: Database manager
        """
        self._position_manager = position_manager
        self._market_data = market_data
        self._database = database
        logger.debug("TradingSummaryService initialized")
    
    async def get_trading_summary(
        self,
        recent_trades_limit: int = 20
    ) -> TradingSummary:
        """
        Get comprehensive trading summary.
        
        Args:
            recent_trades_limit: Maximum number of recent trades to include
            
        Returns:
            TradingSummary with performance metrics and position details
        """
        try:
            # Get raw data
            positions = await self._position_manager.get_all_positions()
            open_trades_result = await self._database.get_open_trades()
            completed_trades_result = await self._database.get_completed_trades(
                limit=recent_trades_limit
            )
            
            # Extract items from PaginatedResult objects using helper
            open_trades = extract_items(open_trades_result)
            completed_trades = extract_items(completed_trades_result)
            
            # Calculate performance metrics
            performance = self._calculate_performance_metrics(completed_trades)
            
            # Build position summaries
            position_summaries = []
            for position in positions:
                if position.quantity != 0:
                    summary = await self._build_position_summary(position)
                    position_summaries.append(summary)
            
            return TradingSummary(
                timestamp=datetime.utcnow(),
                performance=performance,
                current_positions=position_summaries,
                open_trades=open_trades,
                recent_trades=completed_trades,
            )
            
        except Exception as e:
            logger.error(f"Error generating trading summary: {str(e)}")
            return TradingSummary(
                timestamp=datetime.utcnow(),
                performance=PerformanceMetrics(),
            )
    
    def _calculate_performance_metrics(
        self,
        completed_trades: List[Dict[str, Any]]
    ) -> PerformanceMetrics:
        """
        Calculate performance metrics from completed trades.
        
        Args:
            completed_trades: List of completed trade records
            
        Returns:
            PerformanceMetrics with calculated values
        """
        if not completed_trades:
            return PerformanceMetrics()
        
        # Categorize trades
        winning_trades = [
            t for t in completed_trades 
            if t.get('realized_pnl') and t['realized_pnl'] > 0
        ]
        losing_trades = [
            t for t in completed_trades 
            if t.get('realized_pnl') and t['realized_pnl'] < 0
        ]
        
        # Calculate totals
        total_realized = sum(
            t['realized_pnl'] for t in completed_trades 
            if t.get('realized_pnl')
        )
        
        # Calculate averages
        avg_win = (
            sum(t['realized_pnl'] for t in winning_trades) / len(winning_trades)
            if winning_trades else 0.0
        )
        avg_loss = (
            sum(t['realized_pnl'] for t in losing_trades) / len(losing_trades)
            if losing_trades else 0.0
        )
        
        # Calculate rates
        win_rate = (
            len(winning_trades) / len(completed_trades) * 100
            if completed_trades else 0.0
        )
        
        # Calculate profit factor (gross profit / gross loss)
        gross_profit = sum(t['realized_pnl'] for t in winning_trades) if winning_trades else 0.0
        gross_loss = abs(sum(t['realized_pnl'] for t in losing_trades)) if losing_trades else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0
        
        return PerformanceMetrics(
            total_realized_pnl=total_realized,
            total_trades=len(completed_trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate_percent=win_rate,
            average_win=avg_win,
            average_loss=avg_loss,
            profit_factor=profit_factor,
        )
    
    async def _build_position_summary(self, position: Any) -> PositionSummary:
        """
        Build a position summary with current market data.
        
        Args:
            position: Position object
            
        Returns:
            PositionSummary with current data
        """
        try:
            current_price = await self._market_data.get_current_price(position.symbol)
            unrealized_pnl = (current_price - position.avg_price) * position.quantity
            unrealized_pct = (
                (current_price - position.avg_price) / position.avg_price * 100
                if position.avg_price > 0 else 0.0
            )
            
            # Get trailing info
            tracking = await self._database.get_position_tracking(position.symbol)
            
            return PositionSummary(
                symbol=position.symbol,
                quantity=position.quantity,
                avg_price=position.avg_price,
                current_price=current_price,
                unrealized_pnl=unrealized_pnl,
                unrealized_percent=unrealized_pct,
                is_trailing=tracking.get('is_trailing', False) if tracking else False,
                trailing_activation_price=tracking.get('trailing_activation_price') if tracking else None,
                trailing_stop_price=tracking.get('trailing_stop_price') if tracking else None,
            )
            
        except Exception as e:
            logger.warning(f"Error building position summary for {position.symbol}: {e}")
            return PositionSummary(
                symbol=position.symbol,
                quantity=position.quantity,
                avg_price=position.avg_price,
                current_price=0.0,
                unrealized_pnl=0.0,
                unrealized_percent=0.0,
            )
    
    async def log_position_status(self) -> None:
        """Log detailed position status for monitoring."""
        try:
            summary = await self.get_trading_summary()
            
            logger.info("📊 TRADING SUMMARY:")
            logger.info(f"   Total P&L: ${summary.performance.total_realized_pnl:.2f}")
            logger.info(f"   Win Rate: {summary.performance.win_rate_percent:.1f}%")
            logger.info(f"   Profit Factor: {summary.performance.profit_factor:.2f}")
            logger.info(f"   Open Positions: {len(summary.current_positions)}")
            logger.info(f"   Open Trades: {len(summary.open_trades)}")
            
            for pos in summary.current_positions:
                trailing_info = ""
                if pos.is_trailing:
                    trailing_info = (
                        f" [TRAILING from ${pos.trailing_activation_price:.2f}, "
                        f"stop @ ${pos.trailing_stop_price:.2f}]"
                    )
                
                logger.info(
                    f"   • {pos.symbol}: {pos.quantity} @ ${pos.avg_price:.2f} "
                    f"(Current: ${pos.current_price:.2f}, "
                    f"P&L: ${pos.unrealized_pnl:.2f} / {pos.unrealized_percent:.2f}%)"
                    f"{trailing_info}"
                )
            
        except Exception as e:
            logger.error(f"Error logging position status: {str(e)}")
    
    def format_summary_for_display(self, summary: TradingSummary) -> str:
        """
        Format summary for console/log display.
        
        Args:
            summary: TradingSummary to format
            
        Returns:
            Formatted string for display
        """
        lines = [
            "=" * 60,
            "📊 TRADING SUMMARY",
            "=" * 60,
            f"Generated: {summary.timestamp.isoformat()}",
            "",
            "📈 PERFORMANCE METRICS:",
            f"   Total Realized P&L: ${summary.performance.total_realized_pnl:.2f}",
            f"   Win Rate: {summary.performance.win_rate_percent:.1f}%",
            f"   Trades: {summary.performance.total_trades} "
            f"(W:{summary.performance.winning_trades} / L:{summary.performance.losing_trades})",
            f"   Average Win: ${summary.performance.average_win:.2f}",
            f"   Average Loss: ${summary.performance.average_loss:.2f}",
            f"   Profit Factor: {summary.performance.profit_factor:.2f}",
            "",
            "📋 OPEN POSITIONS:",
        ]
        
        if summary.current_positions:
            for pos in summary.current_positions:
                pnl_emoji = "🟢" if pos.unrealized_pnl >= 0 else "🔴"
                trailing = " 🎯" if pos.is_trailing else ""
                lines.append(
                    f"   {pnl_emoji} {pos.symbol}: {pos.quantity} @ ${pos.avg_price:.2f} → "
                    f"${pos.current_price:.2f} ({pos.unrealized_percent:+.2f}%){trailing}"
                )
        else:
            lines.append("   (No open positions)")
        
        lines.append("=" * 60)
        return "\n".join(lines)


# ============================================================================
# Factory Function
# ============================================================================

def create_trading_summary_service(
    position_manager: IPositionManager,
    market_data: IMarketDataProvider,
    database: IDatabaseManager,
) -> TradingSummaryService:
    """
    Factory function to create TradingSummaryService.
    
    Args:
        position_manager: Position management service
        market_data: Market data provider
        database: Database manager
        
    Returns:
        Configured TradingSummaryService instance
    """
    return TradingSummaryService(
        position_manager=position_manager,
        market_data=market_data,
        database=database,
    )
